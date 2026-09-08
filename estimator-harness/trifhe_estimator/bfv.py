# -*- coding: utf-8 -*-
"""
A textbook BFV implementation over an arbitrary 2/3-smooth cyclotomic ring.

PURPOSE
-------
This is not a production FHE library and must never be used as one: no
constant-time behaviour, no RNS ciphertext representation, no side-channel
hardening, no modulus switching. It exists to measure the thing a formula
cannot tell you — the actual distribution of invariant noise after a real
1 multiplication + relinearisation circuit, over many randomised trials, in the
candidate ring.

The point of measuring is that the noise-growth formulas in the original TriFHE
proposal were heuristics presented as certification. An empirical distribution
plus an explicit tail model is a defensible statement; a closed-form expression
with unstated assumptions is not.

WHAT IS MODELLED
----------------
  * R_q = Z_q[X]/Phi_m(X), q a single prime with q = 1 mod L (no RNS chain).
  * Plaintext space R_t with t = 3 — balanced ternary, which is the point of the
    VM. Plaintexts are represented by centred residues {-1, 0, +1}.
  * Secret: uniform ternary, matching the secret model the estimator is fed.
  * Error: rounded Gaussian of width sigma (default HES v1.1 sigma = 3.19).
  * Relinearisation: BFV version 1, gadget base B with ell = ceil(log_B q)
    digits, evaluation key encrypting B^i * s^2.

EXACTNESS OF MULTIPLICATION
---------------------------
BFV multiplication needs the tensor product computed over Z and then scaled by
t/q with rounding. It cannot be done modulo q. The product coefficients reach
~N * (q/2)^2, about 2^100 at N = 2916 and log2 q = 45, which exceeds any single
transform modulus this code can use.

So the tensor is computed by CRT over several transform primes, each
independently satisfying p = 1 mod L, and reconstructed to exact integers. The
reconstruction bound is asserted at runtime against the actual maximum
coefficient: if the CRT modulus were ever too small the products would be
silently wrong, which is exactly the class of bug this whole programme exists to
rule out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np

from .rings import CyclotomicRing, find_transform_prime
from .transform import RingMultiplier, transform_length

CRT_PRIME_BITS = 40


def round_div(a: int, b: int) -> int:
    """Round-half-away-from-zero integer division. Used for both the t/q scaling
    in BFV multiplication and the decryption rounding, so the two cannot drift
    apart."""
    if a >= 0:
        return (2 * a + b) // (2 * b)
    return -((-2 * a + b) // (2 * b))


def centre(a: np.ndarray, q: int) -> np.ndarray:
    """Map Z_q residues to the centred representative in (-q/2, q/2]."""
    a = np.mod(np.asarray(a, dtype=np.int64), q)
    return np.where(a > q // 2, a - q, a)


class ExactProduct:
    """Exact integer product in Z[X]/Phi_m(X) via multi-prime CRT transforms."""

    def __init__(self, m: int, bound_log2: float):
        self.m = m
        self.N = CyclotomicRing(m).degree
        self.L = transform_length(m, self.N)
        # Signed reconstruction needs M > 2 * bound. Trinomial reduction over Z
        # inflates coefficients by at most a factor of 3, hence the +2 bits, and
        # 16 bits of slack on top so the runtime assertion is never load-bearing.
        need = bound_log2 + 2 + 16
        nprimes = max(2, math.ceil(need / (CRT_PRIME_BITS - 1)))
        self.primes: list[int] = []
        k = 0
        while len(self.primes) < nprimes:
            cand = find_transform_prime(self.L, CRT_PRIME_BITS, len(self.primes) + 1 + k)
            self.primes = sorted(set(cand))[:nprimes]
            k += 1
        self.mults = [RingMultiplier(CyclotomicRing(m, p)) for p in self.primes]
        self.M = math.prod(self.primes)
        self.bound_log2 = bound_log2

    def mul(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Exact product of two integer polynomials, reduced mod Phi_m, as a
        Python-int object array. Inputs must be centred integers."""
        a = np.asarray(a, dtype=object)
        b = np.asarray(b, dtype=object)

        # Guard on the INPUTS, before any modular arithmetic happens.
        #
        # This replaces an earlier check on the reconstructed output, which was
        # vacuous: CRT reconstruction always returns a representative inside
        # (-M/2, M/2], so an overflowed product is indistinguishable from a
        # legitimate one after the fact. Overflow is only detectable a priori,
        # from the input magnitudes. An assertion that cannot fail is worse than
        # no assertion at all, because it reads as a guarantee.
        #
        # Worst case for a coefficient of the reduced product: the length-N
        # convolution sums N products of magnitude max|a|*max|b|, and reduction
        # modulo the trinomial folds at most 3 such coefficients together.
        amax = max((abs(int(v)) for v in a), default=0)
        bmax = max((abs(int(v)) for v in b), default=0)
        worst = amax * bmax * self.N * 3
        if worst * 2 >= self.M:
            raise ValueError(
                "ExactProduct would overflow its CRT modulus: worst-case product "
                f"coefficient is 2^{math.log2(max(worst, 1)):.1f} but the signed "
                f"reconstruction range is 2^{math.log2(self.M) - 1:.1f}. Construct "
                f"ExactProduct with a larger bound_log2 (currently {self.bound_log2:.1f})."
            )

        residues = []
        for p, mult in zip(self.primes, self.mults):
            ap = np.array([int(x) % p for x in a], dtype=np.int64)
            bp = np.array([int(x) % p for x in b], dtype=np.int64)
            residues.append(mult.mul(ap, bp))
        out = np.empty(self.N, dtype=object)
        M = self.M
        # Precompute CRT coefficients once per instance.
        if not hasattr(self, "_crt"):
            self._crt = [
                (M // p) * pow(M // p, -1, p) % M for p in self.primes
            ]
        for i in range(self.N):
            x = 0
            for c, r in zip(self._crt, residues):
                x += c * int(r[i])
            x %= M
            if x > M // 2:
                x -= M
            out[i] = x
        return out


@dataclass
class BFVParams:
    m: int
    log2_q: int
    t: int = 3
    sigma: float = 3.19
    gadget_base_bits: int = 15
    seed: int = 0
    q: int = field(init=False)
    N: int = field(init=False)

    def __post_init__(self):
        L = transform_length(self.m, CyclotomicRing(self.m).degree)
        self.q = find_transform_prime(L, self.log2_q, 1)[0]
        self.N = CyclotomicRing(self.m).degree

    @property
    def delta(self) -> int:
        return self.q // self.t

    @property
    def ell(self) -> int:
        return math.ceil(self.log2_q_exact / self.gadget_base_bits)

    @property
    def log2_q_exact(self) -> float:
        return math.log2(self.q)

    def to_dict(self) -> dict:
        return dict(
            conductor=self.m,
            degree=self.N,
            phi_m=CyclotomicRing(self.m).phi_str,
            q=self.q,
            log2_q=round(self.log2_q_exact, 4),
            q_mod_m=self.q % self.m,
            t=self.t,
            delta=self.delta,
            sigma=self.sigma,
            gadget_base=2 ** self.gadget_base_bits,
            gadget_digits=self.ell,
            secret="uniform ternary {-1,0,+1}",
            error="rounded Gaussian, width sigma",
            relinearisation="BFV v1, evk encrypts B^i * s^2",
        )


class BFV:
    def __init__(self, p: BFVParams):
        self.p = p
        self.ring = CyclotomicRing(p.m, p.q)
        self.mult = RingMultiplier(self.ring)
        self.rng = np.random.default_rng(p.seed)
        # Tensor coefficients reach N * (q/2)^2.
        bound = math.log2(p.N) + 2 * (p.log2_q_exact - 1) + 1
        self.exact = ExactProduct(p.m, bound)
        self.keygen()

    # ------------------------------------------------------------ sampling

    def _ternary(self) -> np.ndarray:
        return self.rng.integers(-1, 2, size=self.p.N, dtype=np.int64)

    def _gauss(self) -> np.ndarray:
        return np.rint(self.rng.normal(0.0, self.p.sigma, self.p.N)).astype(np.int64)

    def _uniform(self) -> np.ndarray:
        return self.rng.integers(0, self.p.q, size=self.p.N, dtype=np.int64)

    # -------------------------------------------------------------- keygen

    def keygen(self) -> None:
        q, N = self.p.q, self.p.N
        self.s = self._ternary()
        a = self._uniform()
        e = self._gauss()
        # pk = (-(a*s + e), a)  so  pk0 + pk1*s = -e
        self.pk = (np.mod(-(self.mult.mul(a, self.s) + e), q), a)

        # Relinearisation key for s^2, gadget base B.
        B = 2 ** self.p.gadget_base_bits
        s2 = self.mult.mul(self.s, self.s)
        self.evk = []
        for i in range(self.p.ell):
            ai = self._uniform()
            ei = self._gauss()
            b = np.mod(-(self.mult.mul(ai, self.s) + ei) + self.mult.scalar_mul(s2, pow(B, i, q)), q)
            self.evk.append((b, ai))

    # ------------------------------------------------------- enc / dec / ops

    def encrypt(self, msg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        q = self.p.q
        u = self._ternary()
        e1, e2 = self._gauss(), self._gauss()
        c0 = np.mod(self.mult.mul(self.pk[0], u) + e1 + self.p.delta * np.mod(msg, self.p.t), q)
        c1 = np.mod(self.mult.mul(self.pk[1], u) + e2, q)
        return c0, c1

    def phase(self, ct) -> np.ndarray:
        """sum_i c_i * s^i mod q, for a ciphertext of any component count.

        Generalised beyond two components on purpose: it lets the noise
        experiment measure the invariant noise of the 3-component ciphertext
        BEFORE relinearisation and the 2-component one after, which is the only
        way to attribute noise growth to relinearisation rather than to
        tensoring. Since relinearisation turns out to dominate the variance, that
        attribution is the substantive measurement, not a convenience.
        """
        q = self.p.q
        acc = np.mod(ct[0], q)
        power = None
        for comp in ct[1:]:
            power = self.s if power is None else self.mult.mul(power, self.s)
            acc = np.mod(acc + self.mult.mul(np.mod(comp, q), power), q)
        return acc

    def decrypt(self, ct) -> np.ndarray:
        q, t = self.p.q, self.p.t
        u = centre(self.phase(ct), q).astype(object)
        return np.array([round_div(t * int(x), q) % t for x in u], dtype=np.int64)

    def invariant_noise(self, ct, msg: np.ndarray) -> np.ndarray:
        """The invariant noise v with (t/q)*(c0 + c1 s) = m + v + t*I.

        Decryption is correct iff ||v||_inf < 1/2. Returned as float64 per
        coefficient; the integer arithmetic is done exactly first so the float
        conversion loses nothing that matters at this magnitude.
        """
        q, t = self.p.q, self.p.t
        u = centre(self.phase(ct), q).astype(object)
        mm = np.mod(msg, t)
        out = np.empty(self.p.N, dtype=np.float64)
        for i in range(self.p.N):
            # e = centred(u_i - Delta * m_i) over Z_q, then v = t*e/q
            e = int(u[i]) - self.p.delta * int(mm[i])
            e %= q
            if e > q // 2:
                e -= q
            out[i] = t * e / q
        return out

    def add(self, ct1, ct2):
        q = self.p.q
        return np.mod(ct1[0] + ct2[0], q), np.mod(ct1[1] + ct2[1], q)

    # ------------------------------------------------------------- multiply

    def multiply_no_relin(self, ct1, ct2):
        """Tensor product, computed exactly over Z then scaled by t/q."""
        q, t = self.p.q, self.p.t
        a0, a1 = centre(ct1[0], q), centre(ct1[1], q)
        b0, b1 = centre(ct2[0], q), centre(ct2[1], q)
        p0 = self.exact.mul(a0, b0)
        p1 = self.exact.mul(a0, b1) + self.exact.mul(a1, b0)
        p2 = self.exact.mul(a1, b1)

        def scale(v):
            # round(t * v / q), exact integer rounding, then reduce mod q
            out = np.empty(self.p.N, dtype=np.int64)
            for i, x in enumerate(v):
                out[i] = round_div(t * int(x), q)
            return np.mod(out, q)

        return scale(p0), scale(p1), scale(p2)

    def relinearise(self, c0, c1, c2):
        """BFV v1 relinearisation: gadget-decompose c2 and fold in the evk."""
        q = self.p.q
        B = 2 ** self.p.gadget_base_bits
        rem = np.mod(c2, q).astype(object)
        acc0, acc1 = np.mod(c0, q), np.mod(c1, q)
        for i in range(self.p.ell):
            digit = np.array([int(x) % B for x in rem], dtype=np.int64)
            rem = np.array([int(x) // B for x in rem], dtype=object)
            b, a = self.evk[i]
            acc0 = np.mod(acc0 + self.mult.mul(b, digit), q)
            acc1 = np.mod(acc1 + self.mult.mul(a, digit), q)
        return acc0, acc1

    def multiply(self, ct1, ct2):
        return self.relinearise(*self.multiply_no_relin(ct1, ct2))

    # ---------------------------------------------------- plaintext product

    def plaintext_mul(self, m1: np.ndarray, m2: np.ndarray) -> np.ndarray:
        """m1 * m2 in R_t, computed exactly (coefficients are tiny)."""
        prod = self.exact.mul(np.mod(m1, self.p.t).astype(object),
                              np.mod(m2, self.p.t).astype(object))
        return np.array([int(x) % self.p.t for x in prod], dtype=np.int64)
