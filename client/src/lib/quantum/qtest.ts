/**
 * Minimal `.qtest` command parser.
 *
 * Phase 0 grammar (one command per line, `#` comments, case-insensitive):
 *   init <n>            allocate |0...0> on n qutrits
 *   reset               re-init at the current qutrit count
 *   h|x|z|s|t <q>
 *   cx|cz <control> <target>
 *   measure
 *   state [limit]       print top amplitudes
 *   probs [limit]       print top probabilities
 *   check hadamard      assert uniform 1/3^n after H on every qutrit
 *   help
 *
 * Phase 2 (TRI-184) replaces this with a CodeMirror 6 language mode over the
 * same command surface, so keep the grammar authoritative here.
 */

import type { GateName } from './types';

export type Command =
  | { kind: 'init'; n: number }
  | { kind: 'reset' }
  | { kind: 'gate'; gate: GateName; target: number; control?: number }
  | { kind: 'measure' }
  | { kind: 'state'; limit: number }
  | { kind: 'probs'; limit: number }
  | { kind: 'check'; what: 'hadamard' }
  | { kind: 'help' }
  | { kind: 'clear' };

const SINGLE: Record<string, GateName> = { h: 'H', x: 'X', z: 'Z', s: 'S', t: 'T' };
const DOUBLE: Record<string, GateName> = { cx: 'CX', cz: 'CZ' };

export function parseLine(raw: string): Command | { kind: 'error'; message: string } | null {
  const line = raw.split('#')[0].trim();
  if (!line) return null;
  const parts = line.split(/\s+/);
  const head = parts[0].toLowerCase();
  const num = (i: number) => Number.parseInt(parts[i], 10);

  if (head === 'init') {
    const n = num(1);
    if (!Number.isFinite(n)) return { kind: 'error', message: 'init needs a qutrit count' };
    return { kind: 'init', n };
  }
  if (head === 'reset') return { kind: 'reset' };
  if (head === 'measure') return { kind: 'measure' };
  if (head === 'help' || head === '?') return { kind: 'help' };
  if (head === 'clear') return { kind: 'clear' };
  if (head === 'state' || head === 'probs') {
    const limit = Number.isFinite(num(1)) ? num(1) : 12;
    return head === 'state' ? { kind: 'state', limit } : { kind: 'probs', limit };
  }
  if (head === 'check') {
    if ((parts[1] ?? '').toLowerCase() === 'hadamard') return { kind: 'check', what: 'hadamard' };
    return { kind: 'error', message: 'only `check hadamard` is implemented' };
  }
  if (SINGLE[head]) {
    const q = num(1);
    if (!Number.isFinite(q)) return { kind: 'error', message: `${head} needs a qutrit index` };
    return { kind: 'gate', gate: SINGLE[head], target: q };
  }
  if (DOUBLE[head]) {
    const c = num(1);
    const t = num(2);
    if (!Number.isFinite(c) || !Number.isFinite(t))
      return { kind: 'error', message: `${head} needs <control> <target>` };
    return { kind: 'gate', gate: DOUBLE[head], target: t, control: c };
  }
  return { kind: 'error', message: `unknown command: ${parts[0]}` };
}

export const HELP_TEXT = [
  'init <n>            allocate |0..0> on n qutrits',
  'reset               re-init at current width',
  'h|x|z|s|t <q>       single-qutrit gate',
  'cx|cz <ctrl> <tgt>  two-qutrit gate',
  'measure             sample and collapse',
  'state [limit]       top amplitudes',
  'probs [limit]       top probabilities',
  'check hadamard      uniformity assertion (R6.2d)',
  'clear               clear this log',
].join('\n');

/** Golden script loaded by the REPL's "Load golden test" action. */
export const GOLDEN_SCRIPT = `# R6.2d golden test — Hadamard uniformity
init 3
h 0
h 1
h 2
check hadamard
probs 6
`;
