# -*- coding: utf-8 -*-
"""
Step 1 of the TriFHE parameter programme: exact ring arithmetic and transform
correctness.

These tests are the gate. No noise measurement and no security estimate for a
non-power-of-two ring means anything until every test in this file passes,
because all of them would still pass on a ring whose multiplication is subtly
wrong — and then every downstream number would be wrong in a way no estimator
can detect.

Run:  python -m pytest tests/ -q
"""

from __future__ import annotations

import random

import numpy as np
import pytest

from trifhe_estimator.rings import (
    CyclotomicRing,
    cyclotomic_closed_form,
    cyclotomic_generic,
    euler_phi,
    factor_2a3b,
    find_transform_prime,
    poly_divmod,
    poly_mul,
)
from trifhe_estimator.transform import (
    CyclicNTT,
    RingMultiplier,
    mulmod,
    primitive_root_of_unity,
    transform_length,
)

# Conductors small enough for the generic O(m^2) cyclotomic recursion.
SMALL_CONDUCTORS = [
    2**a * 3**b
    for a in range(0, 8)
    for b in range(0, 6)
    if 3 <= 2**a * 3**b <= 250
]

# The rings that actually matter, at full size.
CANDIDATE_CONDUCTORS = [
    8748,   # 2^2 * 3^7 -> N = 2916. The leading experimental ternary candidate.
    5832,   # 2^3 * 3^6 -> N = 1944.
    2187,   # 3^7       -> N = 1458. Pure 3-power; needs L = 3m.
    4096,   # 2^12      -> N = 2048. Power-of-two baseline.
    8192,   # 2^13      -> N = 4096. Power-of-two baseline.
]

# Small rings used wherever the schoolbook reference must run many times.
SMALL_RINGS = [36, 54, 108, 162, 324, 486]


# ------------------------------------------------------------ conductor model


@pytest.mark.parametrize("m", SMALL_CONDUCTORS)
def test_closed_form_matches_generic_cyclotomic(m):
    """The closed-form identities are the ones the original proposal got wrong.

    Phi_{3^b} has PLUS signs; the signed trinomial belongs to the mixed cases.
    This test is what makes that a fact rather than an assertion.
    """
    assert cyclotomic_closed_form(m) == cyclotomic_generic(m)


@pytest.mark.parametrize("m", SMALL_CONDUCTORS + CANDIDATE_CONDUCTORS)
def test_degree_is_euler_phi(m):
    assert len(cyclotomic_closed_form(m)) - 1 == euler_phi(m)
    assert CyclotomicRing(m).degree == euler_phi(m)


@pytest.mark.parametrize("m", SMALL_CONDUCTORS + CANDIDATE_CONDUCTORS)
def test_phi_m_divides_x_m_minus_one(m):
    """Phi_m | X^m - 1 is the defining property. If it fails, the ring is not
    the ring we think it is and the whole transform argument collapses."""
    phi = cyclotomic_closed_form(m)
    num = [-1] + [0] * (m - 1) + [1]
    _, rem = poly_divmod(num, phi)
    assert rem == [0]


@pytest.mark.parametrize("m", SMALL_CONDUCTORS + CANDIDATE_CONDUCTORS)
def test_phi_m_is_monic_and_sparse(m):
    phi = cyclotomic_closed_form(m)
    assert phi[-1] == 1
    assert sum(1 for c in phi if c) <= 3
    assert all(c in (-1, 0, 1) for c in phi)


def test_the_headline_candidate_polynomial():
    """m = 8748 is the candidate this programme is built around. Pin it."""
    r = CyclotomicRing(8748)
    assert factor_2a3b(8748) == (2, 7)
    assert r.degree == 2916
    assert r.phi_str == "X^2916 - X^1458 + 1"
    phi = r.phi
    assert phi[0] == 1 and phi[1458] == -1 and phi[2916] == 1
    assert sum(1 for c in phi if c) == 3


def test_pure_three_power_signs_are_positive():
    """Phi_2187 = X^1458 + X^729 + 1, NOT X^1458 - X^729 + 1."""
    assert CyclotomicRing(2187).phi_str == "X^1458 + X^729 + 1"
    assert CyclotomicRing(6561).phi_str == "X^4374 + X^2187 + 1"


def test_non_smooth_conductor_rejected():
    with pytest.raises(ValueError):
        euler_phi(5 * 27)


# --------------------------------------------------------- modular arithmetic


def test_mulmod_exact_against_python_ints():
    """A silent failure here corrupts every downstream number."""
    rng = random.Random(0)
    for bits in (20, 30, 40, 45, 49):
        q = find_transform_prime(2, bits, 1)[0]
        a = np.array([rng.randrange(q) for _ in range(4000)], dtype=np.int64)
        b = np.array([rng.randrange(q) for _ in range(4000)], dtype=np.int64)
        got = mulmod(a, b, q)
        want = [(int(x) * int(y)) % q for x, y in zip(a, b)]
        assert list(map(int, got)) == want, f"mulmod wrong at {bits} bits"


def test_mulmod_edge_values():
    q = find_transform_prime(2, 45, 1)[0]
    edges = np.array([0, 1, 2, q - 1, q - 2, q // 2], dtype=np.int64)
    a, b = np.meshgrid(edges, edges)
    got = mulmod(a.ravel(), b.ravel(), q)
    want = [(int(x) * int(y)) % q for x, y in zip(a.ravel(), b.ravel())]
    assert list(map(int, got)) == want


@pytest.mark.parametrize("L", [12, 36, 108, 324, 4096, 8748])
def test_root_of_unity_has_exact_order(L):
    q = find_transform_prime(L, 30, 1)[0]
    w = primitive_root_of_unity(L, q)
    assert pow(w, L, q) == 1
    for p in (2, 3):
        if L % p == 0:
            assert pow(w, L // p, q) != 1


def test_root_of_unity_refused_when_congruence_fails():
    """q = 1 mod 2N holding while q = 1 mod m fails is exactly the TRI-213
    false-positive shape. The transform layer must refuse, not proceed."""
    with pytest.raises(ValueError):
        primitive_root_of_unity(8748, 12289)


# ----------------------------------------------------------- transform layer


@pytest.mark.parametrize("L", [12, 18, 36, 108, 324, 972])
def test_ntt_roundtrip(L):
    q = find_transform_prime(L, 40, 1)[0]
    ntt = CyclicNTT(L, q)
    rng = random.Random(L)
    x = np.array([rng.randrange(q) for _ in range(L)], dtype=np.int64)
    assert list(map(int, ntt.inverse(ntt.forward(x)))) == list(map(int, x))


@pytest.mark.parametrize("L", [36, 108, 324])
def test_ntt_matches_naive_dft(L):
    """The transform is a DFT over Z_q, checked against the O(L^2) definition."""
    q = find_transform_prime(L, 30, 1)[0]
    ntt = CyclicNTT(L, q)
    w = ntt.w
    rng = random.Random(1)
    x = [rng.randrange(q) for _ in range(L)]
    got = list(map(int, ntt.forward(np.array(x, dtype=np.int64))))
    want = [sum(x[i] * pow(w, i * k, q) for i in range(L)) % q for k in range(L)]
    assert got == want


@pytest.mark.parametrize("L", [36, 108, 324])
def test_ntt_is_cyclic_convolution(L):
    """Pointwise product in the transform domain must be cyclic convolution."""
    q = find_transform_prime(L, 40, 1)[0]
    ntt = CyclicNTT(L, q)
    rng = random.Random(2)
    a = [rng.randrange(q) for _ in range(L)]
    b = [rng.randrange(q) for _ in range(L)]
    got = list(map(int, ntt.inverse(mulmod(ntt.forward(np.array(a)), ntt.forward(np.array(b)), q))))
    want = [sum(a[i] * b[(k - i) % L] for i in range(L)) % q for k in range(L)]
    assert got == want


def test_transform_length_is_wraparound_safe():
    """L >= 2N - 1 is the no-wraparound condition. A pure 3-power conductor
    fails it at L = m and must be enlarged, which is easy to get wrong."""
    for m in CANDIDATE_CONDUCTORS:
        N = euler_phi(m)
        L = transform_length(m, N)
        assert L >= 2 * N - 1, f"m={m} transform length {L} wraps"
        assert L % m == 0
    assert transform_length(8748, 2916) == 8748     # a >= 1: L = m suffices
    assert transform_length(2187, 1458) == 6561     # pure 3-power needs 3m


# ------------------------------------------------- ring multiplication itself


@pytest.mark.parametrize("m", SMALL_RINGS)
def test_transform_mul_matches_schoolbook_randomised(m):
    """The central correctness claim, over many random inputs on small rings."""
    N = euler_phi(m)
    L = transform_length(m, N)
    q = find_transform_prime(L, 40, 1)[0]
    ring = CyclotomicRing(m, q)
    mult = RingMultiplier(ring)
    rng = random.Random(m)
    for _ in range(25):
        a = [rng.randrange(q) for _ in range(N)]
        b = [rng.randrange(q) for _ in range(N)]
        assert list(map(int, mult.mul(a, b))) == ring.mul_schoolbook(a, b)


@pytest.mark.parametrize("m", CANDIDATE_CONDUCTORS)
def test_transform_mul_matches_schoolbook_full_size(m):
    """Same claim at the sizes that will actually ship. Slow (schoolbook is
    O(N^2) in pure Python) but non-negotiable."""
    N = euler_phi(m)
    L = transform_length(m, N)
    q = find_transform_prime(L, 45, 1)[0]
    ring = CyclotomicRing(m, q)
    mult = RingMultiplier(ring)
    rng = random.Random(m)
    a = [rng.randrange(q) for _ in range(N)]
    b = [rng.randrange(q) for _ in range(N)]
    assert list(map(int, mult.mul(a, b))) == ring.mul_schoolbook(a, b)


@pytest.mark.parametrize("m", SMALL_RINGS)
def test_ring_axioms(m):
    """Associativity, distributivity, identity, and that X^N really does reduce
    by the trinomial rule rather than by an off-by-one variant of it."""
    N = euler_phi(m)
    q = find_transform_prime(transform_length(m, N), 40, 1)[0]
    ring = CyclotomicRing(m, q)
    mult = RingMultiplier(ring)
    rng = random.Random(m + 1)
    a, b, c = (
        [rng.randrange(q) for _ in range(N)],
        [rng.randrange(q) for _ in range(N)],
        [rng.randrange(q) for _ in range(N)],
    )
    L = lambda v: list(map(int, v))  # noqa: E731

    assert L(mult.mul(mult.mul(a, b), c)) == L(mult.mul(a, mult.mul(b, c)))
    assert L(mult.mul(a, b)) == L(mult.mul(b, a))
    assert L(mult.mul(a, mult.add(b, c))) == L(
        mult.add(mult.mul(a, b), mult.mul(a, c))
    )
    assert L(mult.mul(a, ring.one())) == [x % q for x in a]
    assert L(mult.mul(a, ring.zero())) == [0] * N


@pytest.mark.parametrize("m", CANDIDATE_CONDUCTORS)
def test_x_to_the_n_reduces_by_the_stated_rule(m):
    """X^N must equal -(lower terms of Phi_m). Checked in the ring itself."""
    N = euler_phi(m)
    q = find_transform_prime(transform_length(m, N), 45, 1)[0]
    ring = CyclotomicRing(m, q)
    mult = RingMultiplier(ring)
    phi = ring.phi
    x_n = mult.reduce(np.array([0] * N + [1], dtype=np.int64))
    want = [(-phi[i]) % q for i in range(N)]
    assert list(map(int, x_n)) == want


@pytest.mark.parametrize("m", CANDIDATE_CONDUCTORS)
def test_x_has_multiplicative_order_m(m):
    """In Z[X]/Phi_m(X), X is a primitive m-th root of unity: X^m = 1 and no
    proper divisor exponent gives 1. This is the strongest cheap structural
    check that the reduction rule implements the intended ring."""
    N = euler_phi(m)
    q = find_transform_prime(transform_length(m, N), 45, 1)[0]
    ring = CyclotomicRing(m, q)
    mult = RingMultiplier(ring)

    def x_pow(e):
        return mult.reduce(np.array([0] * e + [1], dtype=np.int64))

    one = [1] + [0] * (N - 1)
    assert list(map(int, x_pow(m))) == one
    for p in (2, 3):
        if m % p == 0:
            assert list(map(int, x_pow(m // p))) != one


# ----------------------------------------------------- admissibility findings


def test_ntt_findings_reject_the_draft_modulus():
    """q = 34993 = 7 x 4999 must produce blockers, not an 'ok'."""
    findings = CyclotomicRing(8748, 34993).ntt_findings()
    ids = {f["id"] for f in findings}
    assert "q-not-prime" in ids
    # 34993 = 8748*4 + 1, so the PRODUCT congruence q = 1 mod m does hold. That
    # is the TRI-213 false positive, not a passing check: 7 = 7 mod 8748 and
    # 4999 = 4999 mod 8748, so neither component admits a primitive m-th root.
    assert "cyclic-transform-false-positive" in ids
    assert "cyclic-transform-available" not in ids
    assert any(f["severity"] == "blocker" for f in findings)


def test_ntt_findings_accept_a_valid_candidate():
    q = find_transform_prime(8748, 45, 1)[0]
    findings = CyclotomicRing(8748, q).ntt_findings()
    ids = {f["id"] for f in findings}
    assert "cyclic-transform-available" in ids
    assert "nwc-ntt-not-applicable" in ids
    assert not [f for f in findings if f["severity"] == "blocker"]


def test_nwc_condition_is_not_quoted_for_trinomial_rings():
    """The 'q = 1 mod 2N' line must be marked inapplicable for m = 8748 rather
    than reported as a passing check. Quoting it there is a category error."""
    q = find_transform_prime(8748, 45, 1)[0]
    findings = {f["id"]: f for f in CyclotomicRing(8748, q).ntt_findings()}
    assert "nwc-ntt-available" not in findings
    note = findings["nwc-ntt-not-applicable"]["detail"]
    assert "NOT the right condition" in note


def test_power_of_two_baseline_reports_nwc():
    q = find_transform_prime(4096, 45, 1)[0]
    ids = {f["id"] for f in CyclotomicRing(4096, q).ntt_findings()}
    assert "nwc-ntt-available" in ids


def test_transform_refuses_oversized_modulus():
    """Above 2^50 the float64 quotient trick is no longer exact. The layer must
    refuse rather than return silently wrong products."""
    with pytest.raises(ValueError):
        CyclicNTT(36, find_transform_prime(36, 55, 1)[0])
