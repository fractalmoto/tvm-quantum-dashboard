# TriFHE hardness harness

A reproducible bridge from a declared TriFHE parameter set to the official
[lattice-estimator](https://github.com/malb/lattice-estimator), producing a
signed-off JSON audit record instead of a number in a slide.

The harness exists because of one rule:

> Raw keyspace is not security. A dense ternary secret of length 2187 has a
> keyspace of \(3^{2187} \approx 2^{3466}\). The security level of that instance
> is the cost of the *cheapest known attack* against the specific LWE/RLWE
> instance — a number several orders of magnitude smaller, produced by the
> estimator, and meaningless without the cost model and estimator commit
> attached.

## Layout

```
estimator-harness/
  trifhe_estimator/
    params.py        # TriFHEParams + structural validation. No Sage import.
    adapter.py       # TriFHEParams -> estimator LWE.Parameters. Records every
                     # modelling decision with its rationale.
    run_estimate.py  # CLI. Runs all attacks x all cost models, emits JSON.
  records/           # Committed audit records, one JSON per parameter set.
```

`params.py` deliberately imports nothing heavier than the standard library, so
the parameter model and every structural check can run in a plain Python
backend, a test suite, or a web request handler without SageMath present. Only
`adapter.py` touches the estimator.

## Environment

The estimator is a SageMath library. It is not pip-installable and it will not
run on CPython alone.

```bash
# 1. SageMath core (the `sagelib` conda-forge package is far lighter than `sage`)
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
export MAMBA_ROOT_PREFIX="$PWD/mamba"
./bin/micromamba create -y -n sage -c conda-forge sagelib scipy

# 2. The estimator, pinned
git clone https://github.com/malb/lattice-estimator.git
git -C lattice-estimator checkout 53da5982597709ba0fdf94ea37a84d822310fd84
export ESTIMATOR_PATH="$PWD/lattice-estimator"

# 3. Run
./bin/micromamba run -n sage python -m trifhe_estimator.run_estimate \
    --preset draft --json-out records/trifhe-draft.json
```

Verified working on SageMath 10.9 / Python 3.14.7 / scipy 1.18.0.

**Pin the estimator commit and record it.** The harness does this automatically
(`provenance.estimator.commit`) and also records whether the working tree was
clean. An estimator result without a commit hash is not reproducible: attack
implementations and cost models change between commits, and published parameter
sets are always stated against a specific one — the
[2024 HE security guidelines](https://eprint.iacr.org/2024/463.pdf) pin
`8f1ff7e`, for example.

Note the currently pinned commit `53da598` carries the message *"not sure this
should go here, but maybe it can"*, i.e. it is an in-progress upstream commit
rather than a tagged release. That is acceptable for internal iteration but
should be moved to a reviewed upstream tag before an external audit.

## Usage

```bash
# The parameter set exactly as the draft memorandum writes it
... run_estimate --preset draft

# The same spec re-read as the 3-power cyclotomic ring (n = 1458, not 2187)
... run_estimate --preset cyclotomic

# Arbitrary instance
... run_estimate --n 4096 --q 132120577 --ring power_of_two_cyclotomic \
                 --secret sparse_ternary --hamming-weight 64 --sigma-e 3.19

# Fast smoke test while developing the harness. NEVER quote the output.
... run_estimate --preset draft --rough
```

Exit code is `0` only when the run produced a **quotable** figure. It is `2` when
any blocker-severity structural finding fired or `--rough` was used, so CI fails
loudly rather than letting a bad number reach a document.

## What the record contains

| Block | Purpose |
| --- | --- |
| `instance` | The parameter set as declared, plus derived `lattice_dim`, `log2_q`, `keyspace_log2`. |
| `estimator_instance` | The estimator's own view: `n`, `q`, `Xs`, `Xe`, `m`. This is what was actually costed. |
| `modelling_decisions` | Every judgement call the adapter made, with rationale. The dimension choice, the secret mapping, the assumed error width, the sample bound. |
| `structural_findings` | Checks that need no estimator: modulus primality and factorisation, the NWC condition, ring soundness, noise budget, sparsity, the keyspace guard. |
| `results` | Per cost model: every attack the estimator implements, its `log2_rop`, `beta`, `d`, memory, and the cheapest of them. |
| `summary` | Headline bits, whether the figure saturated the estimator's block-size bound, and `quotable` with reasons. |
| `uncovered_attacks` | Attacks outside the estimator's model, each with a reference. The matrix is not a complete cryptanalysis and says so. |
| `provenance` | Estimator commit + date + clean/dirty, Sage version, Python, platform, UTC timestamp. |

## Design decisions worth arguing about

**Dimension.** `ring_kind` is an explicit input, not an inference, because
"N = 2187" is ambiguous and the ambiguity is worth 729 dimensions. A power-of-3
*cyclotomic* has degree \(\varphi(3^k) = 2\cdot 3^{k-1}\), so the 3-power ring
near 2187 has lattice dimension **1458**. Taking the number 2187 at face value
instead describes \(\mathbb{Z}[x]/(x^{2187}+1)\), which is not a cyclotomic ring
at all. Both readings are shipped as presets so the difference is visible rather
than buried.

**RLWE is costed as plain LWE of the same dimension.** Standard and conservative:
no known attack exploits the ring structure of a well-chosen cyclotomic to beat
the plain-LWE cost. This assumption is void for rings with exploitable subfields
or badly splitting moduli, which is exactly why `ring-not-cyclotomic` is a
blocker rather than a warning.

**Four cost models, not one.** MATZOV (the estimator default, concrete gate
counts) alongside core-SVP classical / quantum / paranoid. The spread between
them is the honest error bar. Quoting one model's number as *the* security level
is the most common way these claims fail review.

**Quantum security means core-SVP quantum.** \(2^{0.265\beta}\), the known
quantum speedup on sieving. It does not mean anything derived from Shor's
algorithm or from scaling an RSA-2048 qubit count — lattice problems have no
known Shor-style quantum break, and any figure obtained by rescaling an RSA qubit
estimate is not a cryptanalytic result.

**Saturation is reported.** The estimator caps block size at `max_beta = 1754`
(\(\approx 2^{512}\)). When the optimal \(\beta\) lands near that cap the result
is a floor imposed by the search bound, not a converged optimum, so it is printed
as `>= N bits` and flagged in the record. Attacks returning infinite cost were
pruned by the same bound and are not "impossible".

**Full estimate, never rough.** `LWE.estimate.rough` uses an optimistic model
and a reduced attack set. The harness supports it for iteration speed and marks
any such record `rough: true` and non-quotable.

## Known limitation

A small \(q\) makes the lattice *harder* and the FHE scheme *less useful*. At
\(\log_2 q \approx 15\) there is almost no noise headroom, so a very large bit
count here is not the good news it looks like — it is a sign the parameters are
not a working FHE parameter set. The harness reports the noise budget as a
blocker precisely so the two facts travel together.

## References

- [lattice-estimator](https://github.com/malb/lattice-estimator) — Albrecht et al., the tool this wraps
- [Security Guidelines for Implementing Homomorphic Encryption (2024)](https://eprint.iacr.org/2024/463.pdf) — the methodology this harness follows
- [Homomorphic Encryption Standard v1.1](https://homomorphicencryption.org/wp-content/uploads/2024/08/Homomorphic-Encryption-Standard-v1.1.pdf) — parameter tables, \(\sigma = 3.19\)
- [May, Meet-LWE (CRYPTO 2021)](https://eprint.iacr.org/2021/216) — MitM on small secrets, not in the estimator
- [The Cool and the Cruel](https://arxiv.org/abs/2403.10328) — statistical dual attack on sparse/small secrets
- [Li & Micciancio, IND-CPA^D](https://eprint.iacr.org/2020/1533) — approximate-FHE decryption-failure attacks
- [Elias, Lauter, Ozman, Stange](https://eprint.iacr.org/2015/106) — weak RLWE instances from ring structure
