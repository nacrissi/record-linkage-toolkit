"""The precision floor the spec requires: auto-match precision >= 98%
against the seeded demo data (seed=7, the same seed the Makefile's `make
demo` recipe uses).
"""

from pathlib import Path

from linkage import matcher
from linkage.evaluate import evaluate
from linkage.generate import generate


def test_precision_floor_on_seeded_data(tmp_path: Path):
    data_dir = tmp_path / "data"
    generate(seed=7, out_dir=data_dir, n_stores=400, n_rows=600)

    out_dir = tmp_path / "out"
    matcher.run(
        data_dir / "store_master.csv",
        data_dir / "field_report.csv",
        data_dir / "aliases.csv",  # does not exist yet -> no aliases
        out_dir,
    )

    stats = evaluate(out_dir / "matches.csv", data_dir / "truth.csv")
    assert stats["overall_total"] > 0
    assert stats["precision"] >= 0.98, f"precision floor breached: {stats['precision']:.4f}"
    assert stats["recall"] >= 0.90, f"recall floor breached: {stats['recall']:.4f}"
