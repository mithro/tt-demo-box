# Compact box Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the merged tt-demo-box as the compact design: a box only marginally bigger than its contents, no screws, a taped-in monitor, the bank beside the board, in both build routes.

**Architecture:** The data/layout/checks/bodies/drafting/scene pipeline of the merged design stays. `layout.py` is rewritten for the new arrangement and every downstream module follows it. Obsolete parts are deleted outright, with their tests:
- the drawer and its packing;
- the monitor inserts, bezel, clip and retainer;
- the deck as a separate part;
- heat-set inserts, M3 hardware, T-slots, nuts and feet.

**Tech Stack:** Python via `uv run --no-project --with ...` (Makefile `PY`), CadQuery/OCP, ezdxf, shapely, Inkscape (sheets), Blender (renders), pytest (`slow` marker).

**Spec:** `docs/superpowers/specs/2026-11-24-compact-box-design.md`. Where it is silent, `docs/superpowers/specs/2026-11-23-tt-demo-box-design.md` still holds.

## Global Constraints

- **Spec values:**
  - lid open `LID_OPEN_DEG = 100.0` against a stop;
  - print bed `(220.0, 220.0)`;
  - laser bed `(300.0, 200.0)`;
  - walls `ROUTES = {"printed": 2.4, "laser": 3.0}`.
- **Size and fasteners:**
  - every dimension is contents + walls + `SLACK = 1.0` a side (spec Goal 1);
  - no screw, nut, bolt or threaded insert anywhere (Goal 3);
  - nothing proud of the outer box (Goal 3, anti-goals).
- **The kit:**
  - `DESIGN_MONITOR = "taobao-tim"`;
  - `DESIGN_BANK = "xiaomi-pb2020"` (spec Decision 1);
  - both board revisions `v3.2` and `v3.3`.
- **Layout:**
  - board row at the front (Y low), bank row behind it, long runs along X (Decision 2);
  - monitor taped to the lid, no pocket, bezel or insert (Decision 3);
  - the lid is a tray covering the monitor's depth (Decision 4);
  - the base is as tall as the bank row (Decision 4);
  - the board is on a plinth with its top level with the rim (Decision 4).
- **Kept from the merged design:**
  - magnets `MAGNET_D = 6.0`, `MAGNET_T = 3.0`, two pairs, flush, both routes (Decision 8);
  - the laser route is 3 mm plywood, finger-jointed, glued (Decision 9);
  - a panel over 300 x 200 is split on a glued seam (Decision 9).
- **Data and drawings:**
  - every number traceable to a source; placeholders are `confirmed=False` (or in `layout.UNCONFIRMED`) and listed by `make verify` and the README;
  - repo conventions stay: `make check` = test-all + verify + check-sheets + check-outputs + check-readme;
  - the sheet stamp is a content hash.
- **Tim's global rules:**
  - `uv` only;
  - never `2>/dev/null`;
  - never pipe output through grep/tail; log to `tmp/*.log` and read the log;
  - no `/tmp`;
  - ISO dates;
  - Apache-2.0;
  - small commits;
  - no push without Tim's say-so.
- **Sheet stamp and commits:** the stamp hashes the committed `demobox`, `scripts`, vendor and Makefile trees. Commit code before regenerating outputs, and commit outputs separately.

## Review Focus

1. **Another bank chosen as `DESIGN_BANK`:** the box regenerates around it, never grows past the Xiaomi box, and every proof still passes. Owned by Task 2, `test_every_bank_as_design_bank`.
2. **Monitor deeper than the placeholder (25 mm, the first spec's figure):** the lid deepens and the closed lid still clears the board, pins and plugs by `CLOSED_CLEARANCE`. Owned by Task 3, `test_deeper_monitor_still_clears`.
3. **Board v3.2 vs v3.3 in the full solid assembly:** both seat on the plinth pins and neither clashes at any lid angle. Owned by Task 5 / Task 6, `test_assembly_no_clash[...board...]`.
4. **Lid swing 0..100 degrees:**
   - no solid clashes;
   - the monitor cable keeps its bend radius through the hinge notch;
   - the stop holds at 100.

   Owned by Task 3 (`hinge_sweep`, `cables_route`) and Task 5 / Task 6 (solid sweep).
5. **Nothing proud:** for both routes, closed, every part's bounding box lies inside `outer` united with the closed `lid_outer`. Owned by Task 5 / Task 6, `test_nothing_proud`.

---

### Task 1: Part data for the compact kit

**Files:**
- Modify: `demobox/parts/monitors.py` (Monitor, `_TAOBAO_TIM`)
- Modify: `demobox/parts/batteries.py` (Battery, BATTERIES)
- Modify: `demobox/parts/cables.py` (add the bank built-in cable)
- Test: `tests/test_parts_data.py`

**Interfaces:**
- Produces:
  - `Monitor.pigtail_len: float | None = None`: cable length from the panel edge to the VGA plug's face.
  - `Monitor.pigtail_exit_u: float | None = None`: where the cable leaves `cable_edge`, measured from the panel's left in the front view with the cable edge at the bottom.
  - `Battery.cable: Literal["socket", "built-in"]`.
  - `CABLES["bank-built-in"]`.
- `_TAOBAO_TIM`:
  - `pigtail_len=300.0` and `pigtail_exit_u=167.0`, both placeholders;
  - a new `Source("Placeholder: pigtail length and exit point", _PHOTOS, ...)`;
  - a Source line saying the stand clip is taken off (spec Decision 3).
- Other monitors keep `None`, which means "not taped in the design kit; reported only".
- Bank cables: INIU P512 is `"socket"`; UGREEN PB505, Xiaomi PB2020 and Anker Zolo are `"built-in"`, each from their survey lines ("built-in C").
- `CABLES["bank-built-in"]`: dia 4.0, min bend 20.0, plug (20.0, 9.0, 8.5), quoting the survey's "built-in C". Unconfirmed.

- [ ] **Step 1: Write failing tests** in `tests/test_parts_data.py`:

```python
def test_design_monitor_has_pigtail_placeholders():
    m = MONITORS["taobao-tim"]
    assert m.pigtail_len == 300.0 and 0 < m.pigtail_exit_u < m.panel[0]
    assert any("pigtail" in s.what.lower() for s in m.sources) and not m.confirmed

def test_bank_cable_kinds():
    assert BATTERIES["iniu-p512"].cable == "socket"
    assert {k for k, b in BATTERIES.items() if b.cable == "built-in"} == {
        "ugreen-pb505", "xiaomi-pb2020", "anker-zolo-20k"}

def test_bank_built_in_cable_data():
    c = CABLES["bank-built-in"]
    assert (c.dia, c.min_bend_r) == (4.0, 20.0)
```
(Use the existing `Source` field names; read `tools.schema.Source` for them.)

- [ ] **Step 2:** `make test` (log to `tmp/t1.log`). Expect these 3 to FAIL (missing attribute or key).
- [ ] **Step 3:** Add the fields and data above.
- [ ] **Step 4:** `make test`. Expect all to pass.
- [ ] **Step 5:** Commit: `Part data: monitor pigtail placeholders, bank cable kinds`.

---

### Task 2: The compact layout

**Files:**
- Rewrite: `demobox/layout.py`
- Rewrite: `tests/test_layout.py`
- Delete tests of removed things wherever they appear: drawer, cable bay, deck, gutters, inserts, heat-set.

**Interfaces:**
- Consumes: Task 1 data.
- Keeps from the merged module (adapt, do not rename):
  - `LID_OPEN_DEG`, `PRINT_BED`, `LASER_BED`, `ROUTES`, `FIT`, `CLOSED_CLEARANCE`, `MAGNET_*`, `PEG_DIA`;
  - `PEG_HOLE_D`, renamed meaning: pin hole;
  - `UNCONFIRMED`, `tinyvga_offset`, `exit_edge`;
  - the `Layout` methods `lid_location`, `lid_profile_yz`, `_open_yz` and the `catch_*` helpers.
- Deletes:
  - `BAY_INSIDE`, `CABLE_BAY`, `LID_POCKET_MIN`, `HEATSET_*`, `INSERT_MATERIAL`, `DRIVER_STANDOFF`, `STANDOFF_MIN`, `FINGER_HOLE_D`, `CATCH_INSET_X`;
  - `insert_stack`, `_pocket_xy`, the gutter functions, `_drawer_depth`, `_finger_slot`.
- New constants:
  - `SLACK = 1.0`;
  - `TAPE_T = 1.0`: foam tape thickness, a placeholder in `UNCONFIRMED`;
  - `DESIGN_MONITOR = "taobao-tim"`;
  - `DESIGN_BANK = "xiaomi-pb2020"`;
  - `PIN_ROD_D = 3.0`: the bought rod, "3 mm steel rod or 2.85 mm filament";
  - `PIN_PROUD = CLOSED_CLEARANCE + 1.0`: how far the board pins stand above the PCB top;
  - `FINGERTIP_D = 16.0`, moved here from `checks.py`;
  - `BANK_SIDE_PLUGS = ("usb-c-right-angle", "usb-a-c", "bank-built-in")`.
  - Keep `CATCH_BLOCK` and `CATCH_BLOCK_H`.
- `layout(wall: float, bank: str = DESIGN_BANK, monitor: str = DESIGN_MONITOR) -> Layout`. The `Layout` fields, all base frame unless noted:
  - `wall: float`, `outer: Box` (the base), `rim_z: float` (the seam);
  - `board_origin: tuple[float, float, float]`;
  - `board_keepouts: dict[str, Box]`, keyed `"<rev>/envelope"`, `"<rev>/usb_plug"`, `"<rev>/tinyvga"`;
  - `vga_adapter: bool`: True when a 90 degree adapter is used;
  - `plinth: Box`;
  - `pins: dict[str, Cyl]`, keyed `"MT2"` (fixed; printed integral, or a rod in laser) and `"v3.2/MT1"`, `"v3.3/MT1"` (holes for the one loose pin);
  - `bank_bay: Box`, `port_room: Box`, `boost_pocket: Box`;
  - `boost_in_lid: bool`: True when `boost_pocket` is lid frame;
  - `hinge_axis: tuple[float, float]`, `hinge_notch: Box`;
  - `lid_outer: Box`, `monitor_space: Box` and `lid_strip: Box`, all lid frame, closed;
  - `lid_catch: tuple[Cyl, ...]`.
- Board placement (the plan's ruling): component side up, not mirrored, turned so that J1 is at -X and the Pmod edge and TinyVGA are at +X:

  ```
  base = (ox - by, oy + bx, oz + bz)
  ```

  Update the module docstring's Frames and Board placement sections to match.

**Placement rules** (all derived; the size-budget test pins them):
- **Board row (front):**
  - Y runs from `wall + SLACK` across the union of both revisions' keep-outs: envelope, USB plug and TinyVGA + plug.
  - `vga_adapter` is whichever of `False`/`True` gives the shorter row along X, with ties going to `False` (no adapter part).
  - The TinyVGA keep-out uses the existing `tinyvga.plug_keepout(straight)`.
- **Bank row (behind):**
  - Y is `bank.size[1] + 2*SLACK` deep, starting `SLACK` behind the board row.
  - Along X: `port_room`, then `bank_bay`, then the `boost_pocket` (when it is in the bank row).
  - `port_room` length is `max(max(CABLES[k].plug[0] for k in BANK_SIDE_PLUGS) + SLACK, FINGERTIP_D)`. It sits at -X, by J1, so the bank-to-board cable is short.
  - The `boost_pocket` goes in the bank row if `port_room + bank + boost + SLACKs` is no longer than the board row. Otherwise it goes in `lid_strip`, with `boost_in_lid=True`.
- **Width:** `max(board row X, bank row X, monitor panel W + 2*SLACK) + 2*wall`.
- **Depth:** `wall + SLACK + board row Y + SLACK + bank row Y + SLACK + wall`. It must also be at least `monitor panel H + 2*SLACK + 2*wall`.
- **Height:**
  - `rim_z = wall + max(bank H, board stack H) + SLACK`, where the board stack is the keep-out union's z extent with the PCB on the plinth.
  - The plinth top is chosen so the union's top equals `rim_z - SLACK`. That puts the board level with the rim; the plinth's height is at least 0, and if the board stack sets `rim_z`, there is no plinth.
  - `outer.z1 = rim_z`. The lid is a separate box on top.
- **Lid:**
  - `lid_outer` is the base footprint, `wall + TAPE_T + monitor depth + CLOSED_CLEARANCE` deep.
  - `monitor_space` is the panel against the lid's free edge (the far end from the hinge, so lid frame y near `-depth`), `SLACK` off the walls, with its cable edge facing the hinge.
  - `lid_strip` is the rest of the lid's inside, between the monitor and the hinge-end wall.
- **Hinge and catch:**
  - The hinge axis is inside the outer box, inset from the back-top edge by `hinge.KNUCKLE_R`, so knuckles never stand proud.
  - `hinge_notch` is a gap in the knuckle line at the X of the monitor's pigtail exit. Its width is the cable `dia + 2*FIT` (the VGA plug does not pass through; the cable is threaded before assembly).
  - `lid_catch`: two magnets under the front rim, one near each front corner. Each sits in a block (`catch_base_block`, `CATCH_BLOCK` square × `CATCH_BLOCK_H`) against the inside of the front wall, because a 2.4 or 3 mm wall can't hold a 6 mm magnet. Each block goes at the X nearest its corner where it clears every board-row keep-out in XY. If no such X exists within the front wall, `layout()` raises `ValueError` naming the keep-out; it does not grow the box silently. The lid's matching blocks sit in its front rim.

- [ ] **Step 1: Write failing tests** in `tests/test_layout.py`, parametrised over both routes:
  - `test_size_budget`: `outer.size` equals exactly the width, depth and `rim_z` formulas above, computed in the test from the part data. This proves no unexplained space.
  - `test_long_edges_along_x`: the board row's X extent is greater than its Y extent, and the bank bay's X is greater than its Y.
  - `test_board_top_level_with_rim`: max over revisions of `board_keepouts[...].z1` == `rim_z - SLACK`.
  - `test_j1_left_tinyvga_right`: every `"<rev>/usb_plug"` x1 is less than every `"<rev>/tinyvga"` x0.
  - `test_pins`: `"MT2"` lies under both revisions' MT2. Each `"<rev>/MT1"` is at that revision's MT1. Each pin top is `PIN_PROUD` above that revision's PCB top.
  - `test_every_bank_as_design_bank`: for each bank, `layout(w, bank=k)` builds, `bank_bay` holds it with `SLACK`, and its `outer` is no larger than the Xiaomi layout's in every dimension.
  - `test_lid`: `lid_outer` z extent == `wall + TAPE_T + panel depth + CLOSED_CLEARANCE`. `monitor_space` lies inside `lid_outer` less the walls, at the free edge. `lid_strip` lies between it and the hinge-end wall.
  - `test_fits_beds`: the base and lid footprints are each at most 220 x 220 (printed). Laser panels are covered in Task 6.
  - `test_unconfirmed_lists_tape`: `TAPE_T` is in `UNCONFIRMED`.
- [ ] **Step 2:** `make test` (log `tmp/t2.log`). Expect the new tests to FAIL.
- [ ] **Step 3:** Rewrite `layout.py` to the rules above.
- [ ] **Step 4:** `make test`. Expect `tests/test_layout.py` to pass. Other modules that import deleted names now fail to import; that is expected until Tasks 3-8. Run `uv run ... pytest tests/test_layout.py tests/test_parts_data.py tests/test_geom.py tests/test_board.py` and report the rest as expected failures.
- [ ] **Step 5:** Commit: `Layout: compact box, bank beside the board, taped monitor`.

---

### Task 3: Checks and `verify.py`

**Files:**
- Rewrite: `demobox/checks.py`, `verify.py`
- Rewrite: `tests/test_verify.py`

**Interfaces:**
- Consumes: Task 2 `Layout`.
- `checks.PROOFS` becomes `(kit_fits, boards_seat, bank_lifts_out, button_reachable, lid_closed_clears, hinge_sweep, cables_route, lid_catch, size_budget)`. Each is `(report: Report, lay: Layout) -> None`.
- Keep `Report`, `Unconfirmed` and `sweep_angles()`.
- Delete:
  - `monitor_window`, `button_cutout`, `panel_in_lid`, `connector_opening` and the insert checks;
  - `batteries_fit` (replaced by `kit_fits` plus a report).
- `verify.py`:
  - its docstring lists the 9 proofs, and nothing else counts them in prose;
  - it prints two reports: which listed monitors fit `monitor_space` (any with panel W and H at most `monitor_space` less `SLACK`, and depth at most it), and which listed banks fit `bank_bay`;
  - these reports are informational and never fail.

**Proofs** (each must be able to fail; Step 1 has a test that breaks each one):
- **`kit_fits`:** `DESIGN_MONITOR` is in `monitor_space` and `DESIGN_BANK` is in `bank_bay`, each with `SLACK`.
- **`boards_seat`:** both revisions are on the plinth. Each pin is inside its PCB hole, with the board hole (3.2 dia) > `PEG_DIA`, and the plinth's `PEG_HOLE_D` > `PEG_DIA`. Nothing on the deck overlaps another keep-out.
- **`bank_lifts_out`:** with the lid at 100°, nothing (lid included) is over `bank_bay`'s XY footprint above `rim_z`.
- **`button_reachable`:** the bank's end button is at the `port_room` end, and `port_room` is at least `FINGERTIP_D` long.
- **`lid_closed_clears`:** the closed monitor face is at least `CLOSED_CLEARANCE` above everything in the base: board keep-outs, pin tops, bank, boost and plugs.
- **`hinge_sweep`:** over `sweep_angles()`, the lid profile never enters the base profile, and at 100° the stop faces meet. Adapt the merged code.
- **`cables_route`:**
  - The pigtail runs from `monitor_space`'s cable-edge exit (`pigtail_exit_u`), along `lid_strip`, through `hinge_notch`, to the TinyVGA plug.
  - Its length must not exceed `pigtail_len`. Use the existing upper-bound path length; fix the review's double-counted plug run.
  - Its bend at the notch must be at least `min_bend_r` at every sweep angle.
  - USB from `port_room` to J1: length must be within a stated maximum of 300 mm, with bend radii checked.
- **`lid_catch`:** the pairs face each other within `CATCH_MAX_GAP` when closed.
- **`size_budget`:** reports `outer` and lid size, and the volume in litres. It fails if any dimension exceeds its Task 2 formula by more than 0.01.

- [ ] **Step 1: Write failing tests** in `tests/test_verify.py`:
  - **`test_all_proofs_pass`:** both routes, the design kit.
  - **`test_each_proof_can_fail[...]`:** one per proof, mutating the layout with `dataclasses.replace` or monkeypatching data so exactly that proof fails and names the offending part. Cases:
    - a monitor 1 mm wider than `monitor_space`;
    - pins moved 1 mm;
    - lid profile over the bay at 100;
    - `port_room` at 10 mm;
    - lid depth minus 3 mm;
    - stop removed;
    - `pigtail_len = 100`;
    - magnet moved 2 mm;
    - outer width plus 5.
  - **`test_deeper_monitor_still_clears`:** set the monitor depth to 25.0 with `monkeypatch`, rebuild the layout, and all proofs pass. This is Review Focus 2.
  - **`test_fit_reports_list_monitors_and_banks`:** the reports name every MONITORS and BATTERIES key with fits or does-not-fit.
- [ ] **Step 2:** Run (log `tmp/t3.log`). Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the tests and `make verify` (log `tmp/verify.log`). Expect everything to pass and UNCONFIRMED listed.
- [ ] **Step 5:** Commit: `Checks: proofs for the compact box`.

---

### Task 4: Screwless hinge

**Files:**
- Rewrite: `demobox/shared/hinge.py`
- Delete: `demobox/shared/m3.py`, `demobox/shared/inserts.py`, `demobox/shared/packing.py` and their tests in `tests/test_shared.py`. Keep the font-pinning lesson in the commit message only; the packing is gone.
- Modify: `demobox/shared/pin.py` (the loose MT1 pin: `PIN_PROUD` above the PCB)
- Test: `tests/test_shared.py`

**Interfaces:**
- Produces:
  - `hinge.knuckles(lay: Layout, which: Literal["base", "lid"]) -> cq.Workplane`: the knuckles in that part's frame (base frame, or lid frame closed), with a `PIN_HOLE_D = PIN_ROD_D + 0.2` bore on the axis.
  - `hinge.knuckle_cut(lay, which) -> cq.Workplane`: the clearance the *other* part's knuckles need, to cut from this part.
  - `hinge.pin_length(lay) -> float`: equals `lay.outer.size[0]`, flush both sides.
  - `hinge.stop_faces(lay) -> tuple[...]`: as `hinge_sweep` needs them.
  - `pin.locating_pin(lay) -> cq.Workplane`.
- Rules:
  - knuckles alternate base/lid along X;
  - the end knuckles are flush with the side faces;
  - there is no knuckle across `hinge_notch`;
  - knuckle count and length come from `KNUCKLE_LEN`, which is kept;
  - the stop is integral (a lid knuckle's tab meets a base face at `LID_OPEN_DEG`);
  - no leaves and no screw holes.

- [ ] **Step 1: Write failing tests:**
  - `test_knuckles_inside_outer`: the knuckles' bbox is within `outer` (base) or `lid_outer` (lid). Nothing proud.
  - `test_knuckles_alternate_and_skip_notch`: X intervals of base and lid knuckles don't overlap, together they cover the axis less the notch, and no knuckle intersects `hinge_notch` in X.
  - `test_pin_flush`: `pin_length == outer.size[0]`.
  - `test_stop_at_100`: at 99° the stop faces don't touch, at 100° they touch (within 0.05), and at 101° they interfere.
  - `test_locating_pin_height`: the pin protrudes `PIN_PROUD` above the PCB top when seated.
- [ ] **Step 2:** Run. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expect PASS.
- [ ] **Step 5:** Commit: `Hinge: printed knuckles on a flush rod, integral stop, no screws`.

---

### Task 5: Printed route

**Files:**
- Rewrite: `demobox/printed/body.py`, `tests/test_printed.py`
- Modify: `scripts/export_printed.py`

**Interfaces:**
- Consumes: Tasks 2-4.
- Produces:
  - `base(lay) -> cq.Solid`: a tub with the floor and four walls up to `rim_z`. It includes:
    - the plinth (hollow underneath if that saves material without thinning it below `wall`);
    - the MT2 pin, integral;
    - the MT1 holes `PEG_HOLE_D`;
    - the base knuckles;
    - the knuckle cut;
    - the notch;
    - two magnet pockets `MAGNET_D + 0.2` dia × `MAGNET_T + MAGNET_RECESS` deep, open at the rim and flush.
  - `lid(lay) -> cq.Solid`: a tray (top plate `wall` thick, rim walls) with the lid knuckles, its knuckle cut, the notch, and two magnet pockets facing the base ones. No pocket for the monitor: a flat inside face for the tape.
  - `printed_parts(lay) -> dict[str, Printed]`: keys `"base"`, `"lid"`, `"mt1-pin"`. `Printed` keeps `kind` and `note`; drop `heatsets`.
  - `hardware(lay) -> dict[str, int]`, exactly: `{"6 x 3 mm disc magnet": 4, f"3 mm rod x {L:.0f} mm (hinge pin; steel, or 2.85 mm filament)": 1, "double-sided foam tape (VHB type), monitor back": 1}`.
  - `assembly(route, angle_deg, bank_out: bool, monitor=DESIGN_MONITOR, board="v3.3") -> list[(name, shape)]`: the parts plus the bought items as solids: board PCB, TinyVGA, monitor block, bank, magnets, rod. With `bank_out`, the bank is lifted 60 mm above the rim.
  - `ASSEMBLY_MONITOR` / `ASSEMBLY_BOARD` stay as names.
- Delete everything about the drawer, deck, rails, detent, clip, splitting (`split_base`/`split_lid` and `_Site`: both parts now fit the bed; if a future kit does not, `check_bed` raises `BedOverflow`, which is enough), heat-sets and `insert_screws`.

- [ ] **Step 1: Write failing tests** in `tests/test_printed.py`:
  - `test_parts_are_single_valid_solids`.
  - `test_parts_fit_the_bed`: each footprint is within 220 x 220 in its print orientation.
  - `test_hardware_exact`.
  - `test_no_fasteners_anywhere`: no key in `hardware()` contains "M3", "screw", "nut" or "insert".
  - `test_nothing_proud` (Review Focus 5): closed assembly, every part's bbox is within `outer` united with the closed lid.
  - `test_magnet_pockets_flush`.
  - `test_plinth_top_level`.
  - `@pytest.mark.slow test_assembly_no_clash[board-angle]`: for both boards, angles 0..100 step 10, and `bank_out` at 100, `clash.clashes(...) == []`. This is Review Focus 3/4.
- [ ] **Step 2:** Run. Expect FAIL.
- [ ] **Step 3:** Implement. Update `export_printed.py` to write `base`, `lid`, `mt1-pin` and `assembly.step`.
- [ ] **Step 4:** `make test-all` for this file (log `tmp/t5.log`). Expect PASS.
- [ ] **Step 5:** Commit: `Printed route: two-part compact box, no screws`.

---

### Task 6: Laser route

**Files:**
- Rewrite: `demobox/laser/panels.py`, `demobox/laser/fittings.py`, `tests/test_laser.py`
- Modify: `demobox/laser/joints.py`: keep the finger functions, delete `tslot`, `nut_pocket` and the screw/nut constants.
- Modify: `scripts/export_laser.py`

**Interfaces:**
- Consumes: Tasks 2-4 and `joints.finger_edge` / `finger_segments`, which are kept.
- Produces:
  - `panels.build(lay, t=3.0, kerf=KERF, bed=LASER_BED) -> LaserBody` with the same `Panel` / `Joint` / `Seam` types, without `Screw`.
  - `panels.panels(lay, t, kerf) -> dict[str, Panel]`. The panel names:
    - base: `"base-floor"`, `"base-front"`, `"base-back"`, `"base-left"`, `"base-right"`;
    - plinth: `"plinth-top"`, `"plinth-front"`, `"plinth-back"`, `"plinth-left"`, `"plinth-right"` (when the plinth height is above 0);
    - lid: `"lid-top"`, `"lid-front"`, `"lid-back"`, `"lid-left"`, `"lid-right"`.
  - `fittings.printed_parts(lay, t) -> dict[str, Printed]`: knuckle blocks (`"knuckles-base"`, `"knuckles-lid"`, glued to the back wall and the lid's back rim) and `"magnet-block"` × 4. The rest of the route is plywood.
  - `fittings.hardware(lay, t) -> dict[str, int]`, exactly: `{"6 x 3 mm disc magnet": 4, f"3 mm rod x {hinge L:.0f} mm (hinge pin)": 1, "3 mm rod x 10 mm (board pins, MT2 + loose MT1)": 2, "wood glue": 1, "double-sided foam tape (VHB type), monitor back": 1}`.
  - `fittings.assembly(angle_deg, bank_out, ...)`, mirroring Task 5.
  - The cache key fix from the PR review: `panels._BUILT` keys on the whole `Layout` (frozen; make it hashable by keying on `(lay.wall, lay.outer, lay.rim_z, t, kerf, tuple(bed))`). It returns a value nobody mutates: make `LaserBody` frozen.
- Board pins in plywood: holes in `plinth-top` for the rods.
- Joints: every glued edge is a finger joint. A panel over 300 x 200 splits on a glued seam, using the kept `_split`.

- [ ] **Step 1: Write failing tests** in `tests/test_laser.py`:
  - `test_panels_fit_bed`.
  - `test_every_edge_jointed`: each pair of touching panels has a `Joint`.
  - `test_no_screws_or_nuts`: no `Screw` type exists, and `hardware()` keys contain no "M3", "nut" or "screw".
  - `test_hardware_exact`.
  - `test_dxf_layers` for every panel, not one: the review's gap.
  - `test_nothing_proud`.
  - `test_cache_key_is_layout`: two layouts with equal wall but different bank give different bodies.
  - `@pytest.mark.slow test_assembly_no_clash[board-angle]`, as in Task 5.
- [ ] **Step 2:** Run. Expect FAIL.
- [ ] **Step 3:** Implement. Update `export_laser.py`: DXF per panel, `printed/` fittings, `hardware.txt`, `assembly.step`.
- [ ] **Step 4:** Run (log `tmp/t6.log`). Expect PASS.
- [ ] **Step 5:** Commit: `Laser route: glued finger-jointed box, no screws or nuts`.

---

### Task 7: Drawings

**Files:**
- Modify: `demobox/drafting/names.py`, `ga_sheet.py`, `part_sheet.py`, `sheetkit.py` (`BODY_KEYS` and groups as needed)
- Delete: `demobox/drafting/insert_sheet.py`
- Modify: `tests/test_drafting.py`, `scripts/check_sheets.py` (if it names sheets)

**Interfaces:**
- `names.SHEETS` becomes exactly these, deleting DECK/DRW/HGB/HGL/CLIP/PKG/INS-*:
  - `TDB-GA-P`, `TDB-GA-L` (general assemblies);
  - `TDB-CUT-L` (cut list);
  - `TDB-BASE-P`, `TDB-LID-P`, `TDB-PIN-P` (printed parts);
  - `TDB-FIT-L` (the laser route's printed knuckle blocks and magnet block).
- **GA sheets:** the parts list comes from `printed_parts` + `hardware` (no hand-typed counts). Notes give:
  - the closed size and volume, from `size_budget`;
  - "monitor: double-sided foam tape";
  - "board: MT2 pin + loose MT1 pin";
  - "bank lifts out with the lid open".
- **Part sheets:**
  - The base shows the plinth, pins, notch and magnet pockets, dimensioned.
  - The lid shows the tray, knuckles and magnet pockets.
  - The drawing note's "100 deg" uses `LID_OPEN_DEG` (review finding).
  - No requirement IDs (R1–R23) or "finding N" text on any sheet. In comments, ruling IDs are allowed only because they are defined in the committed `docs/superpowers/specs/2026-11-24-compact-box-rulings.md` (amended by R36).

- [ ] **Step 1: Write failing tests:**
  - `test_sheet_set_exact`;
  - `test_ga_parts_list_matches_hardware`;
  - `test_no_ruling_ids_on_sheets`: no `R\d+` or "finding" text in any generated SVG text;
  - the existing per-sheet checks (annotation inside the frame, no overlaps), adapted.
- [ ] **Step 2:** Run. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Commit the code. Then `make sheets` (log `tmp/sheets.log`), read every preview PNG, and run `make check-sheets`. Expect 0 problems.
- [ ] **Step 5:** Commit the code first, then the sheets: `Drawings: compact box sheet set`.

---

### Task 8: Scene and renders

**Files:**
- Modify: `scripts/export_scene.py`, `render/render_scene.py` (only if needed), `tests/test_scene.py`, Makefile `RENDERS` and `renders` recipe.

**Interfaces:**
- `RENDERS` per route: `closed`, `open-front`, `open-back`, `bank-out`, plus `laser-flatpack`. That is 9, replacing `drawer-out`.
- The monitor block is taped at `monitor_space`. The pigtail is drawn along the `cables_route` path.
- The Makefile `BLENDER` gains `--python-exit-code 1`. The recipe deletes each target PNG before rendering, and fails if the log lacks "rendered in" (review finding: renders reported success on a crash).

- [ ] **Step 1: Write failing tests:**
  - `test_render_names`;
  - `test_scene_parts_match_assembly` (the merged test adapted);
  - `test_pigtail_follows_route`.
- [ ] **Step 2:** Run. Expect FAIL.
- [ ] **Step 3:** Implement. Commit the code. Then `make renders` (log `tmp/renders.log`), Read every PNG, and confirm the box, board, monitor and bank are visible and correct.
- [ ] **Step 4:** Commit the PNGs separately: `Renders: compact box`.

---

### Task 9: README, outputs, full check

**Files:**
- Modify: `README.md`, `scripts/update_readme.py`, `scripts/check_outputs.py` (if `NOT_REBUILT` changes), `.github/workflows/check.yml` (drop `fetch-depth: 0` if it is still unneeded; review note).

- [ ] **Step 1:** Rewrite the README prose for the compact box:
  - what it is;
  - size and volume;
  - bought parts (magnets, rod, tape, glue for laser);
  - "the bank lifts out with the lid open";
  - "choose a bank: set `DESIGN_BANK`, then `make outputs sheets readme`".

  Keep the generated `unconfirmed` and hardware markers.
- [ ] **Step 2:** Commit the code. Run `make outputs sheets readme` (log `tmp/regen.log`). Expect `git status` to show only `output/` and `README.md` changes. Commit them separately.
- [ ] **Step 3:** `make fetch check` (log `tmp/check.log`). Expect rc=0: test-all, verify, check-sheets 0 problems, check-outputs identical, and check-readme. Record the size and volume line from `make verify` in the commit message.
- [ ] **Step 4:** `git grep -n -E "drawer|heat-set|insert|bezel|T-slot|M3"` over `demobox scripts tests README.md`. Every hit must be deliberate (e.g. the data's survey quotes). Remove the rest. Commit: `Compact box: README and outputs`.
