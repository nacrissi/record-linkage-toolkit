"""Orchestrates the matcher: aliases (pass 0) -> passes 1-5 -> triage.

Builds a MasterIndex once per run (precomputed normal forms, token sets,
city blocking) and then walks the field report, stopping at the first pass
that returns a confident match.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .jaro_winkler import jaro_winkler_similarity
from .normalize import extract_store_number, normalize_full, normalize_key, token_set, tokenize
from .passes import ORDERED_PASSES, PassResult, pass_0_alias

PASS_LABELS = {
    0: "Learned aliases (pass 0)",
    1: "Exact match on normalized key",
    2: "Normalized + abbreviation expansion",
    3: "Store-number token cross-check",
    4: "Token-set similarity, blocked by city",
    5: "Jaro-Winkler fuzzy match",
}


class MasterIndex:
    """Precomputed lookups over the canonical store master list."""

    def __init__(self, master_rows: list[dict]):
        chains = sorted({r["chain"] for r in master_rows})
        self.chain_tokens_list = [tokenize(c) for c in chains]

        self.rows: list[dict] = []
        self.by_city: dict[str, list[dict]] = {}
        self.by_city_key: dict[tuple[str, str], list[str]] = {}

        for raw in master_rows:
            row = dict(raw)
            row["norm_full"] = normalize_full(raw["store_name"], None)
            row["norm_full_stripped"] = normalize_full(raw["store_name"], self.chain_tokens_list)
            row["tokens"] = token_set(raw["store_name"], None)
            row["chain_tokens"] = set(tokenize(raw["chain"]))
            row["store_number"] = extract_store_number(raw["store_name"])
            # True if the name carries any descriptor beyond the chain name
            # itself (a suffix word, a directional, a neighborhood). A bare
            # numbered store ("Brightmart #5") has none -- pass 3 (store
            # number) is its home, not pass 4 (token-set), which has no
            # real signal to offer for it.
            row["has_suffix_tokens"] = bool(row["tokens"] - row["chain_tokens"])

            self.rows.append(row)
            self.by_city.setdefault(raw["city"], []).append(row)

            key = normalize_key(raw["store_name"])
            self.by_city_key.setdefault((raw["city"], key), []).append(raw["store_id"])

    def normalize_key(self, text: str) -> str:
        return normalize_key(text)

    def normalize_full(self, text: str, strip_chain: bool = False) -> str:
        return normalize_full(text, self.chain_tokens_list if strip_chain else None)

    def token_set(self, text: str) -> set[str]:
        return token_set(text, None)

    def top_candidates(self, text: str, city: str, n: int = 3) -> list[tuple[float, str]]:
        rows = self.by_city.get(city) or self.rows
        norm_text = self.normalize_full(text, strip_chain=False)
        scored = [(jaro_winkler_similarity(norm_text, row["norm_full"]), row["store_id"]) for row in rows]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[:n]


def load_master(path: Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_field_report(path: Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_aliases(path: Path) -> dict[tuple[str, str], str]:
    """Load learned aliases, keyed on (normalized_text, city).

    A bare fragment like "#11" is only unique within a chain, not globally,
    so aliases must stay scoped to the city they were learned in.
    """
    path = Path(path)
    if not path.exists():
        return {}
    aliases: dict[tuple[str, str], str] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            text = row.get("normalized_text", "")
            city = row.get("city", "")
            decision = (row.get("decision") or "").strip()
            if not text:
                continue
            aliases[(text, city)] = "" if decision.lower() == "none" else decision
    return aliases


def match_row(text: str, city: str, index: MasterIndex, aliases: dict[str, str]) -> tuple[PassResult | None, int | None]:
    result = pass_0_alias(text, city, index, aliases)
    if result is not None:
        return result, 0
    for pass_num, fn in ORDERED_PASSES:
        result = fn(text, city, index)
        if result is not None:
            return result, pass_num
    return None, None


def run(master_path: Path, field_report_path: Path, aliases_path: Path | None, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    master_rows = load_master(master_path)
    field_rows = load_field_report(field_report_path)
    aliases = load_aliases(aliases_path) if aliases_path else {}
    index = MasterIndex(master_rows)

    matches = []
    triage = []
    pass_counts = {n: 0 for n in range(0, 6)}

    for row in field_rows:
        text, city = row["store_text"], row["city"]
        result, pass_num = match_row(text, city, index, aliases)

        if result is not None:
            pass_counts[pass_num] += 1
            matches.append(
                {
                    "report_row_id": row["report_row_id"],
                    "store_text": text,
                    "city": city,
                    "store_id": result.store_id,
                    "pass": pass_num,
                    "score": result.score,
                    "confidence": result.confidence,
                }
            )
        else:
            top3 = index.top_candidates(text, city, 3)
            entry = {"report_row_id": row["report_row_id"], "store_text": text, "city": city}
            for i in range(3):
                score, sid = top3[i] if i < len(top3) else (0.0, "")
                entry[f"candidate_{i + 1}_store_id"] = sid
                entry[f"candidate_{i + 1}_score"] = round(score, 4)
            entry["decision"] = ""
            triage.append(entry)

    _write_csv(
        out_dir / "matches.csv",
        matches,
        ["report_row_id", "store_text", "city", "store_id", "pass", "score", "confidence"],
    )
    _write_csv(
        out_dir / "triage.csv",
        triage,
        [
            "report_row_id", "store_text", "city",
            "candidate_1_store_id", "candidate_1_score",
            "candidate_2_store_id", "candidate_2_score",
            "candidate_3_store_id", "candidate_3_score",
            "decision",
        ],
    )

    total = len(field_rows)
    matched_total = sum(pass_counts.values())
    report_text = _build_report(pass_counts, total, len(triage))
    (out_dir / "report.md").write_text(report_text, encoding="utf-8")

    return {
        "total": total,
        "matched": matched_total,
        "triage": len(triage),
        "pass_counts": pass_counts,
    }


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _build_report(pass_counts: dict[int, int], total: int, triage_count: int) -> str:
    lines = ["# Match Report", "", "| Pass | Description | Rows matched | Cumulative matched | Cumulative % |", "|---|---|---|---|---|"]
    cumulative = 0
    for pass_num in range(0, 6):
        count = pass_counts.get(pass_num, 0)
        cumulative += count
        pct = (cumulative / total * 100) if total else 0.0
        lines.append(f"| {pass_num} | {PASS_LABELS[pass_num]} | {count} | {cumulative} | {pct:.1f}% |")
    lines.append("")
    triage_pct = (triage_count / total * 100) if total else 0.0
    lines.append(f"{triage_count} rows ({triage_pct:.1f}% of {total}) went to triage: unmatched or too ambiguous to auto-match.")
    lines.append("")
    return "\n".join(lines)
