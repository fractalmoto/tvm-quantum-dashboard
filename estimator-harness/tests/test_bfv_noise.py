# -*- coding: utf-8 -*-
"""
Correctness tests for the BFV reference implementation and the noise model.

These run at small conductors so the suite stays fast, but every conductor used
here has the same shape as the parameter sets under study: a mixed 2^a 3^b
conductor whose cyclotomic is a signed trinomial, a pure 3-power conductor, and
a power-of-two conductor. A bug that only shows up in one of those three shapes
therefore cannot hide.

The point of the exact-product tests is that they do not trust the transform:
they compare against schoolbook reduction modulo the exact cyclotomic. Every
noise figure in the worksheet depends on the arithmetic underneath being right,
so the arithmetic is checked independently of the noise.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from trifhe_estimator.bfv import BFV, BFVParams, ExactProduct, round_div, centre
from trifhe_estimator.noise import (
    formal_model,
    min_log2_q_for_one_mult,
    run_experiment,
    tail_multiplier,
)
from trifhe_estimator.rings import CyclotomicRing

# (conductor, degree). 324 = 2^2*3^4 -> trinomial; 243 = 3^5 -> pure 3-power;
# 256 = 2^8 -> power of two.
SMALL_RINGS = [(324, 108), (243, 162), (256, 128)]


# ------------------------------------------------------------- helpers


def test_round_div_is_round_half_away_from_zero():
    assert round_div(5, 2) == 3
    assert round_div(-5, 2) == -3
    assert round_div(4, 2) == 2
    assert round_div(-4, 2) == -2
    assert round_div(1, 3) == 0
    assert round_div(-1, 3) == 0
    assert round_div(2, 3) == 1
    assert round_div(-2, 3) == -1


def test_round_div_matches_exact_rational_rounding():
    # Against Fraction-based rounding, over a range including both signs.
    from fractions import Fraction

    for a in range(-40, 41):
        for b in (3, 7, 11):
            expect = math.floor(Fraction(a, b) + Fraction(1, 2)) if a >= 0 else \
                -math.floor(Fraction(-a, b) + Fraction(1, 2))
            assert round_div(a, b) == expect, (a, b)


def test_centre_maps_into_symmetric_range():
    q = 97
    for x in range(q):
        c = centre(np.array([x]), q)[0]
        assert -q // 2 <= c <= q // 2
        assert (c - x) % q == 0


# ------------------------------------------------------------- exact products


@pytest.mark.parametrize("m,degree", SMALL_RINGS)
def test_exact_product_matches_schoolbook_over_integers(m, degree):
    """The CRT exact-product path must reproduce integer polynomial products
    reduced modulo Phi_m exactly, with no modular wraparound anywhere."""
    ring = CyclotomicRing(m)
    assert ring.degree == degree
    rng = np.random.default_rng(11)
    # bound_log2 must cover the largest product coefficient: |a|,|b| < 2^20 and
    # the convolution sums N terms, so 20 + 20 + log2(N) is ample.
    ep = ExactProduct(m, 20 + 20 + math.log2(degree))
    for _ in range(3):
        a = rng.integers(-10**6, 10**6, degree).astype(object)
        b = rng.integers(-10**6, 10**6, degree).astype(object)
        got = ep.mul(a, b)
        want = ring.reduce(ring.mul_schoolbook(list(a), list(b)))
        want = np.array(want + [0] * (degree - len(want)), dtype=object)[:degree]
        assert list(got) == list(want)


def test_exact_product_reconstruction_bound_is_enforced():
    """The CRT modulus must exceed the largest possible product coefficient. If
    it does not, the class must raise rather than return a wrapped value."""
    ring = CyclotomicRing(324)
    ep = ExactProduct(324, 40.0)
    huge = np.full(ring.degree, 2 ** 200, dtype=object)
    with pytest.raises((AssertionError, ValueError)):
        ep.mul(huge, huge)


# ------------------------------------------------------------- BFV correctness


@pytest.mark.parametrize("m,degree", SMALL_RINGS)
def test_encrypt_decrypt_roundtrip(m, degree):
    p = BFVParams(m=m, log2_q=40, seed=3)
    scheme = BFV(p)
    rng = np.random.default_rng(4)
    for _ in range(5):
        msg = rng.integers(0, p.t, p.N)
        assert np.array_equal(scheme.decrypt(scheme.encrypt(msg)), msg)


@pytest.mark.parametrize("m,degree", SMALL_RINGS)
def test_homomorphic_addition(m, degree):
    p = BFVParams(m=m, log2_q=40, seed=3)
    scheme = BFV(p)
    rng = np.random.default_rng(5)
    for _ in range(5):
        m1, m2 = rng.integers(0, p.t, p.N), rng.integers(0, p.t, p.N)
        ct = scheme.add(scheme.encrypt(m1), scheme.encrypt(m2))
        assert np.array_equal(scheme.decrypt(ct), np.mod(m1 + m2, p.t))


@pytest.mark.parametrize("m,degree", SMALL_RINGS)
def test_multiplication_with_relinearisation(m, degree):
    """The load-bearing test: one multiplication plus relinearisation must
    decrypt to the ring product of the plaintexts, in every ring shape."""
    p = BFVParams(m=m, log2_q=40, seed=3)
    scheme = BFV(p)
    rng = np.random.default_rng(6)
    for _ in range(5):
        m1, m2 = rng.integers(0, p.t, p.N), rng.integers(0, p.t, p.N)
        ct = scheme.multiply(scheme.encrypt(m1), scheme.encrypt(m2))
        assert np.array_equal(scheme.decrypt(ct), scheme.plaintext_mul(m1, m2))
        assert len(ct) == 2, "relinearisation must return a 2-component ciphertext"


@pytest.mark.parametrize("m,degree", SMALL_RINGS)
def test_multiplication_without_relinearisation_also_decrypts(m, degree):
    """Isolates relinearisation from the tensoring-and-scaling step: if this
    passes and the relinearised version fails, the fault is in relinearisation."""
    p = BFVParams(m=m, log2_q=40, seed=3)
    scheme = BFV(p)
    rng = np.random.default_rng(7)
    m1, m2 = rng.integers(0, p.t, p.N), rng.integers(0, p.t, p.N)
    ct3 = scheme.multiply_no_relin(scheme.encrypt(m1), scheme.encrypt(m2))
    assert len(ct3) == 3
    # decrypt/phase handle any component count, so the 3-component ciphertext is
    # decrypted directly under s and s^2 with no relinearisation involved.
    assert np.array_equal(scheme.decrypt(ct3), scheme.plaintext_mul(m1, m2))


def test_relinearisation_preserves_the_plaintext_it_is_applied_to():
    p = BFVParams(m=324, log2_q=40, seed=3)
    scheme = BFV(p)
    rng = np.random.default_rng(8)
    m1, m2 = rng.integers(0, p.t, p.N), rng.integers(0, p.t, p.N)
    ct3 = scheme.multiply_no_relin(scheme.encrypt(m1), scheme.encrypt(m2))
    ct2 = scheme.relinearise(*ct3)
    assert np.array_equal(scheme.decrypt(ct2), scheme.decrypt(ct3))


def test_invariant_noise_is_small_for_a_fresh_ciphertext():
    """Fresh invariant noise must be far below the 1/2 correctness threshold,
    and must be measured relative to the CORRECT plaintext -- passing the wrong
    plaintext must produce a large value, which is what makes the metric
    meaningful."""
    p = BFVParams(m=324, log2_q=40, seed=3)
    scheme = BFV(p)
    rng = np.random.default_rng(9)
    msg = rng.integers(0, p.t, p.N)
    ct = scheme.encrypt(msg)
    assert np.abs(scheme.invariant_noise(ct, msg)).max() < 1e-6
    wrong = np.mod(msg + 1, p.t)
    assert np.abs(scheme.invariant_noise(ct, wrong)).max() > 0.1


def test_decryption_fails_when_the_modulus_is_too_small():
    """A negative control. If the noise budget is exhausted, decryption after a
    multiplication must actually break -- otherwise the correctness tests are
    passing for reasons unrelated to the noise budget."""
    p = BFVParams(m=324, log2_q=20, seed=3, gadget_base_bits=15)
    scheme = BFV(p)
    rng = np.random.default_rng(10)
    failures = 0
    for _ in range(5):
        m1, m2 = rng.integers(0, p.t, p.N), rng.integers(0, p.t, p.N)
        ct = scheme.multiply(scheme.encrypt(m1), scheme.encrypt(m2))
        if not np.array_equal(scheme.decrypt(ct), scheme.plaintext_mul(m1, m2)):
            failures += 1
    assert failures > 0, "expected decryption failure at an exhausted noise budget"


# ------------------------------------------------------------- noise model


def test_tail_multiplier_hits_its_target_probability():
    for n in (1, 2048, 2916):
        D = tail_multiplier(n, -128.0)
        assert math.erfc(D / math.sqrt(2.0)) <= (2.0 ** -128) / n
        # And is not wastefully loose: one notch smaller must violate the target.
        assert math.erfc((D - 0.05) / math.sqrt(2.0)) > (2.0 ** -128) / n


def test_tail_multiplier_grows_with_stricter_failure_target():
    assert tail_multiplier(2916, -256.0) > tail_multiplier(2916, -128.0)


def test_relinearisation_term_dominates_at_a_large_gadget_base():
    """Documents the substantive finding: with a 2^15 gadget base the
    relinearisation term is not a correction, it is essentially the whole
    variance. Any noise formula that omits it -- as the original draft's did --
    cannot produce a defensible modulus recommendation."""
    d = formal_model(BFVParams(m=8748, log2_q=45)).to_dict()["after_mult_relin"]
    assert d["dominant_term"] == "relinearisation digits * evk error"
    assert d["dominant_share"] > 0.99


def test_smaller_gadget_base_reduces_the_required_modulus():
    """A direct consequence: the gadget base is a lever on the noise budget, so
    a modulus recommendation that does not state its gadget base is incomplete."""
    big = min_log2_q_for_one_mult(8748, gadget_base_bits=15)
    small = min_log2_q_for_one_mult(8748, gadget_base_bits=8)
    assert small is not None and big is not None
    assert small < big


def test_formal_model_predicts_failure_below_its_own_minimum_modulus():
    """Self-consistency: the reported minimum log2 q must be a real threshold,
    not a value the model would also accept one bit lower."""
    m = 8748
    k = min_log2_q_for_one_mult(m)
    assert k is not None
    above = formal_model(BFVParams(m=m, log2_q=k)).to_dict()
    below = formal_model(BFVParams(m=m, log2_q=k - 1)).to_dict()
    assert above["after_mult_relin"]["predicted_correct"]
    assert not below["after_mult_relin"]["predicted_correct"]


def test_noise_sigma_scales_inversely_with_q():
    """Invariant noise carries a t/q factor, so doubling q must halve sigma_v.
    A model that failed this would be dimensionally wrong."""
    a = formal_model(BFVParams(m=324, log2_q=40)).sigma_mult
    b = formal_model(BFVParams(m=324, log2_q=41)).sigma_mult
    assert 0.45 < b / a < 0.55


@pytest.mark.parametrize("m", [324, 243, 256])
def test_experiment_agrees_with_the_formal_model(m):
    """The end-to-end check: measured sigma_v must land within a factor of two
    of the predicted sigma_v, in every ring shape, with no decryption failures."""
    p = BFVParams(m=m, log2_q=42, seed=1)
    rec = run_experiment(p, trials=12, seed=2)
    assert rec["decryption"]["fresh_failures"] == 0
    assert rec["decryption"]["after_mult_relin_failures"] == 0
    for key in ("fresh", "after_mult_relin"):
        ratio = rec["empirical"][key]["ratio_empirical_over_predicted"]
        assert 0.5 <= ratio <= 2.0, (m, key, ratio)
    assert rec["verdict"]["model_agrees_with_measurement"]
