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

from dataclasses import dataclass

import cadquery as cq

import demobox  # noqa: F401  (puts the submodule on sys.path)
from demobox.geom import BedOverflow, Box
from demobox.layout import (CATCH_BLOCK_H, DESIGN_BANK, DESIGN_MONITOR, MAGNET_D,
                            MAGNET_RECESS, MAGNET_T, PEG_DIA, PEG_HOLE_D, PIN_ROD_D,
                            PRINT_BED, ROUTES, SLACK, TAPE_T, Layout, layout)
from demobox.parts.batteries import BATTERIES
from demobox.parts.board import board_spec
from demobox.parts.cables import CABLES
from demobox.parts.monitors import MONITORS
from demobox.shared import hinge as H
from demobox.shared.pin import PIN_CHAMFER, locating_pin, socket_depth

# --- design choices ------------------------------------------------------------
#: A catch magnet's pocket: a slip fit across, deep enough to leave the
#: magnet MAGNET_RECESS under the seam face.
MAGNET_POCKET_D = MAGNET_D + 0.2
MAGNET_POCKET_DEPTH = MAGNET_T + MAGNET_RECESS
#: ``assembly(..., bank_out=True)``: the bank lifted this far above the rim.
BANK_OUT_LIFT = 60.0

#: The assembly's default monitor, bank and board revision.
ASSEMBLY_MONITOR = DESIGN_MONITOR
ASSEMBLY_BANK = DESIGN_BANK
ASSEMBLY_BOARD = "v3.3"

COLOURS: dict[str, tuple[float, float, float]] = {
    "base": (0.22, 0.24, 0.28), "lid": (0.22, 0.24, 0.28), "mt1-pin": (0.95, 0.85, 0.20),
    "board": (0.05, 0.40, 0.15), "tinyvga": (0.05, 0.30, 0.45), "vga-plug": (0.10, 0.10, 0.12),
    "monitor": (0.02, 0.02, 0.05), "boost": (0.15, 0.15, 0.15), "bank": (0.85, 0.85, 0.85),
    "magnet": (0.55, 0.55, 0.60), "hw": (0.75, 0.75, 0.78),
}

#: The assembly's one declared overlap (``clash.clashes``): the rod in the
#: lid's last knuckle, whose last PRESS_LEN is a press fit (R24).  Every other
#: pair -- the rod in its slip bores, the magnets in their pockets, the board
#: on the plinth and pins, the loose pin in its hole -- only touches, and
#: must not interpenetrate.
DECLARED_OVERLAPS: frozenset[frozenset[str]] = frozenset({frozenset(("hw:hinge-rod", "lid"))})


@dataclass(frozen=True)
class Printed:
    """A printed part in its design frame, the turn (axis, degrees about the
    origin) that lays it on the bed, and a print note."""

    solid: cq.Shape
    print_orientation: tuple[tuple[float, float, float], float]
    note: str


# --- small solids --------------------------------------------------------------------

def _box(x0, y0, z0, x1, y1, z1) -> cq.Solid:
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def _bx(b: Box) -> cq.Solid:
    return _box(b.x0, b.y0, b.z0, b.x1, b.y1, b.z1)


def _zcyl(cx, cy, z0, z1, r) -> cq.Solid:
    return cq.Solid.makeCylinder(r, z1 - z0, cq.Vector(cx, cy, z0), cq.Vector(0, 0, 1))


def _prism_x(pts, x0, x1) -> cq.Solid:
    """A (y, z) polygon extruded along X from x0 to x1."""
    return cq.Workplane("YZ", origin=(x0, 0, 0)).polyline(pts).close().extrude(x1 - x0).val()


def _fuse(a: cq.Shape, *others: cq.Shape) -> cq.Shape:
    return a.fuse(*others).clean() if others else a


def _cut(a: cq.Shape, *others: cq.Shape) -> cq.Shape:
    return a.cut(*others).clean() if others else a


def _one(shape: cq.Shape, what: str) -> cq.Solid:
    solids = shape.Solids()
    if len(solids) != 1:
        raise ValueError(f"{what}: {len(solids)} solids, expected one")
    return solids[0]


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

#: Turns (axis, degrees) about the origin.
FLAT = ((1.0, 0.0, 0.0), 0.0)
FLIP = ((1.0, 0.0, 0.0), 180.0)
#: How each part lies on the bed: the base on its floor, the lid on its top
#: plate, the pin standing on its end.
PRINT_POSE: dict[str, tuple[tuple[float, float, float], float]] = {
    "base": FLAT, "lid": FLIP, "mt1-pin": FLAT,
}


def _turned(shape: cq.Shape, turn) -> cq.Shape:
    axis, angle = turn
    if angle == 0.0:
        return shape
    return shape.rotate(cq.Vector(0, 0, 0), cq.Vector(*axis), angle)


def bed_contact_area(shape: cq.Shape) -> float:
    """Area of the planar faces lying on the shape's lowest Z plane."""
    z = shape.BoundingBox().zmin
    area = 0.0
    for f in shape.Faces():
        if f.geomType() != "PLANE":
            continue
        bb = f.BoundingBox()
        if abs(bb.zmin - z) < 1e-6 and abs(bb.zmax - z) < 1e-6:
            area += f.Area()
    return area


def posed(p: Printed) -> cq.Shape:
    """The part turned onto the bed, its bounding box's corner at the origin."""
    s = _turned(p.solid, p.print_orientation)
    bb = s.BoundingBox()
    return s.translate(cq.Vector(-bb.xmin, -bb.ymin, -bb.zmin))


def _footprint(shape: cq.Shape) -> tuple[float, float]:
    bb = shape.BoundingBox()
    return bb.xlen, bb.ylen


def check_bed(name: str, shape: cq.Shape, bed=PRINT_BED) -> None:
    """Raise BedOverflow when ``shape`` (posed) is bigger than the bed."""
    x, y = _footprint(shape)
    if x > bed[0] + 1e-6 or y > bed[1] + 1e-6:
        raise BedOverflow(f"{name} {x:.2f} x {y:.2f} mm does not fit the {bed[0]:g} x "
                          f"{bed[1]:g} mm print bed")


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
            f"lid on the base, push the {PIN_ROD_D:g} mm x {rod:.0f} mm rod in from the right "
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
        f"{PIN_ROD_D:g} mm rod x {H.pin_length(lay):.0f} mm (hinge pin; steel, or 2.85 mm "
        "filament)": 1,
        tape: 1,
    }


# --- assembly ------------------------------------------------------------------------

def board_pcb(lay: Layout, key: str) -> cq.Shape:
    """Board ``key``'s PCB with its holes, base frame (``layout``'s board
    placement: base = (ox - by, oy + bx, oz + bz))."""
    ol = board_spec(key).outline
    ox, oy, oz = lay.board_origin
    pcb = _box(ox - ol.height, oy, oz, ox, oy + ol.width, oz + ol.thickness)
    return _cut(pcb, *(_zcyl(ox - h.y, oy + h.x, oz - 1.0, oz + ol.thickness + 1.0, h.dia / 2)
                       for h in board_spec(key).holes))


def _monitor_block(lay: Layout, monitor: str) -> cq.Solid:
    """The monitor's panel taped to the lid, lid frame: centred in X on the
    monitor space, SLACK in from its front edge, its back TAPE_T under the
    inside face."""
    mw, mh, md = MONITORS[monitor].panel
    ms = lay.monitor_space
    cx, y0 = (ms.x0 + ms.x1) / 2, ms.y0 + SLACK
    top = lay.lid_outer.z1 - lay.wall - TAPE_T
    return _box(cx - mw / 2, y0, top - md, cx + mw / 2, y0 + mh, top)


def _boost_block(lay: Layout) -> cq.Solid:
    """The boost module taped in the lid strip (R25), lid frame: its room
    less SLACK round it, its back TAPE_T under the inside face."""
    b = lay.boost_pocket
    top = lay.lid_outer.z1 - lay.wall - TAPE_T
    return _box(b.x0 + SLACK, b.y0 + SLACK, top - CABLES["usb-12v-boost"].plug[2],
                b.x1 - SLACK, b.y1 - SLACK, top)


def _rod(lay: Layout) -> cq.Solid:
    hy, hz = lay.hinge_axis
    length = H.pin_length(lay)
    return cq.Solid.makeCylinder(PIN_ROD_D / 2, length, cq.Vector(lay.outer.x1 - length, hy, hz),
                                 cq.Vector(1, 0, 0))


def _packed(lay: Layout, bank: str) -> Box:
    """Bank ``bank`` on the bay floor, centred in the bay (as
    ``checks.packed_bank`` packs the design bank), base frame."""
    l_, w, h = BATTERIES[bank].size
    bay = lay.bank_bay
    x0, y0 = (bay.x0 + bay.x1 - l_) / 2, (bay.y0 + bay.y1 - w) / 2
    return Box(x0, y0, bay.z0, x0 + l_, y0 + w, bay.z0 + h, f"bank {bank}")


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

    bank_box = _bx(_packed(lay, bank))
    if bank_out:
        bank_box = bank_box.translate(cq.Vector(0, 0, lay.rim_z + BANK_OUT_LIFT - lay.bank_bay.z0))
    mt1 = lay.pins[f"{board}/MT1"]
    pin = locating_pin(lay).val().translate(cq.Vector(mt1.cx, mt1.cy, mt1.z0 - socket_depth(lay)))
    base_items = [("base", base(lay)), ("mt1-pin", pin), ("board", board_pcb(lay, board)),
                  ("tinyvga", _bx(lay.board_keepouts[f"{board}/tinyvga"])),
                  ("vga-plug", _bx(lay.board_keepouts[f"{board}/vga_plug"])),
                  ("bank", bank_box), ("hw:hinge-rod", _rod(lay))]
    base_items += [(f"hw:catch-magnet-base-{i}", _zcyl(c.cx, c.cy, c.z0, c.z1, MAGNET_D / 2))
                   for i, c in enumerate(lay.lid_catch, 1)]
    lid_items = [("lid", lid(lay)), ("monitor", _monitor_block(lay, monitor))]
    if lay.boost_in_lid:
        lid_items.append(("boost", _boost_block(lay)))
    lid_items += [(f"hw:catch-magnet-lid-{i}", _zcyl(m.cx, m.cy, m.z0, m.z1, MAGNET_D / 2))
                  for i, m in enumerate(map(lay.catch_lid_magnet, lay.lid_catch), 1)]

    def colour(n: str) -> tuple[float, float, float]:
        if n.startswith("hw:catch-magnet"):
            return COLOURS["magnet"]
        return COLOURS["hw"] if n.startswith("hw:") else COLOURS[n]

    out = [(n, s, colour(n)) for n, s in base_items]
    out += [(n, s.moved(loc), colour(n)) for n, s in lid_items]
    return out
