import { createContext, useCallback, useContext, useMemo, useReducer } from 'react';
import { MockEngine, MOCK_MAX_QUTRITS } from './mockEngine';
import {
  type EngineKind,
  type GateOp,
  type MeasurementResult,
  dimensionOf,
  ketLabel,
  recommendedEngine,
  tritsOf,
} from './types';

export interface LogEntry {
  id: number;
  kind: 'in' | 'out' | 'err' | 'ok';
  text: string;
}

interface State {
  n: number;
  ops: GateOp[];
  /** Recorded collapse, replayed deterministically so undo stays pure. */
  collapse: MeasurementResult | null;
  log: LogEntry[];
  /** null = follow the n<=10 dispatch rule; otherwise a manual override. */
  override: EngineKind | null;
  /** Palette selection, held here so it survives panel switches. */
  sel: { target: number; control: number };
  seq: number;
}

type Action =
  | { type: 'setQutrits'; n: number }
  | { type: 'push'; op: Omit<GateOp, 'id'> }
  | { type: 'undo' }
  | { type: 'clearCircuit' }
  | { type: 'measure'; result: MeasurementResult }
  | { type: 'log'; entries: Array<Omit<LogEntry, 'id'>> }
  | { type: 'clearLog' }
  | { type: 'override'; kind: EngineKind | null }
  | { type: 'select'; which: 'target' | 'control'; q: number }
  /** Wholesale replacement, used by the .qtest interpreter after a script run. */
  | { type: 'load'; n: number; ops: GateOp[]; collapse: MeasurementResult | null };

const initial: State = {
  n: 3,
  ops: [],
  collapse: null,
  log: [
    { id: 0, kind: 'out', text: 'TrinaryVM quantum dashboard — Phase 0 shell.' },
    { id: 1, kind: 'out', text: 'Mock TypeScript engine active. Type `help` for commands.' },
  ],
  override: null,
  sel: { target: 0, control: 1 },
  seq: 2,
};

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case 'setQutrits':
      return { ...s, n: a.n, ops: [], collapse: null };
    case 'push':
      return {
        ...s,
        ops: [...s.ops, { ...a.op, id: `op${s.seq}` }],
        collapse: null,
        seq: s.seq + 1,
      };
    case 'undo':
      return s.collapse
        ? { ...s, collapse: null }
        : { ...s, ops: s.ops.slice(0, -1) };
    case 'clearCircuit':
      return { ...s, ops: [], collapse: null };
    case 'measure':
      return { ...s, collapse: a.result };
    case 'log': {
      let seq = s.seq;
      const added = a.entries.map((e) => ({ ...e, id: seq++ }));
      return { ...s, log: [...s.log, ...added].slice(-300), seq };
    }
    case 'clearLog':
      return { ...s, log: [] };
    case 'override':
      return { ...s, override: a.kind };
    case 'select':
      return { ...s, sel: { ...s.sel, [a.which]: a.q } };
    case 'load':
      return { ...s, n: a.n, ops: a.ops, collapse: a.collapse };
    default:
      return s;
  }
}

export interface Snapshot {
  n: number;
  dimension: number;
  amplitudes: Float64Array;
  probabilities: Float64Array;
  /** Indices sorted by descending probability. */
  ranked: number[];
  /** Max probability, for normalising visual intensity. */
  peak: number;
  error: string | null;
}

export function buildSnapshot(
  n: number,
  ops: GateOp[],
  collapse: MeasurementResult | null,
): Snapshot {
  const engine = new MockEngine(n);
  let error: string | null = null;
  for (const op of ops) {
    try {
      engine.applyGate(op);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      break;
    }
  }
  const amplitudes = engine.amplitudes().slice();
  if (collapse) {
    amplitudes.fill(0);
    amplitudes[2 * collapse.outcome] = 1;
  }
  const d = dimensionOf(n);
  const probabilities = new Float64Array(d);
  let peak = 0;
  for (let k = 0; k < d; k++) {
    const re = amplitudes[2 * k];
    const im = amplitudes[2 * k + 1];
    const p = re * re + im * im;
    probabilities[k] = p;
    if (p > peak) peak = p;
  }
  const ranked = Array.from({ length: d }, (_, i) => i).sort(
    (a, b) => probabilities[b] - probabilities[a],
  );
  return { n, dimension: d, amplitudes, probabilities, ranked, peak, error };
}

interface Ctx {
  state: State;
  snap: Snapshot;
  /** Engine actually in force, after the dispatch rule and any override. */
  activeEngine: EngineKind;
  maxQutrits: number;
  setQutrits: (n: number) => void;
  pushGate: (op: Omit<GateOp, 'id'>) => void;
  undo: () => void;
  clearCircuit: () => void;
  measure: () => void;
  log: (entries: Array<Omit<LogEntry, 'id'>>) => void;
  clearLog: () => void;
  setOverride: (kind: EngineKind | null) => void;
  select: (which: 'target' | 'control', q: number) => void;
  /** Replace the whole circuit at once (used by the .qtest interpreter). */
  load: (next: { n: number; ops: GateOp[]; collapse: MeasurementResult | null }) => void;
}

const QuantumContext = createContext<Ctx | null>(null);

export function QuantumProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);
  const snap = useMemo(() => buildSnapshot(state.n, state.ops, state.collapse), [
    state.n,
    state.ops,
    state.collapse,
  ]);

  const log = useCallback(
    (entries: Array<Omit<LogEntry, 'id'>>) => dispatch({ type: 'log', entries }),
    [],
  );

  const measure = useCallback(() => {
    const engine = new MockEngine(state.n);
    let failed: string | null = null;
    for (const op of state.ops) {
      try {
        engine.applyGate(op);
      } catch (e) {
        failed = e instanceof Error ? e.message : String(e);
        break;
      }
    }
    if (failed) {
      log([{ kind: 'err', text: failed }]);
      return;
    }
    const result = engine.measure();
    dispatch({ type: 'measure', result });
    log([
      {
        kind: 'ok',
        text: `measure -> |${ketLabel(result.outcome, state.n)}>  (index ${result.outcome}, p = ${result.probability.toFixed(6)})`,
      },
    ]);
  }, [state.n, state.ops, log]);

  const value: Ctx = {
    state,
    snap,
    activeEngine: state.override ?? recommendedEngine(state.n),
    maxQutrits: MOCK_MAX_QUTRITS,
    setQutrits: (n) => dispatch({ type: 'setQutrits', n }),
    pushGate: (op) => dispatch({ type: 'push', op }),
    undo: () => dispatch({ type: 'undo' }),
    clearCircuit: () => dispatch({ type: 'clearCircuit' }),
    measure,
    log,
    clearLog: () => dispatch({ type: 'clearLog' }),
    setOverride: (kind) => dispatch({ type: 'override', kind }),
    select: (which, q) => dispatch({ type: 'select', which, q }),
    load: ({ n, ops, collapse }) => dispatch({ type: 'load', n, ops, collapse }),
  };

  return <QuantumContext.Provider value={value}>{children}</QuantumContext.Provider>;
}

export function useQuantum(): Ctx {
  const ctx = useContext(QuantumContext);
  if (!ctx) throw new Error('useQuantum must be used inside QuantumProvider');
  return ctx;
}

export { ketLabel, tritsOf };
