# Render Dimensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every 3D render carries dimension lines with the box's real sizes, drawn crisply over the image.

**Architecture:**
1. The scene export adds dimension specs (3D anchors, offset, label) to each view's manifest.
2. Blender frames them, projects them with its own camera after rendering, and writes a sidecar of pixel coordinates.
3. A Pillow step draws the lines, arrows and labels onto the PNG.

**Tech Stack:** Python via the Makefile `PY` line, Blender `bpy` / `bpy_extras.object_utils.world_to_camera_view`, Pillow, pytest.

**Spec:** `docs/superpowers/specs/2026-11-25-render-dimensions-design.md`

## Global Constraints

- **Dimensions per view** (spec table):

  | View | Dimensions |
  |---|---|
  | closed | width, depth, height |
  | open-front | width, plus the open height and the `LID_OPEN_DEG` arc |
  | open-back | depth, plus the open lid's reach behind the back face |
  | bank-out | bank bay length and width |
  | laser-flatpack | each panel's size, or the overall extent if not legible |

- **Labels:** every value comes from the layout, printed with `demobox.geom.mm`, so no number is typed by hand.
- **Style:** colour `C_DIM` (`#004c99`) from `tools.drafting.style` (vendor). The font is the DejaVu Sans file, `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`. Labels go on a white backing.
- **Fail loudly:**
  - a projected point outside the image raises;
  - overlapping labels that can't be nudged apart raise;
  - a missing sidecar fails `make renders`.
- **Renders stay out of `make check`'s byte comparison.** The specs, labels and annotation are tested.
- **Tim's rules:**
  - `uv`;
  - log to `tmp/*.log`;
  - no `2>/dev/null`;
  - no `/tmp`;
  - no `pgrep -f` wait loops;
  - commit code before outputs;
  - never push.

## Review Focus

1. **A label at the image edge or over the model:** it must stay inside the frame and readable. Covered by Task 2's `test_labels_inside_and_apart`.
2. **A different bank as `DESIGN_BANK`:** the bank-out dimensions follow `lay.bank_bay`. Covered by Task 1's `test_dims_follow_layout[bank]`.
3. **The flat-pack's many panels:** if per-panel labels overlap, it falls back to the overall extent rather than overlapping. Covered by Task 2's `test_flatpack_falls_back_when_crowded`.
4. **Blender run headless:** `annotate.py` must not import `bpy`, and the sidecar is plain JSON. Covered by Task 2's `test_annotate_runs_without_bpy`.
5. **Rounding:** a render label must equal the sheet's text for the same dimension. Covered by Task 1's `test_labels_use_geom_mm`.

---

### Task 1: Dimension specs, camera framing, projection sidecar

**Files:**
- Modify: `scripts/export_scene.py`: add `view_dimensions(lay, route, view) -> list[dict]` and the `"dimensions"` key in `view_manifest` and `flatpack`.
- Modify: `render/render_scene.py`: fold the dimension points into `_camera`'s fit points; after rendering, write `<out>.dims.json`.
- Test: `tests/test_scene.py`

**Interfaces:**
- **Produces:** a manifest entry `"dimensions": [{"label": str, "a": [x,y,z], "b": [x,y,z], "offset": [dx,dy,dz], "kind": "linear"}]`.
  - `a` and `b` are world-space anchor points, in the same units and frame as the `transform`s.
  - `offset` is the vector from the anchors to the dimension line.
  - For the arc: `{"kind": "angle", "label": "100°", "centre": [...], "a": [...], "b": [...]}`, with `a` and `b` points on the two arms.
- **Produces:** the sidecar `<png>.dims.json`, holding `{"resolution": [w, h], "dimensions": [same entries, but every point as pixel [px, py], plus "line_a", "line_b" for linear]}`. Pixel origin is top-left.

- [ ] **Step 1: Write failing tests** in `tests/test_scene.py`:
  - `test_view_dimensions_per_view`: for every route, closed has labels for W, D and H; open-front has W, the open height and `f"{LID_OPEN_DEG:g}°"`; open-back has D and the reach; bank-out has the bay's L and W.
  - `test_labels_use_geom_mm`: each linear label is `geom.mm(|b - a|)` (in mm), and equals the layout's value. For example, closed W is `geom.mm(lay.outer.size[0])`.
  - `test_dims_follow_layout[bank]`: for each bank, the bank-out labels use `layout(w, bank=k).bank_bay`.
  - `test_manifest_has_dimensions`: every `view_manifest` and the flat-pack manifest has a non-empty `"dimensions"`.
- [ ] **Step 2:** Run (log to `tmp/rd1.log`). The tests FAIL.
- [ ] **Step 3: Implement `view_dimensions`.** Anchors come from the layout's boxes, transformed by the same `frame_matrix` as the parts. The offset is outward from the model, at a fixed distance (`DIM_OFFSET = 15.0` mm, a constant).
- [ ] **Step 4: `render_scene.py`.**
  - Include `a + offset` and `b + offset` in `_camera`'s `pts`.
  - After `bpy.ops.render.render`, project every point with `world_to_camera_view(scene, cam, Vector(p))` to pixels: `(x * w, (1 - y) * h)`.
  - Raise if any point is outside `[0, w] × [0, h]`.
  - Write the sidecar next to `a.out`.
- [ ] **Step 5:** Run the tests and one real render: `make` the single target with the Blender line from the Makefile, for `printed-closed`. The tests PASS, `output/renders/printed-closed.png.dims.json` exists, and every point is inside the frame.
- [ ] **Step 6:** Commit: `Scene: dimension specs, framed and projected to a sidecar`.

### Task 2: Draw the overlay; wire into `make renders`

**Files:**
- Create: `render/annotate.py`: `annotate(png: Path, sidecar: Path) -> None` (draws in place) and a `main()` CLI.
- Modify: `Makefile` `renders` recipe: after the "rendered in" check, run `$(PY) python render/annotate.py output/renders/$$r.png`. It fails the recipe if `annotate` fails or the sidecar is missing.
- Modify: `.gitignore` if the sidecars should not be committed. Commit them: they are cheap and they document the overlay.
- Test: `tests/test_annotate.py`

**Interfaces:**
- **Consumes:** the Task 1 sidecar format.
- **Produces:** the annotated PNG, overwriting the render.

- [ ] **Step 1: Write failing tests** in `tests/test_annotate.py`, using a synthetic white PNG and sidecar, with no Blender:
  - `test_annotate_draws_dim_colour`: after `annotate`, pixels of `C_DIM` lie along the line.
  - `test_labels_inside_and_apart`: the label boxes are inside the image and don't overlap. A label placed at the edge is nudged inward along its line.
  - `test_point_outside_raises`: a sidecar point off the image raises `ValueError`.
  - `test_unresolvable_overlap_raises`: two labels on the same spot with no room raise.
  - `test_flatpack_falls_back_when_crowded`: a crowded per-panel set is replaced by the overall-extent entry, which must be present in the sidecar as `"fallback"`.
  - `test_deterministic`: two runs on the same inputs give byte-identical PNGs.
  - `test_annotate_runs_without_bpy`: importing `render.annotate` doesn't import `bpy`.
- [ ] **Step 2:** Run (log to `tmp/rd2.log`). The tests FAIL.
- [ ] **Step 3: Implement.**
  - Lines: extension lines from the anchors to the line, then the line with filled arrowheads.
  - Labels: font size scaled to the image (`max(18, h // 50)` px), centred on the line, on a white rectangle with 3 px padding.
  - Angle: an arc through the projected points, labelled at its middle.
- [ ] **Step 4:**
  1. Commit the code.
  2. Run `make renders` in the foreground with the maximum timeout (log to `tmp/renders.log`).
  3. Read every PNG in `output/renders/` and check the dimensions are legible, correct and inside the frame.
  4. Commit the PNGs and sidecars separately.
- [ ] **Step 5:** Update the README's renders section with one line saying the renders carry the layout's dimensions. Run `make check` (log to `tmp/check.log`); it must exit 0. Commit.
