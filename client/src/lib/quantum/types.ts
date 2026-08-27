/**
 * QuantumEngineAdapter — the single seam between the dashboard UI and any
 * qutrit simulation backend.
 *
 * Phase 0 ships `MockEngine` (pure TypeScript).
 * Phase 1 (TRI-186) adds `WasmEngine` (trinaryvm_quantum_wasm) and
 * `RpcEngine` (`tvm quantum --server --port 9546`) behind this same interface.
 * No UI code may import a concrete engine — only this interface.
 */

export type EngineKind = 'mock' | 'wasm' | 'rpc';

/** Single-qutrit gates. Phase convention: w = exp(2*pi*i/3). */
export type SingleGate = 'H' | 'X' | 'Z' | 'S' | 'T';
/** Two-qutrit gates: controlled shift and controlled clock. */
export type TwoGate = 'CX' | 'CZ';
export type GateName = SingleGate | TwoGate;

export interface GateOp {
  id: string;
  gate: GateName;
  /** Target qutrit index (0 = leftmost trit of the ket). */
  target: number;
  /** Control qutrit index, present for CX / CZ. */
  control?: number;
}

export interface EngineCapabilities {
  kind: EngineKind;
  /** Highest qutrit count this engine will accept. */
  maxQutrits: number;
  /** Human label for the status bar. */
  label: string;
  /** True when the backend is reachable / loaded. */
  ready: boolean;
}

export interface MeasurementResult {
  /** Collapsed basis-state index in [0, 3^n). */
  outcome: number;
  /** Balanced-ternary digits of the outcome, most significant first. */
  trits: number[];
  probability: number;
}

/**
 * The contract. Amplitudes are returned as an interleaved Float64Array
 * `[re0, im0, re1, im1, ...]` of length `2 * 3^n` — byte-identical to the
 * zero-copy buffer R6.2a will export from wasm-bindgen, so Phase 1 is a swap
 * and not a rewrite.
 */
export interface QuantumEngineAdapter {
  readonly capabilities: EngineCapabilities;
  /** Allocate |0...0> on `n` qutrits. */
  reset(n: number): void;
  readonly qutrits: number;
  /** 3^n */
  readonly dimension: number;
  applyGate(op: GateOp): void;
  /** Interleaved [re, im] amplitude buffer, length 2 * 3^n. */
  amplitudes(): Float64Array;
  /** |alpha_k|^2 for every basis state. */
  probabilities(): Float64Array;
  /** Sample and collapse the full register. */
  measure(rng?: () => number): MeasurementResult;
}

export const OMEGA_ARG = (2 * Math.PI) / 3;

/** Balanced-ternary digits (most significant first) for basis index k. */
export function tritsOf(k: number, n: number): number[] {
  const out = new Array<number>(n);
  let rest = k;
  for (let i = n - 1; i >= 0; i--) {
    out[i] = (rest % 3) - 1; // unsigned digit 0,1,2 -> balanced -1,0,+1
    rest = Math.floor(rest / 3);
  }
  return out;
}

/** Basis index whose balanced digits are all 0 — the register's zero state. */
export function zeroStateIndex(n: number): number {
  return (Math.pow(3, n) - 1) / 2;
}

/** Basis index for a balanced-ternary digit vector (most significant first). */
export function indexOfTrits(trits: number[]): number {
  return trits.reduce((acc, t) => acc * 3 + (t + 1), 0);
}

/** Ket label such as |-0+> using balanced-ternary glyphs. */
export function ketLabel(k: number, n: number): string {
  return tritsOf(k, n)
    .map((t) => (t < 0 ? '-' : t > 0 ? '+' : '0'))
    .join('');
}

export function dimensionOf(n: number): number {
  return Math.pow(3, n);
}

/** Rough state-vector footprint in bytes (interleaved f64). */
export function stateBytes(n: number): number {
  return dimensionOf(n) * 16;
}

export function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Dispatch rule from the R6.2 feasibility research: n <= 10 runs in the
 * browser, n > 10 must be handed to the native RPC daemon.
 */
export const WASM_QUTRIT_CEILING = 10;

export function recommendedEngine(n: number): EngineKind {
  return n <= WASM_QUTRIT_CEILING ? 'wasm' : 'rpc';
}
