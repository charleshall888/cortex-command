"""Shared brief-scoring helpers for the discovery-output-density feature.

Extracted from ``tests/test_discovery_gate_brief.py`` (Task 9) so the
``score-corpus`` subcommand and the pre-merge test suite consume the same
pattern definitions without duplication drift.

Public API
----------
``_score_brief_patterns(brief: str) -> dict[str, int]``
    Score a brief against the six reader-study patterns.  Returns a mapping
    from pattern key to 1 (pattern found) or 0 (clean).

All helpers in this module depend only on the stdlib (``re``).
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Compiled pattern regexes
# ---------------------------------------------------------------------------

# Pattern (e): citation-as-credibility — [path:line] tokens.
# A ratio > 1 per 80 words is the threshold.
_CITATION_RE = re.compile(r"\[[^\]]*:[0-9]+\]")

# Pattern (a): forward references to undefined vocab — numbered-label tokens.
_FORWARD_REF_RE = re.compile(r"\b(DR|OQ|RQ)-?\s*[N0-9]+\b|§[N0-9]+")

# Pattern (b): headline negation-near-claim — negation word adjacent to a
# claim word within the first two sentences of the brief.
_NEGATION_WORDS = re.compile(
    r"\b(NOT|never|no\b|doesn?['']t|cannot|can't|won't|will not)\b",
    re.IGNORECASE,
)
_CLAIM_WORDS = re.compile(
    r"\b(is|are|will|should|does|can|has|have)\b",
    re.IGNORECASE,
)

# Pattern (c): author-process narration — banned phrases from the rubric.
_AUTHOR_PROCESS_RE = re.compile(
    r"walked back|decomposition history|per template rule",
    re.IGNORECASE,
)

# Pattern (d): headline negation rebuttal — explicit "does NOT" constructions.
_NEGATION_REBUTTAL_RE = re.compile(
    r"\bdoes\s+NOT\b|does\s+not\s+preserve|does\s+not\s+extend",
    re.IGNORECASE,
)

# Pattern (f): conditional repetition — near-duplicate sentences across sections.
# Two sentences are near-duplicates if their Jaccard similarity on word sets is >= 0.75.
_MIN_WORDS_FOR_DUP = 6  # ignore very short sentences


# ---------------------------------------------------------------------------
# Sentence-level helpers
# ---------------------------------------------------------------------------

def _sentence_word_set(sentence: str) -> frozenset[str]:
    """Return the lowercased word set for a sentence (punctuation stripped)."""
    return frozenset(re.findall(r"[a-z]+", sentence.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity between two sets. Returns 0.0 when both are empty."""
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _has_near_duplicate_sentences(text: str, threshold: float = 0.75) -> bool:
    """Return True if any two sentences in ``text`` are near-duplicates.

    A pair is a near-duplicate when their Jaccard similarity on word sets
    is >= ``threshold`` AND both sentences have >= ``_MIN_WORDS_FOR_DUP`` words.
    """
    raw_sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    word_sets = [
        _sentence_word_set(s)
        for s in raw_sentences
        if len(_sentence_word_set(s)) >= _MIN_WORDS_FOR_DUP
    ]
    for i in range(len(word_sets)):
        for j in range(i + 1, len(word_sets)):
            if _jaccard(word_sets[i], word_sets[j]) >= threshold:
                return True
    return False


def _first_two_sentences(text: str) -> str:
    """Return the first two sentences of ``text`` (sentence-boundary split)."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=2)
    return " ".join(parts[:2])


# ---------------------------------------------------------------------------
# Primary scoring entry point
# ---------------------------------------------------------------------------

def _score_brief_patterns(brief: str) -> dict[str, int]:
    """Score a brief against the six reader-study patterns.

    Returns a dict mapping each pattern key to 1 (pattern found) or 0 (clean).
    A total score of 0 means all six patterns are absent — the brief passes.

    Pattern keys:
        forward_refs        (a) forward refs to undefined vocab (DR-N, OQ-N, RQ-N, §N)
        headline_negation   (b) negation-near-claim in first <= 2 sentences
        author_process      (c) author-process narration banned phrases
        negation_rebuttal   (d) headline negation rebuttal ("B does NOT", etc.)
        citation_density    (e) [path:line] density > 1 per 80 words
        conditional_repeat  (f) near-duplicate sentence detection across sections
    """
    scores: dict[str, int] = {}

    # (a) Forward refs to undefined vocab
    scores["forward_refs"] = 1 if _FORWARD_REF_RE.search(brief) else 0

    # (b) Headline negation-near-claim — within first <= 2 sentences
    opening = _first_two_sentences(brief)
    has_negation = bool(_NEGATION_WORDS.search(opening))
    has_claim = bool(_CLAIM_WORDS.search(opening))
    scores["headline_negation"] = 1 if (has_negation and has_claim) else 0

    # (c) Author-process narration
    scores["author_process"] = 1 if _AUTHOR_PROCESS_RE.search(brief) else 0

    # (d) Headline negation rebuttal
    scores["negation_rebuttal"] = 1 if _NEGATION_REBUTTAL_RE.search(brief) else 0

    # (e) Citation-as-credibility: > 1 citation per 80 words
    citation_count = len(_CITATION_RE.findall(brief))
    word_count = len(brief.split())
    ratio = citation_count / max(word_count, 1) * 80
    scores["citation_density"] = 1 if ratio > 1 else 0

    # (f) Conditional repetition
    scores["conditional_repeat"] = 1 if _has_near_duplicate_sentences(brief) else 0

    return scores
