# -*- coding: utf-8 -*-
"""
Reproducible TriFHE hardness harness.

Runs the official lattice-estimator over a declared TriFHE instance across every
attack the estimator implements and every cost model we report against, then
emits a single JSON record containing:

  * the instance, exactly as declared
  * every modelling decision the adapter had to make, with its rationale
  * structural findings that do not need the estimator at all
  * the full attack cost matrix
  * a provenance block: estimator commit, Sage version, host, UTC timestamp
  * the attacks the estimator does not cover

The JSON record is the audit artifact. The pretty-printed table is a convenience.

USAGE
-----
    sage -python -m trifhe_estimator.run_estimate --preset draft
    sage -python -m trifhe_estimator.run_estimate --n 2187 --q 34993 --secret dense_ternary
    sage -python -m trifhe_estimator.run_estimate --preset draft --rough    # fast smoke test

`--rough` calls LWE.estimate.rough, which runs a reduced attack set with
optimistic assumptions. It is for iterating on the harness only. Never quote a
rough number: the emitted record marks it `"rough": true` for exactly that reason.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

from .params import (
    TriFHEParams,
    draft_spec_2187,
    cyclotomic_reading_2187,
)
from .adapter import to_lwe_parameters, cost_models, UNCOVERED_ATTACKS

DEFAULT_ESTIMATOR_PATH = os.environ.get(
    "ESTIMATOR_PATH", "/home/user/workspace/lattice-estimator"
)

PRESETS = {
    "draft": draft_spec_2187,
    "cyclotomic": cyclotomic_reading_2187,
}


# --------------------------------------------------------------- provenance

def git_provenance(path: str) -> dict:
    def run(*args) -> str | None:
        try:
            return subprocess.check_output(
                args, cwd=path, stderr=subprocess.DEVNULL, text=True
            ).strip()
        except Exception:
            return None

    dirty = run("git", "status", "--porcelain")
    return dict(
        path=path,
        commit=run("git", "rev-parse", "HEAD"),
        commit_date=run("git", "log", "-1", "--format=%cI"),
        commit_subject=run("git", "log", "-1", "--format=%s"),
        branch=run("git", "rev-parse", "--abbrev-ref", "HEAD"),
        working_tree_clean=(dirty == "" if dirty is not None else None),
    )


def sage_version() -> str | None:
    try:
        from sage.env import SAGE_VERSION

        return SAGE_VERSION
    except Exception:
        try:
            import sage.all  # noqa: F401
            from sage.version import version

            return version
        except Exception:
            return None


def provenance(estimator_path: str) -> dict:
    return dict(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        estimator=git_provenance(estimator_path),
        sage_version=sage_version(),
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        harness_version="1.0.0",
    )


# ------------------------------------------------------------ result shaping

def _to_float(x):
    """Estimator costs are Sage RealField / Integer objects. Normalise to float."""
    try:
        return float(x)
    except Exception:
        return None


def _log2(x):
    v = _to_float(x)
    if v is None or v <= 0:
        return None
    return math.log2(v)


def flatten_cost(name: str, cost) -> dict:
    """Turn one estimator Cost object into a JSON-safe row."""
    row: dict = {"attack": name}
    try:
        items = dict(cost)
    except Exception:
        items = {}

    rop = items.get("rop")
    row["log2_rop"] = _log2(rop)
    for key in ("mem", "m", "red", "svp", "guess", "repetitions"):
        if key in items:
            row[f"log2_{key}"] = _log2(items[key])
    for key in ("beta", "d", "eta", "zeta", "t", "p", "delta", "b", "k"):
        for cand in (key, {"beta": "β", "eta": "η", "zeta": "ζ", "delta": "δ"}.get(key)):
            if cand and cand in items:
                row[key] = _to_float(items[cand])
                break
    row["raw"] = {str(k): str(v) for k, v in items.items()}
    return row


# `arora-gb` and `bkw` are never competitive against an FHE-sized instance with a
# small secret, but their optimisation loops are by far the slowest part of a full
# estimate -- they can add tens of minutes at n > 2000. Denying them by default
# keeps a full (non-rough) run tractable; every denial is recorded in the audit
# record so the omission is visible rather than silent.
DEFAULT_DENY = ("arora-gb", "bkw")


def run_one_model(
    lwe_params, model_name, model, LWE, rough: bool, deny: tuple = (), jobs: int = 1
) -> dict:
    t0 = time.time()
    try:
        if rough:
            res = LWE.estimate.rough(lwe_params, quiet=True, jobs=jobs)
        else:
            res = LWE.estimate(
                lwe_params,
                red_cost_model=model,
                deny_list=tuple(deny),
                jobs=jobs,
                quiet=True,
                catch_exceptions=True,
            )
    except Exception as exc:
        return dict(
            cost_model=model_name,
            error=f"{type(exc).__name__}: {exc}",
            wall_seconds=round(time.time() - t0, 1),
        )

    rows = [flatten_cost(name, cost) for name, cost in res.items()]
    valid = [
        r["log2_rop"]
        for r in rows
        if r["log2_rop"] is not None and math.isfinite(r["log2_rop"])
    ]
    finite = [r for r in rows if r["log2_rop"] is not None and math.isfinite(r["log2_rop"])]
    cheapest = min(finite, key=lambda r: r["log2_rop"]) if finite else None

    # The estimator caps block size at conf.max_beta (1754, ~2^512). An estimate
    # whose optimal beta sits near that cap is saturated: the true cost is at
    # least this, but the figure is a floor imposed by the search bound, not a
    # converged optimum. Reporting it as an exact bit count is wrong.
    max_beta = 1754
    saturated = any(
        (r.get("beta") or 0) > 0.9 * max_beta for r in finite
    )

    return dict(
        cost_model=model_name,
        rough=rough,
        denied_attacks=list(deny),
        wall_seconds=round(time.time() - t0, 1),
        attacks=sorted(rows, key=lambda r: r["log2_rop"] or math.inf),
        # THE security level for this cost model: the cheapest attack, not the
        # average and certainly not the most expensive.
        security_bits=round(min(valid), 1) if valid else None,
        cheapest_attack=cheapest["attack"] if cheapest else None,
        saturated=saturated,
        saturation_note=(
            "Optimal block size is within 10% of the estimator's max_beta bound (1754). "
            "Read the figure as a LOWER BOUND ('at least ~N bits'), not an exact level. "
            "Attacks that returned infinite cost were pruned by the same bound."
            if saturated
            else None
        ),
    )


def estimate(
    p: TriFHEParams,
    estimator_path: str,
    rough: bool = False,
    deny: tuple = DEFAULT_DENY,
    jobs: int = 1,
) -> dict:
    lwe_params, decisions = to_lwe_parameters(p, estimator_path)
    sys.path.insert(0, estimator_path) if estimator_path not in sys.path else None
    from estimator import LWE

    models = cost_models(estimator_path)
    if rough:
        # LWE.estimate.rough ignores red_cost_model entirely (it hardcodes its own
        # optimistic model), so running it once per cost model would emit four
        # identical rows and imply a spread that does not exist.
        results = [
            run_one_model(
                lwe_params, "rough (model-independent)", None, LWE, True, jobs=jobs
            )
        ]
    else:
        results = [
            run_one_model(lwe_params, name, model, LWE, False, deny=deny, jobs=jobs)
            for name, model in models.items()
        ]

    headline = next(
        (r for r in results if r["cost_model"] == "MATZOV" and r.get("security_bits")),
        None,
    )
    conservative = next(
        (
            r
            for r in results
            if r["cost_model"] == "CoreSVP_quantum" and r.get("security_bits")
        ),
        None,
    )

    findings = p.structural_findings()
    blockers = [f for f in findings if f["severity"] == "blocker"]

    return dict(
        instance=p.to_dict(),
        estimator_instance=dict(
            n=int(lwe_params.n),
            q=int(lwe_params.q),
            Xs=str(lwe_params.Xs),
            Xe=str(lwe_params.Xe),
            m=str(lwe_params.m),
            tag=lwe_params.tag,
        ),
        modelling_decisions=decisions,
        structural_findings=findings,
        results=results,
        summary=dict(
            security_bits_matzov=headline["security_bits"] if headline else None,
            security_bits_coresvp_quantum=(
                conservative["security_bits"] if conservative else None
            ),
            saturated=any(r.get("saturated") for r in results),
            cheapest_attack_matzov=headline["cheapest_attack"] if headline else None,
            keyspace_log2=p.keyspace_log2,
            # The whole reason the harness exists.
            quotable=len(blockers) == 0 and not rough,
            not_quotable_because=(
                [b["id"] for b in blockers] + (["rough-mode"] if rough else []) or None
            ),
        ),
        uncovered_attacks=UNCOVERED_ATTACKS,
        provenance=provenance(estimator_path),
    )


# ----------------------------------------------------------------- printing

def print_report(rec: dict) -> None:
    inst = rec["instance"]
    w = 78
    print("=" * w)
    print(f"TriFHE hardness harness  |  {inst['tag']}")
    print("=" * w)
    print(
        f"declared N={inst['ring_size']}  ring={inst['ring_kind']}  ->  LWE dimension n={inst['lattice_dim']}"
    )
    print(
        f"q={inst['q']} (log2 q = {inst['log2_q']:.2f})   secret={inst['secret_kind']}   "
        f"sigma_e={inst['error_sigma_effective']:.2f}"
        + ("  [ASSUMED]" if inst["error_sigma_is_assumed"] else "")
    )
    if inst.get("keyspace_log2"):
        print(f"raw keyspace ~ 2^{inst['keyspace_log2']:.0f}   <-- NOT a security level")
    print()

    print("-" * w)
    print("STRUCTURAL FINDINGS (no estimator required)")
    print("-" * w)
    order = {"blocker": 0, "warning": 1, "info": 2, "ok": 3}
    for f in sorted(rec["structural_findings"], key=lambda f: order.get(f["severity"], 9)):
        print(f"[{f['severity'].upper():8}] {f['id']}")
        for line in _wrap(f["detail"], w - 12):
            print(f"            {line}")
    print()

    print("-" * w)
    print("ATTACK COST MATRIX  (log2 of operation count; lower = weaker)")
    print("-" * w)
    for res in rec["results"]:
        if res.get("error"):
            print(f"{res['cost_model']:22} ERROR: {res['error']}")
            continue
        bound = ">= " if res.get("saturated") else ""
        print(
            f"{res['cost_model']:22} security = {bound}{res['security_bits']} bits "
            f"via '{res['cheapest_attack']}'   ({res['wall_seconds']}s)"
        )
        if res.get("saturation_note"):
            for line in _wrap("SATURATED: " + res["saturation_note"], w - 4):
                print(f"    {line}")
        if res.get("denied_attacks"):
            print(f"    (skipped: {', '.join(res['denied_attacks'])})")
        for a in res["attacks"]:
            if a["log2_rop"] is None:
                print(f"    {a['attack']:20} (no estimate)")
                continue
            extra = []
            if a.get("beta"):
                extra.append(f"beta={a['beta']:.0f}")
            if a.get("d"):
                extra.append(f"d={a['d']:.0f}")
            if a.get("log2_mem") is not None:
                extra.append(f"mem=2^{a['log2_mem']:.1f}")
            print(
                f"    {a['attack']:20} 2^{a['log2_rop']:.1f}"
                + ("   " + "  ".join(extra) if extra else "")
            )
        print()

    print("-" * w)
    print("NOT COVERED BY THIS MATRIX")
    print("-" * w)
    for u in rec["uncovered_attacks"]:
        print(f"  - {u['name']}")
        for line in _wrap(u["why"], w - 6):
            print(f"      {line}")
        print(f"      {u['reference']}")
    print()

    s = rec["summary"]
    print("=" * w)
    if s["quotable"]:
        print(f"QUOTABLE: {s['security_bits_matzov']} bits (MATZOV), "
              f"{s['security_bits_coresvp_quantum']} bits (core-SVP quantum)")
    else:
        print("NOT QUOTABLE as a security level. Reasons: "
              + ", ".join(s["not_quotable_because"] or []))
        print("Fix the blockers above before any number from this run is used in a claim.")
    print("=" * w)


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        if len(cur) + len(word) + 1 > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


# --------------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--preset", choices=sorted(PRESETS), help="named parameter set")
    ap.add_argument("--n", type=int, help="declared ring size N")
    ap.add_argument("--q", type=int, help="ciphertext modulus")
    ap.add_argument(
        "--ring",
        default="negacyclic_pow3",
        choices=["power_of_two_cyclotomic", "ternary_cyclotomic", "negacyclic_pow3"],
    )
    ap.add_argument(
        "--secret",
        default="dense_ternary",
        choices=["dense_ternary", "sparse_ternary", "gaussian"],
    )
    ap.add_argument("--hamming-weight", type=int)
    ap.add_argument("--sigma-e", type=float, help="error stddev (omit to use HES 3.19)")
    ap.add_argument("--samples", type=int, help="limit adversary samples m")
    ap.add_argument("--tag")
    ap.add_argument("--rough", action="store_true", help="fast smoke test; NOT quotable")
    ap.add_argument(
        "--deny",
        default=",".join(DEFAULT_DENY),
        help=("comma-separated attacks to skip. Default '%(default)s' (never "
              "competitive here, dominate runtime). Pass '' to run everything."),
    )
    ap.add_argument("--jobs", type=int, default=1, help="estimator worker threads")
    ap.add_argument("--estimator-path", default=DEFAULT_ESTIMATOR_PATH)
    ap.add_argument("--json-out", help="write the audit record here")
    args = ap.parse_args(argv)

    if args.preset:
        p = PRESETS[args.preset]()
        if args.sigma_e or args.samples:
            from dataclasses import replace

            p = replace(
                p,
                error_sigma=args.sigma_e or p.error_sigma,
                samples=args.samples if args.samples else p.samples,
            )
    else:
        if not (args.n and args.q):
            ap.error("provide --preset, or both --n and --q")
        p = TriFHEParams(
            ring_size=args.n,
            q=args.q,
            ring_kind=args.ring,
            secret_kind=args.secret,
            hamming_weight=args.hamming_weight,
            error_sigma=args.sigma_e,
            samples=args.samples,
            tag=args.tag or f"TriFHE-n{args.n}-q{args.q}",
        )

    deny = tuple(x.strip() for x in args.deny.split(",") if x.strip())
    rec = estimate(
        p, args.estimator_path, rough=args.rough, deny=deny, jobs=args.jobs
    )
    print_report(rec)

    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w") as fh:
            json.dump(rec, fh, indent=2, default=str)
        print(f"\naudit record written to {args.json_out}")

    # Exit non-zero when the run produced something that must not be quoted, so
    # CI fails loudly rather than a bad number reaching a document.
    return 0 if rec["summary"]["quotable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
