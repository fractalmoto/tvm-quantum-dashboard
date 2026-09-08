# TriFHE security worksheet

Generated 2026-09-08T05:08:42.696230+00:00.

This worksheet exists so that no security figure in the TriFHE hardness document has to be taken on trust. Every number below is accompanied by the command, commit and full parameter record needed to regenerate it, the complete attack table rather than a selected row, and an explicit statement of what is assumed and what is not covered.


## Summary

| parameter set | conductor m | n | log2 q | min bits (MATZOV) | min bits (CoreSVP quantum) | cheapest attack | status | blockers |
|---|---|---|---|---|---|---|---|---|
| TriFHE-draft-N2187-q34993 | 2187 | 2187 | 15.09 | 499.0 | 443.7 | dual_hybrid | NOT QUOTABLE | q-not-prime, nwc-crt-fail, ring-not-cyclotomic, noise-budget-thin |
| TriFHE-cyclotomic-n1458-q34993 | 2187 | 1458 | 15.09 | 325.7 | 280.6 | dual_hybrid | NOT QUOTABLE | q-not-prime, nwc-crt-fail, noise-budget-thin |
| ternary-experimental | - | - | - | PENDING | PENDING | - | NOT GENERATED | - |
| baseline-2048 | - | - | - | PENDING | PENDING | - | NOT GENERATED | - |
| baseline-4096 | - | - | - | PENDING | PENDING | - | NOT GENERATED | - |
| ternary-pure | - | - | - | PENDING | PENDING | - | NOT GENERATED | - |


`min bits` is the minimum over all attacks the estimator costed in that model. `NOT QUOTABLE` means a structural finding disqualifies the parameter set regardless of its estimated cost: a large number attached to an unsound ring is not a security claim.


## Pending estimator runs

The following parameter sets have a validated ring and a validated noise budget but **no estimator run in this worksheet**, because the SageMath toolchain was not available in the environment that generated it. They are listed as PENDING rather than filled in with figures from another source or from a hand-rolled cost model.

To fill them in, in an environment with Sage:

```sh
git clone https://github.com/malb/lattice-estimator /path/to/lattice-estimator
cd /path/to/lattice-estimator
git checkout 53da5982597709ba0fdf94ea37a84d822310fd84
cd /path/to/estimator-harness

sage -python -m trifhe_estimator.run_estimate --preset ternary-experimental --log2-q 45 --json-out records/ternary-experimental.json

sage -python -m trifhe_estimator.run_estimate --preset baseline-2048 --log2-q 45 --json-out records/baseline-2048.json

sage -python -m trifhe_estimator.run_estimate --preset baseline-4096 --log2-q 45 --json-out records/baseline-4096.json

sage -python -m trifhe_estimator.run_estimate --preset ternary-pure --log2-q 45 --json-out records/ternary-pure.json

```

Then regenerate this worksheet:

```sh
python -m trifhe_estimator.worksheet records/*.json --noise records/noise-*.json --out SECURITY-WORKSHEET.md
```


## Noise validation

Ring arithmetic and transform correctness are validated by the test suite (`pytest tests/`), which checks the bespoke transform against schoolbook reduction modulo the exact cyclotomic at full parameter size. The tables below then validate the noise MODEL against measurement in that ring.

| m | N | log2 q | formal sigma_v | measured sigma_v | ratio | tail bound on v_inf | headroom (bits) | correctness | dec failures |
|---|---|---|---|---|---|---|---|---|---|
| 2187 | 1458 | 45.0 | 2^-21.28 | 2^-21.24 | 1.027 | 5.510e-06 | 16.47 | PASS | 0/128 |
| 4096 | 2048 | 45.0 | 2^-21.03 | 2^-21.13 | 0.936 | 5.959e-06 | 16.36 | PASS | 0/128 |
| 8748 | 2916 | 29.0 | 2^-5.28 | 2^-4.71 | 1.483 | 5.231e-01 | -0.07 | FAIL | 0/128 |
| 8748 | 2916 | 45.0 | 2^-20.78 | 2^-20.40 | 1.304 | 9.926e-06 | 15.62 | PASS | 0/128 |
| 8192 | 4096 | 45.0 | 2^-20.53 | 2^-21.02 | 0.714 | 6.456e-06 | 16.24 | PASS | 0/128 |


The `log2 q = 29` row is the informative one: it decrypted correctly in every trial and still FAILS, because its tail bound does not clear 0.5. That is the whole reason the empirical run cannot stand alone — a few hundred successful trials say nothing about a 2^-128 failure target. It is also why the harness exits non-zero on that row rather than reporting zero failures as a pass.


### Noise: formal model vs measurement — Phi_2187, N = 1458, log2 q = 45.00
Ring `X^1458 + X^729 + 1`, q = 35184372316633 (q mod m = 1), t = 3, sigma = 3.19, secret uniform ternary {-1,0,+1}, gadget base 32768 x 4 digits, BFV v1, evk encrypts B^i * s^2.
| stage | formal sigma_v | measured sigma_v | measured/formal | max v_inf observed |
|---|---|---|---|---|
| fresh ciphertext | 2^-36.28 | 2^-36.05 | 1.168 | 7.324e-11 (5.23 sigma) |
| after 1 mult + relin | 2^-21.28 | 2^-21.24 | 1.027 | 1.294e-06 (3.20 sigma) |

#### Variance decomposition after mult + relin
| term | share of variance |
|---|---|
| relinearisation digits * evk error | 99.9995% |
| v1 * m2 (fresh noise times plaintext) | 0.0002% |
| v2 * m1 (fresh noise times plaintext) | 0.0002% |
| scaling rounding r2 * s^2 | 0.0000% |
| scaling rounding r1 * s | 0.0000% |
| scaling rounding r0 | 0.0000% |
| v1 * v2 (product of noises) | 0.0000% |

Dominant term: **relinearisation digits * evk error**. The original draft's noise formula omitted this term entirely, which is why its modulus recommendation cannot be reproduced.

#### Correctness bound
| quantity | value |
|---|---|
| tail multiplier D | 13.650 (union bound over 1458 coefficients at 2^-128.0 / N) |
| formal bound on v_inf | 5.3641e-06 |
| bound from MEASURED sigma | 5.5102e-06 |
| correctness threshold | 0.5 |
| headroom | 16.47 bits |
| minimum log2 q for 1 mult + relin | 28 |
| decryption failures observed | 0 of 128 |
| model agrees with measurement | yes |

> A passing empirical run over a few hundred trials cannot certify a 2^-128 failure probability directly — it bounds failure at roughly 2^-7.0. The tail claim rests on the Gaussian extrapolation from the MEASURED standard deviation, and the experiment's job is to validate that standard deviation, not the tail itself.

> The independence heuristic is an assumption, not a theorem. It treats coefficients of ring products as independent, which is false in detail. This model is only credible where the empirical distribution agrees with it.

Reproduce: `python -m trifhe_estimator.run_noise --m 2187 --log2-q 45 --trials 128 --quiet --json-out records/noise-m2187-q45.json`


### Noise: formal model vs measurement — Phi_4096, N = 2048, log2 q = 45.00
Ring `X^2048 + 1`, q = 35184372121601 (q mod m = 1), t = 3, sigma = 3.19, secret uniform ternary {-1,0,+1}, gadget base 32768 x 4 digits, BFV v1, evk encrypts B^i * s^2.
| stage | formal sigma_v | measured sigma_v | measured/formal | max v_inf observed |
|---|---|---|---|---|
| fresh ciphertext | 2^-36.03 | 2^-36.03 | 1.001 | 6.514e-11 (4.58 sigma) |
| after 1 mult + relin | 2^-21.03 | 2^-21.13 | 0.936 | 1.562e-06 (3.59 sigma) |

#### Variance decomposition after mult + relin
| term | share of variance |
|---|---|
| relinearisation digits * evk error | 99.9994% |
| v1 * m2 (fresh noise times plaintext) | 0.0003% |
| v2 * m1 (fresh noise times plaintext) | 0.0003% |
| scaling rounding r2 * s^2 | 0.0000% |
| scaling rounding r1 * s | 0.0000% |
| scaling rounding r0 | 0.0000% |
| v1 * v2 (product of noises) | 0.0000% |

Dominant term: **relinearisation digits * evk error**. The original draft's noise formula omitted this term entirely, which is why its modulus recommendation cannot be reproduced.

#### Correctness bound
| quantity | value |
|---|---|
| tail multiplier D | 13.675 (union bound over 2048 coefficients at 2^-128.0 / N) |
| formal bound on v_inf | 6.3690e-06 |
| bound from MEASURED sigma | 5.9593e-06 |
| correctness threshold | 0.5 |
| headroom | 16.36 bits |
| minimum log2 q for 1 mult + relin | 29 |
| decryption failures observed | 0 of 128 |
| model agrees with measurement | yes |

> A passing empirical run over a few hundred trials cannot certify a 2^-128 failure probability directly — it bounds failure at roughly 2^-7.0. The tail claim rests on the Gaussian extrapolation from the MEASURED standard deviation, and the experiment's job is to validate that standard deviation, not the tail itself.

> The independence heuristic is an assumption, not a theorem. It treats coefficients of ring products as independent, which is false in detail. This model is only credible where the empirical distribution agrees with it.

Reproduce: `python -m trifhe_estimator.run_noise --m 4096 --log2-q 45 --trials 128 --quiet --json-out records/noise-m4096-q45.json`


### Noise: formal model vs measurement — Phi_8748, N = 2916, log2 q = 29.00
Ring `X^2916 - X^1458 + 1`, q = 536882257 (q mod m = 1), t = 3, sigma = 3.19, secret uniform ternary {-1,0,+1}, gadget base 32768 x 2 digits, BFV v1, evk encrypts B^i * s^2.
| stage | formal sigma_v | measured sigma_v | measured/formal | max v_inf observed |
|---|---|---|---|---|
| fresh ciphertext | 2^-19.78 | 2^-19.55 | 1.169 | 6.560e-06 (5.05 sigma) |
| after 1 mult + relin | 2^-5.28 | 2^-4.71 | 1.483 | 1.064e-01 (2.79 sigma) |

#### Variance decomposition after mult + relin
| term | share of variance |
|---|---|
| relinearisation digits * evk error | 99.9982% |
| v1 * m2 (fresh noise times plaintext) | 0.0009% |
| v2 * m1 (fresh noise times plaintext) | 0.0009% |
| scaling rounding r2 * s^2 | 0.0000% |
| scaling rounding r1 * s | 0.0000% |
| scaling rounding r0 | 0.0000% |
| v1 * v2 (product of noises) | 0.0000% |

Dominant term: **relinearisation digits * evk error**. The original draft's noise formula omitted this term entirely, which is why its modulus recommendation cannot be reproduced.

#### Correctness bound
| quantity | value |
|---|---|
| tail multiplier D | 13.700 (union bound over 2916 coefficients at 2^-128.0 / N) |
| formal bound on v_inf | 3.5284e-01 |
| bound from MEASURED sigma | 5.2310e-01 |
| correctness threshold | 0.5 |
| headroom | -0.07 bits |
| minimum log2 q for 1 mult + relin | 29 |
| decryption failures observed | 0 of 128 |
| model agrees with measurement | yes |

> A passing empirical run over a few hundred trials cannot certify a 2^-128 failure probability directly — it bounds failure at roughly 2^-7.0. The tail claim rests on the Gaussian extrapolation from the MEASURED standard deviation, and the experiment's job is to validate that standard deviation, not the tail itself.

> The independence heuristic is an assumption, not a theorem. It treats coefficients of ring products as independent, which is false in detail. This model is only credible where the empirical distribution agrees with it.

Reproduce: `python -m trifhe_estimator.run_noise --m 8748 --log2-q 29 --trials 128 --quiet --json-out records/noise-m8748-q29.json`


### Noise: formal model vs measurement — Phi_8748, N = 2916, log2 q = 45.00
Ring `X^2916 - X^1458 + 1`, q = 35184372141673 (q mod m = 1), t = 3, sigma = 3.19, secret uniform ternary {-1,0,+1}, gadget base 32768 x 4 digits, BFV v1, evk encrypts B^i * s^2.
| stage | formal sigma_v | measured sigma_v | measured/formal | max v_inf observed |
|---|---|---|---|---|
| fresh ciphertext | 2^-35.78 | 2^-35.54 | 1.178 | 8.731e-11 (4.37 sigma) |
| after 1 mult + relin | 2^-20.78 | 2^-20.40 | 1.304 | 2.145e-06 (2.96 sigma) |

#### Variance decomposition after mult + relin
| term | share of variance |
|---|---|
| relinearisation digits * evk error | 99.9991% |
| v1 * m2 (fresh noise times plaintext) | 0.0005% |
| v2 * m1 (fresh noise times plaintext) | 0.0005% |
| scaling rounding r2 * s^2 | 0.0000% |
| scaling rounding r1 * s | 0.0000% |
| scaling rounding r0 | 0.0000% |
| v1 * v2 (product of noises) | 0.0000% |

Dominant term: **relinearisation digits * evk error**. The original draft's noise formula omitted this term entirely, which is why its modulus recommendation cannot be reproduced.

#### Correctness bound
| quantity | value |
|---|---|
| tail multiplier D | 13.700 (union bound over 2916 coefficients at 2^-128.0 / N) |
| formal bound on v_inf | 7.6140e-06 |
| bound from MEASURED sigma | 9.9263e-06 |
| correctness threshold | 0.5 |
| headroom | 15.62 bits |
| minimum log2 q for 1 mult + relin | 29 |
| decryption failures observed | 0 of 128 |
| model agrees with measurement | yes |

> A passing empirical run over a few hundred trials cannot certify a 2^-128 failure probability directly — it bounds failure at roughly 2^-7.0. The tail claim rests on the Gaussian extrapolation from the MEASURED standard deviation, and the experiment's job is to validate that standard deviation, not the tail itself.

> The independence heuristic is an assumption, not a theorem. It treats coefficients of ring products as independent, which is false in detail. This model is only credible where the empirical distribution agrees with it.

Reproduce: `python -m trifhe_estimator.run_noise --m 8748 --log2-q 45 --trials 128 --quiet --json-out records/noise-m8748-q45.json`


### Noise: formal model vs measurement — Phi_8192, N = 4096, log2 q = 45.00
Ring `X^4096 + 1`, q = 35184372121601 (q mod m = 1), t = 3, sigma = 3.19, secret uniform ternary {-1,0,+1}, gadget base 32768 x 4 digits, BFV v1, evk encrypts B^i * s^2.
| stage | formal sigma_v | measured sigma_v | measured/formal | max v_inf observed |
|---|---|---|---|---|
| fresh ciphertext | 2^-35.53 | 2^-35.53 | 1.003 | 1.023e-10 (5.07 sigma) |
| after 1 mult + relin | 2^-20.53 | 2^-21.02 | 0.714 | 1.964e-06 (4.17 sigma) |

#### Variance decomposition after mult + relin
| term | share of variance |
|---|---|
| relinearisation digits * evk error | 99.9987% |
| v1 * m2 (fresh noise times plaintext) | 0.0006% |
| v2 * m1 (fresh noise times plaintext) | 0.0006% |
| scaling rounding r2 * s^2 | 0.0000% |
| scaling rounding r1 * s | 0.0000% |
| scaling rounding r0 | 0.0000% |
| v1 * v2 (product of noises) | 0.0000% |

Dominant term: **relinearisation digits * evk error**. The original draft's noise formula omitted this term entirely, which is why its modulus recommendation cannot be reproduced.

#### Correctness bound
| quantity | value |
|---|---|
| tail multiplier D | 13.725 (union bound over 4096 coefficients at 2^-128.0 / N) |
| formal bound on v_inf | 9.0403e-06 |
| bound from MEASURED sigma | 6.4560e-06 |
| correctness threshold | 0.5 |
| headroom | 16.24 bits |
| minimum log2 q for 1 mult + relin | 29 |
| decryption failures observed | 0 of 128 |
| model agrees with measurement | yes |

> A passing empirical run over a few hundred trials cannot certify a 2^-128 failure probability directly — it bounds failure at roughly 2^-7.0. The tail claim rests on the Gaussian extrapolation from the MEASURED standard deviation, and the experiment's job is to validate that standard deviation, not the tail itself.

> The independence heuristic is an assumption, not a theorem. It treats coefficients of ring products as independent, which is false in detail. This model is only credible where the empirical distribution agrees with it.

Reproduce: `python -m trifhe_estimator.run_noise --m 8192 --log2-q 45 --trials 128 --quiet --json-out records/noise-m8192-q45.json`


## Parameter sets in detail


### TriFHE-draft-N2187-q34993


### Parameter record
| field | value |
|---|---|
| tag | TriFHE-draft-N2187-q34993 |
| ring kind | negacyclic_pow3 |
| declared ring size | 2187 |
| lattice dimension n | **2187** |
| q | 34993 |
| log2 q | 15.0948 |
| secret distribution | dense_ternary |
| error sigma | 3.19 (ASSUMED, not specified by the spec) |
| samples m | +Infinity |
| estimator Xs | `D(σ=0.82, μ=0.00, n=2187)` |
| estimator Xe | `D(σ=3.19, μ=0.00)` |


### Structural findings
| severity | id | detail |
|---|---|---|
| BLOCKER | q-not-prime | q = 34993 is COMPOSITE: 34993 = 7 x 4999. Z_q is therefore not a field, it has zero divisors, and not every nonzero element is invertible. A single-modulus NTT over Z_q requires a primitive 2N-th root of unity in a field; a composite modulus needs an explicit CRT/RNS decomposition with each factor separately satisfying the root-of-unity condition, and the smallest factor here bounds what the scheme can actually represent. If the specification describes q as prime, that statement is false and the NTT correctness argument built on it does not hold. |
| BLOCKER | nwc-crt-fail | q = 34993 = 1 mod 2N (4374) holds for the PRODUCT, which looks like the right congruence, but q is composite so the product congruence is not what an NTT needs. A negative-wrapped convolution NTT requires a primitive 2N-th root of unity, which exists in Z_p only when p = 1 mod 2N; over a composite modulus each CRT component must satisfy this independently. Residues: 7 = 7 mod 4374, 4999 = 625 mod 4374. Component(s) [7, 4999] do NOT satisfy p = 1 mod 2N, so no primitive 2N-th root of unity exists in those components and the NWC NTT cannot be constructed as specified. The product congruence holding while no factor does is a classic false-positive on this check. |
| BLOCKER | ring-not-cyclotomic | x^2187 + 1 is not a cyclotomic polynomial. For odd d, x^d + 1 is divisible by (x + 1), so Z[x]/(x^2187 + 1) has zero divisors and is not a field extension. The 3-power cyclotomic of comparable size is Phi_2187, of degree phi(3^7) = 2*3^6 = 1458, not 2187. Any bit-security figure computed against this ring inherits the ring's unsoundness and must not be quoted as the scheme's security. |
| BLOCKER | noise-budget-thin | log2(q) = 15.1 against error stddev 3.19 leaves only ~13.4 bits of total noise headroom. That is far below what a single homomorphic multiplication plus relinearisation consumes in BGV/BFV-style schemes, so this instance is not a usable FHE parameter set regardless of how hard the lattice is. Smaller q makes the lattice HARDER and the scheme LESS useful; these two must be reported together. |
| info | keyspace-not-security | Raw secret keyspace is ~2^3466. This is NOT the security level and must never be quoted as one. The estimator output below is the security level. |


### Attack table (every attack, every cost model)
Security is the MINIMUM over all applicable attacks. Individual rows are not security levels; the minimum row is.

**Cost model: MATZOV** — 117.2s
| attack | log2 rop | beta | d | log2 m | zeta | eta | log2 red | log2 svp | log2 guess |
|---|---|---|---|---|---|---|---|---|---|
| **dual_hybrid** (min) | 499.0 | 1662 | - | 11.1 | 0 | - | 498.8 | - | 496.2 |
| bdd | 525.1 | 1754 | 3865 | - | - | 1796 | 523.5 | 524.5 | - |
| bdd_hybrid | 525.1 | 1754 | 3880 | - | 0 | 1796 | 523.5 | 524.5 | - |
| dual | 773.4 | 1751 | 3877 | 10.7 | - | - | - | - | - |
| bdd_mitm_hybrid | 823.6 | 1755 | 3124 | - | 770 | 2 | 713.3 | 823.6 | - |
| usvp | inf | - | - | - | - | - | - | - | - |

Minimum over attacks in this model: **499.0 bits** via `dual_hybrid`.

SATURATED: Optimal block size is within 10% of the estimator's max_beta bound (1754). Read the figure as a LOWER BOUND ('at least ~N bits'), not an exact level. Attacks that returned infinite cost were pruned by the same bound.

**Cost model: CoreSVP_classical** — 119.0s
| attack | log2 rop | beta | d | log2 m | zeta | eta | log2 red | log2 svp | log2 guess |
|---|---|---|---|---|---|---|---|---|---|
| **dual_hybrid** (min) | 484.5 | 1659 | - | 11.1 | 0 | - | 484.4 | - | 480.3 |
| bdd | 524.7 | 1754 | 3865 | - | - | 1796 | 512.2 | 524.7 | - |
| bdd_hybrid | 524.7 | 1754 | 3880 | - | 0 | 1796 | 512.2 | 524.7 | - |
| dual | 673.9 | 1751 | 3877 | 10.7 | - | - | - | - | - |
| bdd_mitm_hybrid | 823.6 | 1755 | 3124 | - | 770 | 2 | 702.6 | 823.6 | - |
| usvp | inf | - | - | - | - | - | - | - | - |

Minimum over attacks in this model: **484.5 bits** via `dual_hybrid`.

SATURATED: Optimal block size is within 10% of the estimator's max_beta bound (1754). Read the figure as a LOWER BOUND ('at least ~N bits'), not an exact level. Attacks that returned infinite cost were pruned by the same bound.

**Cost model: CoreSVP_quantum** — 112.3s
| attack | log2 rop | beta | d | log2 m | zeta | eta | log2 red | log2 svp | log2 guess |
|---|---|---|---|---|---|---|---|---|---|
| **dual_hybrid** (min) | 443.7 | 1673 | - | 11.1 | 20 | - | 443.3 | - | 441.5 |
| bdd | 476.2 | 1754 | 3865 | - | - | 1796 | 464.8 | 476.2 | - |
| bdd_hybrid | 476.2 | 1754 | 3880 | - | 0 | 1796 | 464.8 | 476.2 | - |
| dual | 626.7 | 1751 | 3877 | 10.7 | - | - | - | - | - |
| bdd_mitm_hybrid | 823.6 | 1755 | 3124 | - | 770 | 2 | 655.2 | 823.6 | - |
| usvp | inf | - | - | - | - | - | - | - | - |

Minimum over attacks in this model: **443.7 bits** via `dual_hybrid`.

SATURATED: Optimal block size is within 10% of the estimator's max_beta bound (1754). Read the figure as a LOWER BOUND ('at least ~N bits'), not an exact level. Attacks that returned infinite cost were pruned by the same bound.

**Cost model: CoreSVP_paranoid** — 111.5s
| attack | log2 rop | beta | d | log2 m | zeta | eta | log2 red | log2 svp | log2 guess |
|---|---|---|---|---|---|---|---|---|---|
| **dual_hybrid** (min) | 356.3 | 1715 | - | 11.1 | 0 | - | 355.9 | - | 354.5 |
| bdd | 372.9 | 1754 | 3865 | - | - | 1796 | 364.0 | 372.9 | - |
| bdd_hybrid | 372.9 | 1754 | 3880 | - | 0 | 1796 | 364.0 | 372.9 | - |
| dual | 527.0 | 1751 | 3877 | 10.7 | - | - | - | - | - |
| bdd_mitm_hybrid | 823.6 | 1755 | 3124 | - | 770 | 2 | 554.3 | 823.6 | - |
| usvp | inf | - | - | - | - | - | - | - | - |

Minimum over attacks in this model: **356.3 bits** via `dual_hybrid`.

SATURATED: Optimal block size is within 10% of the estimator's max_beta bound (1754). Read the figure as a LOWER BOUND ('at least ~N bits'), not an exact level. Attacks that returned infinite cost were pruned by the same bound.


### Provenance
| field | value |
|---|---|
| estimator commit | `53da5982597709ba0fdf94ea37a84d822310fd84` |
| estimator commit date | 2026-08-19T09:11:23+01:00 |
| estimator commit subject | not sure this *should* go here, but maybe it can |
| estimator branch | main |
| estimator working tree clean | yes |
| Sage version | 10.9 |
| Python version | 3.14.7 |
| platform | Linux-6.1.155+-x86_64-with-glibc2.43 |
| harness version | 1.0.0 |
| generated at (UTC) | 2026-08-27T13:08:13.429834+00:00 |


### TriFHE-cyclotomic-n1458-q34993


### Parameter record
| field | value |
|---|---|
| tag | TriFHE-cyclotomic-n1458-q34993 |
| ring kind | ternary_cyclotomic |
| declared ring size | 2187 |
| lattice dimension n | **1458** |
| q | 34993 |
| log2 q | 15.0948 |
| secret distribution | dense_ternary |
| error sigma | 3.19 (ASSUMED, not specified by the spec) |
| samples m | +Infinity |
| estimator Xs | `D(σ=0.82, μ=0.00, n=1458)` |
| estimator Xe | `D(σ=3.19, μ=0.00)` |


### Structural findings
| severity | id | detail |
|---|---|---|
| BLOCKER | q-not-prime | q = 34993 is COMPOSITE: 34993 = 7 x 4999. Z_q is therefore not a field, it has zero divisors, and not every nonzero element is invertible. A single-modulus NTT over Z_q requires a primitive 2N-th root of unity in a field; a composite modulus needs an explicit CRT/RNS decomposition with each factor separately satisfying the root-of-unity condition, and the smallest factor here bounds what the scheme can actually represent. If the specification describes q as prime, that statement is false and the NTT correctness argument built on it does not hold. |
| BLOCKER | nwc-crt-fail | q = 34993 = 1 mod 2N (4374) holds for the PRODUCT, which looks like the right congruence, but q is composite so the product congruence is not what an NTT needs. A negative-wrapped convolution NTT requires a primitive 2N-th root of unity, which exists in Z_p only when p = 1 mod 2N; over a composite modulus each CRT component must satisfy this independently. Residues: 7 = 7 mod 4374, 4999 = 625 mod 4374. Component(s) [7, 4999] do NOT satisfy p = 1 mod 2N, so no primitive 2N-th root of unity exists in those components and the NWC NTT cannot be constructed as specified. The product congruence holding while no factor does is a classic false-positive on this check. |
| BLOCKER | noise-budget-thin | log2(q) = 15.1 against error stddev 3.19 leaves only ~13.4 bits of total noise headroom. That is far below what a single homomorphic multiplication plus relinearisation consumes in BGV/BFV-style schemes, so this instance is not a usable FHE parameter set regardless of how hard the lattice is. Smaller q makes the lattice HARDER and the scheme LESS useful; these two must be reported together. |
| info | keyspace-not-security | Raw secret keyspace is ~2^2311. This is NOT the security level and must never be quoted as one. The estimator output below is the security level. |


### Attack table (every attack, every cost model)
Security is the MINIMUM over all applicable attacks. Individual rows are not security levels; the minimum row is.

**Cost model: MATZOV** — 78.2s
| attack | log2 rop | beta | d | log2 m | zeta | eta | log2 red | log2 svp | log2 guess |
|---|---|---|---|---|---|---|---|---|---|
| **dual_hybrid** (min) | 325.7 | 1048 | - | 10.5 | 0 | - | 325.6 | - | 321.2 |
| bdd | 339.7 | 1099 | 2598 | - | - | 1135 | 338.8 | 338.6 | - |
| bdd_hybrid | 339.7 | 1099 | 2643 | - | 0 | 1135 | 338.8 | 338.6 | - |
| usvp | 343.8 | 1117 | 2623 | - | - | - | 343.8 | - | - |
| dual | 359.4 | 1169 | 2706 | 10.3 | - | - | - | - | - |
| bdd_mitm_hybrid | 521.1 | 1117 | 2202 | - | 459 | 2 | 478.5 | 521.1 | - |

Minimum over attacks in this model: **325.7 bits** via `dual_hybrid`.

**Cost model: CoreSVP_classical** — 74.3s
| attack | log2 rop | beta | d | log2 m | zeta | eta | log2 red | log2 svp | log2 guess |
|---|---|---|---|---|---|---|---|---|---|
| **dual_hybrid** (min) | 306.9 | 1049 | - | 10.5 | 0 | - | 306.3 | - | 305.3 |
| usvp | 326.2 | 1117 | 2623 | - | - | - | 326.2 | - | - |
| bdd | 327.2 | 1117 | 2616 | - | - | 1116 | 326.2 | 326.2 | - |
| bdd_hybrid | 327.2 | 1117 | 2660 | - | 0 | 1116 | 326.2 | 326.2 | - |
| dual | 335.8 | 1150 | 2689 | 10.3 | - | - | - | - | - |
| bdd_mitm_hybrid | 521.1 | 1117 | 2202 | - | 459 | 2 | 461.3 | 521.1 | - |

Minimum over attacks in this model: **306.9 bits** via `dual_hybrid`.

**Cost model: CoreSVP_quantum** — 72.6s
| attack | log2 rop | beta | d | log2 m | zeta | eta | log2 red | log2 svp | log2 guess |
|---|---|---|---|---|---|---|---|---|---|
| **dual_hybrid** (min) | 280.6 | 1058 | - | 10.5 | 10 | - | 280.4 | - | 277.8 |
| usvp | 296.0 | 1117 | 2623 | - | - | - | 296.0 | - | - |
| bdd | 297.0 | 1117 | 2616 | - | - | 1116 | 296.0 | 296.0 | - |
| bdd_hybrid | 297.0 | 1117 | 2660 | - | 0 | 1116 | 296.0 | 296.0 | - |
| dual | 304.8 | 1150 | 2689 | 10.3 | - | - | - | - | - |
| bdd_mitm_hybrid | 521.1 | 1117 | 2202 | - | 459 | 2 | 431.2 | 521.1 | - |

Minimum over attacks in this model: **280.6 bits** via `dual_hybrid`.

**Cost model: CoreSVP_paranoid** — 71.0s
| attack | log2 rop | beta | d | log2 m | zeta | eta | log2 red | log2 svp | log2 guess |
|---|---|---|---|---|---|---|---|---|---|
| **dual_hybrid** (min) | 226.5 | 1086 | - | 10.5 | 0 | - | 225.3 | - | 225.7 |
| usvp | 231.8 | 1117 | 2623 | - | - | - | 231.8 | - | - |
| bdd | 232.8 | 1117 | 2616 | - | - | 1116 | 231.8 | 231.8 | - |
| bdd_hybrid | 232.8 | 1117 | 2660 | - | 0 | 1116 | 231.8 | 231.8 | - |
| dual | 239.2 | 1152 | 2691 | 10.3 | - | - | - | - | - |
| bdd_mitm_hybrid | 521.1 | 1117 | 2202 | - | 459 | 2 | 366.9 | 521.1 | - |

Minimum over attacks in this model: **226.5 bits** via `dual_hybrid`.


### Provenance
| field | value |
|---|---|
| estimator commit | `53da5982597709ba0fdf94ea37a84d822310fd84` |
| estimator commit date | 2026-08-19T09:11:23+01:00 |
| estimator commit subject | not sure this *should* go here, but maybe it can |
| estimator branch | main |
| estimator working tree clean | yes |
| Sage version | 10.9 |
| Python version | 3.14.7 |
| platform | Linux-6.1.155+-x86_64-with-glibc2.43 |
| harness version | 1.0.0 |
| generated at (UTC) | 2026-08-27T13:13:11.511824+00:00 |


### Attacks NOT covered by the estimator
Every figure above is a minimum over the attacks the estimator implements. It is **not** a bound over all known attacks. These are excluded and must be costed separately before any figure is quoted as a security level.
| attack | why it is not covered | reference |
|---|---|---|
| Meet-LWE (May, CRYPTO 2021) | Representation-technique MitM against small/sparse secrets. Not implemented in the estimator; must be costed separately for ternary secrets. | <https://eprint.iacr.org/2021/216> |
| Cool and Cruel / statistical dual | Exploits the uneven contribution of secret coordinates. Reported to beat estimator dual costs for sparse and small secrets. | <https://arxiv.org/abs/2403.10328> |
| Subfield / Gentry-Szydlo-style structural attacks | Applies when the ring has exploitable subfields or the modulus splits badly. Entirely outside the estimator's plain-LWE model. | <https://eprint.iacr.org/2015/106> |
| IND-CPA^D / decryption-failure attacks | Approximate-FHE key recovery from decryption results. Orthogonal to lattice hardness; a scheme can be 128-bit hard and still fully broken here. | <https://eprint.iacr.org/2020/1533> |


## What this worksheet does not claim

- It does not claim any parameter set meets a 128-bit target. It reports minimum estimator costs and names what is excluded.
- It does not claim the nonstandard ternary-aligned ring is as well understood as a power-of-two cyclotomic. Costing RLWE in a bespoke ring as plain LWE of dimension phi(m) is standard practice but is not a reduction; subfield and structural screening remains open.
- It does not claim a 2^-128 decryption failure probability has been measured. A few hundred trials bound failure near 2^-8, not 2^-128. The tail figure is a Gaussian extrapolation from a MEASURED standard deviation, and the experiment validates that standard deviation only.
- It does not treat key space size as a security level.
