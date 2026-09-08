# -*- coding: utf-8 -*-
"""
Exact cyclotomic ring arithmetic for TriFHE candidate rings.

This module is the ground truth the transform is checked against. It is pure
Python integer arithmetic with no numpy, no Sage, and no cleverness: every
operation is either a textbook schoolbook convolution or an explicit long
division. It is slow on purpose. `transform.py` is the fast path; this is what
proves the fast path correct.

SCOPE
-----
Conductors of the form m = 2^a * 3^b (a >= 0, b >= 0, m >= 3), which covers:

    m = 2^k          -> Phi_m(X) = X^(m/2) + 1              (the FHE standard ring)
    m = 3^b          -> Phi_m(X) = X^(2*3^(b-1)) + X^(3^(b-1)) + 1
    m = 2 * 3^b      -> Phi_m(X) = X^(2*3^(b-1)) - X^(3^(b-1)) + 1
    m = 2^a * 3^b    -> Phi_m(X) = Phi_(3^b)(-X^(2^(a-1)))  for a >= 2

The a >= 2 identity is the one the original TriFHE proposal got wrong: it
listed signed trinomials for the PURE 3-power cases, where the correct sign is
positive. Every identity used here is verified against generic cyclotomic
computation in `test_rings.py` rather than trusted.

AUDIT NOTE
----------
Correct ring arithmetic is a prerequisite for a security claim, not a
substitute for one. Nothing in this file is a security result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import math

# --------------------------------------------------------------- conductors


def factor_2a3b(m: int) -> tuple[int, int]:
    """Return (a, b) with m = 2^a * 3^b, or raise if m has another prime factor."""
    if m < 1:
        raise ValueError("conductor must be positive")
    n, a, b = m, 0, 0
    while n % 2 == 0:
        n //= 2
        a += 1
    while n % 3 == 0:
        n //= 3
        b += 1
    if n != 1:
        raise ValueError(
            f"conductor {m} is not of the form 2^a * 3^b (residual factor {n}). "
            "This module only models 2/3-smooth conductors."
        )
    return a, b


def euler_phi(m: int) -> int:
    """phi(m) for m = 2^a * 3^b. Also the degree of Phi_m."""
    a, b = factor_2a3b(m)
    phi = 1
    if a >= 1:
        phi *= 2 ** (a - 1)
    if b >= 1:
        phi *= 2 * 3 ** (b - 1)
    return phi


# ------------------------------------------------------- polynomial helpers


def poly_trim(p: list[int]) -> list[int]:
    while len(p) > 1 and p[-1] == 0:
        p.pop()
    return p


def poly_mul(a: Sequence[int], b: Sequence[int]) -> list[int]:
    """Schoolbook product over Z. O(len(a)*len(b)). Exact, arbitrary precision."""
    if not a or not b:
        return [0]
    out = [0] * (len(a) + len(b) - 1)
    for i, ai in enumerate(a):
        if ai == 0:
            continue
        for j, bj in enumerate(b):
            if bj:
                out[i + j] += ai * bj
    return out


def poly_divmod(num: Sequence[int], den: Sequence[int]) -> tuple[list[int], list[int]]:
    """Exact long division over Z, valid when the leading coefficient of `den`
    divides every intermediate leading coefficient. Cyclotomics are monic, so
    this always holds for our use."""
    den = poly_trim(list(den))
    if den == [0]:
        raise ZeroDivisionError
    r = list(num)
    dl = den[-1]
    if dl not in (1, -1):
        raise ValueError("poly_divmod requires a monic (or -monic) divisor")
    qout = [0] * max(1, len(r) - len(den) + 1)
    for i in range(len(r) - len(den), -1, -1):
        c = r[i + len(den) - 1] // dl
        if c:
            qout[i] = c
            for j, dj in enumerate(den):
                r[i + j] -= c * dj
    return poly_trim(qout), poly_trim(r[: len(den) - 1] or [0])


def cyclotomic_generic(m: int) -> list[int]:
    """Phi_m(X) from the defining recursion, coefficients low-degree first.

        X^m - 1 = prod_{d | m} Phi_d(X)

    Independent of the closed-form identities used elsewhere in this module,
    so the two can be cross-checked.
    """
    num = [-1] + [0] * (m - 1) + [1]  # X^m - 1
    for d in range(1, m):
        if m % d == 0:
            q, r = poly_divmod(num, cyclotomic_generic(d))
            if r != [0]:
                raise AssertionError(f"Phi_{d} does not divide the running quotient")
            num = q
    return num


def cyclotomic_closed_form(m: int) -> list[int]:
    """Phi_m(X) for m = 2^a * 3^b from closed-form identities.

    Returns coefficients low-degree first. Cross-checked against
    `cyclotomic_generic` in the test suite for every conductor in range.
    """
    a, b = factor_2a3b(m)
    if m == 1:
        return [-1, 1]
    if m == 2:
        return [1, 1]

    if b == 0:
        # m = 2^a, a >= 2: Phi_m(X) = X^(2^(a-1)) + 1
        n = 2 ** (a - 1)
        c = [0] * (n + 1)
        c[0] = 1
        c[n] = 1
        return c

    t = 3 ** (b - 1)
    if a == 0:
        # Phi_(3^b)(X) = X^(2t) + X^t + 1
        c = [0] * (2 * t + 1)
        c[0] = c[t] = c[2 * t] = 1
        return c
    if a == 1:
        # Phi_(2*3^b)(X) = Phi_(3^b)(-X) = X^(2t) - X^t + 1
        c = [0] * (2 * t + 1)
        c[0] = c[2 * t] = 1
        c[t] = -1
        return c
    # a >= 2: Phi_(2^a 3^b)(X) = Phi_(3^b)(-X^(2^(a-1)))
    #                          = X^(2t*2^(a-1)) - X^(t*2^(a-1)) + 1
    s = 2 ** (a - 1)
    c = [0] * (2 * t * s + 1)
    c[0] = 1
    c[t * s] = -1
    c[2 * t * s] = 1
    return c


# ------------------------------------------------------------------- ring


@dataclass(frozen=True)
class CyclotomicRing:
    """R = Z[X]/(Phi_m(X)), and R_q = R/qR when q is supplied.

    `m` is the CONDUCTOR. `degree` = phi(m) is the lattice dimension. Confusing
    the two is the error that cost TRI-214 729 dimensions.
    """

    m: int
    q: int | None = None

    # -------------------------------------------------------------- derived

    @property
    def degree(self) -> int:
        return euler_phi(self.m)

    @property
    def phi(self) -> list[int]:
        """Phi_m coefficients, low-degree first."""
        return cyclotomic_closed_form(self.m)

    @property
    def is_power_of_two(self) -> bool:
        a, b = factor_2a3b(self.m)
        return b == 0

    @property
    def phi_str(self) -> str:
        terms = []
        for i, c in reversed(list(enumerate(self.phi))):
            if c == 0:
                continue
            mono = "1" if i == 0 else ("X" if i == 1 else f"X^{i}")
            if c == 1:
                terms.append(("+ " if terms else "") + mono)
            elif c == -1:
                terms.append("- " + mono)
            else:
                terms.append(("+ " if terms and c > 0 else "- ") + f"{abs(c)}*{mono}")
        return " ".join(terms)

    @property
    def sparsity(self) -> int:
        """Number of nonzero coefficients of Phi_m. 3 for every ring here."""
        return sum(1 for c in self.phi if c != 0)

    # ------------------------------------------------------------ arithmetic

    def _mod_q(self, p: list[int]) -> list[int]:
        if self.q is None:
            return p
        return [c % self.q for c in p]

    def reduce(self, p: Sequence[int]) -> list[int]:
        """Reduce an arbitrary-degree polynomial into the ring, then mod q.

        Uses explicit long division by Phi_m. Slow and obviously correct.
        """
        _, r = poly_divmod(list(p), self.phi)
        r = list(r) + [0] * (self.degree - len(r))
        return self._mod_q(r[: self.degree])

    def mul_schoolbook(self, a: Sequence[int], b: Sequence[int]) -> list[int]:
        """Reference multiplication: full schoolbook product, then reduce."""
        return self.reduce(poly_mul(list(a), list(b)))

    def add(self, a: Sequence[int], b: Sequence[int]) -> list[int]:
        n = self.degree
        return self._mod_q([(a[i] if i < len(a) else 0) + (b[i] if i < len(b) else 0)
                            for i in range(n)])

    def sub(self, a: Sequence[int], b: Sequence[int]) -> list[int]:
        n = self.degree
        return self._mod_q([(a[i] if i < len(a) else 0) - (b[i] if i < len(b) else 0)
                            for i in range(n)])

    def one(self) -> list[int]:
        c = [0] * self.degree
        c[0] = 1
        return c

    def zero(self) -> list[int]:
        return [0] * self.degree

    # -------------------------------------------------- ntt admissibility

    def ntt_findings(self) -> list[dict]:
        """Whether a transform-based multiplication is constructible over Z_q,
        and by which route. This is the check the draft spec failed.

        The two conditions that matter are different things and are reported
        separately:

          * q = 1 mod m  ->  Z_q contains a primitive m-th root of unity, so
            Phi_m splits completely and a length-m cyclic transform exists.
            Sufficient for a correct (if not maximally fast) implementation.

          * q = 1 mod 2n where Phi_m(X) = X^n + 1  ->  the classical negacyclic
            NWC-NTT applies. This is ONLY meaningful for power-of-two m. For a
            trinomial ring it is neither necessary nor sufficient, and quoting
            it there is a category error.
        """
        if self.q is None:
            return []
        out: list[dict] = []
        n = self.degree
        q = self.q

        prime = _is_prime(q)
        if not prime:
            out.append(dict(
                id="q-not-prime",
                severity="blocker",
                detail=(
                    f"q = {q} is composite ({' x '.join(map(str, _factorise(q)))}). "
                    "Z_q is not a field. Every CRT component must independently admit "
                    "the required root of unity; the product congruence alone is a "
                    "false positive (TRI-213)."
                ),
            ))

        if q % self.m == 1 and not prime:
            # THE TRI-213 SHAPE. The product congruence can hold while no CRT
            # component satisfies it, in which case no primitive m-th root of
            # unity exists anywhere and the transform does not exist. Checking
            # only the product is the classic false positive.
            comps = sorted(set(_factorise(q)))
            bad = [p for p in comps if p % self.m != 1]
            residues = ", ".join(f"{p} = {p % self.m} mod {self.m}" for p in comps)
            out.append(dict(
                id="cyclic-transform-false-positive" if bad else "cyclic-transform-crt",
                severity="blocker" if bad else "warning",
                detail=(
                    f"q = {q} = 1 mod m ({self.m}) holds for the PRODUCT, which looks like the "
                    "right congruence, but q is composite so the product congruence is not what "
                    "the transform needs. Each CRT component must satisfy p = 1 mod m "
                    f"independently. Residues: {residues}. "
                    + (
                        f"Component(s) {bad} fail it, so no primitive {self.m}-th root of unity "
                        "exists in those components and the transform cannot be constructed as "
                        "specified."
                        if bad
                        else "All components satisfy it, so a CRT/RNS transform is constructible, "
                        "but it must be implemented and documented per component."
                    )
                ),
            ))
        elif q % self.m == 1:
            out.append(dict(
                id="cyclic-transform-available",
                severity="ok",
                detail=(
                    f"q = 1 mod m ({self.m}), so Z_q contains a primitive {self.m}-th root "
                    f"of unity, Phi_{self.m} splits into {n} distinct linear factors over Z_q, "
                    "and multiplication in R_q is implementable as a length-m cyclic "
                    "transform followed by reduction mod Phi_m. Correctness of that route is "
                    "proved by the no-wraparound argument: deg(a*b) <= 2*phi(m) - 2 < m."
                ),
            ))
        else:
            out.append(dict(
                id="cyclic-transform-unavailable",
                severity="blocker",
                detail=(
                    f"q = {q} != 1 mod m ({self.m}); q mod m = {q % self.m}. No primitive "
                    f"{self.m}-th root of unity in Z_q, so the length-m transform does not "
                    "exist and Phi_m does not split completely. A different multiplication "
                    "route must be specified and proved."
                ),
            ))

        if self.is_power_of_two:
            ok = q % (2 * n) == 1
            out.append(dict(
                id="nwc-ntt-available" if ok else "nwc-ntt-unavailable",
                severity="ok" if ok else "warning",
                detail=(
                    f"Phi_m(X) = X^{n} + 1, so the classical negative-wrapped convolution "
                    f"NTT applies iff q = 1 mod 2n ({2 * n}); q mod 2n = {q % (2 * n)}."
                ),
            ))
        else:
            out.append(dict(
                id="nwc-ntt-not-applicable",
                severity="info",
                detail=(
                    f"Phi_{self.m}(X) = {self.phi_str} is a trinomial, not X^n + 1. The "
                    "'q = 1 mod 2N' negacyclic condition is NOT the right condition for this "
                    "ring and must not be quoted for it. The applicable condition is "
                    "q = 1 mod m above. A production implementation must additionally "
                    "document its transform, twiddle construction, and reduction step, and "
                    "test them against schoolbook reduction modulo this exact trinomial."
                ),
            ))
        return out

    def to_dict(self) -> dict:
        a, b = factor_2a3b(self.m)
        return dict(
            conductor=self.m,
            conductor_factorisation=f"2^{a} * 3^{b}",
            degree=self.degree,
            phi_m=self.phi_str,
            phi_m_nonzero_terms=self.sparsity,
            is_power_of_two_cyclotomic=self.is_power_of_two,
            q=self.q,
            log2_q=(math.log2(self.q) if self.q else None),
        )


# ------------------------------------------------------------- small utils


def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _factorise(n: int) -> list[int]:
    fs, d = [], 2
    while d * d <= n:
        while n % d == 0:
            fs.append(d)
            n //= d
        d += 1
    if n > 1:
        fs.append(n)
    return fs


def find_transform_prime(m: int, min_log2_q: int, count: int = 1) -> list[int]:
    """Smallest primes q > 2^min_log2_q with q = 1 mod m.

    q = 1 mod m is the condition for the length-m cyclic transform. Note this
    is a *stronger* requirement than q = 1 mod 2*phi(m) for trinomial rings, and
    a weaker-looking congruence that happens to hold mod 2*phi(m) proves nothing
    about the ring.
    """
    out: list[int] = []
    k = (2 ** min_log2_q) // m + 1
    while len(out) < count:
        q = k * m + 1
        if _is_prime(q):
            out.append(q)
        k += 1
    return out


# ----------------------------------------------------------- named candidates

# The leading experimental ternary-aligned candidate. m = 2^2 * 3^7.
TERNARY_EXPERIMENTAL_M = 8748
# The pure 3-power ring at comparable size. m = 3^7, degree 1458.
TERNARY_PURE_M = 2187
# Implementation and security baselines.
BASELINE_M_2048 = 4096   # Phi_4096 = X^2048 + 1
BASELINE_M_4096 = 8192   # Phi_8192 = X^4096 + 1
