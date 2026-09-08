# -*- coding: utf-8 -*-
"""
Generate an auditable security worksheet from audit records.

    python -m trifhe_estimator.worksheet records/*.json --noise records/noise-*.json \
        --out SECURITY-WORKSHEET.md

WHAT "AUDITABLE" MEANS HERE
---------------------------
A number is auditable when a third party can regenerate it without asking you
anything. So the worksheet must carry, for every reported figure:

  * the exact command that produced it,
  * the estimator commit hash and whether its working tree was clean,
  * the Sage and Python versions and the platform,
  * the complete parameter record, including which values were ASSUMED,
  * every attack the estimator costed, in every cost model -- not a selection,
  * the MINIMUM cost across attacks, because that and nothing else is the
    security level,
  * the attacks the estimator does NOT cover, named, so the number is not
    mistaken for a bound over all attacks,
  * and the structural findings that determine whether the number may be quoted
    at all.

Anything the harness could not generate is printed as PENDING with the command
needed to fill it in. A gap that is visible is a gap that gets closed; a gap
that is quietly interpolated becomes a false claim in a document.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
from datetime import datetime, timezone

SEV_MARK = {"blocker": "BLOCKER", "warning": "WARNING", "info": "info", "ok": "ok"}

# Columns worth showing per attack. The estimator emits different keys per
# attack family, so absent keys render as a dash rather than being dropped.
ATTACK_COLS = [
    ("log2_rop", "log2 rop", 1),
    ("beta", "beta", 0),
    ("d", "d", 0),
    ("log2_m", "log2 m", 1),
    ("zeta", "zeta", 0),
    ("eta", "eta", 0),
    ("log2_red", "log2 red", 1),
    ("log2_svp", "log2 svp", 1),
    ("log2_guess", "log2 guess", 1),
]


def fmt(v, places=1):
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{places}f}" if places else f"{v:.0f}"
    return str(v)


def h(text, level=2):
    return f"\n{'#' * level} {text}\n"


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ sections


def section_parameters(rec: dict) -> str:
    i = rec["instance"]
    ring = rec.get("ring")
    rows = [
        ("tag", i["tag"]),
        ("ring kind", i["ring_kind"]),
        ("declared ring size", i["ring_size"]),
        ("lattice dimension n", f"**{i['lattice_dim']}**"),
        ("q", i["q"]),
        ("log2 q", f"{i['log2_q']:.4f}"),
        ("secret distribution", i["secret_kind"]),
        ("error sigma", f"{i['error_sigma_effective']}"
                       + (" (ASSUMED, not specified by the spec)"
                          if i.get("error_sigma_is_assumed") else " (specified)")),
        ("samples m", rec["estimator_instance"].get("m", "-")),
        ("estimator Xs", f"`{rec['estimator_instance']['Xs']}`"),
        ("estimator Xe", f"`{rec['estimator_instance']['Xe']}`"),
    ]
    if ring:
        rows[3:3] = [
            ("conductor m", f"{ring['m']} = {ring.get('factorisation', '?')}"),
            ("degree phi(m)", ring["degree"]),
            ("Phi_m(X)", f"`{ring['phi_str']}`"),
            ("nonzero terms of Phi_m", ring.get("sparsity", "-")),
        ]
    return h("Parameter record", 3) + table(["field", "value"], rows)


def section_findings(rec: dict) -> str:
    f = rec.get("structural_findings", [])
    if not f:
        return h("Structural findings", 3) + "None recorded.\n"
    rows = [(SEV_MARK.get(x["severity"], x["severity"]), x["id"], x["detail"]) for x in f]
    return h("Structural findings", 3) + table(["severity", "id", "detail"], rows)


def section_attacks(rec: dict) -> str:
    out = [h("Attack table (every attack, every cost model)", 3),
           "Security is the MINIMUM over all applicable attacks. Individual rows are "
           "not security levels; the minimum row is.\n"]
    for res in rec.get("results", []):
        out.append(f"\n**Cost model: {res['cost_model']}**"
                   + (" (rough mode)" if res.get("rough") else "")
                   + f" — {res.get('wall_seconds', '?')}s\n")
        attacks = res.get("attacks", [])
        if not attacks:
            out.append("No attacks costed.\n")
            continue
        cheapest = res.get("cheapest_attack")
        headers = ["attack"] + [c[1] for c in ATTACK_COLS]
        rows = []
        for a in sorted(attacks, key=lambda x: x.get("log2_rop") or math.inf):
            name = a["attack"]
            label = f"**{name}** (min)" if name == cheapest else name
            rows.append([label] + [fmt(a.get(k), p) for k, _l, p in ATTACK_COLS])
        out.append(table(headers, rows))
        out.append(f"\nMinimum over attacks in this model: **{res.get('security_bits')} bits** "
                   f"via `{cheapest}`.\n")
        if res.get("saturated"):
            out.append(f"\nSATURATED: {res.get('saturation_note')}\n")
    return "".join(out)


def section_noise(nrec: dict) -> str:
    p, fm, em, v = nrec["params"], nrec["formal_model"], nrec["empirical"], nrec["verdict"]
    out = [h(f"Noise: formal model vs measurement — Phi_{p['conductor']}, "
             f"N = {p['degree']}, log2 q = {p['log2_q']:.2f}", 3)]
    out.append(f"Ring `{p['phi_m']}`, q = {p['q']} (q mod m = {p['q_mod_m']}), "
               f"t = {p['t']}, sigma = {p['sigma']}, secret {p['secret']}, "
               f"gadget base {p['gadget_base']} x {p['gadget_digits']} digits, "
               f"{p['relinearisation']}.\n")
    out.append(table(
        ["stage", "formal sigma_v", "measured sigma_v", "measured/formal", "max v_inf observed"],
        [[label,
          f"2^{math.log2(e['predicted_sigma_v']):.2f}",
          f"2^{math.log2(e['empirical_sigma_v']):.2f}",
          f"{e['ratio_empirical_over_predicted']:.3f}",
          f"{e['observed_max_v_inf']:.3e} ({e['observed_max_over_sigma']:.2f} sigma)"]
         for label, key in (("fresh ciphertext", "fresh"),
                            ("after 1 mult + relin", "after_mult_relin"))
         for e in [em[key]]]))
    a = fm["after_mult_relin"]
    tot = sum(a["variance_terms"].values())
    out.append(h("Variance decomposition after mult + relin", 4))
    out.append(table(["term", "share of variance"],
                     [[k, f"{val / tot * 100:.4f}%"]
                      for k, val in sorted(a["variance_terms"].items(), key=lambda kv: -kv[1])]))
    out.append(f"\nDominant term: **{a['dominant_term']}**. "
               "The original draft's noise formula omitted this term entirely, which is why "
               "its modulus recommendation cannot be reproduced.\n")
    out.append(h("Correctness bound", 4))
    out.append(table(["quantity", "value"], [
        ["tail multiplier D",
         f"{fm['tail']['gaussian_tail_multiplier_D']:.3f} "
         f"(union bound over {fm['tail']['union_bounded_over_coefficients']} coefficients "
         f"at {fm['tail']['per_coefficient_failure_target']})"],
        ["formal bound on v_inf", f"{a['predicted_tail_bound_on_v_inf']:.4e}"],
        ["bound from MEASURED sigma", f"{v['empirical_tail_bound_on_v_inf']:.4e}"],
        ["correctness threshold", "0.5"],
        ["headroom", f"{v['headroom_bits']:.2f} bits"],
        ["minimum log2 q for 1 mult + relin",
         fm.get("min_log2_q_for_one_mult_relin", "-")],
        ["decryption failures observed",
         f"{nrec['decryption']['after_mult_relin_failures']} of {nrec['decryption']['trials']}"],
        ["model agrees with measurement", fmt(v["model_agrees_with_measurement"])],
    ]))
    out.append(f"\n> {v['note']}\n")
    out.append(f"\n> {fm['caveat']}\n")
    out.append(f"\nReproduce: `{nrec['provenance']['command']}`\n")
    return "".join(out)


def section_provenance(rec: dict) -> str:
    pv = rec.get("provenance", {})
    est = pv.get("estimator", {}) or {}
    rows = [
        ("estimator commit", f"`{est.get('commit', 'PENDING')}`"),
        ("estimator commit date", est.get("commit_date", "-")),
        ("estimator commit subject", est.get("commit_subject", "-")),
        ("estimator branch", est.get("branch", "-")),
        ("estimator working tree clean", fmt(est.get("working_tree_clean"))),
        ("Sage version", pv.get("sage_version", "-")),
        ("Python version", pv.get("python_version", "-")),
        ("platform", pv.get("platform", "-")),
        ("harness version", pv.get("harness_version", "-")),
        ("generated at (UTC)", pv.get("generated_at_utc", "-")),
    ]
    if pv.get("command"):
        rows.append(("command", f"`{pv['command']}`"))
    return h("Provenance", 3) + table(["field", "value"], rows)


def section_uncovered(rec: dict) -> str:
    u = rec.get("uncovered_attacks", [])
    if not u:
        return ""
    out = [h("Attacks NOT covered by the estimator", 3),
           "Every figure above is a minimum over the attacks the estimator implements. "
           "It is **not** a bound over all known attacks. These are excluded and must be "
           "costed separately before any figure is quoted as a security level.\n"]
    out.append(table(["attack", "why it is not covered", "reference"],
                     [[x["name"], x["why"], f"<{x.get('reference', '')}>"] for x in u]))
    return "".join(out)


# ------------------------------------------------------------------- builder


def build(records: list[dict], noise: list[dict], pending: list[str]) -> str:
    out = ["# TriFHE security worksheet",
           "",
           f"Generated {datetime.now(timezone.utc).isoformat()}.",
           "",
           "This worksheet exists so that no security figure in the TriFHE hardness "
           "document has to be taken on trust. Every number below is accompanied by the "
           "command, commit and full parameter record needed to regenerate it, the "
           "complete attack table rather than a selected row, and an explicit statement "
           "of what is assumed and what is not covered.",
           ""]

    # ---- headline comparison
    out.append(h("Summary", 2))
    rows = []
    for r in records:
        i, s = r["instance"], r.get("summary", {})
        ring = r.get("ring") or {}
        blockers = [f["id"] for f in r.get("structural_findings", [])
                    if f["severity"] == "blocker"]
        rows.append([
            i["tag"],
            ring.get("m", i["ring_size"]),
            i["lattice_dim"],
            f"{i['log2_q']:.2f}",
            fmt(s.get("security_bits_matzov")),
            fmt(s.get("security_bits_coresvp_quantum")),
            s.get("cheapest_attack_matzov", "-"),
            "QUOTABLE" if s.get("quotable") else "NOT QUOTABLE",
            ", ".join(blockers) or "-",
        ])
    for name in pending:
        rows.append([name, "-", "-", "-", "PENDING", "PENDING", "-", "NOT GENERATED", "-"])
    out.append(table(
        ["parameter set", "conductor m", "n", "log2 q", "min bits (MATZOV)",
         "min bits (CoreSVP quantum)", "cheapest attack", "status", "blockers"],
        rows))
    out.append(
        "\n`min bits` is the minimum over all attacks the estimator costed in that model. "
        "`NOT QUOTABLE` means a structural finding disqualifies the parameter set "
        "regardless of its estimated cost: a large number attached to an unsound ring is "
        "not a security claim.\n")

    if pending:
        out.append(h("Pending estimator runs", 2))
        out.append(
            "The following parameter sets have a validated ring and a validated noise "
            "budget but **no estimator run in this worksheet**, because the SageMath "
            "toolchain was not available in the environment that generated it. They are "
            "listed as PENDING rather than filled in with figures from another source or "
            "from a hand-rolled cost model.\n\n"
            "To fill them in, in an environment with Sage:\n\n"
            "```sh\n"
            "git clone https://github.com/malb/lattice-estimator /path/to/lattice-estimator\n"
            "cd /path/to/lattice-estimator\n"
            "git checkout 53da5982597709ba0fdf94ea37a84d822310fd84\n"
            "cd /path/to/estimator-harness\n")
        for name in pending:
            out.append(f"sage -python -m trifhe_estimator.run_estimate --preset {name} "
                       f"--log2-q 45 --json-out records/{name}.json\n")
        out.append("```\n\nThen regenerate this worksheet:\n\n"
                   "```sh\npython -m trifhe_estimator.worksheet records/*.json "
                   "--noise records/noise-*.json --out SECURITY-WORKSHEET.md\n```\n")

    # ---- noise
    if noise:
        out.append(h("Noise validation", 2))
        out.append(
            "Ring arithmetic and transform correctness are validated by the test suite "
            "(`pytest tests/`), which checks the bespoke transform against schoolbook "
            "reduction modulo the exact cyclotomic at full parameter size. The tables "
            "below then validate the noise MODEL against measurement in that ring.\n")
        nrows = []
        for nrec in sorted(noise, key=lambda r: (r["params"]["degree"], r["params"]["log2_q"])):
            np_, ne, nv = nrec["params"], nrec["empirical"]["after_mult_relin"], nrec["verdict"]
            nrows.append([
                np_["conductor"], np_["degree"], f"{np_['log2_q']:.1f}",
                f"2^{math.log2(ne['predicted_sigma_v']):.2f}",
                f"2^{math.log2(ne['empirical_sigma_v']):.2f}",
                f"{ne['ratio_empirical_over_predicted']:.3f}",
                f"{nv['empirical_tail_bound_on_v_inf']:.3e}",
                f"{nv['headroom_bits']:.2f}",
                "PASS" if nv["empirical_predicted_correct"] else "FAIL",
                f"{nrec['decryption']['after_mult_relin_failures']}/{nrec['decryption']['trials']}",
            ])
        out.append(table(
            ["m", "N", "log2 q", "formal sigma_v", "measured sigma_v", "ratio",
             "tail bound on v_inf", "headroom (bits)", "correctness", "dec failures"],
            nrows))
        out.append(
            "\nThe `log2 q = 29` row is the informative one: it decrypted correctly in "
            "every trial and still FAILS, because its tail bound does not clear 0.5. That "
            "is the whole reason the empirical run cannot stand alone — a few hundred "
            "successful trials say nothing about a 2^-128 failure target. It is also why "
            "the harness exits non-zero on that row rather than reporting zero failures "
            "as a pass.\n")
        for nrec in sorted(noise, key=lambda r: (r["params"]["degree"], r["params"]["log2_q"])):
            out.append(section_noise(nrec))

    # ---- per-parameter detail
    out.append(h("Parameter sets in detail", 2))
    for r in records:
        out.append(h(r["instance"]["tag"], 3).replace("### ", "### "))
        out.append(section_parameters(r))
        out.append(section_findings(r))
        out.append(section_attacks(r))
        out.append(section_provenance(r))

    if records:
        out.append(section_uncovered(records[0]))

    out.append(h("What this worksheet does not claim", 2))
    out.append(
        "- It does not claim any parameter set meets a 128-bit target. It reports "
        "minimum estimator costs and names what is excluded.\n"
        "- It does not claim the nonstandard ternary-aligned ring is as well understood "
        "as a power-of-two cyclotomic. Costing RLWE in a bespoke ring as plain LWE of "
        "dimension phi(m) is standard practice but is not a reduction; subfield and "
        "structural screening remains open.\n"
        "- It does not claim a 2^-128 decryption failure probability has been measured. "
        "A few hundred trials bound failure near 2^-8, not 2^-128. The tail figure is a "
        "Gaussian extrapolation from a MEASURED standard deviation, and the experiment "
        "validates that standard deviation only.\n"
        "- It does not treat key space size as a security level.\n")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the auditable security worksheet")
    ap.add_argument("records", nargs="*", help="estimator audit record JSON files")
    ap.add_argument("--noise", nargs="*", default=[], help="noise experiment JSON files")
    ap.add_argument("--pending", nargs="*", default=[],
                    help="preset names with no estimator run yet")
    ap.add_argument("--out", default="SECURITY-WORKSHEET.md")
    args = ap.parse_args(argv)

    def load(patterns):
        paths: list[str] = []
        for pat in patterns:
            paths.extend(sorted(glob.glob(pat)) or ([pat] if os.path.exists(pat) else []))
        out = []
        for pth in paths:
            with open(pth) as fh:
                out.append(json.load(fh))
        return out

    records = [r for r in load(args.records) if "instance" in r]
    noise = load(args.noise)
    md = build(records, noise, args.pending)
    with open(args.out, "w") as fh:
        fh.write(md)
    print(f"wrote {args.out}: {len(records)} estimator record(s), "
          f"{len(noise)} noise record(s), {len(args.pending)} pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
