"""
protocol_sorter.py

Normalizes protocol YAMLs in data/.
- Wraps top-level lists under 'criteria:' if needed (to fix invalid YAML).
- Splits criteria into structured_criteria and unstructured_criteria.
- Logs unknown types so new protocol designs can be reviewed.
- Provides sort_protocols() for orchestrator integration.

Usage:
    python protocol_sorter.py
"""

import os
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Track unknown criterion types we encounter
UNKNOWN_TYPES = set()


def classify_criterion(crit: dict) -> str:
    """Classify a criterion into structured/unstructured, log unknowns."""
    ctype = str(crit.get("type", "")).lower()

    if any(k in crit for k in ["value", "metric", "unit"]):
        return "structured"
    if ctype in {"age", "calculated_metric", "smoker_status", "lab_test"}:
        return "structured"
    if "concepts" in crit or ctype in {"medical_history", "diagnosis", "text"}:
        return "unstructured"

    # Log new/unexpected types
    if ctype not in {"", "unknown"}:
        UNKNOWN_TYPES.add(ctype)
    return "unstructured"


def fix_and_load_yaml(path: str):
    """Ensure YAML is valid by wrapping dangling lists under 'criteria:'."""
    lines = open(path, "r", encoding="utf-8").read().splitlines()
    header, body = [], []
    hit_list = False

    for line in lines:
        if line.strip().startswith("-"):
            hit_list = True
        if hit_list:
            body.append(line)
        else:
            header.append(line)

    if body:
        fixed = "\n".join(header + ["criteria:"] + ["  " + l for l in body])
    else:
        fixed = "\n".join(lines)

    return yaml.safe_load(fixed)


def normalize_protocol(raw: dict, proto_id: str) -> dict:
    clean = {
        "protocol_id": raw.get("protocol_id", proto_id),
        "study_name": raw.get("study_name", "Unnamed Study"),
        "structured_criteria": [],
        "unstructured_criteria": [],
    }

    for key, value in raw.items():
        if isinstance(value, list):
            for crit in value:
                if isinstance(crit, dict):
                    bucket = classify_criterion(crit)
                    # 🔑 Fallback concepts if not defined
                    if bucket == "unstructured" and "concepts" not in crit:
                        desc = crit.get("description", "")
                        words = [w.lower() for w in desc.split() if len(w) > 3]
                        crit["concepts"] = words[:5]
                    clean[f"{bucket}_criteria"].append(crit)

    return clean


def normalize_file(in_path: str, out_path: str):
    """Normalize a single YAML file and save it."""
    raw = fix_and_load_yaml(in_path) or {}
    proto_id = os.path.splitext(os.path.basename(in_path))[0]
    clean = normalize_protocol(raw, proto_id)

    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(clean, f, sort_keys=False, allow_unicode=True)

    print(
        f"Processed {os.path.basename(in_path)} → {os.path.basename(out_path)} "
        f"(structured={len(clean['structured_criteria'])}, "
        f"unstructured={len(clean['unstructured_criteria'])})"
    )
    return clean


def sort_protocols(in_dir: str = DATA_DIR) -> list:
    """
    Normalize all protocol YAMLs in in_dir.
    Returns a list of cleaned protocol dicts for orchestrator.
    """
    normalized = []
    for fname in os.listdir(in_dir):
        if fname.startswith("protocol_") and fname.endswith(".yaml") and not fname.endswith("_clean.yaml"):
            in_path = os.path.join(in_dir, fname)
            out_path = os.path.join(in_dir, fname.replace(".yaml", "_clean.yaml"))
            clean = normalize_file(in_path, out_path)
            normalized.append(clean)

    if UNKNOWN_TYPES:
        print("\n[!] Unknown types encountered (defaulted to unstructured):")
        for t in UNKNOWN_TYPES:
            print("   -", t)

    return normalized


if __name__ == "__main__":
    sort_protocols()
