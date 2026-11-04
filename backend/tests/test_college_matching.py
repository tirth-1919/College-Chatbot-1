from types import SimpleNamespace

from app.matching import fuzzy_college_match


def test_fuzzy_match_resolves_typos_from_live_records():
    colleges = [
        SimpleNamespace(name="alpha entity", code="alpha", aliases=["first entity"]),
        SimpleNamespace(name="beta entity", code="beta", aliases=[]),
    ]
    assert fuzzy_college_match("alpha entitiy", colleges) is colleges[0]


def test_fuzzy_college_match_rejects_ambiguous_and_short_queries():
    colleges = [
        SimpleNamespace(name="same entity", code="first", aliases=[]),
        SimpleNamespace(name="same entity", code="second", aliases=[]),
    ]
    assert fuzzy_college_match("same entity", colleges) is None
    assert fuzzy_college_match("n", colleges) is None
