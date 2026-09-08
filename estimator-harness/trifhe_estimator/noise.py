# -*- coding: utf-8 -*-
"""
Formal invariant-noise tail model for BFV, and the empirical experiment that
checks it.

WHY BOTH
--------
The original TriFHE proposal certified "1 mult + relin" from a three-line
closed-form expression. That expression omitted the gadget base, the digit
count, the plaintext second moment, the scaling rounding, and any tail bound —
and at realistic parameters the omitted relinearisation term is the *dominant*
one. A formula whose largest term is missing is not a correctness argument.

So this module does two independent things and reports them side by side:

  1. `formal_model` — coefficient-wise variance propagation under the standard
     independence heuristic, term by term, each term labelled with what it comes
     from, plus an explicit Gaussian tail bound union-bounded over all N
     coefficients at a stated failure probability.

  2. `run_experiment` — the same circuit executed for real, many times, in the
     actual ring, measuring the actual invariant noise.

Agreement between them is evidence. Either one alone is not. The independence
heuristic is a heuristic: it is standard practice and it is also the assumption
most likely to be wrong in a ring nobody has stress-tested, which is exactly why
the empirical run exists.

DEFINITIONS
-----------
Invariant noise v is defined by (t/q)*(c0 + c1*s + ...) = m + v + t*I over the
rationals. Decryption of a fresh or evaluated ciphertext is correct iff
||v||_inf < 1/2. Everything below is stated in those terms.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .bfv import BFV, BFVParams

# Second moments of the distributions involved, per coefficient.
VAR_TERNARY = 2.0 / 3.0          # uniform on {-1,0,+1}
E2_PLAINTEXT_T3 = 5.0 / 3.0      # uniform on {0,1,2}: (0+1+4)/3
VAR_ROUNDING = 1.0 / 12.0        # uniform on [-1/2, 1/2]


def tail_multiplier(n_coeffs: int, log2_failure: float = -128.0) -> float:
    """D such that P[|X| > D*sigma] <= 2^log2_failure for a Gaussian X, after a
    union bound over `n_coeffs` coefficients.

    Solved by bisection on erfc so no scipy dependency is introduced.
    """
    target = (2.0 ** log2_failure) / n_coeffs
    lo, hi = 0.0, 60.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if math.erfc(mid / math.sqrt(2.0)) > target:
            lo = mid
        else:
            hi = mid
    return hi


@dataclass
class NoiseModel:
    """Predicted invariant-noise standard deviation, decomposed by source."""

    N: int
    q: int
    t: int
    sigma: float
    gadget_base: int
    gadget_digits: int
    terms_fresh: dict
    terms_mult: dict
    log2_failure: float

    @property
    def scale(self) -> float:
        return self.t / self.q

    @property
    def var_fresh(self) -> float:
        return sum(self.terms_fresh.values())

    @property
    def var_mult(self) -> float:
        return sum(self.terms_mult.values())

    @property
    def sigma_fresh(self) -> float:
        return self.scale * math.sqrt(self.var_fresh)

    @property
    def sigma_mult(self) -> float:
        return self.scale * math.sqrt(self.var_mult)

    @property
    def D(self) -> float:
        return tail_multiplier(self.N, self.log2_failure)

    def to_dict(self) -> dict:
        D = self.D
        bound = D * self.sigma_mult
        dominant = max(self.terms_mult, key=self.terms_mult.get)
        return dict(
            model="coefficient-wise variance propagation under the independence heuristic",
            caveat=(
                "The independence heuristic is an assumption, not a theorem. It treats "
                "coefficients of ring products as independent, which is false in detail. "
                "This model is only credible where the empirical distribution agrees with it."
            ),
            tail=dict(
                per_coefficient_failure_target=f"2^{self.log2_failure} / N",
                union_bounded_over_coefficients=self.N,
                gaussian_tail_multiplier_D=round(D, 4),
            ),
            fresh=dict(
                variance_terms={k: float(v) for k, v in self.terms_fresh.items()},
                sigma_v=self.sigma_fresh,
                log2_sigma_v=math.log2(self.sigma_fresh) if self.sigma_fresh else None,
            ),
            after_mult_relin=dict(
                variance_terms={k: float(v) for k, v in self.terms_mult.items()},
                dominant_term=dominant,
                dominant_share=self.terms_mult[dominant] / self.var_mult,
                sigma_v=self.sigma_mult,
                log2_sigma_v=math.log2(self.sigma_mult) if self.sigma_mult else None,
                predicted_tail_bound_on_v_inf=bound,
                decryption_correctness_threshold=0.5,
                predicted_correct=bool(bound < 0.5),
                headroom_bits=(math.log2(0.5 / bound) if bound > 0 else None),
            ),
        )


def formal_model(p: BFVParams, log2_failure: float = -128.0) -> NoiseModel:
    """Variance of the invariant noise, term by term.

    FRESH CIPHERTEXT
        c0 + c1*s = Delta*m + (e1 + e2*s - u*e), so
        v_fresh = (t/q) * (e1 + e2*s - u*e).

    AFTER ONE MULTIPLICATION AND RELINEARISATION
        v = v1*m2 + v2*m1 + v1*v2 + v_scale + v_relin.
        The v1*v2 term is negligible at any usable parameter set and is
        included for completeness. v_scale comes from rounding the t/q scaling
        of the three tensor components. v_relin comes from the gadget digits
        multiplying the evaluation-key errors and is usually DOMINANT — the
        term the original proposal omitted entirely.
    """
    N, q, t, s = p.N, p.q, p.t, p.sigma
    B, ell = 2 ** p.gadget_base_bits, p.ell

    terms_fresh = {
        "e1 (encryption error)": s * s,
        "e2 * s (encryption error times secret)": N * s * s * VAR_TERNARY,
        "u * e (ephemeral times public-key error)": N * s * s * VAR_TERNARY,
    }
    var_fresh = sum(terms_fresh.values())

    terms_mult = {
        "v1 * m2 (fresh noise times plaintext)": N * var_fresh * E2_PLAINTEXT_T3,
        "v2 * m1 (fresh noise times plaintext)": N * var_fresh * E2_PLAINTEXT_T3,
        # v1*v2 is scaled by (t/q) once more than everything else, so express it
        # in the same units by folding the extra factor in explicitly.
        "v1 * v2 (product of noises)": N * (var_fresh ** 2) * (t / q) ** 2,
        "scaling rounding r0": VAR_ROUNDING,
        "scaling rounding r1 * s": N * VAR_ROUNDING * VAR_TERNARY,
        "scaling rounding r2 * s^2": N * VAR_ROUNDING * (N * VAR_TERNARY ** 2),
        "relinearisation digits * evk error": ell * N * (B * B / 3.0) * s * s,
    }

    return NoiseModel(
        N=N, q=q, t=t, sigma=s, gadget_base=B, gadget_digits=ell,
        terms_fresh=terms_fresh, terms_mult=terms_mult, log2_failure=log2_failure,
    )


def min_log2_q_for_one_mult(m: int, t: int = 3, sigma: float = 3.19,
                            gadget_base_bits: int = 15,
                            log2_failure: float = -128.0,
                            lo: int = 25, hi: int = 49) -> int | None:
    """Smallest integer log2(q) in [lo, hi] whose formal tail bound clears the
    0.5 correctness threshold for 1 mult + relin. None if none does.

    This is the honest replacement for the proposal's `compute_noise_bound`: it
    includes the relinearisation term, uses a stated tail probability rather
    than a bare factor of 2, and is checked against measurement.
    """
    for k in range(lo, hi + 1):
        p = BFVParams(m=m, log2_q=k, t=t, sigma=sigma, gadget_base_bits=gadget_base_bits)
        if formal_model(p, log2_failure).to_dict()["after_mult_relin"]["predicted_correct"]:
            return k
    return None


# ------------------------------------------------------------- experiment


def run_experiment(p: BFVParams, trials: int, seed: int = 0,
                   log2_failure: float = -128.0, progress=None) -> dict:
    """Execute the 1 mult + relin circuit `trials` times and measure v.

    Every trial uses fresh randomness for messages, ephemeral values and all
    errors, under a fixed key. Returns the empirical distribution alongside the
    formal prediction so the two can be compared directly.
    """
    scheme = BFV(p)
    rng = np.random.default_rng(seed + 991)

    fresh_max, fresh_sq = [], 0.0
    mult_max, mult_sq = [], 0.0
    n_obs = 0
    dec_fail_fresh = dec_fail_mult = 0

    for i in range(trials):
        m1 = rng.integers(0, p.t, p.N)
        m2 = rng.integers(0, p.t, p.N)
        ct1, ct2 = scheme.encrypt(m1), scheme.encrypt(m2)

        v1 = scheme.invariant_noise(ct1, m1)
        fresh_max.append(float(np.abs(v1).max()))
        fresh_sq += float(np.sum(v1 * v1))

        ct = scheme.multiply(ct1, ct2)
        expected = scheme.plaintext_mul(m1, m2)
        v = scheme.invariant_noise(ct, expected)
        mult_max.append(float(np.abs(v).max()))
        mult_sq += float(np.sum(v * v))
        n_obs += p.N

        if not np.array_equal(scheme.decrypt(ct1), np.mod(m1, p.t)):
            dec_fail_fresh += 1
        if not np.array_equal(scheme.decrypt(ct), expected):
            dec_fail_mult += 1

        if progress:
            progress(i + 1, trials)

    model = formal_model(p, log2_failure)
    md = model.to_dict()

    emp_sigma_fresh = math.sqrt(fresh_sq / n_obs)
    emp_sigma_mult = math.sqrt(mult_sq / n_obs)

    def stats(maxes, emp_sigma, predicted_sigma):
        arr = np.array(maxes)
        return dict(
            trials=len(maxes),
            coefficients_observed=n_obs,
            empirical_sigma_v=emp_sigma,
            log2_empirical_sigma_v=math.log2(emp_sigma) if emp_sigma > 0 else None,
            predicted_sigma_v=predicted_sigma,
            ratio_empirical_over_predicted=(
                emp_sigma / predicted_sigma if predicted_sigma > 0 else None
            ),
            observed_max_v_inf=float(arr.max()),
            observed_mean_max_v_inf=float(arr.mean()),
            observed_max_over_sigma=(float(arr.max()) / emp_sigma if emp_sigma > 0 else None),
        )

    fresh_stats = stats(fresh_max, emp_sigma_fresh, model.sigma_fresh)
    mult_stats = stats(mult_max, emp_sigma_mult, model.sigma_mult)

    # The extrapolated bound uses the MEASURED sigma with the SAME tail
    # multiplier, so a model that underestimates sigma cannot hide behind it.
    D = model.D
    extrapolated = D * emp_sigma_mult

    return dict(
        params=p.to_dict(),
        formal_model=md,
        empirical=dict(fresh=fresh_stats, after_mult_relin=mult_stats),
        decryption=dict(
            fresh_failures=dec_fail_fresh,
            after_mult_relin_failures=dec_fail_mult,
            trials=trials,
        ),
        verdict=dict(
            model_agrees_with_measurement=bool(
                0.5 <= mult_stats["ratio_empirical_over_predicted"] <= 2.0
            ),
            empirical_tail_bound_on_v_inf=extrapolated,
            empirical_predicted_correct=bool(extrapolated < 0.5),
            headroom_bits=(math.log2(0.5 / extrapolated) if extrapolated > 0 else None),
            note=(
                "A passing empirical run over a few hundred trials cannot certify a "
                f"2^{log2_failure:.0f} failure probability directly — it bounds failure at "
                f"roughly 2^-{math.log2(max(trials,1)):.1f}. The tail claim rests on the "
                "Gaussian extrapolation from the MEASURED standard deviation, and the "
                "experiment's job is to validate that standard deviation, not the tail itself."
            ),
        ),
    )
