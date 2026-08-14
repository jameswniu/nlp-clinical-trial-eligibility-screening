"""One real-model test, marked slow and excluded from the default run.

Asserts sign and ordering only, never exact scores: embedding values move at
the third decimal across torch builds, and a test pinned to them would fail
for reasons that are not regressions."""
import pytest


@pytest.mark.slow
def test_real_model_orders_similar_above_dissimilar():
    from note_parser import semantic_scores

    notes = "Patient has a long history of congestive heart failure with EF 35%."
    similar = "History of heart failure"
    dissimilar = "Completed marathon training program last spring"

    s_sim, s_dis = semantic_scores(notes, [similar, dissimilar])
    assert s_sim > s_dis
    assert -1.0 <= s_dis <= 1.0 and -1.0 <= s_sim <= 1.0
