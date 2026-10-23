"""Pass 0's feedback loop: fold human triage decisions back into aliases.csv.

Reads a triage.csv where a human has filled the `decision` column with
either a store_id or the literal "none" (confirmed: this text matches no
master record). Appends/updates data/aliases.csv so the next matcher run
resolves those rows automatically via pass 0, without re-triaging them.

Pass 0 is meant to be the *most* trustworthy pass, not the least: an alias
is only as reliable as the claim "this exact text, in this city, always
means this one store." If the master list itself has two stores with the
same name in the same city, that claim is false by construction -- so the
learner refuses (and reports) any alias whose key would map to more than
one master store, rather than silently guessing one of them.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .matcher import MasterIndex, load_master
from .normalize import normalize_key

# Aliases are keyed on (normalized_text, city), never normalized_text alone:
# a bare store-number fragment like "#11" is not globally unique (store
# numbers are only unique within a chain), so an alias must stay scoped to
# the city it was learned in.
ALIAS_FIELDS = ["normalized_text", "city", "decision", "source"]


@dataclass
class LearnResult:
    added: int = 0
    refused: list[dict] = field(default_factory=list)


def load_aliases(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        return {(row["normalized_text"], row["city"]): row for row in csv.DictReader(fh)}


def learn(triage_path: Path, aliases_path: Path, master_path: Path) -> LearnResult:
    """Fold decided triage rows into aliases.csv. Returns counts/details."""
    aliases = load_aliases(aliases_path)
    index = MasterIndex(load_master(master_path))
    result = LearnResult()

    with Path(triage_path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            decision = (row.get("decision") or "").strip()
            if not decision:
                continue

            city = row["city"]
            text_key = normalize_key(row["store_text"])

            if decision.lower() != "none":
                # Refuse an alias whose literal key matches more than one
                # master store in this city -- a same-name-same-city
                # collision means "this exact text always means this
                # store" isn't actually true, and guessing would make
                # pass 0 the least trustworthy pass instead of the most.
                same_name_candidates = index.by_city_key.get((city, text_key), [])
                if len(same_name_candidates) > 1:
                    result.refused.append(
                        {
                            "report_row_id": row["report_row_id"],
                            "normalized_text": text_key,
                            "city": city,
                            "reason": f"matches {len(same_name_candidates)} master stores: "
                            f"{', '.join(same_name_candidates)}",
                        }
                    )
                    continue

            key = (text_key, city)
            if key not in aliases or aliases[key].get("decision") != decision:
                result.added += 1
            aliases[key] = {
                "normalized_text": key[0],
                "city": key[1],
                "decision": decision,
                "source": row["report_row_id"],
            }

    aliases_path = Path(aliases_path)
    aliases_path.parent.mkdir(parents=True, exist_ok=True)
    with aliases_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=ALIAS_FIELDS)
        writer.writeheader()
        for key in sorted(aliases):
            writer.writerow(aliases[key])

    return result


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Learn aliases from decided triage rows.")
    parser.add_argument("--triage", type=str, required=True)
    parser.add_argument("--aliases", type=str, required=True)
    parser.add_argument("--master", type=str, default="data/store_master.csv")
    args = parser.parse_args(argv)

    result = learn(Path(args.triage), Path(args.aliases), Path(args.master))
    print(f"Learned/updated {result.added} alias(es) in {args.aliases}")
    if result.refused:
        print(f"Refused {len(result.refused)} alias(es) -- key maps to more than one master store:")
        for r in result.refused:
            print(f"  {r['report_row_id']}: \"{r['normalized_text']}\" in {r['city']} -- {r['reason']}")


if __name__ == "__main__":
    main()
