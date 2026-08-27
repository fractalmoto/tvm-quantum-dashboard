/**
 * `.qtest` interpreter.
 *
 * Deliberately pure: it takes a session (n, ops, collapse) plus a batch of
 * source lines and returns the next session together with the lines to append
 * to the log. Nothing here touches React.
 *
 * Why it must be pure: an earlier version drove the store directly from the
 * REPL, one dispatch per command. Read-only commands (`state`, `probs`,
 * `check`) then evaluated against the *previous* render's snapshot, so a
 * multi-line script reported results for a state that no longer existed —
 * `check hadamard` failed on a circuit that was in fact uniform. Evaluating the
 * whole batch against a locally advanced session removes that class of bug, and
 * makes the semantics identical whether a line is typed or loaded from a file.
 */

import { MockEngine, MOCK_MAX_QUTRITS } from './mockEngine';
import { parseLine, HELP_TEXT } from './qtest';
import { buildSnapshot, type Snapshot } from './store';
import { ketLabel, type GateOp, type MeasurementResult } from './types';

export interface Session {
  n: number;
  ops: GateOp[];
  collapse: MeasurementResult | null;
}

export type LineKind = 'in' | 'out' | 'ok' | 'err';
export interface OutLine {
  kind: LineKind;
  text: string;
}

export interface RunResult {
  session: Session;
  lines: OutLine[];
  /** True if a `clear` command ran, so the caller can wipe the log first. */
  clearLog: boolean;
}

const CHECK_TOLERANCE = 1e-9;

let opCounter = 0;
const nextOpId = () => `q${Date.now().toString(36)}${(opCounter++).toString(36)}`;

/** Deterministic RNG so a scripted `measure` is reproducible in tests. */
function seededRng(seed: number): () => number {
  let s = seed >>> 0 || 0x9e3779b9;
  return () => {
    s ^= s << 13;
    s ^= s >>> 17;
    s ^= s << 5;
    return ((s >>> 0) % 1_000_000) / 1_000_000;
  };
}

export function runScript(
  start: Session,
  source: string,
  opts: { rng?: () => number } = {},
): RunResult {
  const session: Session = { n: start.n, ops: [...start.ops], collapse: start.collapse };
  const lines: OutLine[] = [];
  let clearLog = false;
  const say = (kind: LineKind, text: string) => lines.push({ kind, text });

  // Snapshots are memoised per mutation so `state` + `probs` + `check` in a row
  // replay the circuit once, not three times.
  let cached: Snapshot | null = null;
  const snapshot = () => {
    if (!cached) cached = buildSnapshot(session.n, session.ops, session.collapse);
    return cached;
  };
  const invalidate = () => {
    cached = null;
  };

  for (const raw of source.split('\n')) {
    const cmd = parseLine(raw);
    if (!cmd) continue;
    say('in', raw.trim());

    if (cmd.kind === 'error') {
      say('err', cmd.message);
      continue;
    }

    switch (cmd.kind) {
      case 'help':
        say('out', HELP_TEXT);
        break;

      case 'clear':
        clearLog = true;
        lines.length = 0;
        break;

      case 'init': {
        if (cmd.n < 1 || cmd.n > MOCK_MAX_QUTRITS) {
          say('err', `mock engine supports 1..${MOCK_MAX_QUTRITS} qutrits (got ${cmd.n})`);
          break;
        }
        session.n = cmd.n;
        session.ops = [];
        session.collapse = null;
        invalidate();
        say('ok', `allocated 3^${cmd.n} = ${3 ** cmd.n} basis states`);
        break;
      }

      case 'reset':
        session.ops = [];
        session.collapse = null;
        invalidate();
        say('ok', `reset to |${'0'.repeat(session.n)}>`);
        break;

      case 'gate': {
        const err = validateGate(cmd.gate, cmd.target, cmd.control, session.n);
        if (err) {
          say('err', err);
          break;
        }
        session.ops = [
          ...session.ops,
          { id: nextOpId(), gate: cmd.gate, target: cmd.target, control: cmd.control },
        ];
        session.collapse = null;
        invalidate();
        break;
      }

      case 'measure': {
        const engine = new MockEngine(session.n);
        try {
          for (const op of session.ops) engine.applyGate(op);
        } catch (e) {
          say('err', e instanceof Error ? e.message : String(e));
          break;
        }
        const result = engine.measure(opts.rng ?? seededRng(session.ops.length + session.n));
        session.collapse = result;
        invalidate();
        say(
          'ok',
          `measure -> |${ketLabel(result.outcome, session.n)}>  (index ${result.outcome}, p = ${result.probability.toFixed(6)})`,
        );
        break;
      }

      case 'state':
      case 'probs': {
        const snap = snapshot();
        if (snap.error) {
          say('err', snap.error);
          break;
        }
        const lim = Math.max(1, Math.min(cmd.limit, snap.dimension));
        const body = snap.ranked
          .slice(0, lim)
          .map((k) => {
            const re = snap.amplitudes[2 * k];
            const im = snap.amplitudes[2 * k + 1];
            const ket = `|${ketLabel(k, session.n)}>`;
            return cmd.kind === 'state'
              ? `${String(k).padStart(5)}  ${ket}  ${re.toFixed(6)} ${im >= 0 ? '+' : '-'} ${Math.abs(im).toFixed(6)}i`
              : `${String(k).padStart(5)}  ${ket}  ${snap.probabilities[k].toFixed(9)}`;
          })
          .join('\n');
        say('out', body || '(empty)');
        break;
      }

      case 'check': {
        const snap = snapshot();
        if (snap.error) {
          say('err', snap.error);
          break;
        }
        const expected = 1 / snap.dimension;
        let worst = 0;
        for (let k = 0; k < snap.dimension; k++) {
          worst = Math.max(worst, Math.abs(snap.probabilities[k] - expected));
        }
        const pass = worst < CHECK_TOLERANCE;
        say(
          pass ? 'ok' : 'err',
          `hadamard uniformity: ${pass ? 'PASS' : 'FAIL'} — expected ${expected.toExponential(6)} per state, max deviation ${worst.toExponential(3)}`,
        );
        break;
      }
    }
  }

  return { session, lines, clearLog };
}

export function validateGate(
  gate: string,
  target: number,
  control: number | undefined,
  n: number,
): string | null {
  if (!Number.isInteger(target) || target < 0 || target >= n) {
    return `${gate}: target qutrit ${target} out of range 0..${n - 1}`;
  }
  const twoQutrit = gate === 'CX' || gate === 'CZ';
  if (twoQutrit) {
    if (control === undefined) return `${gate}: needs a control qutrit`;
    if (!Number.isInteger(control) || control < 0 || control >= n) {
      return `${gate}: control qutrit ${control} out of range 0..${n - 1}`;
    }
    if (control === target) return `${gate}: control and target must differ`;
  }
  return null;
}
