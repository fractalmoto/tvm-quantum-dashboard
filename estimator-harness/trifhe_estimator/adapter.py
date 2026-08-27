# -*- coding: utf-8 -*-
"""
Adapter: TriFHEParams -> lattice-estimator LWE.Parameters.

This is the only module that imports the estimator (and therefore SageMath). It
does exactly one job: turn a declared TriFHE instance into the estimator's own
data type without editorialising, and record every modelling decision it had to
make so the decision appears in the audit record rather than in a comment.

Run under Sage's Python:  sage -python -m trifhe_estimator.run_estimate
"""

from __future__ import annotations

import sys
from typing import Any

from .params import TriFHEParams

# The estimator is a Sage library; it is not pip-installable and must be on
# sys.path as a checkout. `ESTIMATOR_PATH` is injected by run_estimate.py.


def _import_estimator(estimator_path: str):
    if estimator_path not in sys.path:
        sys.path.insert(0, estimator_path)
    try:
        from estimator import LWE, ND, RC  # noqa: N811
        from estimator.reduction import ADPS16
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Could not import the lattice-estimator. It requires SageMath and must be "
            "run as `sage -python`, with ESTIMATOR_PATH pointing at a checkout of "
            "https://github.com/malb/lattice-estimator. "
            f"Underlying error: {exc}"
        ) from exc
    return LWE, ND, RC, ADPS16


def build_secret_distribution(p: TriFHEParams, ND, n: int):
    """Map the declared secret to an estimator noise distribution.

    Returns (distribution, decision_record).
    """
    if p.secret_kind == "dense_ternary":
        # Uniform on {-1, 0, +1}: stddev sqrt(2/3) ~ 0.8165, density 2/3.
        return ND.Uniform(-1, 1, n), dict(
            field="Xs",
            mapped_to="ND.Uniform(-1, 1, n)",
            rationale=(
                "Dense ternary secret. The estimator models this as uniform on the "
                "inclusive integer range [-1, 1], giving stddev sqrt(2/3) and density 2/3. "
                "This is the same modelling the HE Standard uses for ternary secrets."
            ),
        )
    if p.secret_kind == "sparse_ternary":
        h = p.hamming_weight
        plus = h // 2
        minus = h - plus
        return ND.SparseTernary(plus, minus, n), dict(
            field="Xs",
            mapped_to=f"ND.SparseTernary(p={plus}, m={minus}, n={n})",
            rationale=(
                f"Sparse ternary with Hamming weight {h}, split as {plus} entries of +1 and "
                f"{minus} of -1. The estimator needs the signed split, not just the weight; "
                "a balanced split is assumed because the spec does not state one. An "
                "unbalanced split changes the secret's mean and slightly changes the estimate."
            ),
        )
    if p.secret_kind == "gaussian":
        return ND.DiscreteGaussian(p.secret_sigma, n=n), dict(
            field="Xs",
            mapped_to=f"ND.DiscreteGaussian({p.secret_sigma}, n={n})",
            rationale="Gaussian secret as declared.",
        )
    raise ValueError(f"unhandled secret_kind {p.secret_kind}")


def to_lwe_parameters(p: TriFHEParams, estimator_path: str) -> tuple[Any, list[dict]]:
    """Build the estimator's LWEParameters object.

    Returns (LWEParameters, list_of_modelling_decisions).
    """
    LWE, ND, RC, _ = _import_estimator(estimator_path)
    from sage.all import oo

    n = p.lattice_dim
    decisions: list[dict] = []

    decisions.append(
        dict(
            field="n",
            mapped_to=str(n),
            rationale=(
                f"Ring '{p.ring_kind}' at declared size {p.ring_size} gives LWE dimension {n}. "
                "The RLWE-to-LWE reduction is treated as dimension-preserving: no known attack "
                "exploits the ring structure of a general cyclotomic to beat the plain-LWE cost, "
                "so estimating the plain-LWE instance of the same dimension is the standard and "
                "conservative practice. This does NOT hold for rings with exploitable subfields."
            ),
        )
    )

    Xs, xs_decision = build_secret_distribution(p, ND, n)
    decisions.append(xs_decision)

    Xe = ND.DiscreteGaussian(p.error_sigma_effective)
    decisions.append(
        dict(
            field="Xe",
            mapped_to=f"ND.DiscreteGaussian({p.error_sigma_effective})",
            rationale=(
                "Discrete Gaussian error."
                + (
                    " WIDTH IS ASSUMED, NOT SPECIFIED: the source specification gives no error "
                    "distribution, so the HE Standard v1.1 value sigma = 3.19 is substituted. "
                    "Every bit-security number in this run is conditional on that assumption and "
                    "is void if the implementation uses a different width."
                    if p.error_sigma_is_assumed
                    else " Width taken from the specification."
                )
            ),
        )
    )

    m = oo if p.samples is None else p.samples
    decisions.append(
        dict(
            field="m",
            mapped_to="oo (unbounded)" if p.samples is None else str(p.samples),
            rationale=(
                "Unbounded samples is the estimator default and the conservative choice: it lets "
                "sample-hungry attacks (BKW, dual with amplification) reach their best cost. A "
                "real RLWE deployment publishes far fewer, so also run with m = n to see the "
                "sample-limited figure."
                if p.samples is None
                else f"Adversary limited to {p.samples} samples."
            ),
        )
    )

    params = LWE.Parameters(n=n, q=p.q, Xs=Xs, Xe=Xe, m=m, tag=p.tag)
    return params, decisions


def cost_models(estimator_path: str) -> dict[str, Any]:
    """The cost models the harness reports against.

    Reporting more than one is the point. A single number from a single model is
    what auditors reject; the spread between MATZOV and core-SVP-classical is the
    honest error bar on the claim.
    """
    _, _, RC, ADPS16 = _import_estimator(estimator_path)
    return {
        # Estimator default. Concrete, gate-counted, includes sieving overheads.
        "MATZOV": RC.MATZOV,
        # Core-SVP, the conservative lower bound convention used by NIST PQC
        # submissions. 2^(0.292 beta) classical.
        "CoreSVP_classical": ADPS16(mode="classical"),
        # 2^(0.265 beta). The quantum speedup on sieving only; this is the number
        # to quote for "quantum security", NOT anything derived from Shor.
        "CoreSVP_quantum": ADPS16(mode="quantum"),
        # 2^(0.2075 beta). Deliberately pessimistic floor.
        "CoreSVP_paranoid": ADPS16(mode="paranoid"),
    }


# Attacks the estimator does NOT cover. These must ride along with every result
# so a reader cannot mistake the matrix for a complete cryptanalysis.
UNCOVERED_ATTACKS = [
    dict(
        name="Meet-LWE (May, CRYPTO 2021)",
        why="Representation-technique MitM against small/sparse secrets. Not implemented in the estimator; must be costed separately for ternary secrets.",
        reference="https://eprint.iacr.org/2021/216",
    ),
    dict(
        name="Cool and Cruel / statistical dual",
        why="Exploits the uneven contribution of secret coordinates. Reported to beat estimator dual costs for sparse and small secrets.",
        reference="https://arxiv.org/abs/2403.10328",
    ),
    dict(
        name="Subfield / Gentry-Szydlo-style structural attacks",
        why="Applies when the ring has exploitable subfields or the modulus splits badly. Entirely outside the estimator's plain-LWE model.",
        reference="https://eprint.iacr.org/2015/106",
    ),
    dict(
        name="IND-CPA^D / decryption-failure attacks",
        why="Approximate-FHE key recovery from decryption results. Orthogonal to lattice hardness; a scheme can be 128-bit hard and still fully broken here.",
        reference="https://eprint.iacr.org/2020/1533",
    ),
]
