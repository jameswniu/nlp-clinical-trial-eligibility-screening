"""Result ordering: eligible first, then MAYBE, then rejected; confidence
descending inside each group."""
from orchestrator import eligibility_sort_key


def rec(pid, elig, score):
    return {"patient_id": pid, "is_eligible": elig, "confidence_score": score}


def test_group_order_then_confidence_desc():
    rows = [
        rec("d", False, "NA"),
        rec("b", True, 0.8),
        rec("c", "MAYBE", 0.5),
        rec("a", True, 0.9),
        rec("e", "MAYBE", 0.4),
    ]
    rows.sort(key=eligibility_sort_key)
    assert [r["patient_id"] for r in rows] == ["a", "b", "c", "e", "d"]


def test_na_scores_sort_as_zero():
    rows = [rec("x", False, "NA"), rec("y", False, "NA")]
    rows.sort(key=eligibility_sort_key)
    assert len(rows) == 2


def test_sort_is_deterministic_for_ties():
    rows = [rec("a", True, 0.7), rec("b", True, 0.7)]
    first = sorted(rows, key=eligibility_sort_key)
    second = sorted(list(reversed(rows)), key=eligibility_sort_key)
    assert [r["confidence_score"] for r in first] == [0.7, 0.7]
    assert [r["confidence_score"] for r in second] == [0.7, 0.7]
