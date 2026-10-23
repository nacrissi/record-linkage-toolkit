from linkage.jaro_winkler import jaro_similarity, jaro_winkler_similarity


def test_identical_strings():
    assert jaro_similarity("brightmart", "brightmart") == 1.0
    assert jaro_winkler_similarity("brightmart", "brightmart") == 1.0


def test_empty_strings():
    assert jaro_similarity("", "anything") == 0.0
    assert jaro_similarity("anything", "") == 0.0


def test_known_jaro_winkler_values():
    # Commonly-cited reference values for the Jaro-Winkler metric.
    cases = [
        ("MARTHA", "MARHTA", 0.961),
        ("DWAYNE", "DUANE", 0.84),
        ("DIXON", "DICKSONX", 0.813),
    ]
    for s1, s2, expected in cases:
        got = jaro_winkler_similarity(s1, s2)
        assert abs(got - expected) < 0.01, f"{s1!r} vs {s2!r}: got {got}, expected ~{expected}"


def test_completely_different_strings_score_low():
    assert jaro_winkler_similarity("brightmart", "zzzzzzzzzz") < 0.3


def test_symmetry():
    a, b = "cornerstone", "cornferstone"
    assert abs(jaro_winkler_similarity(a, b) - jaro_winkler_similarity(b, a)) < 1e-9


def test_prefix_boost_increases_score_over_plain_jaro():
    s1, s2 = "brightmart center", "brightmart centre"
    jaro = jaro_similarity(s1, s2)
    jw = jaro_winkler_similarity(s1, s2)
    assert jw >= jaro
