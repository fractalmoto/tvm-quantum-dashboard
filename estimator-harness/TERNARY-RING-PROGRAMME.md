# The ternary-aligned ring programme

This document records the execution of a five-step programme against the
estimator harness:

1. Treat \(m = 8748\), \(N = 2916\), \(\Phi_m(X) = X^{2916} - X^{1458} + 1\) as the
   leading **experimental** ternary-aligned candidate.
2. Maintain a standard \(N = 2048\) or \(N = 4096\) power-of-two configuration as
   the implementation and security baseline.
3. Validate exact ring arithmetic and transform correctness **first**.
4. Then run empirical noise experiments over many randomised trials for the
   target circuit, and compare against a formal tail analysis.
5. Finally, publish an auditable security worksheet with the full estimator
   command, version, parameters, attack table, and the **minimum** attack cost —
   not selected Core-SVP output.

Steps 1–4 are done. Step 5 is done for everything except the estimator runs
themselves, which are blocked on toolchain availability and are recorded as
PENDING with exact reproduction commands rather than filled in.

## Step 1 — the candidate ring

\(m = 8748 = 2^2 \cdot 3^7\), so \(N = \varphi(m) = 2 \cdot 1458 = 2916\).

The closed form follows from \(\Phi_{2^a 3^b}(X) = \Phi_{3^b}\left(-X^{2^{a-1}}\right)\)
for \(a \ge 2\), giving

\[
\Phi_{8748}(X) = \Phi_{2187}(-X^2) = X^{2916} - X^{1458} + 1.
\]

Note the sign. The **pure** 3-power cyclotomics have plus signs,
\(\Phi_{3^b}(X) = X^{2 \cdot 3^{b-1}} + X^{3^{b-1}} + 1\), so
\(\Phi_{2187}(X) = X^{1458} + X^{729} + 1\). The signed trinomials belong to the
mixed \(2^a 3^b\) cases only. `rings.py` carries both a closed form and an
independent generic recursion from \(X^m - 1\), and the test suite checks them
against each other for **every** \(2^a 3^b\) conductor up to a bound, so a sign
error of this kind cannot survive.

## Step 2 — the baselines

| preset | conductor | \(\Phi_m(X)\) | \(N\) | role |
|---|---|---|---|---|
| `baseline-2048` | \(4096 = 2^{12}\) | \(X^{2048} + 1\) | 2048 | standard control |
| `baseline-4096` | \(8192 = 2^{13}\) | \(X^{4096} + 1\) | 4096 | standard control |
| `ternary-experimental` | \(8748 = 2^2 3^7\) | \(X^{2916} - X^{1458} + 1\) | 2916 | candidate |
| `ternary-pure` | \(2187 = 3^7\) | \(X^{1458} + X^{729} + 1\) | 1458 | contrast |

Every preset names the **conductor**, not the degree. The original draft's most
expensive error was writing \(N = 2187\) when the cyclotomic degree is
\(\varphi(3^7) = 1458\) — a factor-of-1.5 error in the lattice dimension, which
moves the security figure substantially. Declaring the conductor makes that class
of error impossible: the degree is derived, never asserted.

## Step 3 — ring arithmetic and transform correctness

Validated **before** any noise or security number was produced, because a
correctness bug underneath would invalidate everything above it.

- Reduction modulo the sparse trinomial uses \(X^N = -\sum_{i<N} \phi_i X^i\),
  which has at most two terms here.
- Multiplication uses a length-\(L\) **cyclic** transform, mixed-radix
  decimation-in-time, then reduces. The exact product is recovered when
  \(L \ge 2N - 1\).
- For a mixed conductor, \(\varphi(m)/m = 1/3\), so \(L = m\) suffices.
  For a **pure** 3-power conductor \(\varphi(m)/m = 2/3\) and the bound fails, so
  `transform_length(2187, 1458) = 6561 = 3m`. This is a real trap: reusing
  \(L = m\) uniformly would silently produce wrong products in the pure ring only.
- `mulmod` is exact only below \(2^{50}\), and raises above it rather than
  corrupting silently — an RNS chain is required past that point.

Validated against schoolbook reduction at full parameter size:

| conductor | \(N\) | transform | schoolbook | agree |
|---|---|---|---|---|
| 8748 | 2916 | 0.015 s | 1.5 s | yes |
| 4096 | 2048 | 0.008 s | 0.7 s | yes |
| 8192 | 4096 | 0.015 s | 2.8 s | yes |
| 2187 | 1458 | 0.009 s | 0.3 s | yes |

`pytest tests/` — 203 tests.

### Two real defects the tests caught

**A false-positive NTT check, of exactly the TRI-213 shape.**
\(34993 \equiv 1 \pmod{8748}\), because \(34992 = 4 \times 8748\). So a naive
product-congruence test reports "transform available" for the composite draft
modulus. `ntt_findings()` now analyses each CRT component separately and emits a
`cyclic-transform-false-positive` **blocker** when any component fails
\(p \equiv 1 \pmod m\). Regression-tested.

**A vacuous overflow assertion.** `ExactProduct` asserted on the *reconstructed*
coefficient magnitude. That assertion can never fire: CRT reconstruction always
returns a representative inside \((-M/2, M/2]\), so an overflowed product is
indistinguishable from a valid one after the fact. Overflow is only detectable
*a priori*, from input magnitudes. The check now runs on the inputs and raises.
An assertion that cannot fail is worse than none, because it reads as a
guarantee.

## Step 4 — noise: model versus measurement

`noise.py` propagates coefficient-wise variance under the independence
heuristic, term by term, and applies a Gaussian tail bound union-bounded over all
\(N\) coefficients at \(2^{-128}\). `run_noise.py` then executes the same circuit
128 times per configuration in the real ring and measures.

| \(m\) | \(N\) | \(\log_2 q\) | formal \(\sigma_v\) | measured \(\sigma_v\) | ratio | tail bound | headroom | correctness |
|---|---|---|---|---|---|---|---|---|
| 2187 | 1458 | 45 | \(2^{-21.28}\) | \(2^{-21.24}\) | 1.03 | 5.51e-6 | 16.47 bits | PASS |
| 4096 | 2048 | 45 | \(2^{-21.03}\) | \(2^{-21.13}\) | 0.94 | 5.96e-6 | 16.36 bits | PASS |
| 8748 | 2916 | 29 | \(2^{-5.28}\) | \(2^{-4.71}\) | 1.48 | 5.23e-1 | −0.07 bits | **FAIL** |
| 8748 | 2916 | 45 | \(2^{-20.78}\) | \(2^{-20.40}\) | 1.30 | 9.93e-6 | 15.62 bits | PASS |
| 8192 | 4096 | 45 | \(2^{-20.53}\) | \(2^{-21.02}\) | 0.71 | 6.46e-6 | 16.24 bits | PASS |

Model and measurement agree within a factor of 1.5 across all four ring shapes.
Zero decryption failures except where noted.

### The finding that matters

**Relinearisation is 99.999% of the variance**, at a \(2^{15}\) gadget base.
Everything else — the multiplication cross terms, the scaling rounding, the
product of noises — is numerical dust.

The draft's noise formula was:

```
V_fresh = 6.0 * sigma * sqrt(N)
V_mult  = 2.0 * N * t * V_fresh**2
V_relin = 3.0 * N * sigma * sqrt(N)
```

Its relinearisation term contains no gadget base and no digit count. The
dominant term in the real variance is \(\ell \cdot N \cdot \frac{B^2}{3} \cdot \sigma^2\),
which at \(B = 2^{15}\) is roughly five orders of magnitude above the terms the
formula does model. So the formula's modulus recommendation is not conservative
or approximate — it is missing its largest term, and its output is not
reproducible from the parameters it names.

A concrete consequence: dropping the gadget base to \(2^8\) lowers the minimum
viable \(\log_2 q\) from 29 to 25. **A modulus recommendation that does not state
its gadget base is incomplete**, and the draft's did not.

### Why zero failures is not a pass

The \(\log_2 q = 29\) row decrypted correctly in all 128 trials and still fails.
Its tail bound is 0.523 against a 0.5 threshold — 0.07 bits *short*. Typical
noise is fine there; the \(2^{-128}\) tail is not.

128 trials bound a failure rate near \(2^{-7}\), not \(2^{-128}\). The experiment's
job is to validate the standard deviation, and the tail claim is a Gaussian
extrapolation from that measured standard deviation. The harness exits non-zero
on that row rather than reporting zero failures as a pass. This is the
\(\text{IND-CPA}^{\mathcal{D}}\) concern in TRI-219: decryption failures are a
key-recovery channel, so a bound that is short by a fraction of a bit is a
finding, not a rounding difference.

## Step 5 — the auditable worksheet

`worksheet.py` generates `SECURITY-WORKSHEET.md` from the JSON records. Per
parameter set it emits the full parameter record with assumptions flagged, the
structural findings, **every** attack in **every** cost model sorted by cost with
the minimum marked, the estimator commit and whether its tree was clean, the Sage
and Python versions, the exact command, the noise tables, and the named list of
attacks the estimator does not cover.

### What is not generated

The estimator runs for the four new presets are **PENDING**. The lattice
estimator requires SageMath, which could not be installed in this environment.
They are listed as PENDING with exact reproduction commands rather than filled in
from a hand-rolled cost model — which is the same category of error as the draft
report, and would be worse here for arriving inside a document about rigour.

```sh
git clone https://github.com/malb/lattice-estimator
cd lattice-estimator && git checkout 53da5982597709ba0fdf94ea37a84d822310fd84
cd /path/to/estimator-harness
sage -python -m trifhe_estimator.run_estimate --preset ternary-experimental \
    --log2-q 45 --json-out records/ternary-experimental.json
sage -python -m trifhe_estimator.run_estimate --preset baseline-2048 \
    --log2-q 45 --json-out records/baseline-2048.json
python -m trifhe_estimator.worksheet records/*.json \
    --noise 'records/noise-*.json' --out SECURITY-WORKSHEET.md
```

## What this programme does not establish

- **Not** that \(N = 2916\) meets 128 bits. No estimator run exists for it yet,
  and when one does it will be a minimum over the attacks the estimator
  implements — not a bound over all known attacks.
- **Not** that the ternary-aligned ring is as well understood as a power-of-two
  cyclotomic. Costing RLWE in a bespoke ring as plain LWE of dimension
  \(\varphi(m)\) is standard practice, but it is not a reduction. \(\mathbb{Q}(\zeta_{8748})\)
  has a subfield for every divisor of the conductor, and subfield and structural
  screening (TRI-218) is open.
- **Not** that a \(2^{-128}\) decryption failure rate has been measured.
- **Not** a recommendation to move off \(N = 2048\). The candidate now has
  validated arithmetic and a validated noise budget, which makes it a legitimate
  experimental track. It does not make it a parameter recommendation, and the
  power-of-two baseline should remain the implementation target until the
  estimator runs and the structural screening are both done.
