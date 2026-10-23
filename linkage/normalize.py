"""Text normalization helpers shared by the matcher passes.

Kept deliberately dumb and table-driven: every rule here is something a
human reviewer could read in thirty seconds and agree with.
"""

from __future__ import annotations

import re
import unicodedata

# Full word -> abbreviation does not matter here; we only ever expand
# *abbreviation -> full word* so that both a messy "Ctr" and a clean
# "Center" normalize to the same token.
ABBREVIATIONS = {
    "st": "street",
    "str": "street",
    "ctr": "center",
    "cntr": "center",
    "blvd": "boulevard",
    "ave": "avenue",
    "av": "avenue",
    "dr": "drive",
    "rd": "road",
    "mkt": "market",
    "mktpl": "marketplace",
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
}

_PUNCT_RE = re.compile(r"[^a-z0-9#\s]")
_WS_RE = re.compile(r"\s+")
# "#1042" is the common case, but the generator (and real field reps) also
# write "No 1042" / "No. 1042" / "Number 1042" when punctuation gets
# stripped or auto-corrected away.
_STORE_NUM_RE = re.compile(r"#\s*(\d+)|\bno\.?\s*(\d+)\b|\bnumber\s*(\d+)\b", re.IGNORECASE)

# Tokens that only ever carry store-number information, not identity.
# Pass 3 is the dedicated home for that signal; everywhere else (pass 1-2,
# 4-5) these are noise that should be dropped rather than compared
# literally, so a dropped "#" or a degraded "No" doesn't masquerade as a
# distinguishing word.
_NUMBER_FILLER_WORDS = {"no", "number", "store"}

# A trailing "<street name> <street type>" is address noise a field rep
# tacked on, not part of the store's identity -- no chain's own suffix
# vocabulary (Center/Plaza/Market/...) is a street type, so stripping this
# is safe for this domain and a reasonable general heuristic besides.
STREET_TYPE_WORDS = {"street", "boulevard", "avenue", "drive", "road"}


def strip_accents(text: str) -> str:
    """Strip combining accent marks, e.g. 'Peña' -> 'Pena'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def basic_clean(text: str) -> str:
    """Lowercase, strip accents, drop punctuation (keep '#'), collapse spaces."""
    text = strip_accents(text or "")
    text = text.lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def tokenize(text: str) -> list[str]:
    return basic_clean(text).split()


def expand_abbreviations(tokens: list[str]) -> list[str]:
    return [ABBREVIATIONS.get(tok, tok) for tok in tokens]


def extract_store_number(text: str) -> str | None:
    """Pull a '#1042' / 'No 1042' / 'Number 1042' token out of free text."""
    match = _STORE_NUM_RE.search(text or "")
    if not match:
        return None
    digits = next(g for g in match.groups() if g is not None)
    return digits.lstrip("0") or "0"


def strip_chain_prefix(tokens: list[str], chain_tokens_list: list[list[str]]) -> list[str]:
    """Drop a leading run of tokens that match any known chain name's tokens."""
    for chain_tokens in chain_tokens_list:
        n = len(chain_tokens)
        if n and tokens[:n] == chain_tokens:
            return tokens[n:]
    return tokens


def strip_trailing_address(tokens: list[str]) -> list[str]:
    """Drop a trailing '<street name> <street type>' hint, e.g. "... Main Street"."""
    if len(tokens) >= 2 and tokens[-1] in STREET_TYPE_WORDS:
        return tokens[:-2] if len(tokens) > 2 else tokens[:-1]
    return tokens


def _drop_number_and_filler(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t and not t.startswith("#") and not t.isdigit() and t not in _NUMBER_FILLER_WORDS]


def normalize_key(text: str) -> str:
    """Pass-1 style key: cheap, exact-ish normalization. No abbreviation expansion."""
    return basic_clean(text)


def normalize_full(text: str, chain_tokens_list: list[list[str]] | None = None) -> str:
    """Pass-2 style key: accents stripped, abbreviations expanded, chain prefix dropped."""
    tokens = tokenize(text)
    tokens = expand_abbreviations(tokens)
    tokens = _drop_number_and_filler(tokens)
    tokens = strip_trailing_address(tokens)
    if chain_tokens_list:
        tokens = strip_chain_prefix(tokens, chain_tokens_list)
    return " ".join(tokens)


def token_set(text: str, chain_tokens_list: list[list[str]] | None = None) -> set[str]:
    tokens = tokenize(text)
    tokens = expand_abbreviations(tokens)
    tokens = _drop_number_and_filler(tokens)
    tokens = strip_trailing_address(tokens)
    if chain_tokens_list:
        tokens = strip_chain_prefix(tokens, chain_tokens_list)
    return set(tokens)
