# tt-demo-box, compact: design rulings

Companion to [`2026-11-24-compact-box-design.md`](2026-11-24-compact-box-design.md). The compact
box was built task by task, and each time the plan, the spec or the parts data left a question
open, a ruling settled it. The code comments cite these rulings by ID ("R18", "(R16a)"); this
document is where those IDs are defined. Every entry gives what was decided, why, and what it
costs if the decision turns out wrong.

The IDs are in the order they were issued, 2026-11-24 to 2026-11-25. Two are sub-rulings: R16a
replaced R16's geometry, and R18b came with R18. R20 was never issued: the numbering went from
R19 to R21.

## Before the work started

### R1: the knuckle radius lives in `layout.py`
- **What:** `KNUCKLE_R`, and any other hinge size the layout needs, is defined in
  `demobox/layout.py`. `demobox/shared/hinge.py` imports it from there.
- **Why:** the layout needs the knuckle radius to place the hinge axis, and the hinge module
  needs the layout. Defining it on the layout side avoids an import cycle.
- **Cost if wrong:** one constant sits in a slightly odd place.

### R2: the layout's hinge check proves the profiles only
- **What:** the layout's `hinge_sweep` proof checks that the lid and base side profiles never
  intersect at any sweep angle, and that the open angle is `LID_OPEN_DEG`. The physical stop
  was proved later, by the hinge's own tests and the solid sweep (it has since moved into
  `hinge_sweep` as well).
- **Why:** the proof was written before the hinge geometry existed.
- **Cost if wrong:** for a while the stop was proved only in tests, not by `make verify`.

### R3: the test suite may be red mid-rewrite
- **What:** while the modules were being rewritten one by one, each step ran only its own tests
  and the modules it touched. The whole suite had to be green again once every module was
  rewritten, and `make check` had to pass at the end.
- **Why:** the rewrite cascaded through every module; old imports broke until each was redone.
- **Cost if wrong:** no full-suite safety net in the middle. Each review checked that the only
  failures were imports of modules not yet rewritten.

### R4: one function gives the pigtail's path
- **What:** `checks.pigtail_path(lay, angle_deg)` returns the monitor cable's route as a
  polyline in the base frame, from the monitor's exit to the VGA plug. The cable check uses it
  and the renders draw it.
- **Why:** one path, one representation, so the check and the picture cannot disagree.
- **Cost if wrong:** a later signature change ripples to both users.

### R5: the size test pins real numbers
- **What:** `test_size_budget` checks the formula and also pins the printed route's sizes as
  literal numbers, worked out by hand from the part data, with the working in a comment.
- **Why:** a formula restated in a test cannot fail on its own; a hand-derived number can.
- **Cost if wrong:** the literals need updating whenever the part data changes. That is
  intended: they flag the change.

## The layout

### R6: the Xiaomi stays the design bank, though the Anker is wider
- **What:** the box stays sized for the Xiaomi PB2020. A test checks that each other bank's box
  is never bigger than the Xiaomi's by more than that bank's own excess size, per dimension.
  The spec's claim that the box "can only shrink" with another bank was corrected.
- **Why:** the spec chose the Xiaomi as the largest bank. It is the longest, but the Anker is
  0.4 mm wider.
- **Cost if wrong:** none; the box follows whichever bank is chosen.

### R7: the plinth covers both board revisions, with a notch under a plug
- **What:** the board's plinth covers both revisions' outlines (v3.3 is longer). A relief notch
  is cut from it under the v3.2 board's USB plug, which hangs below the PCB there. Every pin
  hole is inside the plinth, at least 1.5 mm from every edge and from the notch.
- **Why:** a pin hole broken out through the plinth's edge would not locate the pin.
- **Cost if wrong:** one more box in the layout.

### R8: the closed lid stops the board lifting off its pins
- **What:** the board, its TinyVGA and the VGA plug can only lift together, and their top is
  `SLACK + CLOSED_CLEARANCE` under the closed monitor. The pins stand 1 mm more than that above
  the PCB (`PIN_PROUD` = 4 mm), so the board cannot come off them with the lid shut.
- **Why:** the geometry holds the board, without a foam pad.
- **Cost if wrong:** if the TinyVGA came unplugged, the board could ride up. That is a broken
  setup anyway.

### R9: leftover tests are deleted by the task that rewrites their file
- **What:** tests of removed features were left in place until the task that rewrote each test
  file, rather than deleted early.
- **Why:** those files were rewritten wholesale; deleting early meant editing them twice.
- **Cost if wrong:** stale tests sat behind import errors for a while.

### R10: the boost module goes on the floor if it fits, else in the lid
- **What:** the USB-to-12 V boost module sits on the floor at the bank row's right-hand end,
  lengthways or turned 90 degrees, whichever fits. Only if neither fits does it go in the lid
  strip beside the monitor. (R16a amended the room it can use.)
- **Why:** the first kit left an empty space there, and the lid strip was meant for the cable
  slack. A boost in the lid costs a cable crossing the hinge.
- **Cost if wrong:** none in size.

## The hinge and the cables

### R11: the hinge is relieved round its axis
- **What:** the layout computes `hinge_relief_r`, the furthest any part of the lid gets from the
  axis while it dips below the seam during the swing, plus a fit clearance. Where the lid has a
  knuckle, the base is cut back to that radius; where the base has one, the lid is.
- **Why:** this is how a clamshell hinge with alternating knuckles clears itself. A single
  profile along the whole width cannot.
- **Cost if wrong:** a small cove in the back rim at the lid's knuckles.

### R12: the bank lifts out past the open lid
- **What:** the check that the bank lifts out uses the bank itself, centred in its bay as
  packed, not the bay with its slack. It clears the open lid by 0.4 mm (printed).
- **Why:** it is the bank that lifts out, not the bay.
- **Cost if wrong:** a tight lift at the back edge.

### R13: the monitor's own cable has its own data
- **What:** the monitor's hard-wired VGA cable (the pigtail) got its own cable entry: 5 mm
  across, marked unconfirmed. The route takes the widest U-turn the closed box allows. (R17 later
  set its bend radius.)
- **Why:** the 30 mm bend radius in use belonged to a different, bought cable.
- **Cost if wrong:** a stiffer real cable needs a deeper lid. Raised with Tim.

### R14: the USB cable leaves its plug towards the bank
- **What:** the bank-to-board USB cable leaves the right-angle plug at J1 towards the bank row,
  and the layout's description says so.
- **Why:** it is the shortest run, and the route already went that way.
- **Cost if wrong:** none; a wording fix.

### R15: three kinds of hinge segment along the width
- **What:** along X the hinge has lid-knuckle segments (base cut back, lid whole), base-knuckle
  segments (lid cut back) and open segments. Knuckles go only in `knuckle_x`: the X ranges with
  no base contents within the relief radius of the axis. There must be at least two such ranges
  of at least the knuckle length. The hinge check tests the real lid against the real contents
  at every angle.
- **Why:** the earlier check only compared the relief with itself, so it proved nothing.
- **Cost if wrong:** fewer knuckles.

### R16: the VGA adapter is always fitted
- **What:** the 90 degree VGA adapter is always used, turning the monitor's plug so its cable
  heads back towards the hinge. Every bend of the cable after the plug's stiff run is checked.
- **Why:** with a straight plug, the plug's stiff run ends 1 mm from the wall and the cable
  would have to double back.
- **Cost if wrong:** the row length and the box width change. (R16a replaced this geometry.)

### R16a: the adapter's shape, and the plug in the bank row's corner
- **What:** the adapter is a left/right-angle type: it stands 17 mm out of the TinyVGA's
  socket and spans 35 mm along it, with its socket on the end towards the bank row. The
  monitor's plug goes into it from behind, and the plug and its stiff run lie in the bank row's
  free right-hand back corner. The cable bends from there up to the hinge notch. The boost
  module goes in the bank row only if room is left after the plug; otherwise it goes in the lid
  strip.
- **Why:** of the three arrangements tried, this gives the smallest box (about 2.1 L printed,
  against 2.21 L).
- **Cost if wrong:** if the adapter bought is the up/down type, the plug turns and the box is
  laid out again. It is flagged unconfirmed; a real adapter may also be longer than 17 mm,
  which would widen the box.

### R17: the pigtail's bend radius placeholder is 15 mm
- **What:** the monitor cable's minimum bend radius is 15 mm (three times its 5 mm diameter),
  still unconfirmed.
- **Why:** Tim asked for the smallest box, and the 20 mm figure before it was a guess, not data.
  At 20 mm the plug cannot sit in the bank row's corner and the box grows to about
  208 x 209 mm.
- **Cost if wrong:** if the real cable needs about 20 mm, the plug corner has to change (about
  2.65 L). This measurement decides the layout.

### R18: the pigtail drops in front of the hinge rod
- **What:** the cable goes down through the hinge notch far enough in front of the axis to clear
  the rod (cable radius + rod radius + fit clearance). The base grows exactly enough in depth for
  the cable's turn behind the plug's stiff run to reach its bend radius; this is a named depth
  term. The rod stays one piece across the notch.
- **Why:** the cable was passing through the rod; and a rod split at the notch could not be
  inserted.
- **Cost if wrong:** about 0.6 mm of depth (printed).

### R18b: the catch blocks push the monitor back only when they overlap it
- **What:** the lid's catch blocks add their size to the depth only when they reach over the
  monitor in X, in the layout and in the size check alike.
- **Why:** the spec forbids space kept "just in case".
- **Cost if wrong:** none; the term applies when it is needed.

### R19: knuckles keep clear of the whole bank bay
- **What:** the knuckle ranges treat the whole bank bay as base contents, not the bank as
  packed, because the bank can slide within its slack. The minimum knuckle length became 9 mm,
  and the knuckles share each range equally, a fit clearance apart. `make verify` enforces it.
- **Why:** a bank pushed to the right overlapped the first lid knuckle by 0.55 mm.
- **Cost if wrong:** knuckles about 1 mm shorter.

### R21: only the lid is relieved in open segments; the base gets a seal bead
- **What:** in open segments only the lid is cut back round the axis. The base's back wall
  stays whole, and the base carries a seal bead that fills the lid's relief above the seam. The
  bead runs along every open segment, with a gap at the hinge notch for the cable.
- **Why:** cutting the base back over 155 mm left a 6.7 mm groove open into the box and the rod
  unsupported. Only the lid swings, so only the lid needs the relief.
- **Cost if wrong:** the bead adds a little material at the back edge.

### R22: the rod runs only from the first knuckle
- **What:** the hinge rod runs from the first knuckle to the right-hand side face, flush there
  and pushed in from there, one piece across the notch. It does not run the full width.
- **Why:** no rod support is possible over the bank bay and the port room without making the box
  deeper, and a full-width rod would hit a bank slid back in its slack.
- **Cost if wrong:** the rod is held by the knuckles only, over about 42 mm at the right-hand
  end, so the open lid has a little rack.

### R23: knuckles keep a fit clearance from every base content along X
- **What:** the knuckle ranges also keep a fit clearance in X from every base content's X range.
- **Why:** the bank bay was touching the first knuckle face to face.
- **Cost if wrong:** knuckles a fit clearance shorter.

### R24: the rod is held in by a blind end and a press fit
- **What:** the first knuckle's bore is blind, stopping 1 mm short of its left face. The last
  5 mm of the right-hand lid knuckle's bore, at the side face, is 0.1 mm under the rod (a press
  fit). Elsewhere the bore is a slip fit.
- **Why:** a flush slip-fit rod would walk out.
- **Cost if wrong:** the press fit needs a mallet. (R35 rules out a filament rod, which this
  press fit would not hold.)

## The bodies and the drawings

### R25: the boost module is taped into the lid
- **What:** when the boost module is in the lid, it is stuck to the lid's inside face with the
  same double-sided foam tape as the monitor; there is no pocket. The tape's hardware line says
  so, in both routes.
- **Why:** loose in the lid strip, it would fall out with the lid open; and the spec allows no
  shaped pockets.
- **Cost if wrong:** none.

### R26: the base is notched only where the cable passes
- **What:** the base is cut at the hinge notch only where the pigtail passes above the rim (the
  seal bead's gap). The back wall under it stays whole.
- **Why:** the spec forbids empty slots.
- **Cost if wrong:** none; the cable is proved clear of the base at 0 and 100 degrees.

### R27: parts are built per layout, and the plinth is solid
- **What:** the part cache and the assemblies key on the whole layout, so a box for another
  monitor or bank builds its own parts and never returns the design kit's. The printed plinth is
  solid, with no enclosed hollows.
- **Why:** a silent wrong part is worse than a slow one; a slicer's infill already saves the
  filament, and trapped supports are a print hazard.
- **Cost if wrong:** more filament or build time than strictly needed.

### R28: the laser route's board pins stand on the floor
- **What:** in the laser route the two board pins (MT2 and the loose MT1) are bought rod
  standing on the base floor through the plinth top's holes, long enough to reach the plinth
  top + the PCB + `PIN_PROUD`. The hardware list gives the computed length.
- **Why:** a pin resting in the plinth's plywood top could drop into the plinth.
- **Cost if wrong:** two slightly longer rods.

### R29: no gap at the laser lid's back
- **What:** in the laser route the gap between the lid's back and the seal bead is at most a fit
  clearance, as in the printed route. How is the implementer's choice; it is tested.
- **Why:** a flat plywood edge left a visible gap down to the relief circle.
- **Cost if wrong:** none.

### R30: shared solids live in a public module
- **What:** the helpers the laser fittings borrowed from the printed body moved to
  `demobox/shared/solids.py`, which both routes import.
- **Why:** one route must not import the other's private helpers.
- **Cost if wrong:** none.

### R31: wrong text on a drawing is a defect
- **What:** drawing-text mistakes are fixed in the same round as code findings: the "reach
  behind" dimension measured from the back face, the right count of printed parts, "4 magnets,
  6 x 3 mm", the rod hole "D3.00", and the rod length the same on every sheet.
- **Why:** a builder reads the drawings, not the code.
- **Cost if wrong:** none.

## The final review

### R32: the monitor's power path is modelled and checked
- **What:** the cables from the bank to the boost module (USB) and from the boost's 12 V output
  to the monitor's DC barrel are modelled and checked. The boost is in the lid strip, so its USB
  cable crosses the hinge with the pigtail, and the hinge notch must take both cables side by
  side. A `checks.boost_cable_path(lay, angle_deg)` route is bend- and length-checked over the
  sweep like the pigtail. The pigtail's DC branch is assumed reachable in the lid strip
  (unconfirmed; measure where Tim's cable splits), and the renders draw the cable.
- **Why:** without it, the monitor has no designed power: it is the one wiring path a builder
  would have to invent.
- **Cost if wrong:** if the monitor's DC branch is at the plug end of its cable, the DC lead
  crosses the hinge too.
- **Status:** not yet built. The bank's ports face the port room at the left, the notch is at
  the right, and the bank fills its row in between; the routing question went back to Tim (see
  the README's open measurements).

### R33: the layout carries its bank and monitor
- **What:** `Layout` records the bank and monitor it was laid out for. The base contents, the
  proofs, the hinge, both bodies, the drawings and the renders read them from the layout, never
  from the `DESIGN_*` defaults. For every listed bank, `layout(wall, bank=...)` passes every
  proof in both routes.
- **Why:** `layout(wall, bank=...)` used to give a box checked against the default bank, which
  nobody had verified (one representation per thing).
- **Cost if wrong:** none.

### R34: the README must not mislead a builder
- **What:** the README's board-orientation line was corrected; the unused slim VGA cable was
  dropped from the parts list and the data; "Adding a monitor" lists the pigtail fields the
  layout needs; there is an assembly order with the magnet polarity (opposite poles facing); the
  size table and the rod lengths are generated and checked by `make check`.
- **Why:** these figures and instructions had gone stale or were missing.
- **Cost if wrong:** none.

### R35: the hinge rod is 3 mm steel only
- **What:** the 2.85 mm filament option is gone everywhere: hardware lists, build notes, the
  drawings and the README.
- **Why:** a 2.85 mm rod is smaller than the 2.9 mm press zone (R24), so nothing would hold it,
  and it would rattle 0.35 mm in the slip bores.
- **Cost if wrong:** a bought steel rod instead of offcut filament.

### R36: the ruling IDs are defined in a committed document
- **What:** this document, listing R1 to R36 in plain language, taken from the working ledger.
  The code comments keep their IDs, which now resolve here, and the spec points here.
- **Why:** the ledger lives in a git-ignored directory; after merge, every "R22" in the code
  would point at nothing, and those comments are where the hinge, rod and cable reasoning lives.
- **Cost if wrong:** one more document to keep in step when a new ruling is made.
