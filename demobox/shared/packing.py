"""Battery packing: the U that holds one power bank in the drawer's bay.

Built in the base frame with the drawer shut, in ``Layout.bay``.  The bank
lies L along X with its port end on the bay's -X end (the cable-bay
boundary), centred across the bay in Y, on the bay floor.  The packing is one
U, as tall as the bank: an end-stop across the bay's +X end, FIT off the bank's
far end, so end-stop + bank = bay length - FIT; and two side arms from the
end-stop to the bay's -X end, FIT off the bank's sides.  The bank's key
(``Battery.key``, its model) is engraved ENGRAVE_DEPTH into the end-stop's
top, reading along Y, so the packing for each bank is told apart.
"""

from __future__ import annotations

import cadquery as cq

from demobox.layout import FIT, Layout
from demobox.parts.batteries import Battery

ENGRAVE_DEPTH = 0.6
#: Largest engraving letter height, and the margin kept round the text.
ENGRAVE_SIZE = 6.0
ENGRAVE_MARGIN = 2.0


def _solid(x0, y0, z0, x1, y1, z1) -> cq.Workplane:
    return cq.Workplane("XY").add(
        cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0)))


def engraving(b: Battery) -> str:
    """The text engraved on the bank's packing: its model key."""
    return b.key


def battery_packing(b: Battery, lay: Layout) -> cq.Workplane:
    bay = lay.bay
    L_, W_, H_ = b.size
    bl, bw, bh = bay.size
    if L_ + FIT > bl or W_ + 2 * FIT > bw or H_ > bh:
        raise ValueError(f"{b.key} {b.size} does not fit the bay {bay.size}")
    cy = (bay.y0 + bay.y1) / 2
    top = bay.z0 + H_
    stop_x0 = bay.x0 + L_ + FIT
    part = _solid(bay.x0, bay.y0, bay.z0, bay.x1, bay.y1, top)
    part = part.cut(_solid(bay.x0 - 1.0, cy - W_ / 2 - FIT, bay.z0 - 1.0,
                           stop_x0, cy + W_ / 2 + FIT, top + 1.0))

    text = engraving(b)
    size = min(ENGRAVE_SIZE, bay.x1 - stop_x0 - 2 * ENGRAVE_MARGIN)
    plane = cq.Plane(origin=((stop_x0 + bay.x1) / 2, cy, top), xDir=(0, 1, 0),
                     normal=(0, 0, 1))
    cut = cq.Workplane(plane).text(text, size, -ENGRAVE_DEPTH, combine=False)
    tb = cut.val().BoundingBox()
    if (tb.xmin < stop_x0 + ENGRAVE_MARGIN or tb.xmax > bay.x1 - ENGRAVE_MARGIN
            or tb.ymin < bay.y0 + ENGRAVE_MARGIN or tb.ymax > bay.y1 - ENGRAVE_MARGIN):
        raise ValueError(f"engraving {text!r} overflows {b.key}'s end-stop")
    return part.cut(cut)
