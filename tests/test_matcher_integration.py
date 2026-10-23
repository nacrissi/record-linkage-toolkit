import csv
from pathlib import Path

from linkage import matcher
from linkage.generate import generate
from linkage.learn import learn


def test_ambiguous_row_goes_to_triage(tmp_path: Path):
    master = [
        {"store_id": "A1", "chain": "Brightmart", "store_name": "Brightmart Crossing", "address": "1 Main St", "city": "Fairview", "state": "TX"},
        {"store_id": "A2", "chain": "Brightmart", "store_name": "Brightmart Crossing", "address": "2 Oak St", "city": "Fairview", "state": "TX"},
    ]
    field_rows = [
        {"report_row_id": "R1", "rep_name": "A B", "store_text": "Brightmart Crossing", "city": "Fairview", "week": "2026-W01", "units": "5"},
    ]
    master_path = tmp_path / "master.csv"
    field_path = tmp_path / "field.csv"
    _write_csv(master_path, master, ["store_id", "chain", "store_name", "address", "city", "state"])
    _write_csv(field_path, field_rows, ["report_row_id", "rep_name", "store_text", "city", "week", "units"])

    out_dir = tmp_path / "out"
    summary = matcher.run(master_path, field_path, tmp_path / "missing_aliases.csv", out_dir)

    assert summary["matched"] == 0
    assert summary["triage"] == 1
    triage_rows = list(csv.DictReader((out_dir / "triage.csv").open()))
    assert triage_rows[0]["report_row_id"] == "R1"
    assert triage_rows[0]["candidate_1_store_id"] in {"A1", "A2"}
    assert triage_rows[0]["candidate_2_store_id"] in {"A1", "A2"}


def test_alias_feedback_loop_reduces_triage(tmp_path: Path):
    data_dir = tmp_path / "data"
    generate(seed=11, out_dir=data_dir, n_stores=60, n_rows=80)

    out1 = tmp_path / "out1"
    aliases_path = data_dir / "aliases.csv"
    summary1 = matcher.run(data_dir / "store_master.csv", data_dir / "field_report.csv", aliases_path, out1)

    triage_rows = list(csv.DictReader((out1 / "triage.csv").open()))
    truth = {r["report_row_id"]: r["store_id"] for r in csv.DictReader((data_dir / "truth.csv").open())}

    assert triage_rows, "expected at least one triage row for this fixture"

    decided_path = tmp_path / "triage_decided.csv"
    decided_rows = []
    for row in triage_rows:
        row = dict(row)
        true = truth.get(row["report_row_id"], "")
        row["decision"] = true if true else "none"
        decided_rows.append(row)
    _write_csv(decided_path, decided_rows, list(decided_rows[0].keys()))

    learn(decided_path, aliases_path, data_dir / "store_master.csv")

    out2 = tmp_path / "out2"
    summary2 = matcher.run(data_dir / "store_master.csv", data_dir / "field_report.csv", aliases_path, out2)

    assert summary2["triage"] < summary1["triage"]
    assert summary2["matched"] > summary1["matched"]
    assert summary2["pass_counts"][0] > 0


def test_learned_none_decision_is_not_re_triaged(tmp_path: Path):
    master = [
        {"store_id": "B1", "chain": "ValuMax", "store_name": "ValuMax Plaza", "address": "1 Main St", "city": "Fairview", "state": "TX"},
    ]
    field_rows = [
        {"report_row_id": "R1", "rep_name": "A B", "store_text": "Phantom Store Nine", "city": "Fairview", "week": "2026-W01", "units": "5"},
    ]
    master_path = tmp_path / "master.csv"
    field_path = tmp_path / "field.csv"
    _write_csv(master_path, master, ["store_id", "chain", "store_name", "address", "city", "state"])
    _write_csv(field_path, field_rows, ["report_row_id", "rep_name", "store_text", "city", "week", "units"])

    aliases_path = tmp_path / "aliases.csv"
    decided_path = tmp_path / "decided.csv"
    _write_csv(
        decided_path,
        [{"report_row_id": "R1", "store_text": "Phantom Store Nine", "city": "Fairview", "decision": "none"}],
        ["report_row_id", "store_text", "city", "decision"],
    )
    learn(decided_path, aliases_path, master_path)

    out_dir = tmp_path / "out"
    summary = matcher.run(master_path, field_path, aliases_path, out_dir)

    assert summary["triage"] == 0
    matches = list(csv.DictReader((out_dir / "matches.csv").open()))
    assert matches[0]["store_id"] == ""
    assert matches[0]["pass"] == "0"


def test_learner_refuses_alias_for_duplicate_name_city(tmp_path: Path):
    # Two master stores share the exact same name in the exact same city.
    # A human deciding a triage row for that text could have meant either
    # one -- the learner must refuse to bake a guess into an alias.
    master = [
        {"store_id": "C1", "chain": "Cornerstone Mobile", "store_name": "Cornerstone Mobile Crossing", "address": "1 Main St", "city": "Spring Hollow", "state": "OK"},
        {"store_id": "C2", "chain": "Cornerstone Mobile", "store_name": "Cornerstone Mobile Crossing", "address": "2 Oak St", "city": "Spring Hollow", "state": "OK"},
    ]
    master_path = tmp_path / "master.csv"
    _write_csv(master_path, master, ["store_id", "chain", "store_name", "address", "city", "state"])

    decided_path = tmp_path / "decided.csv"
    _write_csv(
        decided_path,
        [{"report_row_id": "R1", "store_text": "Cornerstone Mobile Crossing", "city": "Spring Hollow", "decision": "C1"}],
        ["report_row_id", "store_text", "city", "decision"],
    )
    aliases_path = tmp_path / "aliases.csv"

    result = learn(decided_path, aliases_path, master_path)

    assert result.added == 0
    assert len(result.refused) == 1
    assert result.refused[0]["report_row_id"] == "R1"

    # Refusal must mean "nothing written", not "written anyway".
    with aliases_path.open() as fh:
        rows = list(csv.DictReader(fh))
    assert rows == []


def test_learner_allows_alias_once_names_are_unique(tmp_path: Path):
    # Same text, but the city's names are unique -- the decision is safe
    # to learn.
    master = [
        {"store_id": "D1", "chain": "Cornerstone Mobile", "store_name": "Cornerstone Mobile Crossing", "address": "1 Main St", "city": "Spring Hollow", "state": "OK"},
        {"store_id": "D2", "chain": "Cornerstone Mobile", "store_name": "Cornerstone Mobile Outlet", "address": "2 Oak St", "city": "Spring Hollow", "state": "OK"},
    ]
    master_path = tmp_path / "master.csv"
    _write_csv(master_path, master, ["store_id", "chain", "store_name", "address", "city", "state"])

    decided_path = tmp_path / "decided.csv"
    _write_csv(
        decided_path,
        [{"report_row_id": "R1", "store_text": "Cornerstone Mobile Crossing", "city": "Spring Hollow", "decision": "D1"}],
        ["report_row_id", "store_text", "city", "decision"],
    )
    aliases_path = tmp_path / "aliases.csv"

    result = learn(decided_path, aliases_path, master_path)

    assert result.added == 1
    assert result.refused == []


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
