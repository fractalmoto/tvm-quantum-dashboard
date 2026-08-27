/**
 * MockEngine — pure-TypeScript qutrit state-vector simulator.
 *
 * Exists so every panel in the dashboard can be built, styled and QA'd before
 * R6.2a (wasm) or R6.2c (rpc daemon) land. It is deliberately naive: dense
 * state vector, in-place gate application, no SIMD. Comfortable to n = 8
 * (6,561 basis states); hard-capped at 9 so nobody mistakes it for the real
 * engine.
 *
 * Conventions (documented here because they must match the Rust core):
 *   w              = exp(2*pi*i/3)
 *   qutrit 0       = most significant trit of the ket
 *   digit encoding = unsigned 0,1,2 internally; displayed balanced -1,0,+1
 *   zero state     = digits 0...0 -> index (3^n - 1)/2, NOT index 0
 *   X (shift)      |t> -> |t+1 mod 3>
 *   Z (clock)      |t> -> w^t |t>
 *   H (Chrestenson) H[j][k] = w^(jk) / sqrt(3)
 *   S = Z^(1/3)    diag(1, e^(2pi i/9),  e^(4pi i/9))
 *   T = Z^(1/9)    diag(1, e^(2pi i/27), e^(4pi i/27))
 *   CX             |c,t> -> |c, t+c mod 3>
 *   CZ             |c,t> -> w^(c*t) |c,t>
 */

import {
  type EngineCapabilities,
  type GateOp,
  type MeasurementResult,
  type QuantumEngineAdapter,
  dimensionOf,
  tritsOf,
  zeroStateIndex,
} from './types';

const TAU = Math.PI * 2;

/** 3x3 complex matrix as flat [re,im] pairs, row-major (18 numbers). */
type Mat3 = Float64Array;

function diagPhase(k1: number, k2: number): Mat3 {
  const m = new Float64Array(18);
  m[0] = 1;
  m[8] = Math.cos(k1);
  m[9] = Math.sin(k1);
  m[16] = Math.cos(k2);
  m[17] = Math.sin(k2);
  return m;
}

function buildGates(): Record<string, Mat3> {
  // X: shift permutation
  const X = new Float64Array(18);
  for (let t = 0; t < 3; t++) X[((t + 1) % 3) * 6 + t * 2] = 1;

  // H: Chrestenson / qutrit Fourier
  const H = new Float64Array(18);
  const inv = 1 / Math.sqrt(3);
  for (let j = 0; j < 3; j++) {
    for (let k = 0; k < 3; k++) {
      const a = (TAU / 3) * ((j * k) % 3);
      H[j * 6 + k * 2] = inv * Math.cos(a);
      H[j * 6 + k * 2 + 1] = inv * Math.sin(a);
    }
  }

  return {
    X,
    H,
    Z: diagPhase(TAU / 3, (2 * TAU) / 3),
    S: diagPhase(TAU / 9, (2 * TAU) / 9),
    T: diagPhase(TAU / 27, (2 * TAU) / 27),
  };
}

const GATES = buildGates();

export const MOCK_MAX_QUTRITS = 9;

export class MockEngine implements QuantumEngineAdapter {
  private buf: Float64Array = new Float64Array(2);
  private n = 0;

  readonly capabilities: EngineCapabilities = {
    kind: 'mock',
    maxQutrits: MOCK_MAX_QUTRITS,
    label: 'Mock (TS)',
    ready: true,
  };

  constructor(n = 3) {
    this.reset(n);
  }

  get qutrits(): number {
    return this.n;
  }

  get dimension(): number {
    return dimensionOf(this.n);
  }

  reset(n: number): void {
    if (n < 1 || n > MOCK_MAX_QUTRITS) {
      throw new Error(`mock engine supports 1..${MOCK_MAX_QUTRITS} qutrits (got ${n})`);
    }
    this.n = n;
    this.buf = new Float64Array(2 * dimensionOf(n));
    // Balanced ternary: the register's zero state is the digit vector 0...0,
    // which sits at the MIDDLE of the index range, not at index 0 (that index
    // is |-...-\u27e9). Getting this wrong silently mislabels every readout, so the
    // future Rust core must use the same convention.
    this.buf[2 * zeroStateIndex(n)] = 1; // |0...0>
  }

  amplitudes(): Float64Array {
    return this.buf;
  }

  probabilities(): Float64Array {
    const d = this.dimension;
    const p = new Float64Array(d);
    for (let k = 0; k < d; k++) {
      const re = this.buf[2 * k];
      const im = this.buf[2 * k + 1];
      p[k] = re * re + im * im;
    }
    return p;
  }

  /** Place value of qutrit q (q = 0 is most significant). */
  private stride(q: number): number {
    return Math.pow(3, this.n - 1 - q);
  }

  private assertIndex(q: number, what: string): void {
    if (!Number.isInteger(q) || q < 0 || q >= this.n) {
      throw new Error(`${what} qutrit ${q} out of range 0..${this.n - 1}`);
    }
  }

  applyGate(op: GateOp): void {
    if (op.gate === 'CX' || op.gate === 'CZ') {
      if (op.control === undefined) throw new Error(`${op.gate} requires a control qutrit`);
      this.assertIndex(op.control, 'control');
      this.assertIndex(op.target, 'target');
      if (op.control === op.target) throw new Error('control and target must differ');
      if (op.gate === 'CX') this.applyCX(op.control, op.target);
      else this.applyCZ(op.control, op.target);
      return;
    }
    this.assertIndex(op.target, 'target');
    this.applySingle(GATES[op.gate], op.target);
  }

  /** Apply a 3x3 unitary to one qutrit, iterating disjoint index triples. */
  private applySingle(m: Mat3, q: number): void {
    const s = this.stride(q);
    const d = this.dimension;
    const buf = this.buf;
    const block = s * 3;
    for (let base = 0; base < d; base += block) {
      for (let off = 0; off < s; off++) {
        const i0 = base + off;
        const i1 = i0 + s;
        const i2 = i1 + s;
        const a0r = buf[2 * i0];
        const a0i = buf[2 * i0 + 1];
        const a1r = buf[2 * i1];
        const a1i = buf[2 * i1 + 1];
        const a2r = buf[2 * i2];
        const a2i = buf[2 * i2 + 1];
        for (let row = 0; row < 3; row++) {
          const r0 = m[row * 6];
          const c0 = m[row * 6 + 1];
          const r1 = m[row * 6 + 2];
          const c1 = m[row * 6 + 3];
          const r2 = m[row * 6 + 4];
          const c2 = m[row * 6 + 5];
          const idx = base + off + row * s;
          buf[2 * idx] = r0 * a0r - c0 * a0i + (r1 * a1r - c1 * a1i) + (r2 * a2r - c2 * a2i);
          buf[2 * idx + 1] = r0 * a0i + c0 * a0r + (r1 * a1i + c1 * a1r) + (r2 * a2i + c2 * a2r);
        }
      }
    }
  }

  private digitAt(k: number, q: number): number {
    return Math.floor(k / this.stride(q)) % 3;
  }

  private applyCX(c: number, t: number): void {
    const d = this.dimension;
    const st = this.stride(t);
    const out = new Float64Array(this.buf.length);
    for (let k = 0; k < d; k++) {
      const cd = this.digitAt(k, c);
      const td = this.digitAt(k, t);
      const dest = k + (((td + cd) % 3) - td) * st;
      out[2 * dest] = this.buf[2 * k];
      out[2 * dest + 1] = this.buf[2 * k + 1];
    }
    this.buf = out;
  }

  private applyCZ(c: number, t: number): void {
    const d = this.dimension;
    for (let k = 0; k < d; k++) {
      const p = (this.digitAt(k, c) * this.digitAt(k, t)) % 3;
      if (p === 0) continue;
      const a = (TAU / 3) * p;
      const cs = Math.cos(a);
      const sn = Math.sin(a);
      const re = this.buf[2 * k];
      const im = this.buf[2 * k + 1];
      this.buf[2 * k] = re * cs - im * sn;
      this.buf[2 * k + 1] = re * sn + im * cs;
    }
  }

  measure(rng: () => number = Math.random): MeasurementResult {
    const p = this.probabilities();
    const r = rng();
    let acc = 0;
    let outcome = p.length - 1;
    for (let k = 0; k < p.length; k++) {
      acc += p[k];
      if (r <= acc) {
        outcome = k;
        break;
      }
    }
    const probability = p[outcome];
    this.buf = new Float64Array(this.buf.length);
    this.buf[2 * outcome] = 1;
    return { outcome, probability, trits: tritsOf(outcome, this.n) };
  }
}
