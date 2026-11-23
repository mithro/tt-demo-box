# tt-demo-box: a portable, zero-setup Tiny Tapeout VGA demo station

Status: approved by Tim, 2026-11-23.

## Intent

A small box you carry to a meetup, put on a table and open: the lid swings up to just past
90 degrees, the ~5" VGA monitor in the lid is already showing the board's VGA designs cycling,
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
- Fits as many small, cheap (~US$15-35) 5" VGA monitors as possible, both cased monitors and
  bare panel + driver-board kits.
- Two build routes from one design: 3D printed, and laser-cut flat panels.
- Mechanical drawings in the style of `fpgas-online/fpgas.online-mechanical`, plus 3D renders.
- Open-source tooling only.

## Non-goals

- No gamepad or input Pmod; the demo is hands-off. (INPUT and BIDIR Pmod headers stay free.)
- No custom electronics (no PCB, no PD trigger/buck board). Cables and off-the-shelf adapters only.
- No mains power inside the box; the battery is the only source. (Running it from a USB charger
  instead of the battery is fine and needs nothing special: the drawer cable just plugs into a
  charger.)
- 7" monitors are not a target (they would set a much bigger box). The data model shouldn't
  preclude them, but nothing is designed for them.

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
2. **Monitors: fit as many as possible**, via a common lid pocket plus a per-monitor insert
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
  each monitor insert exposes that monitor's power button (or holds kit D's keypad board behind
  a cutout). Opening means pressing two buttons; closing means pressing them again, so it doesn't
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
| D | "800050" 5" 800x480 VGA/CVBS kit (bare) | panel 120.7 x 76.3, FPC 47; board 89 x 58 | VGA on a DE-15 pigtail; 12 V DC jack + included DC-to-USB 5 V cable; ~US$27 |
| E | ZJ050NA-08C 640x480 4:3 kit (bare) | panel 117.65 x 88.43 x 5.9, active 101.76 x 76.32; board size unknown | VGA/HDMI/AV on board; cheapest (~US$16-20); native 640x480 = TT's VGA mode pixel-for-pixel |
| T | Tim's Taobao ~US$20 cased 5" | unknown | Measure it; it is the unit already owned |

**Monitors whose sockets face backwards are out of scope** (Tim: "Probably can ignore monitors
who socket faces backwards"). That drops the Eyoyo S501H (124 x 79 x 18, VGA on the rear face)
and lets the lid stay thin. Supported: bare panel + driver-board kits (D, E, and Adafruit 1678 /
EastRising ER-TFTV050-3, same 800x480 panel class) as the main targets; cased monitors with side
sockets (Miktver 5", generic 5" touch 126 x 96 x 17) best-effort; T once measured. Most 5"
800x480 panels share the 108 x 64.8 active area; the 4:3 ZJ050 is 101.8 x 76.3.

Lid pocket target: ~130 x 100 mm inside. Depth: bare panel (~3-6 mm) plus its driver board on
standoffs behind it, with the VGA cable leaving sideways or along the lid; side-socket cased
monitors (<= 20 mm) with the plug exiting through the lid's side wall.

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
3. **Single-monitor design**: simplest, but fails "as many monitors as possible".

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

- Tim's Taobao monitor: dimensions, connector positions, power input.
- Tim's USB to 12 V DC boost adapter: body size (so the box can hold it).
- TinyVGA Pmod outline and DE-15 position.
- Board top-side tallest component height (chip carrier, 7-seg), for lid clearance.
