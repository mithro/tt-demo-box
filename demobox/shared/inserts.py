"""Monitor inserts: the front bezel plate and the rear retainer.

Both are built in the lid frame, closed (``demobox.layout``), where the
monitor sits as ``checks.panel_in_lid`` puts it: screen facing -Z, the bezel
plate filling Z 0 .. INSERT_MATERIAL, the panel's front face on the bezel's
back, its bottom (button) edge towards the hinge end.  The insert stack is
``layout.insert_stack(m)`` deep.

Bezel
-----
One frame plate over the lid's whole inside opening: the pocket and every
cable gutter (they are open on the screen side like the pocket), FIT inside
the opening all round so it drops in.  It has the window
``checks.monitor_window(m)`` (R4) and, where the window does not expose the
front button, the cut-out ``checks.button_cutout(m)``; nothing else of the
pocket or the gutters shows, so cables do not show round the picture.

Retainer
--------
A back plate the pocket's outline less FIT, at the back of the stack, and
INSERT_MATERIAL walls round the panel's edges from the bezel to the plate that
locate the panel.  Along the edge the cables leave by (``layout.exit_edge``)
the wall is cut away but for EXIT_TAB at each corner, so the cable is free to
leave into its gutter.  The plate covers the pocket only, not the gutters,
so the cables run past it.  For a bare kit the plate also carries four posts
that hold the driver board DRIVER_STANDOFF behind the panel's back: each post
runs from the plate to the board and takes an M3 heat-set insert in its tip,
the board screwed on from the panel side (the screw heads sit in the
DRIVER_STANDOFF gap).
"""

from __future__ import annotations

import cadquery as cq
from tools.schema import Source

from demobox.checks import MIN_BOSS_WALL, button_cutout, monitor_window, panel_in_lid
from demobox.geom import Box, Cyl
from demobox.layout import (DRIVER_STANDOFF, FIT, HEATSET_DEPTH, HEATSET_HOLE_D,
                            INSERT_MATERIAL, Layout, exit_edge, insert_stack)
from demobox.parts.monitors import Monitor

#: Wall left at each end of the cable-exit edge to locate the panel there.
EXIT_TAB = 15.0
#: Plastic round a driver post's heat-set insert.
POST_WALL = 1.5
#: Driver board mounting holes: inset from each corner of the board.
DRIVER_HOLE_INSET = 3.5

#: (name, value, source) for verify.py to report as UNCONFIRMED.
UNCONFIRMED: tuple[tuple[str, float, Source], ...] = (
    ("DRIVER_HOLE_INSET", DRIVER_HOLE_INSET, Source(
        "Placeholder: driver board mounting holes", "demobox/shared/inserts.py",
        "PCB800099 holes assumed M3, 3.5 mm in from each corner; measure a real board.")),
)

if POST_WALL < MIN_BOSS_WALL:
    raise ValueError(f"POST_WALL {POST_WALL} < MIN_BOSS_WALL {MIN_BOSS_WALL}")


def _solid(x0, y0, z0, x1, y1, z1) -> cq.Workplane:
    return cq.Workplane("XY").add(
        cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0)))


def _panel_rect(m: Monitor, lay: Layout, rect) -> tuple[float, float, float, float]:
    """A (w, h, x, y) rect in the panel's front frame (lower-left origin) ->
    (x0, y0, x1, y1) in the closed lid frame."""
    w, h, x, y = rect
    pb = panel_in_lid(m, lay)
    return pb.x0 + x, pb.y1 - y - h, pb.x0 + x + w, pb.y1 - y


def lid_opening(lay: Layout) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) of the lid's inside opening: pocket plus gutters."""
    boxes = [lay.lid_pocket, *lay.lid_cable_gutters.values()]
    return (min(b.x0 for b in boxes), min(b.y0 for b in boxes),
            max(b.x1 for b in boxes), max(b.y1 for b in boxes))


def monitor_bezel(m: Monitor, lay: Layout) -> cq.Workplane:
    """The front bezel plate for monitor ``m`` (closed lid frame)."""
    x0, y0, x1, y1 = lid_opening(lay)
    t = INSERT_MATERIAL
    plate = _solid(x0 + FIT, y0 + FIT, 0.0, x1 - FIT, y1 - FIT, t)
    holes = [monitor_window(m)]
    cut = button_cutout(m)
    if cut is not None:
        holes.append(cut)
    for rect in holes:
        hx0, hy0, hx1, hy1 = _panel_rect(m, lay, rect)
        plate = plate.cut(_solid(hx0, hy0, -1.0, hx1, hy1, t + 1.0))
    return plate


def driver_posts(m: Monitor, lay: Layout) -> tuple[Cyl, ...]:
    """The kit's driver-board posts (closed lid frame), from the board's
    panel-side face to the retainer plate; () for a cased monitor."""
    if m.driver is None:
        return ()
    d, W = m.driver, m.panel[0]
    pb = panel_in_lid(m, lay)
    z0 = pb.z1 + DRIVER_STANDOFF
    z1 = insert_stack(m) - INSERT_MATERIAL
    r = HEATSET_HOLE_D / 2 + POST_WALL
    i = DRIVER_HOLE_INSET
    posts = []
    for bx in (d.x0 + i, d.x1 - i):          # driver: the panel's back frame
        for by in (d.y0 + i, d.y1 - i):
            u, v = W - bx, by                  # back frame -> front frame
            posts.append(Cyl(pb.x0 + u, pb.y1 - v, z0, z1, r, f"{m.key} driver post"))
    return tuple(posts)


def _exit_slot(m: Monitor, pb: Box, z0: float, z1: float) -> cq.Workplane:
    """The cut-away along the cable-exit edge's wall, between the corner tabs."""
    t = INSERT_MATERIAL + 1.0
    edge = exit_edge(m)
    if edge in ("bottom", "top"):
        if pb.size[0] <= 2 * EXIT_TAB:
            raise ValueError(f"{m.key}: {pb.size[0]} mm edge too short for the exit tabs")
        y0, y1 = (pb.y1, pb.y1 + t) if edge == "bottom" else (pb.y0 - t, pb.y0)
        return _solid(pb.x0 + EXIT_TAB, y0, z0, pb.x1 - EXIT_TAB, y1, z1)
    if pb.size[1] <= 2 * EXIT_TAB:
        raise ValueError(f"{m.key}: {pb.size[1]} mm edge too short for the exit tabs")
    x0, x1 = (pb.x1, pb.x1 + t) if edge == "right" else (pb.x0 - t, pb.x0)
    return _solid(x0, pb.y0 + EXIT_TAB, z0, x1, pb.y1 - EXIT_TAB, z1)


def monitor_retainer(m: Monitor, lay: Layout) -> cq.Workplane:
    """The rear retainer for monitor ``m`` (closed lid frame)."""
    p = lay.lid_pocket
    pb = panel_in_lid(m, lay)
    t = INSERT_MATERIAL
    stack = insert_stack(m)
    if stack > p.z1 - FIT:
        raise ValueError(f"{m.key}: insert stack {stack} mm deeper than the pocket")
    ox0, oy0, ox1, oy1 = p.x0 + FIT, p.y0 + FIT, p.x1 - FIT, p.y1 - FIT
    part = _solid(ox0, oy0, stack - t, ox1, oy1, stack)

    ring = _solid(max(pb.x0 - t, ox0), max(pb.y0 - t, oy0), t,
                  min(pb.x1 + t, ox1), min(pb.y1 + t, oy1), stack)
    ring = ring.cut(_solid(pb.x0, pb.y0, t - 1.0, pb.x1, pb.y1, stack - t))
    ring = ring.cut(_exit_slot(m, pb, t - 1.0, stack - t))
    part = part.union(ring)

    for c in driver_posts(m, lay):
        post = (cq.Workplane("XY", origin=(c.cx, c.cy, c.z0)).circle(c.r)
                .extrude(c.z1 - c.z0 + t / 2))
        part = part.union(post)
        hole = (cq.Workplane("XY", origin=(c.cx, c.cy, c.z0 - 1.0))
                .circle(HEATSET_HOLE_D / 2).extrude(HEATSET_DEPTH + 1.0))
        part = part.cut(hole)
    return part
