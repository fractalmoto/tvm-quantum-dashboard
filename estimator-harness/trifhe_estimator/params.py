# -*- coding: utf-8 -*-
"""
TriFHE parameter model and structural validation.

This module is deliberately free of any SageMath / lattice-estimator import so it
can be unit-tested, imported by a web backend, or serialised without the heavy
Sage runtime present. All estimator interaction lives in `adapter.py`.

AUDIT NOTE
----------
Nothing in this file constitutes a security claim. It records the *instance*
being claimed about. The security number comes from `run_estimate.py`, and is
only meaningful together with the provenance block that names the estimator
commit and cost models used.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, Optional
import math

# Standard deviation recommended by the Homomorphic Encryption Standard v1.1 for
# the LWE error distribution. Used ONLY as an explicit fallback; when it is used
# the emitted record flags Xe as ASSUMED rather than SPECIFIED.
HES_DEFAULT_SIGMA = 3.19

SecretKind = Literal["dense_ternary", "sparse_ternary", "gaussian"]

# Ring construction. This is the single most consequential modelling choice in
# the whole harness, so it is named explicitly rather than inferred.
#
#   power_of_two_cyclotomic : Z[x]/(x^d + 1), d = 2^k. The standard FHE ring.
#                             Lattice dimension n = d.
#   ternary_cyclotomic      : Z[x]/(Phi_{3^k}(x)). Phi_{3^k} has degree
#                             phi(3^k) = 2*3^(k-1), NOT 3^k. So a "ring of size
#                             3^7" has lattice dimension 1458, not 2187.
#   negacyclic_pow3         : Z[x]/(x^(3^k) + 1). This is what "N = 2187" most
#                             literally reads as, but x^2187 + 1 is NOT a
#                             cyclotomic polynomial and factors non-trivially
#                             (x^odd + 1 is divisible by x + 1). Modelled here
#                             because the draft spec implies it, but see
#                             `structural_findings()` -- it is not a sound ring.
#   smooth_cyclotomic       : Z[x]/(Phi_m(x)) for any m = 2^a 3^b, where the
#                             DECLARED number is the CONDUCTOR m and the lattice
#                             dimension is phi(m). This is the only ring kind
#                             that is unambiguous, because it names m rather
#                             than a degree that could mean either. Prefer it.
RingKind = Literal[
    "power_of_two_cyclotomic",
    "ternary_cyclotomic",
    "negacyclic_pow3",
    "smooth_cyclotomic",
]


def is_prime(n: int) -> bool:
    """Deterministic trial division. Fine for the 16-bit moduli in play here."""
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True


def factorise(n: int) -> list[int]:
    """Trial-division factorisation. Fine for the 16-bit moduli in play here."""
    fs, d = [], 2
    while d * d <= n:
        while n % d == 0:
            fs.append(d)
            n //= d
        d += 1
    if n > 1:
        fs.append(n)
    return fs


def euler_phi_prime_power(p: int, k: int) -> int:
    """phi(p^k) = p^k - p^(k-1) for prime p."""
    return p**k - p ** (k - 1)


@dataclass(frozen=True)
class TriFHEParams:
    """A single TriFHE instance, as claimed.

    Attributes
    ----------
    ring_size:
        The number the spec calls `N`. For a power-of-3 spec this is 3^k. NOTE
        this is *not* necessarily the lattice dimension -- see `lattice_dim`.
    q:
        Ciphertext modulus. For an RNS chain, pass the *product* as `q` and
        record the chain in `modulus_chain`.
    ring_kind:
        Which ring the coefficients actually live in. Drives `lattice_dim`.
    secret_kind:
        `dense_ternary` = uniform on {-1,0,+1}^n.
        `sparse_ternary` = exactly `hamming_weight` nonzero entries.
        `gaussian` = discrete Gaussian with stddev `secret_sigma`.
    hamming_weight:
        Required iff secret_kind == "sparse_ternary".
    error_sigma:
        Stddev of the error distribution. If None, HES_DEFAULT_SIGMA is used and
        the run is marked as carrying an ASSUMED error width.
    samples:
        Number of LWE samples `m` the adversary may observe. None => unbounded
        (the estimator's default). For RLWE, one ring sample yields `lattice_dim`
        scalar samples, so `m = lattice_dim` is the natural finite choice.
    """

    ring_size: int
    q: int
    ring_kind: RingKind = "negacyclic_pow3"
    secret_kind: SecretKind = "dense_ternary"
    hamming_weight: Optional[int] = None
    error_sigma: Optional[float] = None
    secret_sigma: Optional[float] = None
    samples: Optional[int] = None
    modulus_chain: tuple[int, ...] = field(default_factory=tuple)
    tag: str = "TriFHE"

    # ---------------------------------------------------------------- derived

    @property
    def error_sigma_effective(self) -> float:
        return HES_DEFAULT_SIGMA if self.error_sigma is None else self.error_sigma

    @property
    def error_sigma_is_assumed(self) -> bool:
        return self.error_sigma is None

    @property
    def lattice_dim(self) -> int:
        """The dimension `n` of the LWE problem the attacker actually faces.

        This is where a spec that says "N = 2187" can silently mean 1458.
        """
        if self.ring_kind == "smooth_cyclotomic":
            from .rings import euler_phi

            return euler_phi(self.ring_size)
        if self.ring_kind == "ternary_cyclotomic":
            k = round(math.log(self.ring_size, 3))
            if 3**k != self.ring_size:
                raise ValueError(
                    f"ring_kind=ternary_cyclotomic requires ring_size to be a power of 3, got {self.ring_size}"
                )
            return euler_phi_prime_power(3, k)
        # power_of_two_cyclotomic: x^d + 1 with d = 2^k has degree d.
        # negacyclic_pow3: x^d + 1 has degree d too (it is just not irreducible).
        return self.ring_size

    @property
    def log2_q(self) -> float:
        return math.log2(self.q)

    @property
    def keyspace_log2(self) -> Optional[float]:
        """log2 of the raw secret keyspace.

        Reported ONLY so the harness can print it next to the real bit-security
        and make the gap explicit. It is NOT a security measure. See
        `structural_findings()`.
        """
        n = self.lattice_dim
        if self.secret_kind == "dense_ternary":
            return n * math.log2(3)
        if self.secret_kind == "sparse_ternary" and self.hamming_weight:
            h = self.hamming_weight
            # C(n,h) * 2^h : choose positions, then signs
            return (
                math.lgamma(n + 1) - math.lgamma(h + 1) - math.lgamma(n - h + 1)
            ) / math.log(2) + h
        return None

    # -------------------------------------------------------------- validation

    def __post_init__(self):
        if self.ring_size < 2:
            raise ValueError("ring_size must be >= 2")
        if self.q < 2:
            raise ValueError("q must be >= 2")
        if self.secret_kind == "sparse_ternary":
            if not self.hamming_weight:
                raise ValueError("secret_kind=sparse_ternary requires hamming_weight")
            if self.hamming_weight > self.lattice_dim:
                raise ValueError("hamming_weight cannot exceed the lattice dimension")
        if self.secret_kind == "gaussian" and self.secret_sigma is None:
            raise ValueError("secret_kind=gaussian requires secret_sigma")
        if self.modulus_chain:
            prod = math.prod(self.modulus_chain)
            if prod != self.q:
                raise ValueError(
                    f"modulus_chain product {prod} does not equal q={self.q}"
                )

    def structural_findings(self) -> list[dict]:
        """Non-estimator checks an auditor will run in the first ten minutes.

        Returns a list of findings, each with a severity. `blocker` means the
        instance as specified is not a sound RLWE instance and no bit-security
        number computed for it should be quoted.
        """
        f: list[dict] = []
        n = self.lattice_dim

        # --- conductor-declared rings get the full ring analysis ----------
        # For `smooth_cyclotomic` the ring module owns every algebraic check,
        # including the one the draft spec failed: that the negacyclic
        # 'q = 1 mod 2N' condition is not the applicable condition for a
        # trinomial ring, and that a product congruence over a composite q is a
        # false positive rather than a pass.
        if self.ring_kind == "smooth_cyclotomic":
            from .rings import CyclotomicRing

            ring = CyclotomicRing(self.ring_size, self.q)
            f.append(
                dict(
                    id="ring-declared-by-conductor",
                    severity="ok",
                    detail=(
                        f"Ring declared by CONDUCTOR m = {self.ring_size}, so the degree is "
                        f"phi(m) = {ring.degree} by construction and cannot be misread. "
                        f"Phi_m(X) = {ring.phi_str}. Cyclotomic polynomials are irreducible "
                        "over Q, so R = Z[X]/Phi_m(X) is the ring of integers of a number "
                        "field and the instance is a well-formed RLWE instance."
                    ),
                )
            )
            f.extend(ring.ntt_findings())
            f.extend(self._noise_and_keyspace_findings())
            from .rings import factor_2a3b

            _a, _b = factor_2a3b(self.ring_size)
            if _b == 0:
                # Power-of-two conductor: Phi_m = X^(m/2) + 1. The standard,
                # mature, published setting. The baseline exists precisely
                # because it carries no bespoke-ring audit burden.
                f.append(
                    dict(
                        id="standard-power-of-two-ring",
                        severity="ok",
                        detail=(
                            f"Conductor {self.ring_size} = 2^{_a} is a power of two, so "
                            f"Phi_m(X) = X^{self.lattice_dim} + 1. This is the standard "
                            "negacyclic setting used by every maintained FHE library and "
                            "every published parameter table, so it carries no bespoke-ring "
                            "audit burden and serves as the control against which the "
                            "experimental ternary-aligned candidate is judged."
                        ),
                    )
                )
                return f
            f.append(
                dict(
                    id="nonstandard-ring-audit-burden",
                    severity="warning",
                    detail=(
                        "This is not a power-of-two cyclotomic. Costing it as plain LWE of "
                        f"dimension {ring.degree} is the standard practice, but it is only "
                        "defensible after subfield and structural screening (TRI-218): "
                        f"Q(zeta_{self.ring_size}) has subfields for every divisor of the "
                        "conductor, and no maintained implementation ships this ring, so the "
                        "transform, twiddle construction and reduction step are all bespoke "
                        "code that must be proved correct against schoolbook reduction before "
                        "any measured or estimated number means anything."
                    ),
                )
            )
            return f

        # --- modulus arithmetic -------------------------------------------
        if not is_prime(self.q):
            fs = factorise(self.q)
            f.append(
                dict(
                    id="q-not-prime",
                    severity="blocker",
                    detail=(
                        f"q = {self.q} is COMPOSITE: {self.q} = "
                        + " x ".join(str(x) for x in fs)
                        + ". Z_q is therefore not a field, it has zero divisors, and not every "
                        "nonzero element is invertible. A single-modulus NTT over Z_q requires a "
                        "primitive 2N-th root of unity in a field; a composite modulus needs an "
                        "explicit CRT/RNS decomposition with each factor separately satisfying the "
                        "root-of-unity condition, and the smallest factor here bounds what the "
                        "scheme can actually represent. If the specification describes q as prime, "
                        "that statement is false and the NTT correctness argument built on it does "
                        "not hold."
                    ),
                )
            )
        else:
            f.append(
                dict(
                    id="q-prime",
                    severity="ok",
                    detail=f"q = {self.q} is prime, so Z_q is a field.",
                )
            )

        nwc_mod = 2 * self.ring_size
        if self.q % nwc_mod == 1:
            if is_prime(self.q):
                f.append(
                    dict(
                        id="nwc-ok",
                        severity="ok",
                        detail=(
                            f"q = {self.q} = 1 mod 2N ({nwc_mod}) and q is prime, so a primitive "
                            f"2N-th root of unity exists in the field Z_q and negative-wrapped "
                            f"convolution NTT is available."
                        ),
                    )
                )
            else:
                fs = sorted(set(factorise(self.q)))
                residues = ", ".join(f"{p} = {p % nwc_mod} mod {nwc_mod}" for p in fs)
                bad = [p for p in fs if p % nwc_mod != 1]
                f.append(
                    dict(
                        id="nwc-conditional" if not bad else "nwc-crt-fail",
                        severity="warning" if not bad else "blocker",
                        detail=(
                            f"q = {self.q} = 1 mod 2N ({nwc_mod}) holds for the PRODUCT, which "
                            "looks like the right congruence, but q is composite so the product "
                            "congruence is not what an NTT needs. A negative-wrapped convolution "
                            "NTT requires a primitive 2N-th root of unity, which exists in Z_p "
                            "only when p = 1 mod 2N; over a composite modulus each CRT component "
                            f"must satisfy this independently. Residues: {residues}. "
                            + (
                                f"Component(s) {bad} do NOT satisfy p = 1 mod 2N, so no primitive "
                                "2N-th root of unity exists in those components and the NWC NTT "
                                "cannot be constructed as specified. The product congruence holding "
                                "while no factor does is a classic false-positive on this check."
                                if bad
                                else "All components satisfy it, so a CRT-based NTT is constructible."
                            )
                        ),
                    )
                )
        else:
            f.append(
                dict(
                    id="nwc-fail",
                    severity="warning",
                    detail=f"q = {self.q} != 1 mod 2N ({nwc_mod}); q mod 2N = {self.q % nwc_mod}. NWC NTT is unavailable as specified.",
                )
            )

        # --- ring soundness ------------------------------------------------
        if self.ring_kind == "negacyclic_pow3":
            k = round(math.log(self.ring_size, 3))
            phi_deg = (
                euler_phi_prime_power(3, k) if 3**k == self.ring_size else None
            )
            f.append(
                dict(
                    id="ring-not-cyclotomic",
                    severity="blocker",
                    detail=(
                        f"x^{self.ring_size} + 1 is not a cyclotomic polynomial. For odd d, "
                        f"x^d + 1 is divisible by (x + 1), so Z[x]/(x^{self.ring_size} + 1) has "
                        f"zero divisors and is not a field extension. The 3-power cyclotomic of "
                        f"comparable size is Phi_{self.ring_size}, of degree "
                        f"phi(3^{k}) = 2*3^{k - 1} = {phi_deg}, not {self.ring_size}. "
                        "Any bit-security figure computed against this ring inherits the ring's "
                        "unsoundness and must not be quoted as the scheme's security."
                    ),
                )
            )

        f.extend(self._noise_and_keyspace_findings())
        return f

    def _noise_and_keyspace_findings(self) -> list[dict]:
        f: list[dict] = []
        n = self.lattice_dim

        # --- noise budget --------------------------------------------------
        # Very rough sanity check: an FHE ciphertext needs headroom between the
        # error width and q for even one multiplication. log2(q) - log2(sigma)
        # is the total budget in bits.
        budget = self.log2_q - math.log2(self.error_sigma_effective)
        if budget < 20:
            f.append(
                dict(
                    id="noise-budget-thin",
                    severity="blocker",
                    detail=(
                        f"log2(q) = {self.log2_q:.1f} against error stddev "
                        f"{self.error_sigma_effective:.2f} leaves only ~{budget:.1f} bits of total "
                        "noise headroom. That is far below what a single homomorphic multiplication "
                        "plus relinearisation consumes in BGV/BFV-style schemes, so this instance "
                        "is not a usable FHE parameter set regardless of how hard the lattice is. "
                        "Smaller q makes the lattice HARDER and the scheme LESS useful; these two "
                        "must be reported together."
                    ),
                )
            )

        # --- sparsity ------------------------------------------------------
        if self.secret_kind == "sparse_ternary":
            f.append(
                dict(
                    id="sparse-secret",
                    severity="warning",
                    detail=(
                        f"Sparse ternary secret (h={self.hamming_weight}, n={n}). The Homomorphic "
                        "Encryption Standard v1.1 ships no sparse parameter sets. Dual-hybrid / MitM "
                        "attacks and the 'Cool and Cruel' statistical dual attack both target this "
                        "case specifically."
                    ),
                )
            )

        # --- keyspace fallacy guard ---------------------------------------
        ks = self.keyspace_log2
        if ks is not None:
            f.append(
                dict(
                    id="keyspace-not-security",
                    severity="info",
                    detail=(
                        f"Raw secret keyspace is ~2^{ks:.0f}. This is NOT the security level and must "
                        "never be quoted as one. The estimator output below is the security level."
                    ),
                )
            )

        return f

    def ring_dict(self) -> dict | None:
        """Full ring description when the ring is declared by conductor."""
        if self.ring_kind != "smooth_cyclotomic":
            return None
        from .rings import CyclotomicRing

        return CyclotomicRing(self.ring_size, self.q).to_dict()

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(
            lattice_dim=self.lattice_dim,
            log2_q=self.log2_q,
            error_sigma_effective=self.error_sigma_effective,
            error_sigma_is_assumed=self.error_sigma_is_assumed,
            keyspace_log2=self.keyspace_log2,
        )
        return d


# ---------------------------------------------------------------- known sets

def draft_spec_2187() -> TriFHEParams:
    """The parameter set as literally written in the draft memorandum.

    N = 2187 = 3^7, q = 34993, dense ternary secret. Error width is NOT
    specified in the memorandum, so it is assumed.
    """
    return TriFHEParams(
        ring_size=2187,
        q=34993,
        ring_kind="negacyclic_pow3",
        secret_kind="dense_ternary",
        tag="TriFHE-draft-N2187-q34993",
    )


def _q_for(m: int, log2_q: int) -> int:
    """An NTT-admissible prime for conductor m: q prime, q = 1 mod L where L is
    the transform length. Chosen by the ring module, not by hand, so the
    congruence cannot be wrong."""
    from .rings import CyclotomicRing, find_transform_prime
    from .transform import transform_length

    ring = CyclotomicRing(m)
    return find_transform_prime(transform_length(m, ring.degree), log2_q, 1)[0]


def ternary_experimental(log2_q: int = 45) -> TriFHEParams:
    """The leading experimental ternary-aligned candidate.

    m = 8748 = 2^2 * 3^7, N = phi(m) = 2916, Phi_m(X) = X^2916 - X^1458 + 1.
    Sound cyclotomic ring, sparse trinomial, 3^7 in the conductor. Experimental
    because the ring is nonstandard: the transform is bespoke and the structural
    screening in TRI-218 is not done.
    """
    return TriFHEParams(
        ring_size=8748,
        q=_q_for(8748, log2_q),
        ring_kind="smooth_cyclotomic",
        secret_kind="dense_ternary",
        error_sigma=HES_DEFAULT_SIGMA,
        tag=f"TriFHE-experimental-m8748-n2916-q{log2_q}bit",
    )


def ternary_pure(log2_q: int = 45) -> TriFHEParams:
    """The pure 3-power ring at comparable size. m = 3^7, N = 1458."""
    return TriFHEParams(
        ring_size=2187,
        q=_q_for(2187, log2_q),
        ring_kind="smooth_cyclotomic",
        secret_kind="dense_ternary",
        error_sigma=HES_DEFAULT_SIGMA,
        tag=f"TriFHE-pure3-m2187-n1458-q{log2_q}bit",
    )


def baseline_2048(log2_q: int = 45) -> TriFHEParams:
    """Power-of-two implementation and security baseline. m = 4096, N = 2048.

    This is the configuration every published parameter table, every maintained
    FHE library and every prior estimator run agrees on. It is the control: any
    claim about the experimental ring is only meaningful relative to it.
    """
    return TriFHEParams(
        ring_size=4096,
        q=_q_for(4096, log2_q),
        ring_kind="smooth_cyclotomic",
        secret_kind="dense_ternary",
        error_sigma=HES_DEFAULT_SIGMA,
        tag=f"TriFHE-baseline-m4096-n2048-q{log2_q}bit",
    )


def baseline_4096(log2_q: int = 45) -> TriFHEParams:
    """Power-of-two baseline at N = 4096. m = 8192."""
    return TriFHEParams(
        ring_size=8192,
        q=_q_for(8192, log2_q),
        ring_kind="smooth_cyclotomic",
        secret_kind="dense_ternary",
        error_sigma=HES_DEFAULT_SIGMA,
        tag=f"TriFHE-baseline-m8192-n4096-q{log2_q}bit",
    )


def cyclotomic_reading_2187() -> TriFHEParams:
    """The same spec re-read as the 3-power *cyclotomic* ring.

    Lattice dimension becomes phi(3^7) = 1458. This is the charitable reading of
    what the spec probably means, and is a sound ring.
    """
    return TriFHEParams(
        ring_size=2187,
        q=34993,
        ring_kind="ternary_cyclotomic",
        secret_kind="dense_ternary",
        tag="TriFHE-cyclotomic-n1458-q34993",
    )
