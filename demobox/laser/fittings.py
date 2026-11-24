"""The laser route's printed fittings, its hardware list and its assembly.

Frames are ``demobox.layout``'s (see ``demobox.laser.panels``).  Spec
Decision 9: the route is plywood but for the hinge and the magnet blocks,
which are printed and glued in:

* ``knuckles-base``: fills the base's hinge cut-out (``panels.hinge_cutouts``,
  the back wall's top right and the right wall's top back corner), flush
  with the outside faces, as the printed base is there: the cut-out less the
  hinge relief round each lid knuckle (``hinge.knuckle_cut``), plus the base
  knuckle and the stop block under each lid knuckle (``hinge.knuckles``).
  Below the rim it stands in for the back wall at the pigtail's notch too
  (R26: no slot there);
* ``knuckles-lid``: fills the lid's cut-out (the back wall's bottom right,
  the right wall's bottom back corner) the same way: the lid knuckles, bored
  for the rod (blind in the first, the R24 press fit at the +X face), and the
  bridge above the relief that joins them;
* ``seal-bead``: the seal bead (``hinge.seal_bead``, R21) along the open
  segments, glued on the back wall's top edge;
* ``magnet-block`` (4 off, one part): the lid catch (``Layout.lid_catch``).
  3 mm plywood can't hold a 3 mm magnet flush, so each magnet is pressed into
  a CATCH_BLOCK square, CATCH_BLOCK_H tall printed block, its pocket open at
  the seam: two glued in the base's front corners under the rim (pocket up),
  two in the lid's over them (the same part, pocket down).

The board's pins are bought rod (``BOARD_PIN_LEN``), in ``plinth-top``'s
holes: MT2's glued, MT1's loose.  The hinge rod is the printed route's
(``hinge.pin_length``), pushed in from the +X side face.
"""

from __future__ import annotations

import cadquery as cq

import demobox  # noqa: F401  (puts the submodule on sys.path)
from demobox.layout import (CATCH_BLOCK, CATCH_BLOCK_H, MAGNET_D, MAGNET_T, PEG_DIA,
                            PIN_ROD_D, PRINT_BED, ROUTES, Layout, layout)
from demobox.laser import panels as P
from demobox.printed import body as PB
from demobox.shared import hinge as H

#: The bought board pins: PEG_DIA rod this long, its top PIN_PROUD above
#: the PCB, so it runs right through the plinth's top (3 mm) and the board.
BOARD_PIN_LEN = 10.0
#: The assembly's defaults: the printed route's.
ASSEMBLY_MONITOR = PB.ASSEMBLY_MONITOR
ASSEMBLY_BANK = PB.ASSEMBLY_BANK
ASSEMBLY_BOARD = PB.ASSEMBLY_BOARD

COLOURS = {**PB.COLOURS, "panel": (0.82, 0.66, 0.44), "fitting": (0.30, 0.32, 0.36)}


def _bx(b) -> cq.Solid:
    return PB._bx(b)


def _one(shape: cq.Shape, what: str) -> cq.Solid:
    return PB._one(shape, what)


_CACHE: dict[tuple, cq.Solid] = {}


def _cached(name: str, lay: Layout, t: float, build) -> cq.Solid:
    """``build()``, once per part, layout and thickness (keyed on the whole
    layout, as ``printed.body`` is: R27)."""
    key = (name, repr(lay), t)
    if key not in _CACHE:
        _CACHE[key] = build()
    return _CACHE[key]


# --- the fittings ---------------------------------------------------------------------

def _knuckles(lay: Layout, t: float, part: str) -> cq.Solid:
    """``part``'s knuckle block (base or lid frame, see the module docstring)."""
    back, side = P.hinge_cutouts(lay, t)[part]
    s = PB._fuse(_bx(back), _bx(side))
    s = PB._cut(s, H.knuckle_cut(lay, part).val())
    s = PB._fuse(s, *H.knuckles(lay, part).vals())
    n = lay.hinge_notch
    if part == "base":       # R26: the notch only above the rim, as the printed base's
        notch = PB._box(n.x0, n.y0, max(n.z0, lay.rim_z), n.x1, n.y1, n.z1)
    else:
        hy, hz = lay.hinge_axis
        notch = _bx(n.moved(0.0, -hy, -hz))
    return _one(PB._cut(s, notch), f"knuckles-{part}")


def knuckles_base(lay: Layout, t: float) -> cq.Solid:
    return _cached("knuckles-base", lay, t, lambda: _knuckles(lay, t, "base"))


def knuckles_lid(lay: Layout, t: float) -> cq.Solid:
    return _cached("knuckles-lid", lay, t, lambda: _knuckles(lay, t, "lid"))


def seal_beads(lay: Layout) -> dict[str, cq.Solid]:
    """The seal bead's pieces, base frame: ``seal-bead`` (or ``seal-bead-<i>``
    when the open segments are more than one)."""
    beads = H.seal_bead(lay).vals()
    if len(beads) == 1:
        return {"seal-bead": beads[0]}
    return {f"seal-bead-{i}": b for i, b in enumerate(beads, 1)}


def magnet_block() -> cq.Solid:
    """The magnet block in its own frame: CATCH_BLOCK square on Z = 0,
    CATCH_BLOCK_H tall, its pocket (the printed route's, a slip fit) open on
    top, the magnet MAGNET_RECESS under the face."""
    blk = PB._box(0.0, 0.0, 0.0, CATCH_BLOCK, CATCH_BLOCK, CATCH_BLOCK_H)
    c = CATCH_BLOCK / 2
    pocket = PB._zcyl(c, c, CATCH_BLOCK_H - PB.MAGNET_POCKET_DEPTH, CATCH_BLOCK_H + 1.0,
                      PB.MAGNET_POCKET_D / 2)
    return _one(PB._cut(blk, pocket), "magnet-block")


def _magnet_blocks(lay: Layout) -> tuple[list[tuple[str, cq.Shape]], list[tuple[str, cq.Shape]]]:
    """The four magnet blocks placed: (base frame, pocket up), (lid frame,
    closed, pocket down)."""
    blk = magnet_block()
    flipped = blk.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 180.0).translate(
        cq.Vector(0.0, CATCH_BLOCK, CATCH_BLOCK_H))
    base, lid = [], []
    for i, c in enumerate(lay.lid_catch, 1):
        b = lay.catch_base_block(c)
        base.append((f"magnet-block-base-{i}", blk.translate(cq.Vector(b.x0, b.y0, b.z0))))
        b = lay.catch_lid_block(c)
        lid.append((f"magnet-block-lid-{i}", flipped.translate(cq.Vector(b.x0, b.y0, b.z0))))
    return base, lid


# --- parts and hardware -----------------------------------------------------------------

def printed_parts(lay: Layout, t: float = 3.0, bed=PRINT_BED) -> dict[str, PB.Printed]:
    """The laser route's printed parts, bed-checked (BedOverflow otherwise)."""
    rod = H.pin_length(lay)
    parts = {
        "knuckles-base": PB.Printed(knuckles_base(lay, t), PB.FLAT, (
            "Base knuckle block: print as it sits (flat bottom down), supports under the "
            "knuckle and the stop blocks. Glue it into the cut-out in the base's back and "
            "right walls, flush with both outside faces.")),
        "knuckles-lid": PB.Printed(knuckles_lid(lay, t), PB.FLIP, (
            "Lid knuckle block: print upside down (its top down), supports under the "
            "knuckles. Glue it into the cut-out in the lid's back and right walls, flush "
            "with both outside faces. Hinge: lid on the base, push the "
            f"{PIN_ROD_D:g} mm x {rod:.0f} mm rod in from the right side face until flush "
            "(the last 5 mm is a press fit).")),
        **{name: PB.Printed(s, PB.FLAT, (
            "Seal bead: print flat side down. Glue it along the base back wall's top edge, "
            "flush with the outside face; it closes the back under the lid's relief."))
           for name, s in seal_beads(lay).items()},
        "magnet-block": PB.Printed(magnet_block(), PB.FLAT, (
            f"Magnet block: print 4, pocket up. Press a {MAGNET_D:g} x {MAGNET_T:g} mm "
            "magnet into each, flush. Glue two in the base's front corners under the rim "
            "(pockets up) and two in the lid's front corners (pockets down), on the "
            "engraved outlines; pole them to pull.")),
    }
    for name, p in parts.items():
        PB.check_bed(name, PB.posed(p), bed)
    return parts


def hardware(lay: Layout, t: float = 3.0) -> dict[str, int]:
    """Bought hardware for the laser route (name -> count): the catch
    magnets, the hinge rod, the board pins' rod, glue and tape (R25: the
    boost module too when that is in the lid)."""
    tape = "double-sided foam tape (VHB type), monitor back"
    if lay.boost_in_lid:
        tape += " and boost module"
    return {
        f"{MAGNET_D:g} x {MAGNET_T:g} mm disc magnet": 2 * len(lay.lid_catch),
        f"{PIN_ROD_D:g} mm rod x {H.pin_length(lay):.0f} mm (hinge pin)": 1,
        f"{PEG_DIA:g} mm rod x {BOARD_PIN_LEN:g} mm (board pins, MT2 + loose MT1)": 2,
        "wood glue": 1,
        tape: 1,
    }


# --- assembly ------------------------------------------------------------------------

def _board_pin(lay: Layout, key: str) -> cq.Solid:
    p = lay.pins[key]
    return PB._zcyl(p.cx, p.cy, p.z1 - BOARD_PIN_LEN, p.z1, PEG_DIA / 2)


def assembly(angle_deg: float, bank_out: bool, monitor: str = ASSEMBLY_MONITOR,
             board: str = ASSEMBLY_BOARD, bank: str = ASSEMBLY_BANK,
             ) -> list[tuple[str, cq.Shape, tuple[float, float, float]]]:
    """The laser box in the base frame, ``(name, shape, colour)`` per solid,
    as ``printed.body.assembly``: the lid ``angle_deg`` open, the bank in its
    bay or (``bank_out``) lifted BANK_OUT_LIFT above the rim, ``monitor``,
    ``board`` and ``bank`` fitted in the box laid out for them.  Panels by
    name, the printed fittings, the bought parts as plain blocks, the rods and
    magnets as ``hw:``."""
    t = ROUTES["laser"]
    lay = layout(t, bank=bank, monitor=monitor)
    body = P.build(lay, t, P.KERF)
    loc = lay.lid_location(angle_deg)
    mag_base, mag_lid = _magnet_blocks(lay)

    bank_box = _bx(PB._packed(lay, bank))
    if bank_out:
        bank_box = bank_box.translate(
            cq.Vector(0, 0, lay.rim_z + PB.BANK_OUT_LIFT - lay.bank_bay.z0))
    base_items = [(n, p.solid()) for n, p in body.panels.items() if p.frame == "base"]
    base_items += [("knuckles-base", knuckles_base(lay, t)), *seal_beads(lay).items(),
                   *mag_base]
    base_items += [("board", PB.board_pcb(lay, board)),
                   ("tinyvga", _bx(lay.board_keepouts[f"{board}/tinyvga"])),
                   ("vga-plug", _bx(lay.board_keepouts[f"{board}/vga_plug"])),
                   ("bank", bank_box), ("hw:hinge-rod", PB._rod(lay)),
                   ("hw:board-pin-mt2", _board_pin(lay, "MT2")),
                   ("hw:board-pin-mt1", _board_pin(lay, f"{board}/MT1"))]
    base_items += [(f"hw:catch-magnet-base-{i}", PB._zcyl(c.cx, c.cy, c.z0, c.z1, MAGNET_D / 2))
                   for i, c in enumerate(lay.lid_catch, 1)]
    lid_items = [(n, p.solid()) for n, p in body.panels.items() if p.frame == "lid"]
    lid_items += [("knuckles-lid", knuckles_lid(lay, t)), *mag_lid,
                  ("monitor", PB._monitor_block(lay, monitor))]
    if lay.boost_in_lid:
        lid_items.append(("boost", PB._boost_block(lay)))
    lid_items += [(f"hw:catch-magnet-lid-{i}", PB._zcyl(m.cx, m.cy, m.z0, m.z1, MAGNET_D / 2))
                  for i, m in enumerate(map(lay.catch_lid_magnet, lay.lid_catch), 1)]

    def colour(n: str) -> tuple[float, float, float]:
        if n in body.panels:
            return COLOURS["panel"]
        if n.startswith(("knuckles-", "seal-bead", "magnet-block")):
            return COLOURS["fitting"]
        if n.startswith("hw:catch-magnet"):
            return COLOURS["magnet"]
        return COLOURS["hw"] if n.startswith("hw:") else COLOURS[n]

    out = [(n, s, colour(n)) for n, s in base_items]
    out += [(n, s.moved(loc), colour(n)) for n, s in lid_items]
    return out
