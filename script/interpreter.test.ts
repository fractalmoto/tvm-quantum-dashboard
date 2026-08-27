/**
 * Interpreter regression tests.
 *
 * Run: npx tsx script/interpreter.test.ts
 *
 * These lock down the bug class found in Phase 0 QA: a multi-line script whose
 * read-only commands (`check`, `probs`) evaluated against a stale snapshot, so
 * the golden Hadamard test reported FAIL on a uniform state.
 */

import { runScript, validateGate, type Session } from '../client/src/lib/quantum/interpreter';
import { GOLDEN_SCRIPT } from '../client/src/lib/quantum/qtest';

let pass = 0;
const fails: string[] = [];

function check(name: string, cond: boolean, detail = '') {
  if (cond) {
    pass++;
    console.log(`  ok  ${name}`);
  } else {
    fails.push(`${name}${detail ? ` — ${detail}` : ''}`);
    console.log(`FAIL  ${name}${detail ? ` — ${detail}` : ''}`);
  }
}

const fresh = (): Session => ({ n: 3, ops: [], collapse: null });
const text = (r: ReturnType<typeof runScript>) => r.lines.map((l) => l.text).join('\n');

console.log('\n.qtest interpreter');

// The original defect: golden script must PASS end to end.
{
  const r = runScript(fresh(), GOLDEN_SCRIPT);
  check('golden script reports PASS', /hadamard uniformity: PASS/.test(text(r)), text(r));
  check('golden script leaves 3 qutrits', r.session.n === 3, `n=${r.session.n}`);
  check('golden script leaves 3 gates', r.session.ops.length === 3, `${r.session.ops.length}`);
  check('golden script logs no errors', !r.lines.some((l) => l.kind === 'err'));
}

// `init` inside a script must be honoured, not skipped.
{
  const r = runScript(fresh(), 'init 2\nh 0\nh 1\ncheck hadamard');
  check('init resizes the session', r.session.n === 2, `n=${r.session.n}`);
  check('uniformity holds at n=2', /PASS/.test(text(r)), text(r));
  check('init clears prior ops', r.session.ops.length === 2);
}

// init out of range.
{
  const r = runScript(fresh(), 'init 12');
  check('init 12 rejected', /supports 1\.\.9/.test(text(r)), text(r));
  check('rejected init leaves n untouched', r.session.n === 3);
}

// Out-of-range gate indices must be rejected, never silently pushed.
{
  const r = runScript({ n: 2, ops: [], collapse: null }, 'h 2');
  check('out-of-range target rejected', /out of range 0\.\.1/.test(text(r)), text(r));
  check('rejected gate is not pushed', r.session.ops.length === 0);
}
{
  const r = runScript(fresh(), 'cx 5 0');
  check('out-of-range control rejected', /control qutrit 5 out of range/.test(text(r)), text(r));
  check('rejected two-qutrit gate not pushed', r.session.ops.length === 0);
}
{
  const r = runScript(fresh(), 'cz 1 1');
  check('control == target rejected', /must differ/.test(text(r)), text(r));
}

// Non-uniform state must FAIL the uniformity check (no false positives).
{
  const r = runScript(fresh(), 'h 0\ncheck hadamard');
  check('partial Hadamard reports FAIL', /FAIL/.test(text(r)), text(r));
}

// reset clears the circuit but keeps the width.
{
  const r = runScript(fresh(), 'h 0\nh 1\nreset\ncheck hadamard');
  check('reset keeps width', r.session.n === 3);
  check('reset clears ops', r.session.ops.length === 0);
  check('reset state is not uniform', /FAIL/.test(text(r)));
}

// measure collapses, and a following state read sees the collapse.
{
  const r = runScript(fresh(), 'h 0\nh 1\nh 2\nmeasure\nprobs 1');
  check('measure records a collapse', r.session.collapse !== null);
  const top = text(r).trim().split('\n').pop() ?? '';
  check('post-measure top probability is 1', /1\.000000000/.test(top), top);
}

// `clear` wipes queued output.
{
  const r = runScript(fresh(), 'help\nclear');
  check('clear requests a log wipe', r.clearLog);
  check('clear drops buffered lines', r.lines.length === 0, `${r.lines.length}`);
}

// Comments and blank lines are ignored, unknown commands reported.
{
  const r = runScript(fresh(), '# comment only\n\n   \nfrobnicate 1');
  check('unknown command reported', /unknown command: frobnicate/.test(text(r)), text(r));
  check('comments produce no ops', r.session.ops.length === 0);
}

// Input purity: the caller's session object is never mutated.
{
  const start = fresh();
  runScript(start, 'init 5\nh 0');
  check('input session not mutated', start.n === 3 && start.ops.length === 0);
}

console.log('\nvalidateGate');
check('valid single gate', validateGate('H', 0, undefined, 3) === null);
check('negative index rejected', validateGate('H', -1, undefined, 3) !== null);
check('missing control rejected', validateGate('CX', 0, undefined, 3) !== null);
check('valid two-qutrit gate', validateGate('CX', 1, 0, 3) === null);

console.log(`\n${pass} passed, ${fails.length} failed`);
if (fails.length) {
  for (const f of fails) console.log(`  - ${f}`);
  process.exit(1);
}
