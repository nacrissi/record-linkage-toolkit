"""Jaro and Jaro-Winkler string similarity, implemented from scratch.

Standard library only. No third-party fuzzy-matching packages.

Reference values this implementation is checked against in
tests/test_jaro_winkler.py (commonly cited in the literature on the
Jaro-Winkler metric):

    jaro_winkler("MARTHA", "MARHTA")   ~= 0.961
    jaro_winkler("DWAYNE", "DUANE")    ~= 0.840
    jaro_winkler("DIXON", "DICKSONX")  ~= 0.813
"""

from __future__ import annotations


def jaro_similarity(s1: str, s2: str) -> float:
    """Return the Jaro similarity of two strings, in [0.0, 1.0]."""
    if s1 == s2:
        return 1.0

    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    transpositions = 0
    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    transpositions //= 2

    return (
        matches / len1
        + matches / len2
        + (matches - transpositions) / matches
    ) / 3.0


def jaro_winkler_similarity(
    s1: str,
    s2: str,
    prefix_weight: float = 0.1,
    max_prefix: int = 4,
) -> float:
    """Return the Jaro-Winkler similarity of two strings, in [0.0, 1.0].

    Adds a bonus for strings that share a common leading prefix, up to
    ``max_prefix`` characters, scaled by ``prefix_weight``.
    """
    jaro = jaro_similarity(s1, s2)

    prefix = 0
    for c1, c2 in zip(s1[:max_prefix], s2[:max_prefix]):
        if c1 != c2:
            break
        prefix += 1

    return jaro + prefix * prefix_weight * (1.0 - jaro)
