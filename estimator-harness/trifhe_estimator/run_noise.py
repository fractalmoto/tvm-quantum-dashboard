# -*- coding: utf-8 -*-
"""
CLI for the empirical invariant-noise experiment.

    python -m trifhe_estimator.run_noise --preset ternary-experimental --trials 128
    python -m trifhe_estimator.run_noise --m 8748 --log2-q 29 --trials 256 \
        --json-out records/noise-m8748-q29.json

Exit code is 2 when the run contradicts the formal model or observes a
decryption failure, so CI fails loudly rather than letting an unvalidated noise
claim reach a document — the same convention as run_estimate.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import time
from datetime import datetime, timezone

from .bfv import BFVParams
from .noise import formal_model, min_log2_q_for_one_mult, run_experiment

# Presets mirror the parameter programme: one experimental ternary-aligned
# candidate, two power-of-two baselines, and the pure 3-power ring for contrast.
PRESETS = {
    "ternary-experimental": dict(m=8748, log2_q=45),
    "ternary-experimental-edge": dict(m=8748, log2_q=29),
    "ternary-pure": dict(m=2187, log2_q=45),
    "baseline-2048": dict(m=4096, log2_q=45),
    "baseline-4096": dict(m=8192, log2_q=45),
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="TriFHE empirical noise experiment")
    ap.add_argument("--preset", choices=sorted(PRESETS))
    ap.add_argument("--m", type=int, help="conductor (NOT the degree)")
    ap.add_argument("--log2-q", type=int)
    ap.add_argument("--t", type=int, default=3, help="plaintext modulus")
    ap.add_argument("--sigma", type=float, default=3.19)
    ap.add_argument("--gadget-base-bits", type=int, default=15)
    ap.add_argument("--trials", type=int, default=128)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--log2-failure", type=float, default=-128.0)
    ap.add_argument("--json-out")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.preset:
        cfg = dict(PRESETS[args.preset])
    else:
        if not (args.m and args.log2_q):
            ap.error("provide --preset, or both --m and --log2-q")
        cfg = dict(m=args.m, log2_q=args.log2_q)

    p = BFVParams(
        m=cfg["m"], log2_q=cfg["log2_q"], t=args.t, sigma=args.sigma,
        gadget_base_bits=args.gadget_base_bits, seed=args.seed,
    )

    t0 = time.time()

    def progress(i, n):
        if not args.quiet and (i % 8 == 0 or i == n):
            el = time.time() - t0
            print(f"  trial {i}/{n}  ({el:.0f}s elapsed, {el / i:.2f}s/trial)", flush=True)

    if not args.quiet:
        print(f"ring: Phi_{p.m} degree {p.N}, q = {p.q} (log2 = {p.log2_q_exact:.2f}), "
              f"t = {p.t}, sigma = {p.sigma}, gadget 2^{args.gadget_base_bits} x {p.ell}")
        print(f"running {args.trials} trials of 1 mult + relin ...", flush=True)

    rec = run_experiment(p, args.trials, seed=args.seed,
                         log2_failure=args.log2_failure, progress=progress)
    rec["provenance"] = dict(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        harness_version="1.1.0",
        wall_seconds=round(time.time() - t0, 1),
        command=" ".join(["python", "-m", "trifhe_estimator.run_noise"] + (argv or sys.argv[1:])),
    )
    rec["formal_model"]["min_log2_q_for_one_mult_relin"] = min_log2_q_for_one_mult(
        p.m, t=p.t, sigma=p.sigma, gadget_base_bits=args.gadget_base_bits,
        log2_failure=args.log2_failure,
    )

    if not args.quiet:
        report(rec)

    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w") as fh:
            json.dump(rec, fh, indent=2, default=str)
        print(f"\nnoise record written to {args.json_out}")

    v = rec["verdict"]
    reasons = []
    if not v["model_agrees_with_measurement"]:
        reasons.append(
            "measured sigma_v is more than a factor of two from the model, so neither "
            "the model nor the measurement can be relied on"
        )
    if rec["decryption"]["fresh_failures"] or rec["decryption"]["after_mult_relin_failures"]:
        reasons.append("a decryption failure was observed")
    if not v["empirical_predicted_correct"]:
        # Zero observed failures over a few hundred trials is NOT a pass. The
        # tail bound is what the parameter set has to clear, and at the edge of
        # the noise budget typical noise looks fine while the tail does not.
        reasons.append(
            "the tail bound from the measured sigma is "
            f"{v['empirical_tail_bound_on_v_inf']:.4g}, which does not clear the 0.5 "
            f"correctness threshold ({v['headroom_bits']:.2f} bits of headroom), even "
            f"though all {rec['decryption']['trials']} trials happened to decrypt correctly"
        )
    if reasons and not args.quiet:
        print("\nNOT QUOTABLE:")
        for r in reasons:
            print(f"  - {r}")
    return 0 if not reasons else 2


def report(rec: dict) -> None:
    w = 78
    fm = rec["formal_model"]
    em = rec["empirical"]
    print("=" * w)
    print("INVARIANT NOISE: FORMAL MODEL vs MEASUREMENT")
    print("=" * w)
    print(f"{'':32}{'formal':>16}{'measured':>16}{'ratio':>10}")
    for stage, key in (("fresh ciphertext", "fresh"), ("after 1 mult + relin", "after_mult_relin")):
        e = em[key]
        print(f"{stage:32}{'2^%.2f' % math.log2(e['predicted_sigma_v']):>16}"
              f"{'2^%.2f' % math.log2(e['empirical_sigma_v']):>16}"
              f"{e['ratio_empirical_over_predicted']:>10.3f}")
    print()
    a = fm["after_mult_relin"]
    print(f"dominant variance term : {a['dominant_term']} ({a['dominant_share'] * 100:.1f}%)")
    print("variance decomposition after mult + relin:")
    tot = sum(a["variance_terms"].values())
    for k, val in sorted(a["variance_terms"].items(), key=lambda kv: -kv[1]):
        print(f"    {k:46} {val / tot * 100:7.3f}%")
    print()
    print(f"tail multiplier D          : {fm['tail']['gaussian_tail_multiplier_D']:.3f} "
          f"(union bound over {fm['tail']['union_bounded_over_coefficients']} coefficients "
          f"at {fm['tail']['per_coefficient_failure_target']})")
    print(f"formal    bound on ||v||inf : {a['predicted_tail_bound_on_v_inf']:.6g}  "
          f"(threshold 0.5)  correct={a['predicted_correct']}")
    v = rec["verdict"]
    print(f"empirical bound on ||v||inf : {v['empirical_tail_bound_on_v_inf']:.6g}  "
          f"correct={v['empirical_predicted_correct']}  "
          f"headroom {v['headroom_bits']:.2f} bits")
    print(f"largest ||v||inf actually observed: {em['after_mult_relin']['observed_max_v_inf']:.6g} "
          f"({em['after_mult_relin']['observed_max_over_sigma']:.2f} sigma)")
    print(f"decryption failures: fresh {rec['decryption']['fresh_failures']}, "
          f"after mult {rec['decryption']['after_mult_relin_failures']} "
          f"of {rec['decryption']['trials']} trials")
    print()
    print("-" * w)
    print(v["note"])
    print("-" * w)
    print("MODEL AGREES WITH MEASUREMENT" if v["model_agrees_with_measurement"]
          else "MODEL DOES NOT AGREE WITH MEASUREMENT -- do not use either number")
    print("=" * w)


if __name__ == "__main__":
    raise SystemExit(main())
