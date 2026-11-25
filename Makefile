# Everything runs through uv; no pyproject.toml.
PY := uv run --no-project --with pytest --with cadquery --with ezdxf --with pypdf --with pillow --with shapely
BLENDER := blender -b --factory-startup --python-exit-code 1
# scripts/export_scene.py RENDERS (tests/test_scene.py checks they agree)
RENDERS := printed-closed printed-open-front printed-open-back printed-bank-out \
	laser-closed laser-open-front laser-open-back laser-bank-out laser-flatpack

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

## readme: rewrite README.md's generated sections (UNCONFIRMED list, hardware tables)
readme:
	$(PY) python scripts/update_readme.py

## check-readme: fail if any of README.md's generated sections is stale
check-readme:
	$(PY) python scripts/update_readme.py --check

## fetch: download upstream sources into tmp/src
fetch:
	$(PY) python scripts/fetch.py

## renders: Blender renders -> output/renders/*.png (scene in tmp/scene, logs tmp/render-*.log)
## Each PNG is deleted first and a render fails unless Blender exits 0 and logs "rendered in"
## (a crashed render must not leave the old image looking current); then render/annotate.py
## draws the dimensions from the sidecar <png>.dims.json onto it, failing if that is missing.
renders:
	$(PY) python scripts/export_scene.py
	mkdir -p output/renders tmp
	@for r in $(RENDERS); do \
	  echo "render $$r (log: tmp/render-$$r.log)"; \
	  rm -f output/renders/$$r.png output/renders/$$r.png.dims.json; \
	  $(BLENDER) -P render/render_scene.py -- --manifest tmp/scene/$$r.json \
	    --out output/renders/$$r.png > tmp/render-$$r.log 2>&1 \
	    || { tail -n 40 tmp/render-$$r.log; echo "render $$r FAILED"; exit 1; }; \
	  grep -q "rendered in" tmp/render-$$r.log \
	    || { tail -n 40 tmp/render-$$r.log; echo "render $$r FAILED: no \"rendered in\""; exit 1; }; \
	  grep "rendered in" tmp/render-$$r.log; \
	  $(PY) python render/annotate.py output/renders/$$r.png \
	    || { echo "render $$r FAILED: annotate (sidecar output/renders/$$r.png.dims.json)"; exit 1; }; \
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
