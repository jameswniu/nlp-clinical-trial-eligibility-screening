"""
note_parser.py

Parses and queries unstructured clinical notes.

Features:
- Embedding-based semantic similarity (MiniLM).
- Synonyms mapping for fuzzy medical terms (diabetes, CHF).
- Fallback bag-of-words cosine similarity.
- Returns PASS / FAIL / MAYBE with inline explanations.
"""

import re
import math
from collections import Counter
from typing import Dict, Any

# The embedding model loads lazily so that the deterministic core (tests, the
# dry-run gate) imports this module without torch installed. Only the first
# real semantic query pays the load.
_MODEL = None


def _get_model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer("paraphrase-MiniLM-L3-v2")
    return _MODEL


# One patient's note is scored against every criterion of every protocol, so
# the same strings recur constantly. Memoizing embeddings changes no score
# (identical input, identical vector) and cuts encode calls roughly 10x on a
# full cohort replay.
_EMBED_CACHE = {}


def _embed(text: str):
    vec = _EMBED_CACHE.get(text)
    if vec is None:
        vec = _get_model().encode([text], convert_to_tensor=True)[0]
        _EMBED_CACHE[text] = vec
    return vec


def semantic_scores(notes: str, phrases: list) -> list:
    """Cosine similarity of the notes against each phrase, via MiniLM.

    This is the default scorer for query_notes; tests inject a fake with the
    same signature so verdict banding is checked without the model.
    """
    from sentence_transformers import util
    note_vec = _embed(notes)
    return [float(util.cos_sim(note_vec, _embed(p))[0][0]) for p in phrases]

# Thresholds for semantic similarity
SEMANTIC_PASS = 0.15
SEMANTIC_MAYBE = 0.1

# Fallback thresholds for bag-of-words cosine similarity
COSINE_PASS = 0.1
COSINE_MAYBE_MARGIN = 0.05

# Synonyms mapping for fuzzy mentions. Keys are LOWERCASE because query_notes
# looks up concept.lower(); the original "CHF" key was unreachable, which made
# every CHF synonym dead code (found by the test suite, 2026-08-14).
SYNONYMS = {
    "diabetes": [
        "borderline sugar",
        "pre-diabetes",
        "prediabetes",
        "high blood sugar",
        "impaired glucose tolerance",
    ],
    "chf": [
        "congestive heart failure",
        "heart failure",
        "cardiac insufficiency",
        "reduced ejection fraction",
        "low ejection fraction",
        "EF 35%",
        "EF 30%",
        "EF 25%",
        "ejection fraction below 40%",
    ],
}


def tokenize(text: str):
    """Lowercase and extract alphanumeric tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())


def cosine_similarity(text1: str, text2: str) -> float:
    """Simple bag-of-words cosine similarity."""
    tokens1, tokens2 = tokenize(text1), tokenize(text2)
    vec1, vec2 = Counter(tokens1), Counter(tokens2)

    intersection = set(vec1.keys()) & set(vec2.keys())
    numerator = sum(vec1[x] * vec2[x] for x in intersection)

    sum1 = sum(v**2 for v in vec1.values())
    sum2 = sum(v**2 for v in vec2.values())
    denominator = math.sqrt(sum1) * math.sqrt(sum2)

    if not denominator:
        return 0.0
    return float(numerator) / denominator


def query_notes(notes: str, criterion: Dict[str, Any], scorer=None) -> str:
    if not notes:
        return f"MAYBE (no notes available for '{criterion.get('description','')}')"

    desc = criterion.get("description", "")
    concepts = criterion.get("concepts", [])
    if not concepts:
        tokens = [w.lower() for w in desc.split() if len(w) > 3]
        concepts = tokens[:5]

    phrases = [desc] + concepts

    # Synonym shortcut
    for concept in concepts:
        for syn in SYNONYMS.get(concept.lower(), []):
            if syn.lower() in notes.lower():
                return f"MAYBE (notes mention '{syn}', possible {concept})"

    # Semantic similarity
    if scorer is None:
        scorer = semantic_scores
    max_score = float(max(scorer(notes, phrases)))

    if max_score >= SEMANTIC_PASS:
        return f"PASS (semantic match for '{desc}', score={max_score:.2f})"
    elif max_score >= SEMANTIC_MAYBE:
        return f"MAYBE (weak semantic match for '{desc}', score={max_score:.2f})"

    # Fallback: bag-of-words
    bow_scores = [cosine_similarity(notes, phrase) for phrase in phrases]
    max_bow = max(bow_scores) if bow_scores else 0.0

    if max_bow >= COSINE_PASS:
        return f"PASS (cosine match for '{desc}', score={max_bow:.2f})"
    elif max_bow >= COSINE_PASS - COSINE_MAYBE_MARGIN:
        return f"MAYBE (weak cosine match for '{desc}', score={max_bow:.2f})"

    return f"FAIL (no clear mention of '{desc}', semantic={max_score:.2f}, cosine={max_bow:.2f})"



if __name__ == "__main__":
    sample_notes = (
        "Patient has borderline sugar, possible pre-diabetes but not formally diagnosed. "
        "Also history of heart failure with EF 35%."
    )

    diabetes_crit = {"description": "History of diabetes", "concepts": ["diabetes"]}
    chf_crit = {"description": "History of CHF", "concepts": ["CHF"]}
    htn_crit = {"description": "History of hypertension", "concepts": ["hypertension"]}

    print(query_notes(sample_notes, diabetes_crit))
    print(query_notes(sample_notes, chf_crit))
    print(query_notes(sample_notes, htn_crit))
