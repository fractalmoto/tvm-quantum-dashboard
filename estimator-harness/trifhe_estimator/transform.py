# -*- coding: utf-8 -*-
"""
Transform-based multiplication in R_q = Z_q[X]/(Phi_m(X)) for m = 2^a * 3^b.

WHY THIS EXISTS
---------------
The classical FHE fast path is the negative-wrapped convolution NTT, which is
specific to Phi_{2^k}(X) = X^n + 1. It does not apply to a trinomial ring such
as Phi_8748(X) = X^2916 - X^1458 + 1, and "q = 1 mod 2N" is not the right
admissibility condition there. This module implements a route that IS correct
for every 2/3-smooth conductor, states its correctness argument explicitly, and
is checked against `rings.CyclotomicRing.mul_schoolbook` in the test suite.

THE ROUTE, AND WHY IT IS CORRECT
--------------------------------
Let N = phi(m) and let a, b in R_q have degree < N.

  1. The exact integer product a*b has degree at most 2N - 2. For every
     conductor of the form 2^a * 3^b we have 2*phi(m) - 2 < m:

         m = 2^k      : 2*(m/2) - 2 = m - 2 < m
         m = 3^b      : 2*(2m/3) - 2 = 4m/3 - 2  ... (see note)
         m = 2^a 3^b  : 2*phi(m) - 2 < m  iff  phi(m)/m < 1/2

     phi(m)/m = 1/2 * 2/3 = 1/3 when a >= 1 and b >= 1, and = 1/2 when b = 0,
     so the bound holds for a >= 1. For a PURE 3-power conductor (a = 0)
     phi(m)/m = 2/3 and the bound FAILS: the length-m cyclic convolution wraps
     and this route needs a length-3m transform instead. The plan below detects
     this and enlarges the transform length rather than silently wrapping.

  2. Therefore multiplying in Z_q[X]/(X^L - 1) for a transform length
     L >= 2N - 1 with L | (a power-of-2 times power-of-3) recovers the exact
     product with no reduction modulo X^L - 1 taking effect.

  3. A length-L cyclic transform over Z_q exists iff Z_q contains a primitive
     L-th root of unity, i.e. iff q = 1 mod L (for prime q).

  4. Reduce the exact product modulo Phi_m using the sparse recurrence
     X^N = -(sum_{i<N} phi_i X^i), which has at most two nonzero terms for every
     ring here.

Step 4 is where a bespoke ring costs you nothing: the trinomial makes reduction
two vectorised slice updates, not a general polynomial division.

MODULAR ARITHMETIC
------------------
`mulmod` uses a float64 quotient estimate with int64 wrap-around correction,
exact for q < 2^50. It is verified against Python's arbitrary-precision
integers over randomised inputs in the test suite; a silent failure here would
corrupt every downstream number, so it is tested rather than assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import numpy as np

MAX_Q_BITS = 50


# ------------------------------------------------------------- modular core


def mulmod(a: np.ndarray, b: np.ndarray, q: int) -> np.ndarray:
    """(a * b) mod q, elementwise, exact for 0 <= a,b < q < 2^50.

    int64 multiplication wraps mod 2^64; the float64 quotient estimate is
    within a couple of units of the true quotient, so the corrected residue has
    magnitude < 4q < 2^52 and is therefore recovered exactly from the wrapped
    value. `np.mod` then normalises into [0, q).
    """
    a = np.asarray(a, dtype=np.int64)
    b = np.asarray(b, dtype=np.int64)
    with np.errstate(over="ignore"):
        prod = a * b
        est = (a.astype(np.float64) * b.astype(np.float64) / float(q)).astype(np.int64)
        r = prod - est * q
    return np.mod(r, q)


def powmod_table(g: int, length: int, q: int) -> np.ndarray:
    """[g^0, g^1, ..., g^(length-1)] mod q as int64."""
    t = np.empty(length, dtype=np.int64)
    x = 1
    for i in range(length):
        t[i] = x
        x = x * g % q
    return t


def _smallest_factor(n: int) -> int:
    for r in (2, 3):
        if n % r == 0:
            return r
    raise ValueError(f"transform length {n} is not 2/3-smooth")


def primitive_root_of_unity(order: int, q: int) -> int:
    """A primitive `order`-th root of unity in Z_q. Requires q prime,
    q = 1 mod order. Verified before return."""
    if (q - 1) % order != 0:
        raise ValueError(
            f"q = {q} does not satisfy q = 1 mod {order}; no primitive "
            f"{order}-th root of unity exists in Z_q"
        )
    cof = (q - 1) // order
    prime_factors = _prime_factors(order)
    for cand in range(2, q):
        w = pow(cand, cof, q)
        if w == 1:
            continue
        if all(pow(w, order // p, q) != 1 for p in prime_factors):
            assert pow(w, order, q) == 1
            return w
    raise RuntimeError("no primitive root found")  # pragma: no cover


def _prime_factors(n: int) -> list[int]:
    fs, d = [], 2
    while d * d <= n:
        if n % d == 0:
            fs.append(d)
            while n % d == 0:
                n //= d
        d += 1
    if n > 1:
        fs.append(n)
    return fs


# ------------------------------------------------------------------- plan


@dataclass
class _Level:
    r: int
    s: int
    n: int
    tw: np.ndarray      # (r, n) twiddles  w_n^{j k}
    idx: np.ndarray     # (n,) = k mod s


class CyclicNTT:
    """Length-L mixed-radix cyclic transform over Z_q, L = 2^a 3^b, q = 1 mod L.

    Decimation-in-time Cooley-Tukey, batched: every subproblem at a given
    recursion level is transformed in one set of numpy operations, so the cost
    is O(L * sum_of_radices) modular multiplications in ~2*log(L) numpy calls
    rather than O(L) interpreted-Python calls.
    """

    def __init__(self, L: int, q: int):
        if q.bit_length() > MAX_Q_BITS:
            raise ValueError(
                f"q has {q.bit_length()} bits; this transform is exact only below "
                f"{MAX_Q_BITS} bits. Use an RNS chain of smaller primes."
            )
        if (q - 1) % L != 0:
            raise ValueError(f"q = {q} != 1 mod L = {L}")
        self.L, self.q = L, q
        self.w = primitive_root_of_unity(L, q)
        self.w_inv = pow(self.w, -1, q)
        self.L_inv = pow(L % q, -1, q)
        self._fwd = self._build_levels(self.w)
        self._inv = self._build_levels(self.w_inv)

    def _build_levels(self, root: int) -> list[_Level]:
        pw = powmod_table(root, self.L, self.q)
        levels: list[_Level] = []
        n = self.L
        while n > 1:
            r = _smallest_factor(n)
            s = n // r
            step = self.L // n            # w_n = root^step
            k = np.arange(n, dtype=np.int64)
            j = np.arange(r, dtype=np.int64)[:, None]
            tw = pw[(step * j * k) % self.L]
            levels.append(_Level(r=r, s=s, n=n, tw=tw, idx=k % s))
            n = s
        return levels

    def _apply(self, X: np.ndarray, levels: list[_Level], depth: int = 0) -> np.ndarray:
        lv = levels[depth]
        B = X.shape[0]
        if lv.n == 1:
            return X
        r, s = lv.r, lv.s
        # split into r interleaved subsequences: rows become X[:, j::r]
        Y = X.reshape(B, s, r).transpose(0, 2, 1).reshape(B * r, s)
        if depth + 1 < len(levels):
            Y = self._apply(Y, levels, depth + 1)
        Y = Y.reshape(B, r, s)
        gathered = Y[:, :, lv.idx]                       # (B, r, n)
        out = mulmod(gathered, lv.tw[None, :, :], self.q).sum(axis=1)
        return np.mod(out, self.q)

    def forward(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.int64).reshape(1, self.L)
        return self._apply(x, self._fwd)[0]

    def inverse(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.int64).reshape(1, self.L)
        y = self._apply(X, self._inv)[0]
        return mulmod(y, np.full(self.L, self.L_inv, dtype=np.int64), self.q)


# --------------------------------------------------------------- ring ops


def transform_length(m: int, degree: int) -> int:
    """Smallest 2/3-smooth L with L >= 2*degree - 1 and L | m * 3^k / ... .

    We restrict L to divisors-or-multiples of m of the form 2^a 3^b so that a
    single q = 1 mod L also gives q = 1 mod m, keeping one congruence condition
    for the whole implementation. In practice L = m when 2*degree - 1 <= m
    (every conductor with a >= 1) and L = 3m for a pure 3-power conductor.
    """
    need = 2 * degree - 1
    L = m
    while L < need:
        L *= 3
    return L


class RingMultiplier:
    """Transform-based multiplication in R_q for a CyclotomicRing.

    Correctness argument is in the module docstring; `mul` is checked against
    `CyclotomicRing.mul_schoolbook` on random inputs by the test suite for every
    supported conductor.
    """

    def __init__(self, ring, q: int | None = None):
        self.ring = ring
        self.q = q if q is not None else ring.q
        if self.q is None:
            raise ValueError("RingMultiplier needs a modulus q")
        self.N = ring.degree
        self.L = transform_length(ring.m, self.N)
        self.ntt = CyclicNTT(self.L, self.q)
        # Sparse reduction rule: X^N = -(sum_{i<N} phi_i X^i).
        phi = ring.phi
        self.reduction_terms = [
            (i, (-c) % self.q) for i, c in enumerate(phi[: self.N]) if c != 0
        ]

    # -------------------------------------------------------- reduction

    def reduce(self, c: np.ndarray) -> np.ndarray:
        """Reduce a coefficient vector of any length into degree < N, mod q.

        Repeatedly folds the tail using X^{N+j} = sum_terms coeff * X^{i+j}.
        Each pass reduces the degree by at least N - max(i) >= N/2, so it
        terminates in at most two passes for every trinomial ring here.
        """
        q, N = self.q, self.N
        c = np.mod(np.asarray(c, dtype=np.int64), q)
        while c.size > N:
            tail = c[N:].copy()
            c = c[:N].copy()
            for i, coeff in self.reduction_terms:
                seg = mulmod(tail, np.int64(coeff), q)
                end = i + tail.size
                if end > c.size:
                    c = np.concatenate([c, np.zeros(end - c.size, dtype=np.int64)])
                c[i:end] = np.mod(c[i:end] + seg, q)
        if c.size < N:
            c = np.concatenate([c, np.zeros(N - c.size, dtype=np.int64)])
        return np.mod(c, q)

    # -------------------------------------------------------- arithmetic

    def _pad(self, a) -> np.ndarray:
        a = np.mod(np.asarray(a, dtype=np.int64), self.q)
        out = np.zeros(self.L, dtype=np.int64)
        out[: a.size] = a
        return out

    def mul(self, a, b) -> np.ndarray:
        A = self.ntt.forward(self._pad(a))
        B = self.ntt.forward(self._pad(b))
        prod = self.ntt.inverse(mulmod(A, B, self.q))
        # No wraparound: deg(a*b) <= 2N-2 < L, so entries above 2N-2 are zero.
        return self.reduce(prod[: 2 * self.N - 1])

    def add(self, a, b) -> np.ndarray:
        return np.mod(np.asarray(a, np.int64) + np.asarray(b, np.int64), self.q)

    def sub(self, a, b) -> np.ndarray:
        return np.mod(np.asarray(a, np.int64) - np.asarray(b, np.int64), self.q)

    def scalar_mul(self, a, k: int) -> np.ndarray:
        return mulmod(np.asarray(a, np.int64), np.int64(k % self.q), self.q)

    def to_dict(self) -> dict:
        return dict(
            conductor=self.ring.m,
            degree=self.N,
            transform_length=self.L,
            transform_length_equals_conductor=(self.L == self.ring.m),
            q=self.q,
            log2_q=float(np.log2(self.q)),
            primitive_root_of_unity=self.ntt.w,
            root_order=self.L,
            reduction_rule=(
                "X^%d = " % self.N
                + " + ".join(
                    f"{(self.q - c) % self.q if c else 0}*X^{i}"
                    for i, c in self.reduction_terms
                )
                + "  (mod q)"
            ),
        )


@lru_cache(maxsize=8)
def multiplier_for(m: int, q: int) -> RingMultiplier:
    from .rings import CyclotomicRing

    return RingMultiplier(CyclotomicRing(m, q))
