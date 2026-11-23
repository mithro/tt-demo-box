# tt-demo-box Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A parametric, verified mechanical design for a portable clamshell Tiny Tapeout VGA demo
box, with a 3D-printed body and a laser-cut 3 mm plywood body, STEP/STL/DXF outputs, ISO-style
drawings and Blender renders.

**Architecture:** Part data (board, TinyVGA Pmod, monitors, batteries, cables) and one shared
internal layout are plain Python; `verify.py` proves every fit from them. Two body generators
(printed, laser) build CadQuery solids from the layout; exporters write STEP/STL/DXF, a Blender
script renders PNGs, and sheets are drawn with fpgas.online-mechanical's drafting library from
hidden-line projections of the solids.

**Tech Stack:** Python 3.12+ under `uv run --no-project --with ...` (no pyproject), CadQuery
(OCP), ezdxf, pytest, Inkscape 1.4 (Debian trixie package, as the submodule's CI uses), Blender
(Debian package, headless), git submodule `fpgas-online/fpgas.online-mechanical`.

**Spec:** `docs/superpowers/specs/2026-11-23-tt-demo-box-design.md` (with `monitor-survey.md`
and `battery-survey.md` beside it). Read it first.

## Global Constraints

- Everything runs with `uv run --no-project --with <deps>`; no `pyproject.toml`; `make` drives it.
  Standard dep sets (put them in the Makefile as variables):
  `PY := uv run --no-project --with pytest --with cadquery --with ezdxf --with pypdf --with pillow --with shapely`.
- Our package is `demobox/`. Never create top-level `tools/` or `tinytapeout/` packages: the
  submodule's own modules import under those names.
- fpgas.online-mechanical is a git submodule at `vendor/fpgas.online-mechanical`, pinned to a
  commit; `demobox/_paths.py` puts it on `sys.path`. Board numbers come from its
  `tinytapeout.boards.BOARDS['v3.2']` and `['v3.3']`; never retype them.
- Every dimension in data modules carries a `Source` (the submodule's `tools.schema.Source`) and a
  `confirmed: bool`. `confirmed=False` figures are reported by `verify.py` as UNCONFIRMED, never
  silently trusted, never a failure on their own.
- Spec values, verbatim: lid open angle **100 degrees** (just past 90); battery bay **158 x 82 x
  34 mm** inside plus **35 mm** cable bay; lid pocket **~130 x 100 mm**; boards **v3.2 (85 x 80)
  and v3.3 (85 x 85)** only; print bed **220 x 220 mm**; laser bed **300 x 200 mm**, **3 mm
  plywood**, M3 T-slot screws with captured nuts; no monitors with rear-facing sockets; all power
  at 5 V; no custom electronics; off-the-shelf cables, slim VGA **<= 0.5 m**.
- Fasteners: M3 throughout. Printed parts take M3 heat-set inserts (hole 4.0 mm, depth 5.7 mm).
- Generated outputs go to `output/` (committed: STEP, STL, DXF, SVG, PDF, PNG). Scratch goes to
  `tmp/` (git-ignored). Make outputs reproducible with the submodule's `tools.reproducible`.
- Commit after every task (small commits; message ends with the Co-Authored-By line).
- Coordinates: base frame origin at the front-left-bottom outside corner of the base; X to the
  right as the visitor sees it, Y away from the visitor (towards the hinge), Z up. Lid frame:
  origin on the hinge axis; the lid rotates about the axis parallel to X.
- Board orientation on the deck: Pmod edge (board y = 0) towards the hinge; i.e. board y maps to
  base -Y. J1 USB-C ends up at the front-right of the deck.

## Review Focus

1. **A monitor whose data is incomplete** (e.g. ZJ050 driver board size unknown, Tim's Taobao unit
   unmeasured): expected `verify.py` to report it UNCONFIRMED and still build its insert from the
   placeholder, not crash or silently drop it. Test in Task 3.
2. **The lid swept from closed to 100 degrees**: expected no collision with the base, the board,
   the TinyVGA plug or the cables at any angle, not just at the two end positions. Test in Task 5.
3. **v3.2 vs v3.3 on the same deck**: expected both to seat on the same standoffs with the USB-C
   slot and the Pmod/VGA keep-out right for each (v3.3 is 5 mm deeper, MT1 moves). Test in Task 4.
4. **Kerf and material thickness off nominal** (plywood sold as 3 mm is often 2.7-3.2):
   expected the laser panels to regenerate with a `--thickness`/`--kerf` override and the finger
   joints to still mate. Test in Task 8.
5. **A part that doesn't fit the bed** after a dimension change: expected the export to fail with
   the part name and its size, not write an unprintable STL. Test in Task 7 and Task 8.

---

### Task 1: Repo scaffold, submodule and tool check

**Files:**
- Create: `.gitmodules`, `vendor/fpgas.online-mechanical` (submodule), `demobox/__init__.py`,
  `demobox/_paths.py`, `Makefile`, `tests/conftest.py`, `tests/test_paths.py`,
  `scripts/check_tools.py`
- Modify: `.gitignore` (add `output/.cache/`), `README.md` (how to build)

**Interfaces:**
- Produces: `demobox._paths.ROOT: Path`, `demobox._paths.VENDOR: Path`; importing `demobox`
  makes `tinytapeout.boards`, `tools.schema`, `tools.drafting.*`, `tools.render_svg`,
  `tools.reproducible` importable.
- Produces: `make test` (pytest), `make verify`, `make outputs`, `make check` (= test + verify +
  sheet checks), `make tools` (runs `scripts/check_tools.py`).

- [ ] **Step 1:** `git submodule add https://github.com/fpgas-online/fpgas.online-mechanical vendor/fpgas.online-mechanical`
  then pin to the commit checked out (`git -C vendor/fpgas.online-mechanical rev-parse HEAD`;
  record it in README).
- [ ] **Step 2: Write the failing test** `tests/test_paths.py::test_submodule_boards_importable`:
  ```python
  import demobox  # noqa: F401
  from tinytapeout.boards import BOARDS
  def test_submodule_boards_importable():
      assert BOARDS["v3.2"].outline.width == 85.0 and BOARDS["v3.2"].outline.height == 80.0
      assert BOARDS["v3.3"].outline.height == 85.0
  ```
- [ ] **Step 3:** Run `uv run --no-project --with pytest python -m pytest tests/test_paths.py -v`;
  expect ImportError.
- [ ] **Step 4:** Implement `demobox/_paths.py` (insert `VENDOR` at the front of `sys.path` once)
  and import it from `demobox/__init__.py`. `tests/conftest.py` adds the repo root to `sys.path`.
- [ ] **Step 5:** Re-run; expect PASS.
- [ ] **Step 6:** `scripts/check_tools.py`: prints `inkscape --version` and `blender --version`
  and exits 1 naming whichever is missing with the fix: `sudo apt install inkscape blender`
  (both from Debian trixie). If missing, ask Tim to run that (`! sudo apt install inkscape
  blender`); do not work around it.
- [ ] **Step 7:** Makefile with the targets above (later tasks fill them in) and the `PY` variable.
- [ ] **Step 8:** Commit "Scaffold: submodule, paths, Makefile, tool check".

### Task 2: Geometry primitives and the TinyVGA Pmod

**Files:**
- Create: `demobox/geom.py`, `demobox/parts/__init__.py`, `demobox/parts/board.py`,
  `demobox/parts/tinyvga.py`, `scripts/fetch.py`, `tests/test_geom.py`, `tests/test_tinyvga.py`

**Interfaces:**
- Produces `demobox.geom`: frozen dataclasses `Box(x0,y0,z0,x1,y1,z1, what: str)` with
  `.size -> tuple[float,float,float]`, `.moved(dx,dy,dz) -> Box`, `.union(other) -> Box`;
  `Cyl(cx,cy,z0,z1,r, what)`; functions `box_gap(a: Box, b: Box) -> float` (negative =
  overlap depth, 0 = touching), `overlaps(a, b, tol=0.0) -> bool`.
- Produces `demobox.parts.board`: `BOARD_KEYS = ("v3.2", "v3.3")`,
  `board_spec(key) -> tools.schema.BoardSpec`, `board_envelope(key) -> Box` in board coordinates
  (PCB outline + Pmod bodies' overhang + USB-C shell, z from 0 to `TALLEST_COMPONENT`),
  `TALLEST_COMPONENT: float = 12.0` with `confirmed=False` (placeholder; spec open item).
- Produces `demobox.parts.tinyvga`: `TINYVGA: PmodBoard` with `pcb: Box`, `de15: Box`
  (socket body), `plug_keepout(straight: bool) -> Box` (DE-15 plug + 40 mm straight / 20 mm
  with a 90 degree adapter, per spec), `sources`, `confirmed`.

- [ ] **Step 1: Failing tests** `tests/test_geom.py`: `box_gap` of two boxes 1 mm apart in X is
  1.0; overlapping by 2 mm is -2.0; touching is 0.0; `Box.union` covers both.
  `tests/test_tinyvga.py::test_tinyvga_from_kicad`: TinyVGA PCB width and DE-15 position equal
  the values extracted from `tmp/src/tiny-vga/pcb/*.kicad_pcb` (the test runs the extractor and
  compares to the committed data module, the submodule's `extract.py` pattern).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** `scripts/fetch.py`: shallow-clones `https://github.com/mole99/tiny-vga` into
  `tmp/src/tiny-vga` (record the commit hash it got). Run it via `make fetch`.
- [ ] **Step 4:** Implement `geom.py`, `board.py` (wraps the submodule; no retyped numbers) and
  `tinyvga.py` + `scripts/extract_tinyvga.py`, which reads the `.kicad_pcb` with the submodule's
  `tools.kicad_pcb` reader: Edge.Cuts outline, the Pmod header footprint, the DE-15 footprint's
  courtyard. Its `Source` cites the repo URL and commit.
- [ ] **Step 5:** Run tests; expect PASS. Commit "Geometry primitives, board wrapper, TinyVGA".

### Task 3: Monitor, battery and cable data

**Files:**
- Create: `demobox/parts/monitors.py`, `demobox/parts/batteries.py`,
  `demobox/parts/cables.py`, `tests/test_parts_data.py`

**Interfaces:**
- Produces `Monitor` (frozen dataclass): `key, title, kind: Literal["kit","cased"],
  panel: tuple[float,float,float]` (W,H,T), `active: tuple[float,float]`,
  `active_offset: tuple[float,float]` (active area's lower-left from the panel's lower-left),
  `driver: Box | None` (kit board, relative to the panel's back lower-left),
  `connector_exit: Literal["left","right","top","bottom","pigtail","board"]`,
  `power_in: Literal["5V","12V-boost"]`, `button: tuple[float,float] | None` (front-face
  position, None = on a separate keypad), `sources, confirmed`.
  `MONITORS: dict[str, Monitor]` with keys `"kit-800050"`, `"kit-zj050"`, `"adafruit-1678"`,
  `"eastrising-tftv050"`, `"miktver-5"`, `"generic-5-touch"`, `"taobao-tim"`.
- Produces `Battery`: `key, title, size: (L,W,H)`, `port_face: Literal["end","top","side"]`,
  `button: tuple[str, float, float] | None` (face, u, v), `sources, confirmed`.
  `BATTERIES` with keys `"iniu-p512"`, `"ugreen-pb505"`, `"xiaomi-pb2020"`,
  `"anker-zolo-20k"`.
- Produces `Cable`: `key, title, dia, min_bend_r, plug: (L,W,H)`, `sources, confirmed`.
  `CABLES` with `"vga-slim"`, `"vga-90-adapter"`, `"usb-c-right-angle"`, `"usb-a-c"`,
  `"usb-12v-boost"` (Tim's adapter; body size placeholder, unconfirmed).

- [ ] **Step 1: Failing tests** (`tests/test_parts_data.py`):
  `MONITORS["kit-800050"].panel[:2] == (120.7, 76.3)`; `MONITORS["kit-zj050"].panel ==
  (117.65, 88.43, 5.9)` and `.active == (101.76, 76.32)`; every 800x480 monitor's `active ==
  (108.0, 64.8)`; no monitor has `connector_exit == "rear"` (spec excludes them);
  `BATTERIES["iniu-p512"].size == (104, 70, 29)`, `["ugreen-pb505"].size == (116.22, 70.55,
  30.03)`, `["xiaomi-pb2020"].size == (128, 73, 32)`, `["anker-zolo-20k"].size == (119.9, 73.4,
  31.5)`; every entry has at least one `Source`; `MONITORS["taobao-tim"].confirmed is False`.
- [ ] **Step 2:** Run; FAIL.
- [ ] **Step 3:** Implement the three modules from the spec's survey files. Sources quote the
  survey line and listing URL. Placeholders (unknown driver boards, Tim's unit, button
  positions, the boost adapter) take plausible values and `confirmed=False`, with a note saying
  what to measure.
- [ ] **Step 4:** Run; PASS. Commit "Monitor, battery and cable data from the surveys".

### Task 4: The shared layout

**Files:**
- Create: `demobox/layout.py`, `tests/test_layout.py`

**Interfaces:**
- Consumes: `geom`, `parts.*`.
- Produces constants `LID_OPEN_DEG = 100.0`, `BAY_INSIDE = (158.0, 82.0, 34.0)`,
  `CABLE_BAY = 35.0`, `LID_POCKET_MIN = (130.0, 100.0)`, `FIT = 0.5` (insert/slide clearance),
  `CLOSED_CLEARANCE = 2.0` (lid above tallest board part), and
  `Layout` (frozen dataclass) built by `layout(wall: float) -> Layout` with:
  `outer: Box` (base), `deck_z: float`, `board_origin: tuple[float,float,float]` (where board
  (0,0) lands; board rotated 180 degrees so its Pmod edge faces +Y),
  `board_keepouts: dict[str, Box]` (per revision: envelope, USB-C plug, TinyVGA + VGA plug),
  `standoffs: tuple[Cyl, ...]` (at MT1 of each revision and MT2, plus edge supports),
  `usb_slot: Box`, `bay: Box`, `cable_bay: Box`, `drawer_face_hole: Box`,
  `hinge_axis: tuple[float, float]` (y, z), `hinge_cable_channel: Box` (where the VGA and
  monitor power cables cross the hinge), `boost_pocket: Box` (holds the USB to 12 V adapter's
  body), `drawer_travel: float` (how far the drawer slides out: enough to lift the bank out
  with its cables still plugged in), `lid_outer: Box` (in lid frame, closed), `lid_pocket: Box`,
  `lid_profile_yz(angle_deg) -> shapely.Polygon` (the lid's side profile rotated about the
  hinge axis; the lid turns about X, so collision is a 2D question in YZ wherever X ranges
  overlap), `lid_location(angle_deg) -> cq.Location` (the same rotation, for solids).
  The printed route calls `layout(2.4)`, the laser route `layout(3.0)`.

- [ ] **Step 1: Failing tests:** `layout(2.4).bay` inside size equals `BAY_INSIDE` and the drawer
  slides out along -X; both revisions' envelopes lie on the deck inside `outer` with >= `FIT`
  from the walls; the v3.2 and v3.3 MT2 standoffs coincide and each revision's MT1 has a
  standoff; `usb_slot` sits under each revision's J1 USB-C plug keep-out; the TinyVGA + plug
  keep-out is behind the board (larger Y) and below the hinge axis; `lid_pocket` >=
  `LID_POCKET_MIN`.
- [ ] **Step 2:** Run; FAIL.
- [ ] **Step 3:** Implement. Derivation order, all in code from the data: deck width/depth from
  the union of both revisions' keep-outs + TinyVGA plug keep-out + margins; base width =
  max(deck, bay + cable bay + walls); base height = bay + drawer floor/rail + deck cavity
  (USB-C plug and cable loop height) + deck; lid pocket = max over monitors of their insert
  envelope; lid depth = deepest insert stack (panel + driver board on standoffs + retainer) +
  wall; closed-lid gap from `TALLEST_COMPONENT + CLOSED_CLEARANCE`.
- [ ] **Step 4:** Run; PASS. Commit "Shared layout derived from the part data".

### Task 5: verify.py, the fit proofs

**Files:**
- Create: `verify.py` (repo root, run as `make verify`), `demobox/checks.py`, `tests/test_verify.py`

**Interfaces:**
- Produces `demobox.checks.Report` with `.check(ok: bool, what: str, detail: str)`,
  `.unconfirmed(what: str, detail: str)`, `.failures: int`; and one function per proof, each
  `(report: Report, lay: Layout) -> None`: `monitors_fit`, `batteries_fit`, `buttons_reachable`,
  `boards_seat`, `lid_closed_clears`, `hinge_sweep`, `cables_route`. `verify.py` runs all for
  both routes and exits non-zero on any failure, printing UNCONFIRMED items at the end (the
  submodule's `camera_holder/verify.py` output style).

- [ ] **Step 1: Failing tests:** `verify.main()` returns 0 on the real data; a monkeypatched
  monitor with panel 140 x 100 makes `monitors_fit` fail naming it; a battery of 170 mm makes
  `batteries_fit` fail; a `TALLEST_COMPONENT` of 60 makes `lid_closed_clears` fail;
  `hinge_sweep` samples every 1 degree from 0 to `LID_OPEN_DEG` (assert it evaluates 101
  angles) and fails if `lid_profile_yz(angle)` overlaps the base's or any board keep-out's YZ
  profile at any of them; `cables_route` fails if `drawer_travel` is shorter than the bank's
  length minus what stays inside, or the cable slack loop can't reach that far;
  unconfirmed data shows up in `report.unconfirmed` without failing.
- [ ] **Step 2:** Run; FAIL.
- [ ] **Step 3:** Implement. Rules: monitor window covers the whole active area and stays 1.0 mm
  inside the panel edge on every side (so panel edges stay hidden); the insert leaves >= 1.2 mm
  of material round the panel; connector exit side has an opening in the lid wall big enough
  for the plug; battery + packing fills the bay with the port end at the cable-bay wall and its
  button (if any) under `drawer_face_hole`; cables: VGA path length <= 0.5 m and every bend >=
  the cable's `min_bend_r`.
- [ ] **Step 4:** Run tests and `make verify`; PASS. Commit "verify.py: fit proofs".

### Task 6: Shared made parts: hinge, standoffs, monitor inserts, battery packing

**Files:**
- Create: `demobox/shared/hinge.py`, `demobox/shared/inserts.py`, `demobox/shared/packing.py`,
  `tests/test_shared.py`

**Interfaces:**
- Produces CadQuery builders: `hinge_base_knuckles(lay) -> cq.Workplane`,
  `hinge_lid_knuckles(lay) -> cq.Workplane` (pin: M3 bolt + nyloc; a stop face that meets the
  base at exactly `LID_OPEN_DEG`), `monitor_bezel(m: Monitor, lay) -> cq.Workplane`,
  `monitor_retainer(m, lay) -> cq.Workplane` (holds the driver board on standoffs for kits),
  `battery_packing(b: Battery, lay) -> cq.Workplane` (end-stop + U spacer; model name engraved).
  These are printed in both routes.

- [ ] **Step 1: Failing tests:** each builder returns one valid solid (`.val().isValid()`); the
  bezel window's size equals the verify rule's window for that monitor; rotating the lid
  knuckle solid to `LID_OPEN_DEG` makes its stop face touch (gap < 0.05 mm) the base knuckle,
  and at `LID_OPEN_DEG - 1` they don't touch; packing + battery length == bay length - `FIT`.
- [ ] **Step 2:** Run; FAIL. **Step 3:** Implement. **Step 4:** Run; PASS.
- [ ] **Step 5:** Commit "Shared parts: hinge, monitor inserts, battery packing".

### Task 7: The 3D-printed body and its exports

**Files:**
- Create: `demobox/printed/body.py`, `scripts/export_printed.py`, `tests/test_printed.py`
- Output: `output/printed/*.step`, `output/printed/*.stl`, `output/printed/assembly.step`

**Interfaces:**
- Produces `printed_parts(lay) -> dict[str, Printed]` where `Printed` has `solid`,
  `print_orientation` (a rotation putting the part flat on the bed), `note: str`. Parts:
  `base` (tub with drawer opening, deck, rails, hinge cable channel, boost-adapter pocket),
  `lid`, `drawer` (with a printed detent latch: a flexing bump on the drawer side that clicks
  into a notch at the closed position, and an end stop at `drawer_travel`), plus the shared
  parts.
  Base/lid larger than 220 x 220 are split into pieces joined by M3 screws into heat-set
  inserts with alignment pins (part names `base-left`, `base-right`...); the split plane is
  chosen in code where the solid is shortest.
- Produces `assembly(route, angle_deg, drawer_out: float) -> list[(name, solid, colour)]` used
  by renders and drawings.

- [ ] **Step 1: Failing tests:** every part, in its print orientation, has a bounding box within
  220 x 220 in X/Y (Review Focus 5: a part made too big raises `BedOverflow` naming the part
  and size); the assembled solids at angles 0 and 100 have no pairwise intersection volume
  above 1 mm^3 except declared fastener overlaps; heat-set holes are 4.0 mm.
- [ ] **Step 2:** Run; FAIL. **Step 3:** Implement the body and `export_printed.py` (STEP via
  CadQuery then `tools.reproducible.normalise_step`; STL at 0.05 mm tolerance).
- [ ] **Step 4:** Run tests and `make outputs`; PASS. Commit code, then outputs, separately.

### Task 8: The laser-cut body and its DXF

**Files:**
- Create: `demobox/laser/joints.py`, `demobox/laser/panels.py`, `scripts/export_laser.py`,
  `tests/test_laser.py`
- Output: `output/laser/<sheet>.dxf`, `output/laser/assembly.step`

**Interfaces:**
- Produces `finger_edge(length: float, t: float, kerf: float, male: bool) -> list[tuple[float,
  float]]`, `tslot(at: float, t: float) -> list[tuple]` (M3 x 12 screw slot with square-nut
  pocket), `panels(lay, t=3.0, kerf=0.15) -> dict[str, Panel]`, `Panel` = outline polygon +
  holes + where it sits in 3D (for the assembly and renders).
- Finger rule: count is the odd number nearest `length / (3 * t)`, >= 3; ends are female on one
  panel and male on its mate; kerf is added to every cut edge (male fingers grow by kerf/2 each
  side, slots shrink by kerf/2).

- [ ] **Step 1: Failing tests:** for every jointed pair the male and female finger patterns are
  complementary (sum of widths == edge length, offsets equal); regenerating with `t=2.7,
  kerf=0.2` still mates (Review Focus 4); every panel fits 300 x 200 (`BedOverflow` otherwise);
  the extruded panels assemble without overlap beyond the joints. The laser drawer is a
  finger-jointed tray running on cut runners, latched by two 6 x 3 mm disc magnets pressed into
  printed corner blocks (drawer front and base front), with a cut end stop at `drawer_travel`.
- [ ] **Step 2:** Run; FAIL. **Step 3:** Implement; `export_laser.py` writes one DXF per panel
  on a layer `CUT` (and `ENGRAVE` for labels), normalised with `tools.reproducible`, with CLI
  overrides `--thickness` and `--kerf`.
- [ ] **Step 4:** Run tests and `make outputs`; PASS. Commit code, then outputs.

### Task 9: Blender renders

**Files:**
- Create: `scripts/export_scene.py` (per-part STL + `tmp/scene/<route>-<view>.json`
  manifest: part, file, colour, transform), `render/render_scene.py` (runs inside Blender),
  `tests/test_scene.py`
- Output: `output/renders/{printed,laser}-{closed,open-front,open-back,drawer-out}.png`,
  `output/renders/laser-flatpack.png`

**Interfaces:**
- `blender -b --factory-startup -P render/render_scene.py -- --manifest <json> --out <png>`;
  1600 x 1200, Cycles on CPU with `scene.cycles.use_denoising = False` (Debian's Blender 4.3.2
  has no OpenImageDenoise; leaving it on fails with "build has no OpenImageDenoise support"),
  256 samples to keep the noise down without it, white world, a three-point light rig and an orthographic-ish
  35 mm camera framed on the scene's bounding box. Monitor screens use an emissive material with
  a TT VGA test pattern image (draw it in `export_scene.py` with Pillow; colour bars are fine).

- [ ] **Step 1: Failing test:** `export_scene.py` writes manifests for all 9 renders and every
  referenced STL exists; transforms for `open-front` put the lid at `LID_OPEN_DEG`.
- [ ] **Step 2:** Run; FAIL. **Step 3:** Implement. **Step 4:** `make renders`; then *look at
  every PNG* (Read tool) and fix framing, overlaps and anything physically wrong before
  committing. Commit code, then renders.

### Task 10: Mechanical drawings

**Files:**
- Create: `demobox/drafting/hlr.py`, `demobox/drafting/names.py`,
  `demobox/drafting/ga_sheet.py`, `demobox/drafting/part_sheet.py`,
  `demobox/drafting/insert_sheet.py`, `scripts/generate_sheets.py`, `scripts/check_sheets.py`,
  `tests/test_drafting.py`
- Output: `output/sheets/*.svg`, `*.pdf`, `previews/*.png`

**Interfaces:**
- `project(shape, view: Literal["front","side","plan"]) -> Projection` with `visible` and
  `hidden: list[list[tuple[float,float]]]` polylines in model mm, using OCP
  `HLRBRep_Algo` + `HLRBRep_HLRToShape` and discretising edges at 0.1 mm chord tolerance.
- Drawing names: prefix `TDB-` + short code (`TDB-GA-P`, `TDB-GA-L`, `TDB-LID-P`, ...,
  `TDB-INS-800050`); `names.py` is the one answer, like the submodule's `tools/layout.py`.
- Sheets are drawn with the submodule's `tools.drafting` (`Sheet`, `TitleBlock`, `View`,
  `dims`, `style`), first-angle, A3 for GA and A4 for parts and inserts, SVG to PDF via
  `tools.render_svg.to_pdf`. GA sheets: front, side (lid shown closed, and at 100 degrees in
  phantom line, with the angle dimensioned) and plan; overall dims; parts list table with
  bought parts (screws, inserts, cables, battery models). Part sheets: views + every dimension
  needed to check the part. Insert sheets: window size and position against the panel.
  Every sheet lists its sources and its UNCONFIRMED inputs in its notes.

- [ ] **Step 1: Failing tests:** `project(box 10x20x30, "front")` gives a visible outline of
  10 x 30; every sheet in `names.py` is generated; `scripts/check_sheets.py` (built on the
  submodule's `tools.check_sheets.boxes/lines/overlap/box_hits_line`) reports no text
  collision, no text under 2.5 mm, nothing outside the frame.
- [ ] **Step 2:** Run; FAIL. **Step 3:** Implement. **Step 4:** `make sheets`; look at every
  preview PNG; fix what a draughtsman would reject. Commit code, then outputs.

### Task 11: Make check, CI, README

**Files:**
- Create: `.github/workflows/check.yml`
- Modify: `Makefile`, `README.md`

- [ ] **Step 1:** `make check` = `test` + `verify` + `check_sheets` + "outputs are up to date"
  (rebuild into `tmp/` and compare with `output/` byte-for-byte, the submodule's
  `check_pdfs.py` idea).
- [ ] **Step 2:** CI on `debian:trixie` with `inkscape blender git make curl` and `uv`;
  checkout with submodules; run `make fetch check`.
- [ ] **Step 3:** README: what it is, render gallery (the open-front renders on top), BOM per
  route (bought parts with links from the surveys), how to build, how to add a monitor (add a
  `Monitor` entry, run `make verify outputs`), the UNCONFIRMED list and what to measure.
- [ ] **Step 4:** Push a branch, open a PR, watch CI go green. Commit.
