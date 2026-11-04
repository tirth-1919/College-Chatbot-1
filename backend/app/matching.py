"""Fuzzy matching against live tenant and college names, without baked-in names."""
from difflib import SequenceMatcher
import re


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _candidate_is_mentioned(query: str, candidate: str) -> bool:
    if query == candidate or f" {candidate} " in f" {query} ":
        return True
    # Let short acronym aliases match forms such as "A.I.T" and "A I T".
    if candidate.isalpha() and 2 <= len(candidate) <= 5:
        acronym_pattern = r"(?<![a-z0-9])" + r"\s*".join(map(re.escape, candidate)) + r"(?![a-z0-9])"
        return re.search(acronym_pattern, query) is not None
    return False


def fuzzy_college_resolution(query: str, colleges, threshold: float = 0.82, margin: float = 0.08):
    normalized_query = _normalize(query)
    if not normalized_query:
        return None, []
    ranked = []
    for college in colleges:
        candidates = [college.name, college.code, *(college.aliases or [])]
        normalized_candidates = [_normalize(candidate) for candidate in candidates if candidate]
        exact_or_mentioned = any(_candidate_is_mentioned(normalized_query, candidate) for candidate in normalized_candidates)
        if len(normalized_query) < 4 and not exact_or_mentioned:
            score = 0
        else:
            score = max(
                (1.0 if _candidate_is_mentioned(normalized_query, candidate)
                 else SequenceMatcher(None, normalized_query, candidate).ratio()
                 for candidate in normalized_candidates),
                default=0,
            )
        ranked.append((score, college))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < threshold:
        return None, []
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < margin:
        options = [college for score, college in ranked if score >= threshold and ranked[0][0] - score < margin][:5]
        return None, options
    return ranked[0][1], []


def fuzzy_college_match(query: str, colleges, threshold: float = 0.82, margin: float = 0.08):
    return fuzzy_college_resolution(query, colleges, threshold, margin)[0]
