import pytest

from linkage.matcher import MasterIndex
from linkage.passes import (
    pass_1_exact,
    pass_2_normalized,
    pass_3_store_number,
    pass_4_token_set,
    pass_5_fuzzy,
)

MASTER_ROWS = [
    {"store_id": "S1", "chain": "Brightmart", "store_name": "Brightmart Plaza", "address": "1 Main Street", "city": "Fairview", "state": "TX"},
    {"store_id": "S2", "chain": "Brightmart", "store_name": "Brightmart #5", "address": "2 Oak Street", "city": "Fairview", "state": "TX"},
    {"store_id": "S3", "chain": "ValuMax", "store_name": "ValuMax Center", "address": "3 Elm Avenue", "city": "Oakview", "state": "CA"},
    {"store_id": "S4", "chain": "ValuMax", "store_name": "ValuMax #5", "address": "4 Pine Road", "city": "Oakview", "state": "CA"},
    {"store_id": "S5", "chain": "Cornerstone Mobile", "store_name": "Cornerstone Mobile #5", "address": "5 Birch Drive", "city": "Fairview", "state": "TX"},
    {"store_id": "S6", "chain": "Cornerstone Mobile", "store_name": "Cornerstone Mobile Market", "address": "6 Cedar Drive", "city": "Rosewood", "state": "NC"},
    {"store_id": "S7", "chain": "Harbor & Vine", "store_name": "Harbor & Vine Outlet", "address": "7 Juniper Drive", "city": "Rosewood", "state": "NC"},
]


@pytest.fixture
def index():
    return MasterIndex(MASTER_ROWS)


def test_pass1_exact_match(index):
    result = pass_1_exact("Brightmart Plaza", "Fairview", index)
    assert result is not None
    assert result.store_id == "S1"
    assert result.confidence == "high"


def test_pass1_no_match_wrong_city(index):
    # Right text, wrong city -> pass 1 must not guess across cities.
    assert pass_1_exact("Brightmart Plaza", "Oakview", index) is None


def test_pass2_expands_abbreviation(index):
    result = pass_2_normalized("ValuMax Ctr", "Oakview", index)
    assert result is not None
    assert result.store_id == "S3"


def test_pass2_drops_chain_prefix(index):
    result = pass_2_normalized("Outlet", "Rosewood", index)
    assert result is not None
    assert result.store_id == "S7"


def test_pass2_rejects_ambiguous_after_stripping(index):
    # Both "Cornerstone Mobile Market" variants collapse differently, but
    # construct a genuine collision: two Rosewood stores whose stripped
    # residual is identical should not be auto-matched.
    rows = MASTER_ROWS + [
        {"store_id": "S8", "chain": "Harbor & Vine", "store_name": "Harbor & Vine Market", "address": "8 Elm Drive", "city": "Rosewood", "state": "NC"},
    ]
    idx = MasterIndex(rows)
    # "Market" alone is ambiguous between S6 (Cornerstone Mobile Market) and
    # the new S8 (Harbor & Vine Market) once each chain prefix is stripped.
    assert pass_2_normalized("Market", "Rosewood", idx) is None


def test_pass3_unique_number_in_city(index):
    result = pass_3_store_number("#5", "Oakview", index)
    assert result is not None
    assert result.store_id == "S4"
    assert result.confidence == "medium"  # no corroborating chain text


def test_pass3_disambiguates_by_chain(index):
    result = pass_3_store_number("Brightmart #5", "Fairview", index)
    assert result is not None
    assert result.store_id == "S2"


def test_pass3_ambiguous_without_chain_hint(index):
    # Two Fairview stores share number 5 (Brightmart and Cornerstone
    # Mobile); a bare "#5" cannot be resolved safely.
    assert pass_3_store_number("#5", "Fairview", index) is None


def test_pass3_rejects_contradicting_chain(index):
    # Only ValuMax #5 exists in Oakview, but the text names a different
    # chain entirely -- the number alone must not override that.
    assert pass_3_store_number("Cornerstone Mobile #5", "Oakview", index) is None


def test_pass3_no_number_present(index):
    assert pass_3_store_number("Brightmart Plaza", "Fairview", index) is None


def test_pass4_token_set_match(index):
    result = pass_4_token_set("vine harbor outlet", "Rosewood", index)
    assert result is not None
    assert result.store_id == "S7"


def test_pass4_no_match_below_threshold(index):
    assert pass_4_token_set("completely unrelated text here", "Rosewood", index) is None


def test_pass4_ambiguous_tie_returns_none():
    rows = [
        {"store_id": "A1", "chain": "Brightmart", "store_name": "Brightmart Plaza", "address": "1 Main St", "city": "Fairview", "state": "TX"},
        {"store_id": "A2", "chain": "ValuMax", "store_name": "ValuMax Plaza", "address": "2 Oak St", "city": "Fairview", "state": "TX"},
    ]
    idx = MasterIndex(rows)
    # "Plaza" alone overlaps both candidates equally -- must not guess.
    assert pass_4_token_set("Plaza", "Fairview", idx) is None


def test_pass4_ignores_bare_numbered_candidates():
    # A bare numbered store ("Brightmart #26") has no suffix word for
    # token-set overlap to work with. Its tiny {"brightmart"} token set
    # must not out-score a longer, correct candidate just because the
    # correct one's extra word has a typo.
    rows = [
        {"store_id": "A1", "chain": "Cornerstone Mobile", "store_name": "Cornerstone Mobile Market", "address": "1 Main St", "city": "Fairview", "state": "TX"},
        {"store_id": "A2", "chain": "Cornerstone Mobile", "store_name": "Cornerstone Mobile #26", "address": "2 Oak St", "city": "Fairview", "state": "TX"},
    ]
    idx = MasterIndex(rows)
    result = pass_4_token_set("Cornerstone Mobile Maret", "Fairview", idx)
    # Not confident enough via pure token overlap (the typo breaks an
    # exact token match) -- but critically, must NOT pick A2.
    assert result is None or result.store_id == "A1"


def test_pass4_number_mismatch_penalty_breaks_a_tie(index):
    # Both ValuMax Center and a same-city rival share no tokens with a
    # number in the text, but a candidate whose *own* number conflicts
    # with the text's number should never win.
    rows = [
        {"store_id": "A1", "chain": "Brightmart", "store_name": "Brightmart Outlet", "address": "1 Main St", "city": "Fairview", "state": "TX"},
        {"store_id": "A2", "chain": "Brightmart", "store_name": "Brightmart #9", "address": "2 Oak St", "city": "Fairview", "state": "TX"},
        {"store_id": "A3", "chain": "Brightmart", "store_name": "Brightmart Outlet #9", "address": "3 Elm St", "city": "Fairview", "state": "TX"},
    ]
    idx = MasterIndex(rows)
    result = pass_4_token_set("Brightmart Outlet #5", "Fairview", idx)
    # The text says #5; A3 says #9 -- conflicting number, must be
    # penalized relative to A1 (which makes no number claim at all).
    assert result is None or result.store_id != "A3"


def test_pass5_fuzzy_typo_match():
    # Scoped to its own index (rather than the shared fixture) so the typo
    # match isn't incidentally close to an unrelated numbered store that
    # happens to share the same chain prefix in the same city.
    rows = [
        {"store_id": "T1", "chain": "Brightmart", "store_name": "Brightmart Plaza", "address": "1 Main St", "city": "Lonetown", "state": "TX"},
    ]
    idx = MasterIndex(rows)
    result = pass_5_fuzzy("Brigtmart Plaz", "Lonetown", idx)
    assert result is not None
    assert result.store_id == "T1"


def test_pass5_ambiguous_close_scores_returns_none():
    rows = [
        {"store_id": "A1", "chain": "Brightmart", "store_name": "Brightmart Plaza", "address": "1 Main St", "city": "Fairview", "state": "TX"},
        {"store_id": "A2", "chain": "Brightmart", "store_name": "Brightmart Plaze", "address": "2 Oak St", "city": "Fairview", "state": "TX"},
    ]
    idx = MasterIndex(rows)
    # Equidistant from two near-identical names in the same city: ambiguous.
    result = pass_5_fuzzy("Brightmart Plazx", "Fairview", idx)
    assert result is None


def test_pass5_no_rows_in_city(index):
    assert pass_5_fuzzy("Anything At All", "Nowhereville", index) is None
