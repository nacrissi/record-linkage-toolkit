"""CLI entry point: python -m linkage <generate|match|learn|evaluate>."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import evaluate as evaluate_mod
from . import generate as generate_mod
from . import learn as learn_mod
from . import matcher as matcher_mod


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m linkage")
    sub = parser.add_subparsers(dest="command", required=True)

    p_generate = sub.add_parser("generate", help="Generate synthetic store_master/field_report/truth CSVs.")
    p_generate.add_argument("--seed", type=int, default=7)
    p_generate.add_argument("--out", type=str, default="data/")
    p_generate.add_argument("--stores", type=int, default=400)
    p_generate.add_argument("--rows", type=int, default=600)

    p_match = sub.add_parser("match", help="Run the 5-pass matcher over the field report.")
    p_match.add_argument("--master", type=str, default="data/store_master.csv")
    p_match.add_argument("--field-report", type=str, default="data/field_report.csv")
    p_match.add_argument("--aliases", type=str, default="data/aliases.csv")
    p_match.add_argument("--out", type=str, default="out/")

    p_learn = sub.add_parser("learn", help="Fold decided triage rows back into aliases.csv.")
    p_learn.add_argument("--triage", type=str, required=True)
    p_learn.add_argument("--aliases", type=str, required=True)
    p_learn.add_argument("--master", type=str, default="data/store_master.csv")

    p_eval = sub.add_parser("evaluate", help="Report precision/recall of matches.csv against truth.csv.")
    p_eval.add_argument("--matches", type=str, default="out/matches.csv")
    p_eval.add_argument("--truth", type=str, default="data/truth.csv")

    args = parser.parse_args()

    if args.command == "generate":
        generate_mod.generate(args.seed, Path(args.out), args.stores, args.rows)
        print(f"Wrote store_master.csv, field_report.csv, truth.csv to {args.out}")
    elif args.command == "match":
        out_dir = Path(args.out)
        summary = matcher_mod.run(Path(args.master), Path(args.field_report), Path(args.aliases), out_dir)
        print(
            f"Matched {summary['matched']}/{summary['total']} rows; "
            f"{summary['triage']} sent to triage. See {out_dir / 'report.md'}"
        )
    elif args.command == "learn":
        result = learn_mod.learn(Path(args.triage), Path(args.aliases), Path(args.master))
        print(f"Learned/updated {result.added} alias(es) in {args.aliases}")
        if result.refused:
            print(f"Refused {len(result.refused)} alias(es) -- key maps to more than one master store:")
            for r in result.refused:
                print(f"  {r['report_row_id']}: \"{r['normalized_text']}\" in {r['city']} -- {r['reason']}")
    elif args.command == "evaluate":
        stats = evaluate_mod.evaluate(Path(args.matches), Path(args.truth))
        print(evaluate_mod.format_report(stats))


if __name__ == "__main__":
    main()
