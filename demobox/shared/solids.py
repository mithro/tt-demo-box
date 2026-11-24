"""Solids and records both build routes use (R30: no private cross-route
imports).

* small CadQuery solids from layout numbers: ``box``, ``bx`` (a ``Box``),
  ``zcyl``, ``prism_x``, and ``fuse`` / ``cut`` / ``one``;
* the printed-part record ``Printed``, its bed turns (``FLAT``, ``FLIP``),
  ``posed``, ``bed_contact_area`` and ``check_bed``;
* the catch magnet's pocket (``MAGNET_POCKET_D``, ``MAGNET_POCKET_DEPTH``);
* the assemblies' bought parts as plain blocks, base or lid frame as noted:
  ``board_pcb``, ``monitor_block``, ``boost_block``, ``hinge_rod``,
  ``packed_bank`` (and ``BANK_OUT_LIFT``), with the assemblies' defaults
  and colours.

Frames are ``demobox.layout``'s.
"""

from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq

import demobox  # noqa: F401  (puts the submodule on sys.path)
from demobox.geom import BedOverflow, Box
from demobox.layout import (DESIGN_BANK, DESIGN_MONITOR, MAGNET_D, MAGNET_RECESS, MAGNET_T,
                            PIN_ROD_D, PRINT_BED, SLACK, TAPE_T, Layout)
from demobox.parts.batteries import BATTERIES
from demobox.parts.board import board_spec
from demobox.parts.cables import CABLES
from demobox.parts.monitors import MONITORS
from demobox.shared import hinge as H

#: A catch magnet's pocket: a slip fit across, deep enough to leave the
#: magnet MAGNET_RECESS under the seam face.
MAGNET_POCKET_D = MAGNET_D + 0.2
MAGNET_POCKET_DEPTH = MAGNET_T + MAGNET_RECESS
#: ``assembly(..., bank_out=True)``: the bank lifted this far above the rim.
BANK_OUT_LIFT = 60.0

#: The assemblies' default monitor, bank and board revision.
ASSEMBLY_MONITOR = DESIGN_MONITOR
ASSEMBLY_BANK = DESIGN_BANK
ASSEMBLY_BOARD = "v3.3"

COLOURS: dict[str, tuple[float, float, float]] = {
    "base": (0.22, 0.24, 0.28), "lid": (0.22, 0.24, 0.28), "mt1-pin": (0.95, 0.85, 0.20),
    "board": (0.05, 0.40, 0.15), "tinyvga": (0.05, 0.30, 0.45), "vga-plug": (0.10, 0.10, 0.12),
    "monitor": (0.02, 0.02, 0.05), "boost": (0.15, 0.15, 0.15), "bank": (0.85, 0.85, 0.85),
    "magnet": (0.55, 0.55, 0.60), "hw": (0.75, 0.75, 0.78),
    "panel": (0.82, 0.66, 0.44), "fitting": (0.30, 0.32, 0.36),
}


# --- small solids --------------------------------------------------------------------

def box(x0, y0, z0, x1, y1, z1) -> cq.Solid:
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def bx(b: Box) -> cq.Solid:
    return box(b.x0, b.y0, b.z0, b.x1, b.y1, b.z1)


def zcyl(cx, cy, z0, z1, r) -> cq.Solid:
    return cq.Solid.makeCylinder(r, z1 - z0, cq.Vector(cx, cy, z0), cq.Vector(0, 0, 1))


def prism_x(pts, x0, x1) -> cq.Solid:
    """A (y, z) polygon extruded along X from x0 to x1."""
    return cq.Workplane("YZ", origin=(x0, 0, 0)).polyline(pts).close().extrude(x1 - x0).val()


def fuse(a: cq.Shape, *others: cq.Shape) -> cq.Shape:
    return a.fuse(*others).clean() if others else a


def cut(a: cq.Shape, *others: cq.Shape) -> cq.Shape:
    return a.cut(*others).clean() if others else a


def one(shape: cq.Shape, what: str) -> cq.Solid:
    solids = shape.Solids()
    if len(solids) != 1:
        raise ValueError(f"{what}: {len(solids)} solids, expected one")
    return solids[0]


# --- printed parts and the bed -----------------------------------------------------------

@dataclass(frozen=True)
class Printed:
    """A printed part in its design frame, the turn (axis, degrees about the
    origin) that lays it on the bed, and a print note."""

    solid: cq.Shape
    print_orientation: tuple[tuple[float, float, float], float]
    note: str


#: Turns (axis, degrees) about the origin.
FLAT = ((1.0, 0.0, 0.0), 0.0)
FLIP = ((1.0, 0.0, 0.0), 180.0)


def turned(shape: cq.Shape, turn) -> cq.Shape:
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
    s = turned(p.solid, p.print_orientation)
    bb = s.BoundingBox()
    return s.translate(cq.Vector(-bb.xmin, -bb.ymin, -bb.zmin))


def check_bed(name: str, shape: cq.Shape, bed=PRINT_BED) -> None:
    """Raise BedOverflow when ``shape`` (posed) is bigger than the bed."""
    bb = shape.BoundingBox()
    x, y = bb.xlen, bb.ylen
    if x > bed[0] + 1e-6 or y > bed[1] + 1e-6:
        raise BedOverflow(f"{name} {x:.2f} x {y:.2f} mm does not fit the {bed[0]:g} x "
                          f"{bed[1]:g} mm print bed")


# --- the assemblies' bought parts ------------------------------------------------------------

def board_pcb(lay: Layout, key: str) -> cq.Shape:
    """Board ``key``'s PCB with its holes, base frame (``layout``'s board
    placement: base = (ox - by, oy + bx, oz + bz))."""
    ol = board_spec(key).outline
    ox, oy, oz = lay.board_origin
    pcb = box(ox - ol.height, oy, oz, ox, oy + ol.width, oz + ol.thickness)
    return cut(pcb, *(zcyl(ox - h.y, oy + h.x, oz - 1.0, oz + ol.thickness + 1.0, h.dia / 2)
                      for h in board_spec(key).holes))


def monitor_block(lay: Layout) -> cq.Solid:
    """The layout's monitor's panel taped to the lid, lid frame: centred in X
    on the monitor space, SLACK in from its front edge, its back TAPE_T under
    the inside face."""
    mw, mh, md = MONITORS[lay.monitor].panel
    ms = lay.monitor_space
    cx, y0 = (ms.x0 + ms.x1) / 2, ms.y0 + SLACK
    top = lay.lid_outer.z1 - lay.wall - TAPE_T
    return box(cx - mw / 2, y0, top - md, cx + mw / 2, y0 + mh, top)


def boost_block(lay: Layout) -> cq.Solid:
    """The boost module taped in the lid strip (R25), lid frame: its room
    less SLACK round it, its back TAPE_T under the inside face."""
    b = lay.boost_pocket
    top = lay.lid_outer.z1 - lay.wall - TAPE_T
    return box(b.x0 + SLACK, b.y0 + SLACK, top - CABLES["usb-12v-boost"].plug[2],
               b.x1 - SLACK, b.y1 - SLACK, top)


def hinge_rod(lay: Layout) -> cq.Solid:
    """The hinge rod (R22, R24), base frame: ``hinge.pin_length`` back from
    the +X side face, on the axis."""
    hy, hz = lay.hinge_axis
    length = H.pin_length(lay)
    return cq.Solid.makeCylinder(PIN_ROD_D / 2, length, cq.Vector(lay.outer.x1 - length, hy, hz),
                                 cq.Vector(1, 0, 0))


def packed_bank(lay: Layout) -> Box:
    """The layout's bank on the bay floor, centred in the bay (as
    ``checks.packed_bank`` packs it), base frame."""
    bank = lay.bank
    l_, w, h = BATTERIES[bank].size
    bay = lay.bank_bay
    x0, y0 = (bay.x0 + bay.x1 - l_) / 2, (bay.y0 + bay.y1 - w) / 2
    return Box(x0, y0, bay.z0, x0 + l_, y0 + w, bay.z0 + h, f"bank {bank}")
