# Everything runs through uv; no pyproject.toml.
PY := uv run --no-project --with pytest --with cadquery --with ezdxf --with pypdf --with pillow --with shapely

.PHONY: test test-all verify outputs check tools fetch renders sheets

## test: run the pytest suite, less the tests marked slow (R21)
test:
	$(PY) python -m pytest tests -v -m "not slow"

## test-all: run every test, slow ones included
test-all:
	$(PY) python -m pytest tests -v

## verify: check dimensions and report UNCONFIRMED figures
verify:
	$(PY) python verify.py

## outputs: regenerate everything under output/ (printed and laser routes)
outputs:
	$(PY) python scripts/export_printed.py
	$(PY) python scripts/export_laser.py

## check: test + verify + sheet checks
check: test verify
	@echo "sheet checks: not implemented yet (Task 13)"; exit 1

## fetch: download upstream sources into tmp/src
fetch:
	$(PY) python scripts/fetch.py

## renders: Blender renders
renders:
	@echo "renders: not implemented yet (Task 14)"; exit 1

## sheets: drawing sheets
sheets:
	@echo "sheets: not implemented yet (Task 13)"; exit 1

## tools: check external tools (inkscape, blender)
tools:
	$(PY) python scripts/check_tools.py
