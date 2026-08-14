"""Patient profile assembly from the three shipped sources."""
import os

from data_loader import build_patient_profiles, calculate_age, calculate_bmi


def profiles(data_dir):
    return build_patient_profiles(
        os.path.join(data_dir, "patients.csv"),
        os.path.join(data_dir, "lab_results.csv"),
        os.path.join(data_dir, "clinical_notes"))


def test_all_25_patients_load(data_dir):
    p = profiles(data_dir)
    assert len(p) == 25


def test_age_is_computed_at_the_pinned_current_date(data_dir):
    # data_loader pins CURRENT_DATE to 2024-05-01 so ages are reproducible.
    p = profiles(data_dir)
    assert p["patient_C001"]["age"] == 53
    assert p["patient_C002"]["age"] == 36


def test_smoker_flag_survives_the_csv(data_dir):
    p = profiles(data_dir)
    assert p["patient_C002"]["is_smoker"] is True
    assert p["patient_C001"]["is_smoker"] is False


def test_latest_lab_wins_by_date(data_dir):
    # C001 has four HbA1c draws; 2024-03-01 = 7.9 is the newest.
    p = profiles(data_dir)
    latest = p["patient_C001"]["latest_labs"]["HbA1c"]
    assert latest["value"] == 7.9


def test_bmi_is_none_when_the_csv_carries_no_anthropometrics(data_dir):
    # patients.csv ships no height/weight columns; the loader must abstain
    # (None), never fabricate.
    p = profiles(data_dir)
    assert all(v["BMI"] is None for v in p.values())


def test_every_patient_has_notes(data_dir):
    p = profiles(data_dir)
    assert all(v["notes"] for v in p.values())


def test_helpers_handle_missing_inputs():
    assert calculate_age(None) is None
    assert calculate_bmi(None, 170) is None
    assert calculate_bmi(70, None) is None
