#!/usr/bin/env python3
"""Check the semantic thresholds against labelled exemplars, and say which are
actually derived and which were typed by hand.

The README claims the match thresholds trace to hand-labelled (note, criterion)
pairs. This file is that claim, executable. Three checks, ordered by how much
they can embarrass the author:

  1. CITE. Every labelled row must quote a measured score that appears verbatim
     in the shipped output JSON for that exact (protocol, patient, criterion).
     A label that cites nothing is not evidence, it is an opinion with a number
     attached. (Recomputing the scores themselves needs the embedding model, so
     that half of the check lives in `evals/suite.py --full`, which CI runs.)

  2. BRACKET. Score each gating constant against the interval its own labels
     imply. All four constants here are FLOORS: a score at or above the
     constant earns the stronger verdict. So the worst labelled positive must
     sit above the constant and the best labelled negative below it. DERIVED
     means the constant sits inside that interval; REFUTED means its own
     labels contradict it; AUTHORED means no exemplar pair exists on its axis.

  3. PIN. Compare the DERIVED/REFUTED/AUTHORED split against the committed
     expectation in evals/derivation.expected.json and fail on any drift.
     On THIS repo the honest result is refutation: a criterion with no
     support in the note scores 0.29 while a genuinely supported one scores
     0.12, so no threshold on this axis can separate them. The expectation
     file pins that finding as a regression guard; if a code change silently
     "fixes" or worsens the refutation, CI goes red until the expectation is
     re-reviewed and re-committed.

The three verdict tiers make each floor a different question. SEMANTIC_PASS
separates "clearly supported" from everything weaker, so its bracket is
pass-labels above versus uncertain-and-reject labels below. SEMANTIC_MAYBE
separates "worth a human look" from "clearly absent", so its bracket is
pass-and-uncertain above versus reject below. Same rows, different groupings.

COSINE_MAYBE_MARGIN is a band width, not a verdict line; only the derived edge
COSINE_PASS - COSINE_MAYBE_MARGIN can refuse anything, so the margin is scored
through that edge and kept out of the headline count.

Exit 0 all checks pass / 1 a check failed / 2 the labels could not be read.

    python3 evals/derive.py
    python3 evals/derive.py --json
"""
import ast
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS = os.path.join(ROOT, "evals", "labels.csv")
EXPECTED = os.path.join(ROOT, "evals", "derivation.expected.json")
NOTE_PARSER = os.path.join(ROOT, "src", "note_parser.py")
OUTPUTS = {
    "ONC-003-Prevention": os.path.join(ROOT, "output", "ONC-003-Prevention_results.json"),
    "RESP-005-Cessation": os.path.join(ROOT, "output", "RESP-005-Cessation_results.json"),
}

# constant, axis, labels that must sit ABOVE it, labels that must sit BELOW it,
# counted in the headline tally
GATES = [
    ("SEMANTIC_PASS", "semantic_similarity", {"pass"}, {"uncertain", "reject"}, True),
    ("SEMANTIC_MAYBE", "semantic_similarity", {"pass", "uncertain"}, {"reject"}, True),
    ("COSINE_PASS", "cosine_bow", {"pass"}, {"uncertain", "reject"}, True),
    # The MAYBE edge of the cosine fallback is COSINE_PASS - COSINE_MAYBE_MARGIN.
    ("COSINE_PASS - COSINE_MAYBE_MARGIN", "cosine_bow", {"pass", "uncertain"}, {"reject"}, False),
]


def read_constants():
    """Read the named constants from note_parser.py SOURCE, never by importing.

    Importing would execute the module; parsing the AST cannot be fooled by a
    stale __pycache__ and needs no model on the machine running this check.
    """
    with open(NOTE_PARSER, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, (int, float)):
                    consts[target.id] = float(node.value.value)
    return consts


def gate_value(expr, consts):
    """Evaluate a gate expression over the parsed constants (name or a - b)."""
    if " - " in expr:
        a, b = expr.split(" - ")
        return consts[a.strip()] - consts[b.strip()]
    return consts[expr.strip()]


def read_labels():
    with open(LABELS, encoding="utf-8") as fh:
        body = [ln for ln in fh if not ln.lstrip().startswith("#")]
    rows = []
    for r in csv.DictReader(body):
        if not r.get("patient"):
            continue
        try:
            r["measured"] = float(r["measured"])
        except (TypeError, ValueError):
            raise ValueError(
                f"row {r.get('patient')}/{r.get('criterion')!r} has a non-numeric "
                f"measured value {r.get('measured')!r}") from None
        if r["verdict"] not in ("pass", "uncertain", "reject"):
            raise ValueError(
                f"row {r.get('patient')}/{r.get('criterion')!r} has verdict "
                f"{r['verdict']!r}, expected pass/uncertain/reject")
        rows.append(r)
    return rows


def load_outputs():
    out = {}
    for proto, path in OUTPUTS.items():
        with open(path, encoding="utf-8") as fh:
            out[proto] = {p["patient_id"]: p for p in json.load(fh)}
    return out


def main():
    as_json = "--json" in sys.argv
    if not os.path.exists(LABELS):
        print(f"no labels at {LABELS}", file=sys.stderr)
        return 2
    try:
        rows = read_labels()
    except ValueError as exc:
        print(f"labels unreadable: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print(f"{LABELS} parsed to zero rows", file=sys.stderr)
        return 2

    consts = read_constants()
    outputs = load_outputs()
    failures, cited, out = [], [], []

    # --- 1. every label must cite a score that ships in output/ -----------
    for r in rows:
        rec = outputs.get(r["protocol"], {}).get(r["patient"])
        evidence = rec["evidence"].get(r["criterion"]) if rec else None
        if evidence is None:
            failures.append(
                f"{r['patient']}/{r['criterion'][:50]!r}: no such criterion in the "
                f"shipped {r['protocol']} output")
            cited.append({"patient": r["patient"], "ok": False, "why": "missing"})
            continue
        needle = f"score={r['measured']:.2f}"
        fallback = f"semantic={r['measured']:.2f}" if r["axis"] == "semantic_similarity" \
            else f"cosine={r['measured']:.2f}"
        ok = needle in evidence or fallback in evidence
        if not ok:
            failures.append(
                f"{r['patient']}/{r['criterion'][:50]!r}: label says {r['measured']:.2f} "
                f"but the shipped evidence reads {evidence!r}")
        cited.append({"patient": r["patient"], "criterion": r["criterion"][:50],
                      "measured": r["measured"], "ok": ok})

    # --- 2 + 3. bracket and classify --------------------------------------
    for expr, axis, above, below, gating in GATES:
        try:
            value = gate_value(expr, consts)
        except KeyError as exc:
            failures.append(f"constant {exc} no longer exists in note_parser.py")
            continue
        rs = [r for r in rows if r["axis"] == axis]
        highs = [r["measured"] for r in rs if r["verdict"] in above]
        lows = [r["measured"] for r in rs if r["verdict"] in below]

        rec = {"gate": expr, "axis": axis, "value": round(value, 4),
               "gating": gating, "n_above": len(highs), "n_below": len(lows)}
        if highs and lows:
            lo_edge, hi_edge = max(lows), min(highs)
            rec.update(below_edge=lo_edge, above_edge=hi_edge)
            rec["status"] = "DERIVED" if lo_edge < value <= hi_edge else "REFUTED"
        else:
            rec.update(status="AUTHORED", below_edge=None, above_edge=None)
        out.append(rec)

    # Pin the split against the committed expectation. Refutation is a
    # finding, not a failure; DRIFT in the finding is the failure.
    if os.path.exists(EXPECTED):
        try:
            with open(EXPECTED, encoding="utf-8") as fh:
                expected = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            expected = {}
            failures.append(f"pinned expectation unreadable: {exc}")
        for r in out:
            want = expected.get(r["gate"])
            if want is None:
                failures.append(f"{r['gate']} has no pinned expectation in "
                                f"{os.path.relpath(EXPECTED, ROOT)}")
            elif want != r["status"]:
                failures.append(
                    f"{r['gate']} is {r['status']} but the pinned expectation says "
                    f"{want}; review the change, then re-commit the expectation")
        for gate in expected:
            if not any(r["gate"] == gate for r in out):
                failures.append(f"pinned gate {gate!r} no longer exists in GATES")
    else:
        failures.append(
            f"no pinned expectation at {os.path.relpath(EXPECTED, ROOT)}; review the "
            f"split printed below, then commit it: python3 evals/derive.py --json | "
            f"python3 -c \"import json,sys; d=json.load(sys.stdin); print(json.dumps("
            f"{{g['gate']: g['status'] for g in d['gates']}}, indent=2))\" > "
            f"evals/derivation.expected.json")

    gates = [r for r in out if r["gating"]]
    derived = [r for r in gates if r["status"] == "DERIVED"]
    authored = [r for r in gates if r["status"] == "AUTHORED"]
    refuted = [r for r in gates if r["status"] == "REFUTED"]

    if as_json:
        print(json.dumps({"gates": out, "cited": cited, "n_labels": len(rows),
                          "derived": len(derived), "authored": len(authored),
                          "refuted": len(refuted), "n_gating": len(gates),
                          "failures": failures}, indent=2))
        return 1 if failures else 0

    n_ok = sum(1 for c in cited if c["ok"])
    print(f"CITED: {n_ok} of {len(rows)} labelled rows quote a score found verbatim "
          f"in the shipped output JSON.")
    print(f"\n{'GATE':38s} {'VALUE':>7s}  {'BELOW EDGE':>10s} {'ABOVE EDGE':>10s}  STATUS")
    for r in out:
        lo = f"{r['below_edge']:.2f}" if r["below_edge"] is not None else "-"
        hi = f"{r['above_edge']:.2f}" if r["above_edge"] is not None else "-"
        tail = "" if r["gating"] else "  (band edge, not counted)"
        print(f"{r['gate']:38s} {r['value']:>7.2f}  {lo:>10s} {hi:>10s}  {r['status']}{tail}")

    print(f"\n{len(derived)} of {len(gates)} named gating thresholds are DERIVED from "
          f"labelled exemplars on both sides.")
    if authored:
        print(f"{len(authored)} are AUTHORED: typed by hand, no exemplar pair on their axis.")
    if refuted:
        print(f"{len(refuted)} are REFUTED by their own labels: no value on this axis "
              f"separates the labelled supported rows from the unsupported ones. That "
              f"finding is pinned in {os.path.relpath(EXPECTED, ROOT)} and guarded by CI.")

    if failures:
        print("\nFAILURES")
        for f in failures:
            print(f"  {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
