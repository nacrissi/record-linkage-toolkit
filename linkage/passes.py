"""The five matcher passes (plus pass 0, the learned-alias lookup).

Every pass shares the same interface:

    pass_fn(text: str, city: str, index: MasterIndex) -> PassResult | None

A pass either returns a confident PassResult or None ("not my job, try the
next pass"). The orchestration in matcher.py stops at the first hit.

Thresholds below were tuned to hold auto-match precision >= 98%, not
hand-picked to make a specific row pass (see README, "Design decisions").
"""

from __future__ import annotations

from dataclasses import dataclass

from .jaro_winkler import jaro_winkler_similarity
from .normalize import extract_store_number

# Tuned on seed 11, a different seed than the seed 7 numbers reported in
# the README, then verified against seed 7's precision floor. Never hand-fit
# per row.
PASS4_THRESHOLD = 0.5
PASS4_MARGIN = 0.15
PASS5_THRESHOLD = 0.80
PASS5_MARGIN = 0.04

# A store number is a near-certain identity signal: two candidates that
# each embed a *different* number than the one in the free text are very
# unlikely to both be plausible, even if their surrounding text is
# similar (e.g. "Cornerstone Mobile #22" vs "...#48" in the same city
# share a long common prefix that raw string similarity rewards). This
# penalty lets passes 4-5 treat a conflicting number as strong negative
# evidence instead of being swamped by shared chain-name characters.
NUMBER_MISMATCH_PENALTY = 0.3

# Pass 5 lets token-set overlap lift the score for word-order shuffles
# (which hurt a pure prefix-biased Jaro-Winkler score) without ever
# dragging a good character-level match down -- see pass_5_fuzzy.
PASS5_TOKEN_WEIGHT = 0.5


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _number_penalty(text_number: str | None, candidate_number: str | None) -> float:
    if text_number is not None and candidate_number is not None and text_number != candidate_number:
        return NUMBER_MISMATCH_PENALTY
    return 0.0


@dataclass(frozen=True)
class PassResult:
    store_id: str  # "" means "confirmed: no master match" (from a learned alias)
    score: float
    confidence: str  # "high" | "medium" | "low"


def confidence_band(score: float) -> str:
    if score >= 0.95:
        return "high"
    if score >= 0.85:
        return "medium"
    return "low"


def pass_0_alias(text: str, city: str, index, aliases: dict) -> PassResult | None:
    key = (index.normalize_key(text), city)
    if key in aliases:
        decision = aliases[key]
        return PassResult(store_id=decision, score=1.0, confidence="high")
    return None


def pass_1_exact(text: str, city: str, index) -> PassResult | None:
    key = index.normalize_key(text)
    candidates = index.by_city_key.get((city, key), [])
    if len(candidates) == 1:
        return PassResult(store_id=candidates[0], score=1.0, confidence="high")
    return None


def pass_2_normalized(text: str, city: str, index) -> PassResult | None:
    rows = index.by_city.get(city, [])
    if not rows:
        return None

    norm_text = index.normalize_full(text, strip_chain=False)
    matches = [r for r in rows if r["norm_full"] == norm_text]
    if len(matches) == 1:
        return PassResult(store_id=matches[0]["store_id"], score=1.0, confidence="high")
    if len(matches) > 1:
        return None

    norm_text_stripped = index.normalize_full(text, strip_chain=True)
    if norm_text_stripped:
        matches = [r for r in rows if r["norm_full_stripped"] == norm_text_stripped and r["norm_full_stripped"]]
        if len(matches) == 1:
            return PassResult(store_id=matches[0]["store_id"], score=1.0, confidence="medium")
    return None


def pass_3_store_number(text: str, city: str, index) -> PassResult | None:
    number = extract_store_number(text)
    if number is None:
        return None
    rows = index.by_city.get(city, [])
    candidates = [r for r in rows if r["store_number"] == number]
    if not candidates:
        return None

    # index.token_set() already drops filler words ("no", "number") and
    # bare digit tokens, so what's left is identity-bearing (chain, suffix,
    # neighborhood) -- exactly what we want to cross-check the chain with.
    meaningful = index.token_set(text)

    def chain_matches(row: dict) -> bool:
        return bool(row["chain_tokens"] & meaningful)

    if len(candidates) == 1:
        row = candidates[0]
        if not meaningful:
            # Rep wrote only a bare number ("#7") -- no corroborating or
            # contradicting evidence either way.
            return PassResult(store_id=row["store_id"], score=0.9, confidence="medium")
        if chain_matches(row):
            return PassResult(store_id=row["store_id"], score=1.0, confidence="high")
        # Meaningful tokens are present but name a different chain: the
        # number alone is not enough to override that contradiction.
        return None

    # Multiple stores share this number in this city: disambiguate by chain.
    narrowed = [r for r in candidates if chain_matches(r)]
    if len(narrowed) == 1:
        return PassResult(store_id=narrowed[0]["store_id"], score=0.9, confidence="medium")
    return None


def pass_4_token_set(text: str, city: str, index) -> PassResult | None:
    rows = index.by_city.get(city, [])
    if not rows:
        return None
    text_tokens = index.token_set(text)
    if not text_tokens:
        return None
    text_number = extract_store_number(text)

    scored = []
    for row in rows:
        other = row["tokens"]
        if not other or not row["has_suffix_tokens"]:
            # A bare numbered store has no descriptor word for token-set
            # overlap to work with; without one, a chain-name-only overlap
            # is too weak a signal (and spuriously favors short names over
            # a longer, correct one that merely has a typo) -- that's
            # pass 3's job, not pass 4's.
            continue
        score = _jaccard(text_tokens, other) - _number_penalty(text_number, row["store_number"])
        scored.append((max(score, 0.0), row["store_id"]))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)

    top_score, top_id = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    if top_score >= PASS4_THRESHOLD and (top_score - runner_up) >= PASS4_MARGIN:
        return PassResult(store_id=top_id, score=round(top_score, 4), confidence=confidence_band(top_score))
    return None


def pass_5_fuzzy(text: str, city: str, index) -> PassResult | None:
    rows = index.by_city.get(city, [])
    if not rows:
        return None
    norm_text = index.normalize_full(text, strip_chain=False)
    if not norm_text:
        return None
    text_tokens = index.token_set(text)
    text_number = extract_store_number(text)

    scored = []
    for row in rows:
        char_score = jaro_winkler_similarity(norm_text, row["norm_full"])
        token_score = _jaccard(text_tokens, row["tokens"])
        # A word-order shuffle or a dropped chain prefix can tank the
        # character-level score for a candidate that token-matches well;
        # let the token view lift the score in that case, but never let it
        # drag down a candidate that already matches well character-wise
        # (that would just punish ordinary typos, which char-level already
        # handles fine).
        blended = char_score + PASS5_TOKEN_WEIGHT * max(0.0, token_score - char_score)
        blended -= _number_penalty(text_number, row["store_number"])
        scored.append((max(blended, 0.0), row["store_id"]))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    top_score, top_id = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    if top_score >= PASS5_THRESHOLD and (top_score - runner_up) >= PASS5_MARGIN:
        return PassResult(store_id=top_id, score=round(top_score, 4), confidence=confidence_band(top_score))
    return None


# Passes 1-5 in order. Pass 0 (aliases) is handled separately by the
# orchestrator because it needs the mutable aliases dict.
ORDERED_PASSES = [
    (1, pass_1_exact),
    (2, pass_2_normalized),
    (3, pass_3_store_number),
    (4, pass_4_token_set),
    (5, pass_5_fuzzy),
]
