# Linear follow-ups for the ternary-aligned ring programme

Drafts for the TRI team, project [TriFHE Hardness Document](https://linear.app/trinaryvm/project/trifhe-hardness-document-96006ba423e2).
Written out here because the Linear connector was unavailable when this branch
was produced. Each one names its relationship to the existing TRI-212..TRI-224
issues so nothing is filed twice.

Note that Linear strips LaTeX delimiters, so these are written in plain text:
`phi(m)` rather than `\varphi(m)`, `2^-128` rather than `$2^{-128}$`.

---

## 1. Run the pinned lattice estimator for the four conductor-declared presets

**Priority: Urgent. Relates to TRI-222.**

The branch adds four presets declared by conductor — `ternary-experimental`
(m = 8748, N = 2916), `baseline-2048` (m = 4096), `baseline-4096` (m = 8192),
`ternary-pure` (m = 2187) — with validated ring arithmetic and a validated noise
budget, but **no estimator figures**. SageMath could not be installed in the
environment that produced the branch, so `SECURITY-WORKSHEET.md` lists all four
as PENDING.

They were left PENDING rather than filled in from a hand-rolled cost model. That
substitution is the same error as the draft report and would be worse here, for
arriving inside a document about rigour.

Acceptance:

- Estimator cloned and checked out at `53da5982597709ba0fdf94ea37a84d822310fd84`,
  working tree clean, and the commit recorded in each JSON record.
- `sage -python -m trifhe_estimator.run_estimate --preset <p> --log2-q 45
  --json-out records/<p>.json` for all four presets.
- `python -m trifhe_estimator.worksheet records/*.json --noise 'records/noise-*.json'`
  regenerated, with every PENDING row replaced by a real minimum-cost figure.
- The reported figure is the MINIMUM over all attacks in each cost model, not a
  selected Core-SVP row.

Until this is done, no bit-security number exists for the ternary-aligned
candidate, and the branch must not be read as providing one.

---

## 2. Subfield and structural screening for Q(zeta_8748)

**Priority: High. Extends TRI-218 to the new candidate ring.**

The programme costs the candidate as plain LWE of dimension phi(m) = 2916. That
is standard practice and it is not a reduction. m = 8748 = 2^2 * 3^7 has a
divisor for every combination of those factors, so Q(zeta_8748) has a
correspondingly rich subfield lattice — considerably richer than a power-of-two
cyclotomic, which is the setting essentially all published RLWE parameter
guidance covers.

Screening required before any figure for this ring is quoted:

- Enumerate subfields and check for norm/trace map attacks that reduce to a
  smaller-dimension problem.
- Root discriminant and spectral distortion of the canonical embedding, and
  whether coefficient-space sigma = 3.19 is the right error width in the
  canonical embedding for this ring.
- Galois action and automorphism structure.
- Screen against the known weak-RLWE conditions
  (https://eprint.iacr.org/2015/106).

Acceptance: a written screening record, or an explicit statement of which
screens could not be performed and what that leaves open.

---

## 3. Every modulus recommendation must state its gadget base and digit count

**Priority: High. Supersedes the noise-budget reasoning in TRI-215.**

Measured on the branch: at a 2^15 gadget base, the relinearisation term is
**99.999% of the invariant-noise variance** after one multiplication. The
multiplication cross terms, the scaling rounding and the product of noises are
numerical dust by comparison.

The draft's formula was `V_relin = 3.0 * N * sigma * sqrt(N)`. It contains no
gadget base and no digit count. The real dominant term is
`ell * N * (B^2 / 3) * sigma^2`, which at B = 2^15 is roughly five orders of
magnitude larger. So the draft formula omits its own largest term, and its
modulus recommendation cannot be reproduced from the parameters it names.

Concrete consequence: dropping B from 2^15 to 2^8 moves the minimum viable
log2 q from 29 to 25.

Acceptance:

- Every modulus recommendation in the hardness document states t, sigma, secret
  distribution, gadget base B, digit count ell, relinearisation variant, and the
  target circuit.
- The document's noise section cites the measured variance decomposition rather
  than a closed-form expression whose dominant term is absent.

---

## 4. Zero observed decryption failures is not a correctness result

**Priority: High. Relates to TRI-219 (IND-CPA^D).**

The branch contains a configuration that decrypted correctly in **all 128
trials** and still fails: at m = 8748, log2 q = 29, the tail bound from the
measured standard deviation is 0.523 against a 0.5 threshold — 0.07 bits short.
Typical noise is fine there; the 2^-128 tail is not.

128 trials bound a failure rate near 2^-7. They say nothing about 2^-128. Since
decryption failures are a key-recovery channel under IND-CPA^D, a bound short by
a fraction of a bit is a finding rather than a rounding difference.

`run_noise` exits 2 on that configuration rather than reporting zero failures as
a pass.

Acceptance: the hardness document states the failure-probability target, the tail
multiplier used, the union bound over coefficients, and the fact that the tail is
a Gaussian extrapolation from a measured standard deviation under the
independence heuristic — not a proof.

---

## 5. Gate CI on the noise harness exit code as well as the estimator's

**Priority: Medium. Extends TRI-223.**

TRI-223 gates CI on `run_estimate` exit code 2. `run_noise` uses the same
convention and needs the same gate. It exits 2 when the measured sigma is more
than a factor of two from the model, when any decryption failure is observed, or
when the tail bound does not clear 0.5 — including the case where every trial
decrypted correctly.

Acceptance: CI runs `pytest tests/` plus `run_noise` for all presets and fails
the build on a non-zero exit from either.

---

## 6. RNS chain for moduli above 2^50, and depth beyond one multiplication

**Priority: Medium. New.**

Two known limits of the current implementation, both documented in the code:

- `transform.py::mulmod` is exact only below 2^50 and raises above it rather than
  corrupting silently. Any parameter set needing a larger single modulus requires
  an RNS chain.
- The noise model and the experiments both cover exactly one multiplication plus
  relinearisation. The target circuit for the VM is deeper, and modulus switching
  is not modelled at all.

Acceptance: variance propagation extended per level with modulus switching, an
RNS ciphertext representation, and experiments at the actual target depth. Note
that a deeper circuit needs a larger q, which lowers the security figure — so
this issue and issue 1 are coupled and should be resolved in that order.
