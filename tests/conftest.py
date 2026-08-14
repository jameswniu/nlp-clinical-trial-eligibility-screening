import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


@pytest.fixture
def data_dir():
    return os.path.join(ROOT, "data")


@pytest.fixture
def make_scorer():
    """Build an injectable scorer that returns fixed similarity scores.

    Matches the signature of note_parser.semantic_scores: (notes, phrases)
    -> one float per phrase.
    """
    def _make(*scores):
        def scorer(notes, phrases):
            assert len(phrases) >= 1
            fixed = list(scores)
            while len(fixed) < len(phrases):
                fixed.append(fixed[-1])
            return fixed[: len(phrases)]
        return scorer
    return _make
