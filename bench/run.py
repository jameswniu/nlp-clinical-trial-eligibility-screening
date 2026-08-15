#!/usr/bin/env python3
"""Measure the batch profile over the generated 1,000-patient corpus.

Throughput and memory are machine-dependent, so this writes a RECEIPT
(bench/receipt.json) carrying the numbers together with a hardware and
environment fingerprint, and the README quotes the receipt as a recorded
measurement. CI checks the receipt's schema and that the README matches it;
CI does not re-run the bench, because a shared runner's numbers would be
noise wearing a decimal point.

    python3 bench/generate.py && python3 bench/run.py
"""
import json
import os
import platform
import resource
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "bench", "corpus")
sys.path.insert(0, os.path.join(ROOT, "src"))


def main():
    if not os.path.isdir(CORPUS):
        print("no corpus; run bench/generate.py first", file=sys.stderr)
        return 1
    from data_loader import build_patient_profiles
    from protocol_sorter import sort_protocols
    from protocol_evaluator import evaluate_patient

    patients = build_patient_profiles(
        os.path.join(CORPUS, "patients.csv"),
        os.path.join(CORPUS, "lab_results.csv"),
        os.path.join(CORPUS, "clinical_notes"))
    protocols = sort_protocols(os.path.join(ROOT, "data"))

    # Warm the model outside the timed window; the receipt measures screening,
    # not the one-time model load.
    from note_parser import semantic_scores
    semantic_scores("warmup note", ["warmup criterion"])

    n_decisions, abstain_by_stratum = 0, {"smoker": [0, 0], "nonsmoker": [0, 0]}
    t0 = time.perf_counter()
    for patient in patients.values():
        for protocol in protocols:
            r = evaluate_patient(patient, {
                "id": protocol["protocol_id"],
                "structured": protocol.get("structured_criteria", []),
                "unstructured": protocol.get("unstructured_criteria", []),
            })
            n_decisions += 1
            key = "smoker" if patient.get("is_smoker") else "nonsmoker"
            vs = [v.split(" ")[0] for v in r["evidence"].values()]
            abstain_by_stratum[key][0] += vs.count("MAYBE")
            abstain_by_stratum[key][1] += len(vs)
    elapsed = time.perf_counter() - t0

    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
        1024 * 1024 if platform.system() == "Darwin" else 1024)
    receipt = {
        "patients": len(patients),
        "decisions": n_decisions,
        "elapsed_s": round(elapsed, 1),
        "patients_per_s": round(len(patients) / elapsed, 1),
        "decisions_per_s": round(n_decisions / elapsed, 1),
        "peak_rss_mb": round(peak_mb),
        "abstention_rate_by_stratum": {
            k: round(a / t, 3) for k, (a, t) in abstain_by_stratum.items() if t},
        "seed": 42,
        "env": {
            "machine": platform.machine(),
            "system": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
    }
    try:
        import torch
        receipt["env"]["torch"] = torch.__version__
    except Exception:
        pass
    out = os.path.join(ROOT, "bench", "receipt.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2)
        fh.write("\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
