PYTHON ?= python3

.PHONY: demo test clean generate match learn evaluate

demo:
	rm -rf data out
	$(PYTHON) -m linkage generate --seed 7 --out data
	@echo ""
	@echo "=== Run 1: match with no learned aliases ==="
	$(PYTHON) -m linkage match --master data/store_master.csv --field-report data/field_report.csv --aliases data/aliases.csv --out out
	cat out/report.md
	@echo ""
	@echo "=== Learn from examples/triage-decided.csv ==="
	$(PYTHON) -m linkage learn --triage examples/triage-decided.csv --aliases data/aliases.csv --master data/store_master.csv
	@echo ""
	@echo "=== Run 2: match with learned aliases ==="
	$(PYTHON) -m linkage match --master data/store_master.csv --field-report data/field_report.csv --aliases data/aliases.csv --out out
	cat out/report.md
	@echo ""
	@echo "=== Evaluate (run 2, against truth.csv) ==="
	$(PYTHON) -m linkage evaluate --matches out/matches.csv --truth data/truth.csv

test:
	$(PYTHON) -m pytest -q

generate:
	$(PYTHON) -m linkage generate --seed 7 --out data

match:
	$(PYTHON) -m linkage match --master data/store_master.csv --field-report data/field_report.csv --aliases data/aliases.csv --out out

learn:
	$(PYTHON) -m linkage learn --triage examples/triage-decided.csv --aliases data/aliases.csv --master data/store_master.csv

evaluate:
	$(PYTHON) -m linkage evaluate --matches out/matches.csv --truth data/truth.csv

clean:
	rm -rf out data __pycache__ .pytest_cache
