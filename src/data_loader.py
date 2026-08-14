"""
data_loader.py

Loads and synthesizes patient data into unified profiles.

Sources:
- patients.csv (demographics, DOB, gender, smoker status, height, weight, smoking data)
- lab_results.csv (time-series lab values)
- clinical_notes/ (unstructured patient notes)

Features:
- Precomputes derived fields (age, BMI, pack-years if available)
- Attaches full lab history AND most recent lab values
- Attaches clinical notes if available
- Handles missing values safely

Usage:
    python data_loader.py
"""

import os
import json
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any

CURRENT_DATE = datetime(2024, 5, 1)


def calculate_age(dob: str) -> Optional[int]:
    """Calculate patient age at CURRENT_DATE.

    Calendar arithmetic, not days // 365: the division form accumulates one
    day per leap year and overstated age by 1 for patients whose birthday had
    not yet arrived (patient_C001's note says 53; the old formula said 54).
    """
    if pd.isna(dob):
        return None
    try:
        birth = datetime.strptime(str(dob), "%Y-%m-%d")
        return (CURRENT_DATE.year - birth.year
                - ((CURRENT_DATE.month, CURRENT_DATE.day) < (birth.month, birth.day)))
    except Exception:
        return None


def calculate_bmi(weight_kg, height_cm) -> Optional[float]:
    """Compute BMI if height and weight are valid."""
    if pd.isna(weight_kg) or pd.isna(height_cm) or not height_cm:
        return None
    try:
        return round(weight_kg / ((height_cm / 100) ** 2), 1)
    except Exception:
        return None


def calculate_pack_years(cigs_per_day, years_smoked) -> Optional[float]:
    """Compute pack-years if smoking data is available."""
    if pd.isna(cigs_per_day) or pd.isna(years_smoked):
        return None
    try:
        return round((cigs_per_day / 20.0) * years_smoked, 1)
    except Exception:
        return None


def load_patients(patients_csv: str) -> dict:
    """Load patient demographics and compute derived metrics."""
    df = pd.read_csv(patients_csv)
    patients = {}

    for _, row in df.iterrows():
        pid = row["patient_id"]
        dob = row.get("date_of_birth")

        patients[pid] = {
            "patient_id": pid,
            "date_of_birth": dob,
            "age": calculate_age(dob),
            "gender": row.get("gender"),
            "is_smoker": bool(row.get("is_smoker", False)),
            "height_cm": row.get("height_cm"),
            "weight_kg": row.get("weight_kg"),
            "BMI": calculate_bmi(row.get("weight_kg"), row.get("height_cm")),
            "cigs_per_day": row.get("cigs_per_day"),
            "years_smoked": row.get("years_smoked"),
            "pack_years": calculate_pack_years(row.get("cigs_per_day"), row.get("years_smoked")),
            "labs": [],
            "latest_labs": {},  # filled by attach_labs_to_patients
            "notes": ""  # will be populated by attach_notes_to_patients
        }

    return patients


def load_lab_results(labs_csv: str) -> pd.DataFrame:
    """Load lab results into a DataFrame."""
    return pd.read_csv(labs_csv)


def attach_labs_to_patients(patients: dict, labs_df: pd.DataFrame):
    """Attach lab results (history + most recent per test) to patient profiles."""
    for _, row in labs_df.iterrows():
        pid = row["patient_id"]
        if pid not in patients:
            continue

        try:
            obs_date = datetime.strptime(str(row["observation_date"]), "%Y-%m-%d")
        except Exception:
            obs_date = None

        lab_entry = {
            "test_name": row["lab_test_name"],
            "value": row["value"],
            "unit": row.get("unit"),
            "date": obs_date,
        }

        patients[pid]["labs"].append(lab_entry)

        test = row["lab_test_name"]
        current_latest = patients[pid]["latest_labs"].get(test)
        if not current_latest or (
            obs_date and current_latest.get("date") and obs_date > current_latest["date"]
        ):
            patients[pid]["latest_labs"][test] = lab_entry


def attach_notes_to_patients(patients: dict, notes_dir: str):
    """Attach clinical notes (if available) to patient profiles."""
    for pid, profile in patients.items():
        note_path = os.path.join(notes_dir, f"{pid}.txt")
        if os.path.exists(note_path):
            with open(note_path, "r", encoding="utf-8") as f:
                profile["notes"] = f.read().strip()
        else:
            profile["notes"] = ""


def build_patient_profiles(patients_csv: str, labs_csv: str,
                           notes_dir="data/clinical_notes") -> dict:
    """Return unified patient profiles keyed by patient_id."""
    patients = load_patients(patients_csv)
    labs_df = load_lab_results(labs_csv)
    attach_labs_to_patients(patients, labs_df)
    attach_notes_to_patients(patients, notes_dir)
    return patients


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.dirname(__file__))
    patients_csv = os.path.join(BASE_DIR, "data", "patients.csv")
    labs_csv = os.path.join(BASE_DIR, "data", "lab_results.csv")
    notes_dir = os.path.join(BASE_DIR, "data", "clinical_notes")

    profiles = build_patient_profiles(patients_csv, labs_csv, notes_dir)
    print("Loaded profiles:", len(profiles))
    first = list(profiles.values())[0]
    print("Sample profile:", json.dumps(first, indent=2, default=str))
