"""Synthetic data generator for the record-linkage demo.

Everything here is invented: chain names, cities, street names, rep names.
No real people, companies, retailers, or carriers appear anywhere below.

Produces three files in the destination directory:
    store_master.csv  - the canonical list (store_id, chain, store_name, ...)
    field_report.csv   - messy free-typed rows referencing those stores
    truth.csv           - report_row_id -> store_id, for tests/evaluation only

Deterministic: the same --seed always produces byte-identical output.
"""

from __future__ import annotations

import argparse
import csv
import random
import unicodedata
from pathlib import Path

CHAINS = [
    "Brightmart",
    "ValuMax",
    "Cornerstone Mobile",
    "NorthGate Foods",
    "Prairie Supply Co",
    "Lonestar Outfitters",
    "Rio Fresh Market",
    "Harbor & Vine",
]

# Stores that genuinely do not exist in the master list. Used to generate
# the ~5% of field-report rows with no true match.
PHANTOM_CHAINS = [
    "QuickStop Depot",
    "Pinecrest Traders",
    "Golden Era Goods",
    "Driftwood Supply",
]

SUFFIXES = ["Center", "Plaza", "Market", "Express", "Outlet", "Supercenter", "Crossing", "Station"]
DIRECTIONALS = ["North", "South", "East", "West"]
NEIGHBORHOODS = ["Pena Vista", "Canada Linda", "La Montana", "El Nino", "Loma Alta", "Rincon Verde"]

CITIES = [
    "Fairview", "Oakview", "Rio Verde", "Santa Elena", "Cedar Falls",
    "Maple Grove", "Nueva Vista", "Los Pinos", "Buena Vista", "Lakeside",
    "Mission Hills", "Palo Seco", "Spring Hollow", "Rosewood", "El Mirador",
    "Stonebridge", "Alta Loma", "Crestwood", "Valle Hermoso", "Prairie Bend",
]

STATES = ["TX", "CA", "AZ", "CO", "NM", "OK", "GA", "FL", "NC", "OH", "IL", "WA", "OR", "NV", "UT"]

STREET_NAMES = [
    "Main", "Oak", "Maple", "Sunset", "Mission", "Rio Grande", "Juniper",
    "Sierra", "Cedar", "Camino Real", "Palomino", "Westfield", "Lakeview",
    "Hillcrest", "Paseo Verde", "Elm", "Birch", "Vista Linda",
]
STREET_TYPES = ["Street", "Boulevard", "Avenue", "Drive", "Road"]
STREET_ABBREV = {"Street": "St", "Boulevard": "Blvd", "Avenue": "Ave", "Drive": "Dr", "Road": "Rd"}

FIRST_NAMES = [
    "Dana", "Marcus", "Priya", "Oliver", "Teresa", "Felix", "Nadia", "Sam",
    "Rosa", "Dimitri", "Kelly", "Amir", "Grace", "Hector", "Wendy", "Jonas",
]
LAST_NAMES = [
    "Ruiz", "Lee", "Nandy", "Kim", "Alvarez", "Brennan", "Osei", "Choudhury",
    "Mercer", "Vance", "Patton", "Reyes", "Whitfield", "Dunmore", "Castillo",
]

WEEKS = [f"2026-W{w:02d}" for w in range(1, 13)]


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def build_store_name(rng: random.Random, chain: str, chain_number: int) -> str:
    if rng.random() < 0.4:
        base = f"{chain} #{chain_number}"
    else:
        parts = [chain]
        if rng.random() < 0.3:
            parts.append(rng.choice(DIRECTIONALS))
        parts.append(rng.choice(SUFFIXES))
        base = " ".join(parts)
    if rng.random() < 0.2:
        base = f"{base} - {rng.choice(NEIGHBORHOODS)}"
    return base


def build_master(rng: random.Random, n_stores: int) -> list[dict]:
    rows = []
    chain_counters = {chain: 0 for chain in CHAINS}
    seen_name_city: set[tuple[str, str]] = set()
    for i in range(1, n_stores + 1):
        chain = CHAINS[(i - 1) % len(CHAINS)]
        chain_counters[chain] += 1
        city = rng.choice(CITIES)

        # Real multi-location chains do sometimes reuse a bare name within
        # one city, but it is rare and always distinguishable by address --
        # never by name alone. Retry a few times, then fall back to a
        # visibly-different disambiguator rather than silently colliding.
        store_name = build_store_name(rng, chain, chain_counters[chain])
        for _ in range(8):
            if (store_name, city) not in seen_name_city:
                break
            store_name = build_store_name(rng, chain, chain_counters[chain])
        else:
            store_name = f"{store_name} ({chain_counters[chain]})"
        seen_name_city.add((store_name, city))

        street = f"{rng.randint(100, 9999)} {rng.choice(STREET_NAMES)} {rng.choice(STREET_TYPES)}"
        state = rng.choice(STATES)
        rows.append(
            {
                "store_id": f"ST{i:04d}",
                "chain": chain,
                "store_name": store_name,
                "address": street,
                "city": city,
                "state": state,
            }
        )
    rng.shuffle(rows)
    return rows


# --- field-report corruption pipeline -------------------------------------

def _typo(text: str, rng: random.Random) -> str:
    if len(text) < 4:
        return text
    pos = rng.randint(1, len(text) - 2)
    kind = rng.choice(["swap", "drop", "dup", "sub"])
    chars = list(text)
    if kind == "swap" and pos + 1 < len(chars):
        chars[pos], chars[pos + 1] = chars[pos + 1], chars[pos]
    elif kind == "drop":
        del chars[pos]
    elif kind == "dup":
        chars.insert(pos, chars[pos])
    elif kind == "sub" and chars[pos].isalpha():
        chars[pos] = rng.choice("abcdefghijklmnopqrstuvwxyz")
    return "".join(chars)


def _abbreviate(text: str, rng: random.Random) -> str:
    full_to_abbrev = {
        "Street": "St", "Boulevard": "Blvd", "Avenue": "Ave", "Drive": "Dr",
        "Road": "Rd", "Center": "Ctr", "Market": "Mkt",
        "North": "N", "South": "S", "East": "E", "West": "W",
    }
    tokens = text.split(" ")
    out = []
    for tok in tokens:
        if tok in full_to_abbrev and rng.random() < 0.7:
            out.append(full_to_abbrev[tok])
        else:
            out.append(tok)
    return " ".join(out)


def _drop_chain_prefix(text: str, chain: str) -> str:
    if text.startswith(chain):
        rest = text[len(chain):].strip()
        return rest or text
    return text


def _reorder_chain(text: str, chain: str, rng: random.Random) -> str:
    if text.startswith(chain):
        rest = text[len(chain):].strip()
        if rest:
            return f"{rest} {chain}"
    return text


def _append_street_hint(text: str, street: str, rng: random.Random) -> str:
    street_type = street.split()[-1]
    abbrev = STREET_ABBREV.get(street_type, street_type)
    street_name = " ".join(street.split()[1:-1])
    tag = f"{street_name} {abbrev}" if rng.random() < 0.5 else f"{street_name} {street_type}"
    return f"{text} {tag}"


def _case_and_punct(text: str, rng: random.Random) -> str:
    choice = rng.random()
    if choice < 0.25:
        text = text.upper()
    elif choice < 0.5:
        text = text.lower()
    if rng.random() < 0.4:
        text = text.replace(" - ", ", ").replace("-", " ")
    if rng.random() < 0.3:
        text = text.replace("#", "No ")
    if rng.random() < 0.3:
        pos = rng.randint(0, len(text))
        text = text[:pos] + "  " + text[pos:]
    return text.strip()


def corrupt_store_text(rng: random.Random, store_name: str, chain: str, street: str) -> str:
    text = store_name
    if rng.random() < 0.15:
        text = _drop_chain_prefix(text, chain)
    elif rng.random() < 0.08:
        text = _reorder_chain(text, chain, rng)
    if rng.random() < 0.35:
        text = _abbreviate(text, rng)
    if rng.random() < 0.15:
        text = _append_street_hint(text, street, rng)
    if rng.random() < 0.3:
        text = _typo(text, rng)
    if rng.random() < 0.25:
        text = strip_accents(text)
    text = _case_and_punct(text, rng)
    return text


def build_phantom_text(rng: random.Random) -> tuple[str, str]:
    chain = rng.choice(PHANTOM_CHAINS)
    suffix = rng.choice(SUFFIXES)
    name = f"{chain} {suffix}" if rng.random() < 0.6 else f"{chain} #{rng.randint(1, 30)}"
    text = _case_and_punct(_abbreviate(name, rng), rng)
    return text, chain


def build_field_report(rng: random.Random, master: list[dict], n_rows: int) -> tuple[list[dict], dict[str, str]]:
    rows = []
    truth = {}
    for i in range(1, n_rows + 1):
        row_id = f"FR{i:04d}"
        if rng.random() < 0.05:
            store_text, _ = build_phantom_text(rng)
            city = rng.choice(CITIES)
            truth[row_id] = ""
        else:
            store = rng.choice(master)
            store_text = corrupt_store_text(rng, store["store_name"], store["chain"], store["address"])
            city = store["city"]
            truth[row_id] = store["store_id"]
        rows.append(
            {
                "report_row_id": row_id,
                "rep_name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                "store_text": store_text,
                "city": city,
                "week": rng.choice(WEEKS),
                "units": rng.randint(1, 500),
            }
        )
    return rows, truth


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate(seed: int, out_dir: Path, n_stores: int = 400, n_rows: int = 600) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    master = build_master(rng, n_stores)
    field_rows, truth = build_field_report(rng, master, n_rows)

    write_csv(
        out_dir / "store_master.csv",
        master,
        ["store_id", "chain", "store_name", "address", "city", "state"],
    )
    write_csv(
        out_dir / "field_report.csv",
        field_rows,
        ["report_row_id", "rep_name", "store_text", "city", "week", "units"],
    )
    truth_rows = [{"report_row_id": rid, "store_id": sid} for rid, sid in truth.items()]
    write_csv(out_dir / "truth.csv", truth_rows, ["report_row_id", "store_id"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic store-matching demo data.")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=str, default="data/")
    parser.add_argument("--stores", type=int, default=400)
    parser.add_argument("--rows", type=int, default=600)
    args = parser.parse_args(argv)
    generate(args.seed, Path(args.out), args.stores, args.rows)
    print(f"Wrote store_master.csv, field_report.csv, truth.csv to {args.out}")


if __name__ == "__main__":
    main()
