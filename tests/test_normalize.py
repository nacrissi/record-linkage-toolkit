from linkage.normalize import (
    basic_clean,
    extract_store_number,
    strip_accents,
    strip_chain_prefix,
    tokenize,
)


def test_strip_accents():
    assert strip_accents("Pena Vista") == "Pena Vista"
    assert strip_accents("Peña Vista") == "Pena Vista"


def test_basic_clean_collapses_whitespace_and_punct():
    assert basic_clean("  Brightmart,  Plaza!! ") == "brightmart plaza"


def test_extract_store_number():
    assert extract_store_number("Brightmart #1042") == "1042"
    assert extract_store_number("Brightmart #0042") == "42"
    assert extract_store_number("Brightmart Plaza") is None


def test_strip_chain_prefix():
    chains = [["brightmart"], ["cornerstone", "mobile"]]
    assert strip_chain_prefix(tokenize("Brightmart Plaza"), chains) == ["plaza"]
    assert strip_chain_prefix(tokenize("Cornerstone Mobile Market"), chains) == ["market"]
    assert strip_chain_prefix(tokenize("Market"), chains) == ["market"]
