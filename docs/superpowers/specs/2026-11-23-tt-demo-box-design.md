# tt-demo-box: a portable, zero-setup Tiny Tapeout VGA demo station

Status: approved by Tim, 2026-11-23.

## Intent

A small box you carry to a meetup, put on a table and open: the lid swings up to just past
90 degrees, the 7" VGA monitor in the lid is already showing the board's VGA designs cycling,
and the Tiny Tapeout dev board sits exposed on the deck in front of it. The flashing screen draws
people to the table; the bare dev board in front of it is what starts the conversation.
Nothing to plug in, nothing to set up: the board is already configured to cycle VGA designs at
power-up (see the demo-station gist, Way 1 / Way 2).

The battery slides out of a drawer in the bottom so it can be taken out at airport security
(and charged separately), and slides back in without rewiring anything.

It replaces the Shenzhen open silicon meetup (2026-11-11) setup: a loose ~US$20 Taobao VGA
monitor, a USB-C to DC adapter, a USB-A power brick and a dev board on the table.

## Goals

- Open the lid and it is a working demo; close it and it is a box that survives a backpack.
- Lid opens to just past 90 degrees (target 100 degrees) and stays there, against a stop.
- Dev board exposed on the deck: chip, 7-segment display, LEDs, DIP switches all visible. No
  window, no cover.
- Battery removable in seconds via a slide-out drawer, with no cable to unplug inside the box
  except at the drawer's own connectors.
- Built around a cheap 7" VGA car-style monitor (Tim's Shenzhen unit). Per-monitor inserts let
  close variants of it (other sellers' 7" car monitors, a bare 7" panel + driver-board kit) fit
  the same lid. 7" only (Tim, 2026-11-23: "Let's just use the 7inch rather than 5inch").
- Two build routes from one design: 3D printed, and laser-cut flat panels.
- Mechanical drawings in the style of `fpgas-online/fpgas.online-mechanical`, plus 3D renders.
- Open-source tooling only.

## Non-goals

- No gamepad or input Pmod; the demo is hands-off. (INPUT and BIDIR Pmod headers stay free.)
- No custom electronics (no PCB, no PD trigger/buck board). Cables and off-the-shelf adapters only.
- No mains power inside the box; the battery is the only source. (Running it from a USB charger
  instead of the battery is fine and needs nothing special: the drawer cable just plugs into a
  charger.)
- Monitors bigger than 7" are not a target.

## Anti-goals (a failure even if it "works")

- A box where setup means opening it and plugging three cables together.
- Hiding the dev board, or putting it behind plastic.
- A monitor mount that only fits the one monitor in the author's hand.
- Drawings/models whose numbers can't be traced to a source, or that silently disagree with each
  other (the fpgas.online-mechanical rule: every dimension traceable, every fit proved).
- A printed-only or laser-only design that the other process can't build.

## Decisions made with Tim

1. **Approach: shared data and layout; separate body per process** ("(1) and (2)").
   - Shared, written once in Python: part data (dev board, VGA Pmod, monitors, batteries,
     adapters, plugs), the internal layout (where board, monitor, drawer, hinge axis and cable
     paths are), and `verify.py`, which proves fit for both builds.
   - Separate per process: the 3D-printed body (shelled walls, printed hinge with integral stop,
     moulded drawer rails) and the laser-cut body (3 mm flat panels, finger joints / T-slot
     screws, separate hinge, cut stop and runners). Each exports, draws and renders on its own.
2. **Monitors: a 7" VGA car-style monitor (Tim's), and close 7" variants**, via a common lid pocket plus a per-monitor insert
   (front trim/bezel plate + rear retainer). Adding a monitor is adding a data entry; `verify.py`
   proves it fits.
3. **Power: everything at 5 V.** Cheap power banks fall back to 5 V on every port as soon as two
   outputs are in use (Xiaomi P16ZM datasheet: "(3 ports) 5V⎓3A"), so the design never relies on
   a 12 V PD contract. The monitor is fed either directly at 5 V (e.g. Eyoyo S501H micro-USB) or
   through a USB to 12 V DC cable that contains its own boost converter (Tim's Shenzhen adapter is
   one of these). The dev board takes 5 V USB-C. Load ~1.1 A (5 W monitor via boost) + ~0.2 A
   (board): inside the 3 A shared limit, and well above banks' low-current shut-off.
4. **Battery: a 20,000 mAh class bank** (74 Wh, cabin legal), for a full day at ~5 W.
5. **Board exposed on the deck, no window, no gamepad.**
6. **No monitors with rear-facing sockets.**

Calls I made where Tim didn't answer (to correct if wrong):

- **On/off**: no added switch. A finger hole in the drawer face reaches the bank's button, and
  each monitor insert exposes that monitor's power button (or holds a kit's keypad board behind a
  cutout). Opening means pressing two buttons; closing means pressing them again, so it doesn't
  drain the battery in a bag. `verify.py` proves each supported bank's button and each monitor's
  button can be reached.
- **Machines**: printed parts fit a 220 x 220 mm bed (Ender/Prusa class; bigger beds are a bonus).
  Laser parts are 3 mm plywood (T-slot M3 screws, nuts captured in slots), each part within
  300 x 200 mm (the smallest common hobby laser bed, K40 class). Acrylic is not a target.

## Constraints and data

### Dev board: Tiny Tapeout demo board v3 "ETR" (RP2350)

From `fpgas.online-mechanical/tinytapeout/boards.py` (KiCad-extracted):

- v3.2: 85.0 x 80.0 mm, v3.3: 85.0 x 85.0 mm, 1.561 mm PCB, R3.2 corners.
- Mounting holes: two only, MT1 (4.0, 76.0 / 81.0 on v3.3) and MT2 (77.0, 8.5), dia 3.2.
- Pmod headers J11/J12/J13 (INPUT/BIDIR/OUTPUT) on one edge, bodies to y = -8.55 (overhang).
- USB-C (J1) on the opposite edge at x 70.9-81.5, shell overhanging to y = 81.65.
- The deck accepts the ETR boards only: v3.2 and v3.3 (Tim: "one of the new ETR boards"). Both
  share the Pmod edge, J13 position, MT2 and USB-C x-range; they differ in depth (80 vs 85) and
  MT1's y, so one layout with the deeper board's envelope covers both. Older revisions are out of
  scope.

### Cable sourcing (builder's call, made here)

Off-the-shelf parts only. VGA: a slim, short (<= 0.5 m) VGA cable, with a 90 degree adapter
where a monitor's socket faces backwards; `verify.py` holds the chosen cable's stated diameter
and minimum bend radius (the cable data names the product it came from). USB: short right-angle
cables. No Pmod extension ribbon: the TinyVGA Pmod stays on J13 on the deck.

### TinyVGA Pmod

Plugs into J13 (OUTPUT); carries a DE-15 socket. Geometry is NOT yet in
fpgas.online-mechanical: to be extracted from the TinyVGA KiCad source (mole99/tiny-vga) or
measured. The VGA plug plus cable bend behind the DE-15 is ~40-60 mm (straight plug); a 90 degree
VGA plug shortens it.

### Monitors (survey 2026-11-23; figures from listings, see `monitor-survey.md` beside this file)

| Ref | What | Size | Notes |
|---|---|---|---|
| H | 7" plastic car-style TFT monitor (AliExpress 1005004614276566) | 173 x 113 x 20 at the rim, plus a rear hump | VGA/HDMI/AV, 12 V; the same family as T |
| J | AT070TN92 7" 800x480 panel + PCB800099 driver board (bare kit) | board 90.6 x 65.7; panel ~165 x 100 x 5.7 (unconfirmed) | HDMI/VGA/AV on the board, 12 V; ~US$15 |
| T | **Tim's Shenzhen monitor: a 7" car-style "TFT color monitor"** (Taobao ~US$20; survey item H's family) | listing: 170 x 113 mm, 800x480 or 1024x600; Tim's photos: front ~176-181 x ~113, back ~182 x ~117-118, window ~159 x ~86; depth unmeasured | Hard-wired cable leaving the long edge on the button side near one corner, ending in VGA + DC barrel (12 V, via Tim's USB boost adapter) + composite (Tim will likely cut the composite off). Buttons on the front along that edge. Flat back with a stand clip. See `docs/measurements/2026-11-23-photo-measurements.md` |

**Tim's 7" (T) is the main monitor** (found 2026-11-23 from his photos; it was thought to be a
5"). It costs almost nothing in size: its ~182 x 118 mm body fits inside the ~205 x 160 mm base
footprint that the drawer and the board already set. Mount it buttons-down, so the cable leaves
next to the hinge and the buttons face the visitor below the screen. Its pocket is sized for
the largest reading (182 x 118) and the insert takes up the listing's smaller figure; depth is
a placeholder (25 mm, unconfirmed) until measured.

**Monitors whose sockets face backwards are out of scope** (Tim: "Probably can ignore monitors
who socket faces backwards"). That drops the Eyoyo S501H (124 x 79 x 18, VGA on the rear face).
Also supported, via their own inserts in the same pocket: H and J. The 5" monitors in the
survey are out of scope (Tim, 2026-11-23).

Lid pocket target: ~185 x 120 mm inside (Tim's 7" plus fit). Depth: the 7"'s body (placeholder
25 mm); kit J (panel ~5.7 mm plus its driver board on standoffs) fits within it.

### Batteries (survey 2026-11-23, see `battery-survey.md` beside this file)

Reference banks: INIU P512 (104 x 70 x 29), UGREEN PB505 (116.2 x 70.6 x 30.0, all ports on one
face), Xiaomi 20000 integrated cable PB2020 (128 x 73 x 32), Anker Zolo 20K A1689
(119.9 x 73.4 x 31.5). Drawer bay ~158 x 82 x 34 mm inside plus a ~35 mm cable bay at the port
end; a per-model end-stop + packing insert puts each bank's port end against the cable-bay wall.

### Cables and adapters

- Bank to dev board: USB-A or USB-C to USB-C, right-angle at the board end preferred.
- Bank to monitor: 5 V cable to the monitor's 5 V input, or a USB to 12 V DC (5.5 x 2.1) boost
  cable. The boost module must have a place to sit.
- VGA: TinyVGA DE-15 to monitor, short; route depends on monitor (rear, side, pigtail).
- All cables that cross the hinge pass through a hinge-side cable channel with a bend radius
  they tolerate over repeated opening.

## Design (the parts decided)

- **Form**: laptop/clamshell. Base = deck (dev board on top) over the battery drawer. Lid =
  monitor. Hinge along the back edge; lid rests on a stop at ~100 degrees.
- **Deck**: board on standoffs at its two holes plus edge supports (two holes alone let it
  rock); exposed. USB-C cable drops through a slot in the deck next to J1 into the base cavity.
  The Pmod edge faces the hinge, so the TinyVGA Pmod and its plug sit behind the board, under or
  near the hinge, and the VGA cable has the shortest path into the lid.
- **Lid**: a common pocket and per-monitor inserts (front bezel plate with that monitor's window,
  rear retainer with that monitor's connector exits). When closed, the screen faces the deck; the
  closed height clears the tallest thing on the board and the Pmod/plug.
- **Drawer**: slides out of a side (or front) of the base; latches closed (detent or magnet).
  The two USB cables plug into the bank inside the drawer's cable bay and run through a slack loop
  to the base cavity, so the drawer can slide out far enough to unplug and lift out the bank.
- **Build routes**: one layout; a printed body (STEP + STL, plate-sized parts, print
  orientations stated) and a laser body (DXF per 3 mm sheet, kerf parameter, assembly hardware
  list). Shared small parts (hinge pins, standoffs, drawer stop, inserts) may be printed in both
  routes.
- **Repo** (follows fpgas.online-mechanical conventions): Python run with
  `uv run --no-project --with ...`, no pyproject; a `Makefile` (`make`, `make check`); data
  modules; `layout.py` (the shared layout); `verify.py` (fit proofs: every monitor in every lid,
  every battery in the drawer, both board revisions on the deck, lid clears board when closed,
  cables' bend radii and lengths, hinge sweep to the stop); CadQuery for solids (STEP/STL);
  ezdxf for laser DXF; mechanical sheets in the fpgas.online-mechanical drafting style (SVG to PDF
  via Inkscape); 3D renders via Blender run headless (portable tarball, no root), committed as
  PNG.
- **Licence**: Apache-2.0 (matches fpgas.online-mechanical and Tim's default).

## Approaches considered

1. **One parametric model, two outputs**: a single geometry from which both printed and
   laser files come. Least duplicated work, but forces the printed body into flat-panel shapes.
2. **Two separate designs**: each process at its best, but every change twice and drift.
3. **Single-monitor design**: simplest, but every seller's 7" differs by a few mm, so inserts are kept.

Chosen: **(1) + (2)**, data, layout and verification shared, the two bodies separate (see
Decision 1).

Power approaches considered: (a) all 5 V with boost cable (chosen); (b) one 12 V PD port split
by an internal 12 V to 5 V buck (needs custom electronics, rejected); (c) dual-converter bank
(CUKTECH No.15 / UGREEN PB723: ~20 mm taller drawer, ~3x the price, rejected).

## Left to the builder

- Reuse of fpgas.online-mechanical code and data: a git submodule pinned to a commit
  (my call: traceable to an exact commit, and nothing copied that can drift).
- Exact box dimensions, wall thicknesses, hinge design, drawer latch, fasteners (prefer M3 and
  heat-set inserts for print; M3 T-slots for laser).
- Which side the drawer opens on.
- Render set: at least closed, open from the visitor's side, open from behind, drawer out, and
  the laser flat-pack.
- Drawing set: a general arrangement sheet per build route, part sheets for every made part, and
  a sheet per monitor insert.

## Open items (need measurements Tim can provide)

- Tim's 7" monitor: depth, and a caliper check of width (listing 170 vs photos 176-182).
- Tim's USB to 12 V DC boost adapter: body size (so the box can hold it).
- TinyVGA Pmod outline and DE-15 position.
- Board top-side tallest component height (chip carrier, 7-seg), for lid clearance.
