"""The unstructured matcher through an injected scorer: verdict banding around
the named thresholds, the synonym shortcut, the bag-of-words fallback, and the
no-notes abstention. No model is loaded anywhere in this file."""
import note_parser
from note_parser import query_notes

CRIT = {"description": "History of hypertension", "concepts": ["hypertension"]}


def test_no_notes_abstains():
    out = query_notes("", CRIT)
    assert out.startswith("MAYBE")
    assert "no notes available" in out


def test_score_at_or_above_pass_threshold_passes(make_scorer):
    scorer = make_scorer(note_parser.SEMANTIC_PASS)
    out = query_notes("some clinical text", CRIT, scorer=scorer)
    assert out.startswith("PASS (semantic match")


def test_score_in_the_maybe_band_abstains(make_scorer):
    mid = (note_parser.SEMANTIC_MAYBE + note_parser.SEMANTIC_PASS) / 2
    out = query_notes("some clinical text", CRIT, scorer=make_scorer(mid))
    assert out.startswith("MAYBE (weak semantic match")


def test_score_below_maybe_falls_back_to_bag_of_words(make_scorer):
    # Semantic score too weak; the criterion words do appear verbatim in the
    # notes, so the bag-of-words fallback catches it.
    notes = "history of hypertension noted in the chart"
    out = query_notes(notes, CRIT, scorer=make_scorer(0.0))
    assert out.startswith("PASS (cosine match")


def test_nothing_matches_anywhere_fails_with_both_scores(make_scorer):
    out = query_notes("entirely unrelated text", CRIT, scorer=make_scorer(0.0))
    assert out.startswith("FAIL")
    assert "semantic=" in out and "cosine=" in out


def test_synonym_shortcut_fires_before_any_scoring():
    crit = {"description": "History of CHF", "concepts": ["CHF"]}
    notes = "echo shows reduced ejection fraction this year"

    def exploding_scorer(notes_, phrases):
        raise AssertionError("scorer must not run when a synonym hits")

    out = query_notes(notes, crit, scorer=exploding_scorer)
    assert out.startswith("MAYBE (notes mention")


def test_evidence_string_carries_the_score(make_scorer):
    out = query_notes("text", CRIT, scorer=make_scorer(0.42))
    assert "score=0.42" in out


def test_evaluate_patient_threads_the_scorer_through(make_scorer):
    from protocol_evaluator import evaluate_patient
    patient = {"patient_id": "t-1", "age": 60, "is_smoker": False,
               "latest_labs": {}, "notes": "long stable history"}
    protocol = {"id": "p", "structured": [
        {"description": "age", "field": "age", "condition": "between",
         "value": [50, 70]}],
        "unstructured": [CRIT]}
    r = evaluate_patient(patient, protocol, scorer=make_scorer(note_parser.SEMANTIC_PASS))
    assert r["evidence"]["age"].startswith("PASS")
    assert r["evidence"]["History of hypertension"].startswith("PASS (semantic match")
    assert r["confidence_score"] == 1.0
