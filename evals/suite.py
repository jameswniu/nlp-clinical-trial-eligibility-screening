#!/usr/bin/env python3
"""The 50-decision golden gate.

Two tiers, priced differently:

  --dry-run   Free. No model download, no torch import. Checks that the golden
              files still describe exactly 50 decisions with a closed verdict
              vocabulary, that every stored confidence re-derives from its own
              stored verdicts (the formula cannot drift silently), that the
              any-FAIL-disqualifies invariant holds on every record, and that
              the data the pipeline reads is still present and parseable.
              This is what the CI `checks` job runs on every push.

  --full      Recomputes all 50 decisions with the real embedding model and
              compares them to the goldens. Eligibility and verdict labels
              must match exactly; scores get 0.02 tolerance, since embedding
              stacks differ across torch builds and a real regression moves a
              verdict, not a third decimal. Also re-measures every labels.csv
              row, closing the loop derive.py leaves open. This is the CI
              `eval-full` job.

Exit 0 green / 1 a check failed.

    python3 evals/suite.py --dry-run
    python3 evals/suite.py --full [--json]
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, "evals", "golden")
PROTOCOLS = ["ONC-003-Prevention", "RESP-005-Cessation"]
SCORE_TOL = 0.02
EXPECTED_PATIENTS = 25

# Tier 2: the pinned regression cohort. 175 generated patients, audited by
# planted-trap manifest plus samples, never blended into the verified tier.
# cohort.expected.json pins what the pipeline actually produces;
# known_wrong.expected.json is the ledger of pinned verdicts the audit judged
# WRONG (mostly negation traps the similarity lane cannot see). A change that
# silently "fixes" a known-wrong case reds the replay until both files are
# re-audited together.
COHORT_ROOT = os.path.join(ROOT, "cohort")
COHORT_GOLDEN = os.path.join(ROOT, "evals", "cohort.expected.json")
KNOWN_WRONG = os.path.join(ROOT, "evals", "known_wrong.expected.json")
TRAPS = os.path.join(COHORT_ROOT, "traps.json")
COHORT_PATIENTS = 175


def cohort_present():
    return os.path.exists(COHORT_GOLDEN) and os.path.isdir(COHORT_ROOT)


def load_golden():
    data = {}
    for proto in PROTOCOLS:
        path = os.path.join(GOLDEN, f"{proto}.expected.json")
        with open(path, encoding="utf-8") as fh:
            data[proto] = {p["patient_id"]: p for p in json.load(fh)}
    return data


def verdict_of(evidence_str):
    return evidence_str.split(" ")[0]


def check_record(proto, pid, rec, failures):
    """Structural checks every golden record must satisfy on its own."""
    verdicts = [verdict_of(v) for v in rec["evidence"].values()]
    bad = [v for v in verdicts if v not in ("PASS", "MAYBE", "FAIL")]
    if bad:
        failures.append(f"{proto}/{pid}: unknown verdict label(s) {bad}")
        return
    n_pass = verdicts.count("PASS")
    n_maybe = verdicts.count("MAYBE")
    n_fail = verdicts.count("FAIL")
    total = len(verdicts)
    elig, score = rec["is_eligible"], rec["confidence_score"]

    if n_fail > 0:
        if elig is not False or score != "NA":
            failures.append(
                f"{proto}/{pid}: has {n_fail} FAIL but is_eligible={elig!r}, "
                f"score={score!r} (any FAIL must disqualify)")
        return
    expected = round((n_pass + 0.5 * n_maybe) / total, 3) if total else 0.0
    if not isinstance(score, (int, float)) or abs(score - expected) > 0.0005:
        failures.append(
            f"{proto}/{pid}: stored confidence {score!r} does not re-derive from "
            f"its own verdicts (PASS={n_pass}, MAYBE={n_maybe} -> {expected})")
    want = True if expected > 0.5 else "MAYBE"
    if elig != want:
        failures.append(
            f"{proto}/{pid}: eligibility {elig!r} inconsistent with score "
            f"{expected} (rule: >0.5 eligible, else MAYBE)")


def dry_run():
    failures = []
    golden = load_golden()
    n_total, n_verdicts, n_maybe_verdicts = 0, 0, 0

    for proto, patients in golden.items():
        if len(patients) != EXPECTED_PATIENTS:
            failures.append(f"{proto}: {len(patients)} patients, expected {EXPECTED_PATIENTS}")
        for pid, rec in patients.items():
            n_total += 1
            vs = [verdict_of(v) for v in rec["evidence"].values()]
            n_verdicts += len(vs)
            n_maybe_verdicts += vs.count("MAYBE")
            check_record(proto, pid, rec, failures)

    # The inputs the pipeline reads must still be present and parseable.
    import csv as _csv
    with open(os.path.join(ROOT, "data", "patients.csv"), encoding="utf-8") as fh:
        n_rows = sum(1 for _ in _csv.DictReader(fh))
    if n_rows != EXPECTED_PATIENTS:
        failures.append(f"data/patients.csv has {n_rows} rows, expected {EXPECTED_PATIENTS}")
    with open(os.path.join(ROOT, "data", "lab_results.csv"), encoding="utf-8") as fh:
        if sum(1 for _ in _csv.DictReader(fh)) == 0:
            failures.append("data/lab_results.csv parsed to zero rows")
    notes = [f for f in os.listdir(os.path.join(ROOT, "data", "clinical_notes"))
             if f.endswith(".txt")]
    if len(notes) != EXPECTED_PATIENTS:
        failures.append(f"{len(notes)} clinical notes, expected {EXPECTED_PATIENTS}")

    sys.path.insert(0, os.path.join(ROOT, "src"))
    from protocol_sorter import sort_protocols  # torch-free import
    protos = sort_protocols(os.path.join(ROOT, "data"))
    found = {p["protocol_id"] for p in protos}
    if found != set(PROTOCOLS):
        failures.append(f"protocols normalized to {sorted(found)}, expected {PROTOCOLS}")

    print(f"verified tier: {n_total} decisions, {n_verdicts} criterion verdicts, "
          f"{n_maybe_verdicts} abstentions")

    if cohort_present():
        failures += cohort_dry_run()

    if failures:
        print(f"\nDRY RUN FAILURES ({len(failures)})")
        for f in failures:
            print(f"  {f}")
        return 1
    print("dry run green: goldens are internally consistent and the inputs are intact")
    return 0


def cohort_dry_run():
    """Structural checks for the pinned cohort tier; returns failures."""
    import csv as _csv
    failures = []
    with open(COHORT_GOLDEN, encoding="utf-8") as fh:
        pinned = {(r["protocol"], r["patient_id"]): r for r in json.load(fh)}
    n_dec = len(pinned)
    if n_dec != COHORT_PATIENTS * len(PROTOCOLS):
        failures.append(f"cohort: {n_dec} pinned decisions, expected "
                        f"{COHORT_PATIENTS * len(PROTOCOLS)}")
    n_verd, n_abst = 0, 0
    for (proto, pid), rec in pinned.items():
        check_record(f"cohort/{proto}", pid, rec, failures)
        vs = [verdict_of(v) for v in rec["evidence"].values()]
        n_verd += len(vs)
        n_abst += vs.count("MAYBE")

    with open(os.path.join(COHORT_ROOT, "patients.csv"), encoding="utf-8") as fh:
        ids = {r["patient_id"] for r in _csv.DictReader(fh)}
    if len(ids) != COHORT_PATIENTS:
        failures.append(f"cohort/patients.csv has {len(ids)} patients, "
                        f"expected {COHORT_PATIENTS}")
    notes = [f for f in os.listdir(os.path.join(COHORT_ROOT, "clinical_notes"))
             if f.endswith(".txt")]
    if len(notes) != COHORT_PATIENTS:
        failures.append(f"cohort has {len(notes)} notes, expected {COHORT_PATIENTS}")

    # The full trap audit, on every dry run: a structured trap's pinned verdict
    # must equal its intended verdict, and an unsupported-intent trap may pin
    # PASS only if the ledger owns that wrong verdict. This keeps the README's
    # "40 of 40 as planted" a machine-checked fact, not a one-time reading.
    with open(TRAPS, encoding="utf-8") as fh:
        traps = json.load(fh)["traps"]
    with open(KNOWN_WRONG, encoding="utf-8") as fh:
        ledger_keys = {(w["patient"], w["criterion"])
                       for w in json.load(fh)["cases"]}
    for t in traps:
        if t["patient"] not in ids:
            failures.append(f"trap references unknown patient {t['patient']}")
            continue
        rec = pinned.get((t["protocol"], t["patient"]))
        ev = rec["evidence"].get(t["criterion"]) if rec else None
        if ev is None:
            failures.append(f"trap {t['patient']}/{t['criterion'][:40]!r} matches "
                            f"no pinned criterion")
            continue
        got = verdict_of(ev)
        if t["intended"] in ("PASS", "FAIL", "MAYBE"):
            if got != t["intended"]:
                failures.append(f"structured trap drift: {t['patient']}/"
                                f"{t['criterion'][:40]!r} planted {t['intended']}, "
                                f"pinned {got}")
        elif t["intended"] == "unsupported":
            if got == "PASS" and (t["patient"], t["criterion"]) not in ledger_keys:
                failures.append(f"unledgered wrong PASS: {t['patient']}/"
                                f"{t['criterion'][:40]!r}")

    with open(KNOWN_WRONG, encoding="utf-8") as fh:
        ledger = json.load(fh)
    trap_keys = {(t["patient"], t["criterion"]) for t in traps}
    for w in ledger["cases"]:
        if (w["patient"], w["criterion"]) not in trap_keys:
            failures.append(f"known-wrong case {w['patient']}/{w['criterion'][:40]!r} "
                            f"matches no planted trap")
        rec = pinned.get((w["protocol"], w["patient"]))
        got = verdict_of(rec["evidence"].get(w["criterion"], "")) if rec else None
        if got != w["pinned_verdict"]:
            failures.append(
                f"ledger drift: {w['patient']}/{w['criterion'][:40]!r} pinned as "
                f"{w['pinned_verdict']} but cohort golden says {got}")
    if len(ledger["cases"]) != ledger["count"]:
        failures.append(f"ledger count {ledger['count']} != {len(ledger['cases'])} cases")

    print(f"cohort tier: {n_dec} pinned decisions, {n_verd} verdicts, {n_abst} "
          f"abstentions; {len(traps)} planted traps; {ledger['count']} known-wrong pinned")
    return failures


def full():
    as_json = "--json" in sys.argv
    failures = []
    golden = load_golden()

    sys.path.insert(0, os.path.join(ROOT, "src"))
    from data_loader import build_patient_profiles
    from protocol_sorter import sort_protocols
    from protocol_evaluator import evaluate_patient

    patients = build_patient_profiles(
        os.path.join(ROOT, "data", "patients.csv"),
        os.path.join(ROOT, "data", "lab_results.csv"),
        os.path.join(ROOT, "data", "clinical_notes"))
    protocols = sort_protocols(os.path.join(ROOT, "data"))

    fresh = {}
    for protocol in protocols:
        proto_id = protocol["protocol_id"]
        fresh[proto_id] = {}
        for patient in patients.values():
            fresh[proto_id][patient["patient_id"]] = evaluate_patient(patient, {
                "id": proto_id,
                "structured": protocol.get("structured_criteria", []),
                "unstructured": protocol.get("unstructured_criteria", []),
            })

    n_agree = 0
    for proto, expected in golden.items():
        got = fresh.get(proto, {})
        for pid, exp in expected.items():
            g = got.get(pid)
            if g is None:
                failures.append(f"{proto}/{pid}: not produced by the fresh run")
                continue
            agree = True
            if str(g["is_eligible"]) != str(exp["is_eligible"]):
                failures.append(f"{proto}/{pid}: eligibility {exp['is_eligible']!r} "
                                f"-> {g['is_eligible']!r}")
                agree = False
            es, gs = exp["confidence_score"], g["confidence_score"]
            if isinstance(es, (int, float)) != isinstance(gs, (int, float)):
                failures.append(f"{proto}/{pid}: score {es!r} -> {gs!r}")
                agree = False
            elif isinstance(es, (int, float)) and abs(es - gs) > SCORE_TOL:
                failures.append(f"{proto}/{pid}: score {es} -> {gs}")
                agree = False
            for crit, ev in exp["evidence"].items():
                gv = g["evidence"].get(crit)
                if gv is None:
                    failures.append(f"{proto}/{pid}: criterion {crit[:50]!r} missing")
                    agree = False
                elif verdict_of(ev) != verdict_of(gv):
                    failures.append(f"{proto}/{pid}/{crit[:40]!r}: "
                                    f"{verdict_of(ev)} -> {verdict_of(gv)}")
                    agree = False
            if agree:
                n_agree += 1

    # Close the loop derive.py leaves open: re-measure every labelled row.
    import csv as _csv
    import re as _re
    labels_path = os.path.join(ROOT, "evals", "labels.csv")
    n_labels, n_remeasured = 0, 0
    if os.path.exists(labels_path):
        with open(labels_path, encoding="utf-8") as fh:
            body = [ln for ln in fh if not ln.lstrip().startswith("#")]
        for r in _csv.DictReader(body):
            if not r.get("patient"):
                continue
            n_labels += 1
            g = fresh.get(r["protocol"], {}).get(r["patient"])
            ev = g["evidence"].get(r["criterion"]) if g else None
            nums = [float(x) for x in _re.findall(r"(?:score|semantic|cosine)=([0-9.]+)", ev or "")]
            if any(abs(n - float(r["measured"])) <= SCORE_TOL for n in nums):
                n_remeasured += 1
            else:
                failures.append(
                    f"label {r['patient']}/{r['criterion'][:40]!r}: measured "
                    f"{r['measured']} not reproduced (fresh evidence: {ev!r})")

    n_total = sum(len(v) for v in golden.values())
    summary = {"decisions": n_total, "agree": n_agree,
               "labels": n_labels, "labels_remeasured": n_remeasured,
               "failures": len(failures)}

    if cohort_present():
        c_total, c_agree, c_failures = cohort_full(patients_root=COHORT_ROOT)
        failures += c_failures
        summary["cohort_decisions"] = c_total
        summary["cohort_agree"] = c_agree
    # The receipt readme_numbers.py checks the README's agreement claim
    # against; committed, so the claim traces to a recorded run.
    with open(os.path.join(ROOT, "evals", "last_full_run.json"), "w",
              encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    if as_json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\nfull eval: {n_agree} of {n_total} decisions agree with the goldens; "
              f"{n_remeasured} of {n_labels} labelled scores re-measured within {SCORE_TOL}")
    if failures:
        print(f"\nFULL EVAL FAILURES ({len(failures)})")
        for f in failures:
            print(f"  {f}")
        return 1
    return 0


def cohort_full(patients_root):
    """Recompute all pinned cohort decisions and compare exactly.

    The ledger's known-wrong verdicts are part of the pin: a change that fixes
    or worsens one shows up here as drift, which is the point.
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from data_loader import build_patient_profiles
    from protocol_sorter import sort_protocols
    from protocol_evaluator import evaluate_patient

    failures = []
    with open(COHORT_GOLDEN, encoding="utf-8") as fh:
        pinned = {(r["protocol"], r["patient_id"]): r for r in json.load(fh)}
    patients = build_patient_profiles(
        os.path.join(patients_root, "patients.csv"),
        os.path.join(patients_root, "lab_results.csv"),
        os.path.join(patients_root, "clinical_notes"))
    protocols = sort_protocols(os.path.join(ROOT, "data"))

    n_agree = 0
    for protocol in protocols:
        proto_id = protocol["protocol_id"]
        for patient in patients.values():
            g = evaluate_patient(patient, {
                "id": proto_id,
                "structured": protocol.get("structured_criteria", []),
                "unstructured": protocol.get("unstructured_criteria", []),
            })
            exp = pinned.get((proto_id, patient["patient_id"]))
            if exp is None:
                failures.append(f"cohort/{proto_id}/{patient['patient_id']}: not pinned")
                continue
            ok = str(g["is_eligible"]) == str(exp["is_eligible"])
            es, gs = exp["confidence_score"], g["confidence_score"]
            if isinstance(es, (int, float)) != isinstance(gs, (int, float)):
                failures.append(f"cohort/{proto_id}/{patient['patient_id']}: "
                                f"score {es!r} -> {gs!r}")
                ok = False
            elif isinstance(es, (int, float)) and abs(es - gs) > SCORE_TOL:
                failures.append(f"cohort/{proto_id}/{patient['patient_id']}: "
                                f"score {es} -> {gs}")
                ok = False
            for crit, ev in exp["evidence"].items():
                gv = g["evidence"].get(crit)
                if gv is None or verdict_of(ev) != verdict_of(gv):
                    failures.append(f"cohort/{proto_id}/{patient['patient_id']}/"
                                    f"{crit[:40]!r}: {verdict_of(ev)} -> "
                                    f"{verdict_of(gv) if gv else 'missing'}")
                    ok = False
            if ok:
                n_agree += 1
            elif str(g["is_eligible"]) != str(exp["is_eligible"]):
                failures.append(f"cohort/{proto_id}/{patient['patient_id']}: "
                                f"eligibility {exp['is_eligible']!r} -> {g['is_eligible']!r}")

    print(f"cohort replay: {n_agree} of {len(pinned)} pinned decisions agree")
    return len(pinned), n_agree, failures


if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        sys.exit(dry_run())
    elif "--full" in sys.argv:
        sys.exit(full())
    print(__doc__)
    sys.exit(2)
