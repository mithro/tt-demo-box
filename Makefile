# Everything runs through uv; no pyproject.toml.
PY := uv run --no-project --with pytest --with cadquery --with ezdxf --with pypdf --with pillow --with shapely
BLENDER := blender -b --factory-startup
# scripts/export_scene.py RENDERS (tests/test_scene.py checks they agree)
RENDERS := printed-closed printed-open-front printed-open-back printed-drawer-out \
	laser-closed laser-open-front laser-open-back laser-drawer-out laser-flatpack

.PHONY: test test-all verify outputs check check-sheets check-outputs check-readme readme tools fetch renders sheets

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

## check: everything CI runs: all tests, verify, sheet checks, outputs up to date
check: test-all verify check-sheets check-outputs check-readme

## check-outputs: rebuild output/ into tmp/check-outputs and compare byte for byte
## (output/renders is not compared: Cycles noise)
check-outputs:
	$(PY) python scripts/check_outputs.py

## check-sheets: text collisions, small text, out of frame, drawing names
check-sheets:
	$(PY) python scripts/check_sheets.py

## readme: rewrite README.md's UNCONFIRMED list from verify.py
readme:
	$(PY) python scripts/update_readme.py

## check-readme: fail if README.md's UNCONFIRMED list is stale
check-readme:
	$(PY) python scripts/update_readme.py --check

## fetch: download upstream sources into tmp/src
fetch:
	$(PY) python scripts/fetch.py

## renders: Blender renders -> output/renders/*.png (scene in tmp/scene, logs tmp/render-*.log)
renders:
	$(PY) python scripts/export_scene.py
	mkdir -p output/renders
	@for r in $(RENDERS); do \
	  echo "render $$r (log: tmp/render-$$r.log)"; \
	  $(BLENDER) -P render/render_scene.py -- --manifest tmp/scene/$$r.json \
	    --out output/renders/$$r.png > tmp/render-$$r.log 2>&1 \
	    || { tail -n 40 tmp/render-$$r.log; exit 1; }; \
	  grep "rendered in" tmp/render-$$r.log; \
	done

## sheets: drawing sheets -> output/sheets/*.svg, *.pdf, previews/*.png (log tmp/sheets.log)
sheets:
	mkdir -p tmp
	$(PY) python scripts/generate_sheets.py > tmp/sheets.log 2>&1 \
	  || { tail -n 40 tmp/sheets.log; exit 1; }
	cat tmp/sheets.log
	$(PY) python scripts/check_sheets.py

## tools: check external tools (inkscape, blender)
tools:
	$(PY) python scripts/check_tools.py
