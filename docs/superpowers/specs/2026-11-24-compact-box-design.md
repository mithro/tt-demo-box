# tt-demo-box, compact: as small as the parts, no screws

Status: approved by Tim, 2026-11-24.

The rulings made while building it (R1 to R36, cited by ID in the code) are in
[`2026-11-24-compact-box-rulings.md`](2026-11-24-compact-box-rulings.md); where a ruling and this
document disagree, the ruling is the later decision.

Supersedes `2026-11-23-tt-demo-box-design.md` (the "first design", merged in PR #1) where the two
disagree. Everything in the first design that this document does not change still holds: the
intent (open the lid and it is a working demo), the 5 V power scheme, the 20,000 mAh-class bank,
the board exposed on the deck, the lid open to 100 degrees against a stop, both build routes, the
traceable-data and `verify.py` rules, the drawings and renders, and the repo conventions.

## Why

Tim, on the first design (214.5 x 209 x 91 mm base + 28 mm lid, about 5.3 litres closed, about
50 pieces to build): "This box is *way* too huge." Then:

- "You want to remove as much excess / unused space as possible. The box should only be
  marginally bigger than everything stored separately."
- "Reduce the part count as well."
- "The choice of pan-head screws is stupid, it leaves things sticking out and could be done
  entirely without them."
- "Long edge of the video monitor should match the long edge of the tiny tapeout."
- "The box doesn't need to have a perfect pocket."
- "The monitor should have no extra bezel either."
- "Just some double sided tape and sticking it to the box lid works."
- "Keep the laser route and make the box just use a bit of glue."
- "Go with whatever makes the box smallest."

Where the first design's space went (printed route): the board's front-to-back run (USB-C plug +
board + TinyVGA + 90 degree VGA adapter, 203 mm) set the depth at 209; a 158 mm battery bay
(longest listed bank: 128) and a 35 mm cable bay set the drawer; a 23.5 mm empty layer let the
USB-C cable drop from the board to the drawer; lid cable gutters (33 + 24 mm) and a
one-box-fits-every-part layout took the rest.

## Goals

1. **Smallest box.** Every dimension is the contents plus walls plus a small stated slack
   (`SLACK`, about 1 mm a side). No space is reserved for anything not in the box. Target, from the
   part data (estimates; `layout.py` computes the real numbers): about 206 x 175 mm footprint,
   about 60 mm closed, about 2.1 litres (first design: 5.3).
2. **Fewest parts.** The printed route is a base, a lid and the hinge parts, plus magnets and tape.
   The laser route is the plywood panels glued together, plus the printed hinge knuckles.
3. **No screws, nuts, bolts or threaded inserts anywhere, and nothing proud of an outside face.**
4. **Long edges together.** The monitor's long edge and the board's long run (USB-C plug, board,
   TinyVGA, VGA plug) both lie along X, side to side.
5. **Both routes stay.** Printed (220 x 220 bed) and laser (3 mm plywood, 300 x 200 bed), from one
   layout.

## Non-goals

- Shaped pockets. Spaces are plain rectangles with slack. A loose bank, or a scrap of foam if it
  rattles, is fine.
- Per-monitor inserts, bezels, retainers or clips. The monitor's own case is the face.
- One box for every listed part at once. The box is sized for one kit (see Decisions 1); a
  different kit gets its own box, regenerated from the same code.
- Taking the glued laser box apart.

## Anti-goals (a failure even if it works)

- Any screw head, nut, foot or catch that stands proud of an outside face.
- A slot, gutter, bay or layer that exists "in case", with nothing in it.
- A board that visitors can't see: the base's front wall must stay low (see Decisions 4).

## Decisions

1. **One kit.**
   - **Monitor:** Tim's Taobao 7" (`taobao-tim`, 182 x 118, depth placeholder: see Open items).
     The other monitors stay in the data. Because the monitor is taped in, any monitor whose
     outline fits the lid works without a new part; `verify.py` reports which listed monitors
     fit the generated lid, not a pass/fail.
   - **Power bank:** not chosen yet (Tim: "No idea on which power bank yet"). The bay is sized
     for the largest listed bank, the Xiaomi PB2020 (128 x 73 x 32). It is one value
     (`DESIGN_BANK`): when Tim picks a bank, the box regenerates around it
     (the Xiaomi is the longest listed bank; the Anker is 0.4 mm wider, so its box is 0.4 mm deeper).
     `verify.py` reports which listed banks fit.
   - **Board:** both ETR revisions (v3.2 and v3.3). They differ by 5 mm on the long run; keeping
     both is cheap and the board in hand may be either.
2. **Layout B: the bank beside the board, both on the base floor** (approaches below). Top view,
   lid open:

   ```
              hinge (back, Y max)
    +---------------------------------------+
    | [boost] [ bank (lies along X) ]  [USB] |   bank row
    | [USB-C]=[ board ]=[TinyVGA]=[VGA plug] |   board row (visitor side)
    +---------------------------------------+
              front (visitor, Y = 0)
   ```

   - The board row is at the front, so visitors see the board in front of the screen; the bank
     row is behind it, under the open lid.
   - Which end the USB-C and the VGA plug go is the builder's call. Choose whatever gives the
     shortest cable runs: VGA to the hinge, bank to board, bank to boost to the monitor.
3. **The monitor is stuck to the lid with double-sided foam tape** (VHB type), face out. The lid
   has no pocket, insert, bezel, clip or retainer. The monitor's stand clip is taken off so the
   tape grips a flat back (my call; if it can't come off, its height adds to the lid depth).
   - **Its cable stays plugged in.** Tim's monitor has a fixed cable ending in VGA, a DC barrel
     and composite (composite cut off). Its VGA plug goes straight into the TinyVGA, so the
     first design's separate slim VGA cable and 90 degree adapter go (if the plug's run fits the
     board row; otherwise the adapter stays). The cable crosses from lid to base in a loop at the
     hinge, through a notch in the hinge line, and its bend radius is checked over the full
     0-100 degree swing. The DC barrel plugs into the boost cable.
4. **The lid is a shallow tray; the base is only as tall as the bank row.**
   - **Lid:** a flat panel whose rim walls cover the monitor's depth.
   - **Base:** its walls are as tall as the bank (the tallest thing on the floor) plus the floor
     and slack.
   - **Why, my call:** the alternative was a flat lid with base walls tall enough to enclose
     the monitor too. That puts the board at the bottom of a roughly 30 mm pit behind a tall
     front wall, hiding it from anyone not looking straight down. The volume is the same either
     way.
   - **The board is raised to the rim:** the board row is shorter than the bank row (board +
     TinyVGA about 21 mm against the bank's 32), so the board stands on a printed plinth (the
     pins of Decision 6 rise from it). Its top is then level with the base rim, in view over the
     front wall, and no taller than the box already is. My call; the plinth fills space that
     was empty anyway.
   - **Closed:** the monitor's face comes down over the board and bank rows.
   - **Spare space:** the strip of the lid tray beside the monitor (lid depth minus the
     monitor's height, about 50 mm) takes the cable runs and, if it fits better there than on
     the floor, the boost module.
5. **No fasteners.**
   - **Hinge:** printed knuckles on a single straight pin, cut flush with the outside faces. The
     pin is steel rod or 1.75 mm filament (builder's call; prefer filament, since no bought
     part). *Amended by ruling R35: 3 mm steel rod only; the hinge holds it with a press fit
     that a filament rod would not meet.*
   - **Printed route:** the knuckles are printed with the base and the lid.
   - **Laser route:** printed knuckle blocks glued into the plywood.
   - **Stop:** the lid's 100-degree stop stays, built into the knuckles.
6. **Board: located, not screwed.**
   - Two printed pins go up through MT1 and MT2 (each revision's MT1 differs; the first design's
     merged-boss approach may be reused).
   - Low edge stops keep it from sliding.
   - What holds it down: closed, the lid holds it (a foam pad on the monitor face, or the
     closed gap kept under the pins' height so it can't lift off them). Open, it rests on the
     pins. Builder's choice.
7. **Bank: lifts straight out with the lid open.**
   - Its cables unplug, and that replaces the drawer, its runners, the cable bay and the slack
     layer. A bank with sockets: the cables unplug at the bank and stay in the box. A bank with a
     built-in cable (three of the four listed, including `DESIGN_BANK`): the cable unplugs at
     the board or the boost cable and leaves with the bank. The bay keeps room for the bank's
     plugs or its built-in cable's loop, whichever the bank in the data has.
   - Spec rule kept: removable in seconds, for airport security.
   - The bank's power button must be reachable with the lid open (a finger gap at that end of
     the bay, or the button facing up); `verify.py` proves it.
8. **Lid catch: the magnets stay**, pressed or glued in flush, two pairs, in both routes.
9. **Laser route: finger-jointed 3 mm plywood, glued.**
   - Removed: T-slots, square nuts, screws and rubber feet. The box no longer sits on screw
     heads, so it needs no feet.
   - A panel over the 300 x 200 bed is split along a glued joint, as before.
   - Printed parts in the laser route are only the hinge knuckle blocks and any magnet block
     where 3 mm plywood is too thin for a 3 mm magnet.

## Approaches considered

| | Layout | Footprint | Closed | Volume |
|---|---|---|---|---|
| A | bank under the board, in a side tunnel | ~201 x 125 | ~83 mm | ~2.09 L |
| **B** | **bank beside the board** | ~201 x 170 | ~60 mm | ~2.05 L |
| C | bank in the lid behind the monitor | ~201 x 125 | ~70 mm | lid ~55 mm thick: tips the box backwards when open at 100 degrees; ruled out |
| (first design) | bank in a drawer under the deck | 214.5 x 209 | 119 mm | 5.3 L |

**B chosen:**
- it's marginally the smallest (Tim: "whatever makes the box smallest");
- it's much flatter;
- the bank lifts out with no tunnel;
- the strip beside the monitor holds cables.

**A's merit:** a footprint close to the monitor's own.

Also considered and dropped:
- **Trimming the first design** (shorter bay, VGA plug not behind the board): still well over 3 L.
- **Turning the plugs down through the deck:** the USB-C plug body (20 mm) and the VGA adapter
  still stick out sideways, so it saves less than it costs in height.

## Left to the builder

- **Board orientation along X:** which end the USB-C goes, and the VGA adapter's direction.
  Shortest runs win; `verify.py` checks bend radii.
- **Placement:** where the boost module and cables sit (the bay's spare end, or the strip in the
  lid tray).
- **Small details:** the hinge knuckle count and pin, and the finger gap for the bank's button.
- **Walls:** thickness for the printed route, keeping today's 2.4 mm unless the hinge needs more.
- **Code:** which first-design code is reused and which is deleted. Delete freely: inserts,
  retainers, the clip, the drawer, packing, T-slots and the hardware tables shrink or go.
  - Keep: part data, the submodule, `checks`/`verify` structure, drafting and renders.
  - Update the README, drawings and renders to the new box.

## Open items (measurements Tim can provide)

- **Tim's 7" monitor depth:** the code says 20 mm, the first spec said 25 mm (placeholder). This
  is now the lid's depth, so it matters directly.
- **Monitor's true width** (170 listing vs about 182 from photos).
- **USB to 12 V boost module body size.**
- **Board's tallest component** (placeholder 12 mm).
- **TinyVGA reach** (KiCad 59.8 vs photo about 53).
- **Which power bank** (sets `DESIGN_BANK`).
- **Monitor cable:** length to the VGA plug, and whether the stand clip comes off.
