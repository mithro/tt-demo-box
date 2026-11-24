"""The 3D-printed route: a base and a lid, a loose pin, and the assembly.

No screws, nuts or inserts (spec Goal 3): the hinge knuckles are printed with
the two parts on one bought rod, the lid catch is four disc magnets pressed
into flush pockets, the board sits on printed pins, and the monitor (and, when
``boost_in_lid``, the boost module, R25) is taped to the lid's flat inside
face.  Frames are ``demobox.layout``'s: the base is built in the base frame,
the lid in the lid frame (closed); ``assembly`` places everything in the base
frame.

Base (``base``)
---------------
A tub: floor and four walls ``wall`` thick, up to ``rim_z``.  It has:

* the board's plinth (``Layout.plinth`` less ``plinth_relief``), its top the
  PCB underside.  It is solid (R27): the slicer's infill saves the
  filament, and an enclosed void would trap supports;
* the MT2 pin, printed with it (``pins["MT2"]``, PEG_DIA, PIN_CHAMFER on top);
* a PEG_HOLE_D hole at each revision's MT1 (``pins["<rev>/MT1"]``),
  ``pin.socket_depth`` deep (to the floor), for the loose ``mt1-pin``;
* the two catch blocks (``catch_base_block``) in the front corners, each
  with a 45 degree gusset under it to the front wall so it prints without
  support, and a magnet pocket MAGNET_POCKET_D across and
  MAGNET_POCKET_DEPTH deep, open at the rim: the magnet sits MAGNET_RECESS
  under the seam (flush);
* the hinge (``demobox.shared.hinge``): ``(body - knuckle_cut) | knuckles |
  seal_bead``, then the pigtail's ``hinge_notch`` cut out above the rim
  only (R26: the seal bead's notch; the back wall under it stays whole).

The bank bay, port room and the VGA plug's corner are plain floor (spec
non-goal: no shaped pockets).  If a kit's boost module sits on the floor
(``not boost_in_lid``), its ``boost_pocket`` is plain floor too.

Lid (``lid``)
-------------
A tray: the top plate ``wall`` thick and rim walls round it, down to the seam.
Its inside face is flat all over (no pocket: the monitor's back is taped to
it, R25 the boost module too).  It has the two catch blocks over the base's
(``catch_lid_block``, a 45 degree gusset up to the front wall) with their
magnet pockets open at the seam, the lid's knuckles less its knuckle cut, and
the notch.

Bed
---
``printed_parts`` gives each part with the turn that lays it on the bed
(``PRINT_POSE``): the base floor down, the lid top plate down, the pin
standing.  Both bodies fit the 220 x 220 bed whole; ``check_bed`` raises
``BedOverflow`` naming any part that does not.
"""

from __future__ import annotations

import cadquery as cq

import demobox  # noqa: F401  (puts the submodule on sys.path)
from demobox.geom import Box
from demobox.layout import (CATCH_BLOCK_H, MAGNET_D, MAGNET_T, PEG_DIA, PEG_HOLE_D, PIN_ROD_D,
                            PRINT_BED, ROUTES, Layout, layout)
from demobox.shared import hinge as H
from demobox.shared.pin import PIN_CHAMFER, locating_pin, socket_depth
from demobox.shared.solids import (  # noqa: F401  (re-exported: the route's public names)
    ASSEMBLY_BANK, ASSEMBLY_BOARD, ASSEMBLY_MONITOR, BANK_OUT_LIFT, COLOURS, FLAT, FLIP,
    MAGNET_POCKET_D, MAGNET_POCKET_DEPTH, Printed, bed_contact_area, board_pcb, boost_block,
    box as _box, bx as _bx, check_bed, cut as _cut, fuse as _fuse, hinge_rod, monitor_block,
    one as _one, packed_bank, posed, prism_x as _prism_x, zcyl as _zcyl)

# --- design choices ------------------------------------------------------------
#: The assembly's one declared overlap (``clash.clashes``): the rod in the
#: lid's last knuckle, whose last PRESS_LEN is a press fit (R24).  Every other
#: pair -- the rod in its slip bores, the magnets in their pockets, the board
#: on the plinth and pins, the loose pin in its hole -- only touches, and
#: must not interpenetrate.
DECLARED_OVERLAPS: frozenset[frozenset[str]] = frozenset({frozenset(("hw:hinge-rod", "lid"))})


_CACHE: dict[tuple[str, str], cq.Solid] = {}


def _cached(name: str, lay: Layout, build) -> cq.Solid:
    """``build()``, once per part and layout (R27: keyed on the whole
    layout, so another kit never gets the design kit's part)."""
    key = (name, repr(lay))
    if key not in _CACHE:
        _CACHE[key] = build()
    return _CACHE[key]


# --- the plinth ------------------------------------------------------------------------

def _mt2_pin(lay: Layout) -> cq.Solid:
    p = lay.pins["MT2"]
    return (cq.Workplane("XY", origin=(p.cx, p.cy, p.z0)).circle(PEG_DIA / 2)
            .extrude(p.z1 - p.z0).faces(">Z").edges().chamfer(PIN_CHAMFER).val())


def _mt1_holes(lay: Layout) -> list[cq.Solid]:
    """A PEG_HOLE_D hole at each revision's MT1, ``socket_depth`` deep."""
    return [_zcyl(p.cx, p.cy, p.z0 - socket_depth(lay), p.z0 + 1.0, PEG_HOLE_D / 2)
            for k, p in lay.pins.items() if k.endswith("/MT1")]


# --- the catch -------------------------------------------------------------------------

def _catch_block(b: Box, seam_z: float, into: float) -> cq.Solid:
    """A catch block ``b`` against the front wall (its y0 face), its seam
    face at ``seam_z``, standing ``into`` (-1 down from the base's rim, +1
    up from the lid's) CATCH_BLOCK_H, with a 45 degree gusset back to the
    wall a further CATCH_BLOCK."""
    y0, y1 = b.y0, b.y1
    z_end = seam_z + into * CATCH_BLOCK_H
    pts = [(y0, seam_z), (y1, seam_z), (y1, z_end), (y0, z_end + into * (y1 - y0))]
    return _prism_x(pts, b.x0, b.x1)


def _pocket(cx: float, cy: float, seam_z: float, into: float) -> cq.Solid:
    """A magnet pocket, open at the seam face ``seam_z``, going ``into``."""
    z_far = seam_z + into * MAGNET_POCKET_DEPTH
    z_out = seam_z - into * 1.0
    return _zcyl(cx, cy, min(z_far, z_out), max(z_far, z_out), MAGNET_POCKET_D / 2)


# --- the bodies --------------------------------------------------------------------------

def _base(lay: Layout) -> cq.Solid:
    o, w, rim = lay.outer, lay.wall, lay.rim_z
    pl = lay.plinth
    body = _cut(_bx(o), _box(w, w, w, o.x1 - w, o.y1 - w, rim + 1.0))
    body = _fuse(body, _bx(pl), _mt2_pin(lay),
                 *(_catch_block(lay.catch_base_block(c), rim, -1.0) for c in lay.lid_catch))
    body = _cut(body, H.knuckle_cut(lay, "base").val())
    body = _fuse(body, *H.knuckles(lay, "base").vals(), *H.seal_bead(lay).vals())
    # R26: the notch only above the rim, where the pigtail passes (the seal
    # bead's notch); the back wall under it stays whole
    n = lay.hinge_notch
    cuts = [_bx(lay.plinth_relief), *_mt1_holes(lay),
            _box(n.x0, n.y0, max(n.z0, rim), n.x1, n.y1, n.z1)]
    cuts += [_pocket(c.cx, c.cy, rim, -1.0) for c in lay.lid_catch]
    return _one(_cut(body, *cuts), "base")


def _lid(lay: Layout) -> cq.Solid:
    o, w = lay.lid_outer, lay.wall
    hy, hz = lay.hinge_axis
    body = _cut(_bx(o), _box(o.x0 + w, o.y0 + w, o.z0 - 1.0, o.x1 - w, o.y1 - w, o.z1 - w))
    body = _fuse(body, *(_catch_block(lay.catch_lid_block(c), 0.0, 1.0) for c in lay.lid_catch))
    body = _cut(body, H.knuckle_cut(lay, "lid").val())
    body = _fuse(body, *H.knuckles(lay, "lid").vals())
    cuts = [_bx(lay.hinge_notch.moved(0.0, -hy, -hz))]
    cuts += [_pocket(m.cx, m.cy, 0.0, 1.0) for m in map(lay.catch_lid_magnet, lay.lid_catch)]
    return _one(_cut(body, *cuts), "lid")


def base(lay: Layout) -> cq.Solid:
    """The base, base frame (see the module docstring)."""
    return _cached("base", lay, lambda: _base(lay))


def lid(lay: Layout) -> cq.Solid:
    """The lid, lid frame, closed (see the module docstring)."""
    return _cached("lid", lay, lambda: _lid(lay))


# --- print orientation and the bed ------------------------------------------------------

#: How each part lies on the bed: the base on its floor, the lid on its top
#: plate, the pin standing on its end.
PRINT_POSE: dict[str, tuple[tuple[float, float, float], float]] = {
    "base": FLAT, "lid": FLIP, "mt1-pin": FLAT,
}


def _printed(kind: str, solid: cq.Shape, note: str) -> Printed:
    return Printed(solid, PRINT_POSE[kind], note)


# --- the parts ------------------------------------------------------------------------

def printed_parts(lay: Layout, bed=PRINT_BED) -> dict[str, Printed]:
    """The printed parts, bed-checked: ``base``, ``lid`` and the loose
    ``mt1-pin``.  Raises BedOverflow naming a part that does not fit."""
    rod = H.pin_length(lay)
    parts = {
        "base": _printed("base", base(lay), (
            "Base: print floor down, normal infill (the plinth is solid; infill keeps it "
            "light). Supports under the hinge knuckle only (the catch "
            "blocks' gussets, the stop blocks and the seal bead's lip print without). Press two "
            f"{MAGNET_D:g} x {MAGNET_T:g} mm magnets into the front-corner pockets, flush, "
            "glued if loose; pole them to pull the lid's.")),
        "lid": _printed("lid", lid(lay), (
            "Lid: print top plate down. Supports under the hinge knuckles only. Press two "
            f"{MAGNET_D:g} x {MAGNET_T:g} mm magnets into the catch pockets, flush. Hinge: "
            f"lid on the base, push the {PIN_ROD_D:g} mm x {rod:.1f} mm rod in from the right "
            "side face until flush (the last 5 mm is a press fit). Tape the monitor's back "
            "to the flat inside face"
            + (", and the boost module beside it in the cable strip." if lay.boost_in_lid
               else "."))),
        "mt1-pin": _printed("mt1-pin", locating_pin(lay).val(), (
            "MT1 locating pin: print standing; print spares, it is loose. It goes in the "
            "plinth hole under the fitted board's MT1.")),
    }
    for name, p in parts.items():
        check_bed(name, posed(p), bed)
    return parts


def hardware(lay: Layout) -> dict[str, int]:
    """Bought hardware for the printed route (name -> count): the catch
    magnets, the hinge rod and the tape (R25: it holds the boost module too
    when that is in the lid)."""
    tape = "double-sided foam tape (VHB type), monitor back"
    if lay.boost_in_lid:
        tape += " and boost module"
    return {
        f"{MAGNET_D:g} x {MAGNET_T:g} mm disc magnet": 2 * len(lay.lid_catch),
        f"{PIN_ROD_D:g} mm rod x {H.pin_length(lay):.1f} mm (hinge pin; steel, or 2.85 mm "
        "filament)": 1,
        tape: 1,
    }


# --- assembly ------------------------------------------------------------------------

def assembly(route: str, angle_deg: float, bank_out: bool, monitor: str = ASSEMBLY_MONITOR,
             board: str = ASSEMBLY_BOARD, bank: str = ASSEMBLY_BANK,
             ) -> list[tuple[str, cq.Shape, tuple[float, float, float]]]:
    """The box in the base frame, ``(name, shape, colour)`` per solid: the
    lid ``angle_deg`` open, the bank in its bay or (``bank_out``) lifted
    BANK_OUT_LIFT above the rim, with ``monitor``, ``board`` and ``bank``
    fitted, in the box laid out for that ``monitor`` and ``bank`` (R27).
    Bought parts are plain blocks: the board's PCB, its TinyVGA (with the
    adapter) and the VGA plug, the monitor panel, the boost module (when in
    the lid), the bank; the magnets and the rod are ``hw:``.  The one entry
    point for both routes: ``"laser"`` is ``demobox.laser.fittings``'."""
    if route == "laser":
        from demobox.laser.fittings import assembly as laser_assembly
        return laser_assembly(angle_deg, bank_out, monitor=monitor, board=board, bank=bank)
    if route != "printed":
        raise ValueError(f"unknown route {route!r}; routes are {sorted(ROUTES)}")
    lay = layout(ROUTES[route], bank=bank, monitor=monitor)
    loc = lay.lid_location(angle_deg)

    bank_box = _bx(packed_bank(lay))
    if bank_out:
        bank_box = bank_box.translate(cq.Vector(0, 0, lay.rim_z + BANK_OUT_LIFT - lay.bank_bay.z0))
    mt1 = lay.pins[f"{board}/MT1"]
    pin = locating_pin(lay).val().translate(cq.Vector(mt1.cx, mt1.cy, mt1.z0 - socket_depth(lay)))
    base_items = [("base", base(lay)), ("mt1-pin", pin), ("board", board_pcb(lay, board)),
                  ("tinyvga", _bx(lay.board_keepouts[f"{board}/tinyvga"])),
                  ("vga-plug", _bx(lay.board_keepouts[f"{board}/vga_plug"])),
                  ("bank", bank_box), ("hw:hinge-rod", hinge_rod(lay))]
    base_items += [(f"hw:catch-magnet-base-{i}", _zcyl(c.cx, c.cy, c.z0, c.z1, MAGNET_D / 2))
                   for i, c in enumerate(lay.lid_catch, 1)]
    lid_items = [("lid", lid(lay)), ("monitor", monitor_block(lay))]
    if lay.boost_in_lid:
        lid_items.append(("boost", boost_block(lay)))
    lid_items += [(f"hw:catch-magnet-lid-{i}", _zcyl(m.cx, m.cy, m.z0, m.z1, MAGNET_D / 2))
                  for i, m in enumerate(map(lay.catch_lid_magnet, lay.lid_catch), 1)]

    def colour(n: str) -> tuple[float, float, float]:
        if n.startswith("hw:catch-magnet"):
            return COLOURS["magnet"]
        return COLOURS["hw"] if n.startswith("hw:") else COLOURS[n]

    out = [(n, s, colour(n)) for n, s in base_items]
    out += [(n, s.moved(loc), colour(n)) for n, s in lid_items]
    return out
