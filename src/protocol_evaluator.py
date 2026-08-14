"""
protocol_evaluator.py

Evaluates patient eligibility against trial protocols.

- Uses structured data (age, BMI, pack-years, labs) from data_loader.py
- Uses unstructured data (notes) from note_parser.py
- Produces PASS / FAIL / MAYBE for each criterion with inline explanations
"""

from datetime import datetime
from note_parser import query_notes


def evaluate_structured(patient: dict, criteria: list) -> dict:
    """Evaluate structured criteria (demographics, labs, age)."""
    evidence = {}

    for crit in criteria:
        desc = crit.get("description", str(crit))
        # A lab criterion names its measurement in test_name (or metric), not
        # in field. Resolving only field/type made every lab check abstain
        # with "no data for lab_result" while the value sat in latest_labs.
        field = (crit.get("field") or crit.get("test_name")
                 or crit.get("metric") or crit.get("type"))
        op = crit.get("condition")
        value = crit.get("value")
        actual = None

        # Resolve actual patient value
        if field == "age":
            actual = patient.get("age")
        elif field == "BMI":
            actual = patient.get("BMI")
        elif field == "pack_years":
            actual = patient.get("pack_years")
        elif field in patient.get("latest_labs", {}):
            actual = patient["latest_labs"][field]["value"]
        elif field in patient:
            actual = patient.get(field)

        # No data → MAYBE
        if actual is None:
            evidence[desc] = f"MAYBE (no data for {field})"
            continue

        # Numeric comparisons
        if op in ["lt", "lte", "gt", "gte", "between"]:
            try:
                if op == "lt":
                    evidence[desc] = (
                        f"PASS ({field}={actual} lt {value})"
                        if actual < value else
                        f"FAIL ({field}={actual} not lt {value})"
                    )
                elif op == "lte":
                    evidence[desc] = (
                        f"PASS ({field}={actual} <= {value})"
                        if actual <= value else
                        f"FAIL ({field}={actual} not <= {value})"
                    )
                elif op == "gt":
                    evidence[desc] = (
                        f"PASS ({field}={actual} gt {value})"
                        if actual > value else
                        f"FAIL ({field}={actual} not gt {value})"
                    )
                elif op == "gte":
                    evidence[desc] = (
                        f"PASS ({field}={actual} >= {value})"
                        if actual >= value else
                        f"FAIL ({field}={actual} not >= {value})"
                    )
                elif op == "between" and isinstance(value, (list, tuple)) and len(value) == 2:
                    lo, hi = value
                    evidence[desc] = (
                        f"PASS ({field}={actual} in range {lo}-{hi})"
                        if lo <= actual <= hi else
                        f"FAIL ({field}={actual} not in range {lo}-{hi})"
                    )
            except Exception:
                evidence[desc] = f"MAYBE (could not evaluate {field} with {op})"

        # Equality checks
        elif op in ["equals", "eq"]:
            evidence[desc] = (
                f"PASS ({field} exactly {value})"
                if str(actual).lower() == str(value).lower() else
                f"FAIL ({field}={actual} not equal {value})"
            )

        else:
            evidence[desc] = f"MAYBE (unsupported op '{op}' for {field})"

    return evidence


def evaluate_unstructured(patient: dict, criteria: list, scorer=None) -> dict:
    evidence = {}
    notes = patient.get("notes", "")

    for crit in criteria:
        desc = crit.get("description", str(crit))
        evidence[desc] = query_notes(notes, crit, scorer=scorer)

    return evidence


def evaluate_patient(patient: dict, protocol: dict, scorer=None) -> dict:
    """Run full evaluation of a single patient against a protocol with fail override."""
    structured_evidence = evaluate_structured(patient, protocol.get("structured", []))
    unstructured_evidence = evaluate_unstructured(patient, protocol.get("unstructured", []),
                                                  scorer=scorer)
    evidence = {**structured_evidence, **unstructured_evidence}

    total = len(evidence)
    passes = sum(1 for v in evidence.values() if v.startswith("PASS"))
    maybes = sum(1 for v in evidence.values() if v.startswith("MAYBE"))
    fails = sum(1 for v in evidence.values() if v.startswith("FAIL"))

    # If any FAIL → disqualified
    if fails > 0:
        is_eligible = False
        score = "NA"
    else:
        # Confidence = PASS=1, MAYBE=0.5
        score_val = (passes + 0.5 * maybes) / total if total > 0 else 0.0
        score = round(score_val, 3)
        if score_val > 0.5:
            is_eligible = True
        else:
            is_eligible = "MAYBE"

    return {
        "patient_id": patient["patient_id"],
        "is_eligible": is_eligible,
        "confidence_score": score,
        "evidence": evidence,
    }


if __name__ == "__main__":
    # Debug run
    patient = {
        "patient_id": "xyz-789",
        "age": 56,
        "BMI": 26.1,
        "pack_years": 12.5,
        "latest_labs": {"HbA1c": {"value": 7.9, "date": datetime(2024, 3, 1)}},
        "is_smoker": False,
        "notes": "borderline sugar, pre-diabetes, documented CHF EF 35%, completed cancer screening",
    }

    protocol = {
        "protocol_id": "protocol123",
        "structured": [
            {"description": "Patient must be between 40 and 70 years of age",
             "field": "age", "condition": "between", "value": [40, 70]},
            {"description": "HbA1c level must be less than 8.0%",
             "field": "HbA1c", "condition": "lt", "value": 8.0},
            {"description": "Patient must not be a current smoker",
             "field": "is_smoker", "condition": "equals", "value": False},
        ],
        "unstructured": [
            {"description": "History of diabetes", "concepts": ["diabetes"]},
            {"description": "History of CHF", "concepts": ["CHF"]},
            {"description": "Must have completed age-appropriate cancer screening",
             "concepts": ["screening", "colonoscopy", "mammogram"]},
        ],
    }

    import json
    print(json.dumps(evaluate_patient(patient, protocol), indent=2, default=str))
