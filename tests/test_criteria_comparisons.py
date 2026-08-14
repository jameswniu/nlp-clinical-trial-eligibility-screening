"""The structured comparator: numeric ranges, equality, and the abstention
contract (missing data must yield MAYBE naming the missing field, never a
guess)."""
import pytest

from protocol_evaluator import evaluate_structured

PATIENT = {
    "patient_id": "t-1",
    "age": 54,
    "BMI": 26.1,
    "is_smoker": False,
    "latest_labs": {"HbA1c": {"value": 7.9, "date": None}},
}


def crit(desc, field, cond, value):
    return {"description": desc, "field": field, "condition": cond, "value": value}


@pytest.mark.parametrize("age,expected", [
    (54, "PASS"),   # inside
    (50, "PASS"),   # lower edge inclusive
    (70, "PASS"),   # upper edge inclusive
    (49, "FAIL"),
    (71, "FAIL"),
])
def test_between_edges(age, expected):
    patient = dict(PATIENT, age=age)
    out = evaluate_structured(patient, [crit("age range", "age", "between", [50, 70])])
    assert out["age range"].startswith(expected)


@pytest.mark.parametrize("cond,value,expected", [
    ("lt", 60, "PASS"), ("lt", 54, "FAIL"),
    ("lte", 54, "PASS"), ("lte", 53, "FAIL"),
    ("gt", 50, "PASS"), ("gt", 54, "FAIL"),
    ("gte", 54, "PASS"), ("gte", 55, "FAIL"),
])
def test_numeric_operators(cond, value, expected):
    out = evaluate_structured(PATIENT, [crit("c", "age", cond, value)])
    assert out["c"].startswith(expected)


def test_equality_is_case_insensitive():
    out = evaluate_structured(PATIENT, [crit("ns", "is_smoker", "equals", False)])
    assert out["ns"].startswith("PASS")
    smoker = dict(PATIENT, is_smoker=True)
    out = evaluate_structured(smoker, [crit("ns", "is_smoker", "equals", False)])
    assert out["ns"].startswith("FAIL")


def test_missing_data_abstains_and_names_the_field():
    patient = dict(PATIENT)
    patient.pop("age")
    patient["age"] = None
    out = evaluate_structured(patient, [crit("age range", "age", "between", [50, 70])])
    assert out["age range"] == "MAYBE (no data for age)"


def test_unsupported_operator_abstains():
    out = evaluate_structured(PATIENT, [crit("c", "age", "quit_duration", 5)])
    assert out["c"].startswith("MAYBE")
    assert "unsupported op" in out["c"]


def test_malformed_between_drops_the_criterion():
    # Documented current behavior: a between with a malformed value list falls
    # through every branch and produces NO evidence entry at all. The dry-run
    # gate would catch the count mismatch downstream; this test pins the
    # behavior so a future fix is a deliberate change.
    out = evaluate_structured(PATIENT, [crit("bad", "age", "between", [50])])
    assert "bad" not in out
