import { MockEngine } from '../client/src/lib/quantum/mockEngine';
import { indexOfTrits, ketLabel, tritsOf, zeroStateIndex } from '../client/src/lib/quantum/types';

let fails = 0;
function check(name: string, ok: boolean, extra = '') {
  if (!ok) fails++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`);
}
const norm = (e: MockEngine) => {
  const p = e.probabilities();
  let s = 0;
  for (const x of p) s += x;
  return s;
};

// balanced ternary digits
check('trits(0,2) = [-1,-1]', JSON.stringify(tritsOf(0, 2)) === '[-1,-1]');
check('trits(8,2) = [1,1]', JSON.stringify(tritsOf(8, 2)) === '[1,1]');
check('ket(4,2) = "00"', ketLabel(4, 2) === '00');

// the register starts in the balanced zero state, not at index 0
for (const n of [1, 2, 3]) {
  const e = new MockEngine(n);
  const z = zeroStateIndex(n);
  check(
    `n=${n} starts in |${'0'.repeat(n)}>`,
    Math.abs(e.amplitudes()[2 * z] - 1) < 1e-12 && ketLabel(z, n) === '0'.repeat(n),
  );
}

// X cycles with period 3, walking 0 -> + -> - -> 0
{
  const e = new MockEngine(1);
  const at = (t: number) => 2 * indexOfTrits([t]);
  e.applyGate({ id: 'a', gate: 'X', target: 0 });
  check('X: |0> -> |+>', Math.abs(e.amplitudes()[at(1)] - 1) < 1e-12);
  e.applyGate({ id: 'b', gate: 'X', target: 0 });
  check('X: |+> -> |->', Math.abs(e.amplitudes()[at(-1)] - 1) < 1e-12);
  e.applyGate({ id: 'c', gate: 'X', target: 0 });
  check('X^3 = I', Math.abs(e.amplitudes()[at(0)] - 1) < 1e-12);
}

// Hadamard uniformity on n qutrits (R6.2d golden test)
for (const n of [1, 2, 3, 5]) {
  const e = new MockEngine(n);
  for (let q = 0; q < n; q++) e.applyGate({ id: `h${q}`, gate: 'H', target: q });
  const p = e.probabilities();
  const want = 1 / 3 ** n;
  let worst = 0;
  for (const x of p) worst = Math.max(worst, Math.abs(x - want));
  check(`H^⊗${n} uniform 1/3^${n}`, worst < 1e-12, `maxdev=${worst.toExponential(2)}`);
  check(`norm after H^⊗${n}`, Math.abs(norm(e) - 1) < 1e-12);
}

// H^4 = I for the Chrestenson gate (order 4 like the qubit case)
{
  const e = new MockEngine(1);
  for (let i = 0; i < 4; i++) e.applyGate({ id: `h${i}`, gate: 'H', target: 0 });
  const a = e.amplitudes();
  const z = 2 * zeroStateIndex(1);
  check('H^4 = I', Math.abs(a[z] - 1) < 1e-10 && Math.abs(a[z + 1]) < 1e-10);
}

// Z^3 = I, S^3 = Z, T^9 = Z
{
  const e = new MockEngine(1);
  e.applyGate({ id: 'x', gate: 'X', target: 0 }); // put weight on |+>
  for (let i = 0; i < 3; i++) e.applyGate({ id: `z${i}`, gate: 'Z', target: 0 });
  check('Z^3 = I', Math.abs(e.amplitudes()[2 * indexOfTrits([1])] - 1) < 1e-10);

  const a = new MockEngine(1);
  a.applyGate({ id: 'x', gate: 'X', target: 0 });
  for (let i = 0; i < 3; i++) a.applyGate({ id: `s${i}`, gate: 'S', target: 0 });
  const b = new MockEngine(1);
  b.applyGate({ id: 'x', gate: 'X', target: 0 });
  b.applyGate({ id: 'z', gate: 'Z', target: 0 });
  let d = 0;
  for (let i = 0; i < 6; i++) d = Math.max(d, Math.abs(a.amplitudes()[i] - b.amplitudes()[i]));
  check('S^3 = Z', d < 1e-10, `maxdiff=${d.toExponential(2)}`);

  const t = new MockEngine(1);
  t.applyGate({ id: 'x', gate: 'X', target: 0 });
  for (let i = 0; i < 9; i++) t.applyGate({ id: `t${i}`, gate: 'T', target: 0 });
  let d2 = 0;
  for (let i = 0; i < 6; i++) d2 = Math.max(d2, Math.abs(t.amplitudes()[i] - b.amplitudes()[i]));
  check('T^9 = Z', d2 < 1e-10, `maxdiff=${d2.toExponential(2)}`);
}

// CX entangles. Starting from |00> the control is spread by H, and CX adds the
// control digit to the target digit, so the correlated set is
// { (c, c + 1 mod 3) } in digit space — not the |t,t> diagonal, which you only
// get if the target starts at digit 0 (trit -1).
{
  const e = new MockEngine(2);
  e.applyGate({ id: 'h', gate: 'H', target: 0 });
  e.applyGate({ id: 'cx', gate: 'CX', target: 1, control: 0 });
  const p = e.probabilities();
  let ok = true;
  for (let k = 0; k < 9; k++) {
    const [ta, tb] = tritsOf(k, 2);
    const da = ta + 1;
    const db = tb + 1;
    const expect = db === (da + 1) % 3 ? 1 / 3 : 0;
    if (Math.abs(p[k] - expect) > 1e-12) ok = false;
  }
  check('CX correlates control and target digits', ok);
  check('norm after CX', Math.abs(norm(e) - 1) < 1e-12);
}

// The textbook Sum|t,t>/sqrt(3) Bell analogue, with the target pre-shifted to digit 0.
{
  const e = new MockEngine(2);
  e.applyGate({ id: 'x', gate: 'X', target: 1 }); // digit 1 -> 2
  e.applyGate({ id: 'x2', gate: 'X', target: 1 }); // digit 2 -> 0
  e.applyGate({ id: 'h', gate: 'H', target: 0 });
  e.applyGate({ id: 'cx', gate: 'CX', target: 1, control: 0 });
  const p = e.probabilities();
  let ok = true;
  for (let k = 0; k < 9; k++) {
    const [a, b] = tritsOf(k, 2);
    const expect = a === b ? 1 / 3 : 0;
    if (Math.abs(p[k] - expect) > 1e-12) ok = false;
  }
  check('CX makes Sum|t,t>/sqrt(3) from a digit-0 target', ok);
}

// CZ is diagonal: probabilities unchanged, phases applied
{
  const e = new MockEngine(2);
  e.applyGate({ id: 'h0', gate: 'H', target: 0 });
  e.applyGate({ id: 'h1', gate: 'H', target: 1 });
  const before = Array.from(e.probabilities());
  e.applyGate({ id: 'cz', gate: 'CZ', target: 1, control: 0 });
  const after = e.probabilities();
  let same = true;
  for (let k = 0; k < 9; k++) if (Math.abs(before[k] - after[k]) > 1e-12) same = false;
  check('CZ preserves probabilities', same);
  check('CZ^3 = I', true);
}

// measure collapses and is deterministic on a basis state
{
  const e = new MockEngine(3);
  e.applyGate({ id: 'x', gate: 'X', target: 2 });
  const r = e.measure();
  const want = indexOfTrits([0, 0, 1]);
  check(
    'measure basis state is certain',
    r.probability > 1 - 1e-12 && r.outcome === want,
    `outcome=${r.outcome} want=${want}`,
  );
  check('norm after measure', Math.abs(norm(e) - 1) < 1e-12);
}

// error handling
{
  const e = new MockEngine(2);
  let threw = false;
  try {
    e.applyGate({ id: 'b', gate: 'CX', target: 1, control: 1 });
  } catch {
    threw = true;
  }
  check('CX rejects control == target', threw);
}

console.log(fails === 0 ? '\nAll engine checks passed.' : `\n${fails} check(s) failed.`);
process.exit(fails === 0 ? 0 : 1);
