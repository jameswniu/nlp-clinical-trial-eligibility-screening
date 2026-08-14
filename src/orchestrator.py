"""
orchestrator.py

Coordinates the medical trial workflow:
- Loads patient profiles (demographics, labs, notes).
- Normalizes trial protocols (structured/unstructured).
- Evaluates patients against protocols.
- Sorts patients by eligibility and confidence score.
- Writes explainable JSON outputs.

Usage:
    python orchestrator.py
"""

import os
from data_loader import build_patient_profiles
from protocol_sorter import sort_protocols
from protocol_evaluator import evaluate_patient
from utils import write_json


def run_workflow(patients_csv: str, labs_csv: str, notes_dir: str,
                 protocols_dir: str, outputs_dir="output"):
    """
    Full workflow runner.
    """
    patients = build_patient_profiles(patients_csv, labs_csv, notes_dir)
    print(f"Loaded {len(patients)} patient profiles")

    protocols = sort_protocols(protocols_dir)
    print(f"Loaded {len(protocols)} normalized protocols")

    for protocol in protocols:
        results = []
        print(f"\n=== Protocol: {protocol['protocol_id']} ===")

        # Evaluate each patient
        for patient in patients.values():
            result = evaluate_patient(patient, {
                "id": protocol["protocol_id"],
                "structured": protocol.get("structured_criteria", []),
                "unstructured": protocol.get("unstructured_criteria", []),
            })
            results.append(result)

        # Sort patients: True/MAYBE by confidence desc, then False
        def sort_key(r):
            elig = r["is_eligible"]
            score = r["confidence_score"]
            score_val = score if isinstance(score, (int, float)) else 0.0

            if elig is True:
                group = 0
            elif elig == "MAYBE":
                group = 1
            else:  # False
                group = 2

            return (group, -score_val)

        results.sort(key=sort_key)

        # Console print and protocol-level summary
        passed_patients = 0
        for r in results:
            score = r["confidence_score"]
            is_eligible = r["is_eligible"]

            if is_eligible is True:
                passed_patients += 1

            print(
                f"Patient {r['patient_id']} | "
                f"confidence_score = {score} | "
                f"is_eligible = {is_eligible}"
            )

        percent_patients = (passed_patients / len(results)) * 100 if results else 0
        print(
            f"Protocol summary: {passed_patients}/{len(results)} patients eligible "
            f"({percent_patients:.1f}%)"
        )

        # Save sorted results
        out_path = write_json(f"{protocol['protocol_id']}_results",
                              results, out_dir=outputs_dir)
        print(f"Saved results for {protocol['protocol_id']} -> {out_path}")


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    patients_csv = os.path.join(BASE_DIR, "data", "patients.csv")
    labs_csv = os.path.join(BASE_DIR, "data", "lab_results.csv")
    notes_dir = os.path.join(BASE_DIR, "data", "clinical_notes")
    protocols_dir = os.path.join(BASE_DIR, "data")
    outputs_dir = os.path.join(BASE_DIR, "output")

    os.makedirs(outputs_dir, exist_ok=True)
    run_workflow(patients_csv, labs_csv, notes_dir, protocols_dir, outputs_dir)
