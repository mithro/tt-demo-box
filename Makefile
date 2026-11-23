# Everything runs through uv; no pyproject.toml.
PY := uv run --no-project --with pytest --with cadquery --with ezdxf --with pypdf --with pillow --with shapely

.PHONY: test verify outputs check tools fetch renders sheets

## test: run the pytest suite
test:
	$(PY) python -m pytest tests -v

## verify: check dimensions and report UNCONFIRMED figures
verify:
	$(PY) python verify.py

## outputs: regenerate everything under output/ (printed route; Task 8 adds laser)
outputs:
	$(PY) python scripts/export_printed.py

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
