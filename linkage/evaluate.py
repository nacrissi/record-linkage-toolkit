"""Evaluate matcher output against the (test-only) ground truth.

truth.csv is never read by the matcher itself -- only by this report and
by tests. Precision is computed over auto-matched rows only (anything the
matcher was confident enough to put in matches.csv); recall is computed
over the rows that truly have a master-list match.
"""

from __future__ import annotations

import csv
from pathlib import Path


def load_truth(path: Path) -> dict[str, str]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return {row["report_row_id"]: row["store_id"] for row in csv.DictReader(fh)}


def load_matches(path: Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def evaluate(matches_path: Path, truth_path: Path) -> dict:
    truth = load_truth(truth_path)
    matches = load_matches(matches_path)

    total_true_positive = sum(1 for v in truth.values() if v)

    per_pass: dict[str, dict[str, int]] = {}
    overall_correct = 0
    correct_nonblank = 0

    for row in matches:
        pred = row["store_id"]
        true = truth.get(row["report_row_id"], "")
        correct = pred == true

        stats = per_pass.setdefault(row["pass"], {"count": 0, "correct": 0})
        stats["count"] += 1
        if correct:
            overall_correct += 1
            stats["correct"] += 1
            if pred:
                correct_nonblank += 1

    overall_total = len(matches)
    precision = overall_correct / overall_total if overall_total else 0.0
    recall = correct_nonblank / total_true_positive if total_true_positive else 0.0

    return {
        "overall_total": overall_total,
        "overall_correct": overall_correct,
        "precision": precision,
        "recall": recall,
        "total_true_positive": total_true_positive,
        "correct_nonblank": correct_nonblank,
        "per_pass": per_pass,
    }


def format_report(stats: dict) -> str:
    lines = []
    lines.append(
        f"Overall auto-match precision: {stats['overall_correct']}/{stats['overall_total']} "
        f"= {stats['precision'] * 100:.2f}%"
    )
    lines.append(
        f"Overall recall (of rows with a true match): {stats['correct_nonblank']}/{stats['total_true_positive']} "
        f"= {stats['recall'] * 100:.2f}%"
    )
    lines.append("")
    lines.append("Per-pass precision:")
    for pass_num in sorted(stats["per_pass"], key=lambda p: int(p)):
        p = stats["per_pass"][pass_num]
        pct = (p["correct"] / p["count"] * 100) if p["count"] else 0.0
        lines.append(f"  pass {pass_num}: {p['correct']}/{p['count']} = {pct:.2f}%")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate matcher precision/recall against truth.csv.")
    parser.add_argument("--matches", type=str, default="out/matches.csv")
    parser.add_argument("--truth", type=str, default="data/truth.csv")
    args = parser.parse_args(argv)

    stats = evaluate(Path(args.matches), Path(args.truth))
    print(format_report(stats))


if __name__ == "__main__":
    main()
