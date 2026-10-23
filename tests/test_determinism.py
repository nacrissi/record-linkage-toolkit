import csv
import filecmp
from collections import Counter
from pathlib import Path

from linkage.generate import generate


def test_same_seed_produces_identical_files(tmp_path: Path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    generate(seed=42, out_dir=out_a, n_stores=50, n_rows=70)
    generate(seed=42, out_dir=out_b, n_stores=50, n_rows=70)

    for name in ["store_master.csv", "field_report.csv", "truth.csv"]:
        assert filecmp.cmp(out_a / name, out_b / name, shallow=False), f"{name} differs between identical-seed runs"


def test_different_seeds_produce_different_output(tmp_path: Path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    generate(seed=1, out_dir=out_a, n_stores=50, n_rows=70)
    generate(seed=2, out_dir=out_b, n_stores=50, n_rows=70)

    assert not filecmp.cmp(out_a / "field_report.csv", out_b / "field_report.csv", shallow=False)


def test_master_has_no_same_name_same_city_duplicates(tmp_path: Path):
    # Real multi-location chains disambiguate by address, never by name
    # alone within one city -- an alias (or a human) can't reliably tell
    # two identically-named-and-located stores apart, so the generator
    # must not produce that collision.
    out_dir = tmp_path / "data"
    generate(seed=99, out_dir=out_dir, n_stores=400, n_rows=10)

    with (out_dir / "store_master.csv").open() as fh:
        rows = list(csv.DictReader(fh))

    counts = Counter((r["store_name"], r["city"]) for r in rows)
    duplicates = {k: v for k, v in counts.items() if v > 1}
    assert duplicates == {}, f"found same-name-same-city duplicates: {duplicates}"
