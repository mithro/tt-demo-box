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

It is screwed to the lid (R15) at ``bezel_screws(lay)``: an M3 clearance
hole at each corner of the opening that lies in a cable gutter, where the lid
has room for a boss; a corner of the pocket itself is skipped, since the
panel and its retainer fill the pocket to within FIT.  The lid bodies put the
boss (heat-set insert, or captured nut) under each hole.

Retainer
--------
A back plate the pocket's outline less FIT, at the back of the stack, and
INSERT_MATERIAL walls round the panel's edges from the bezel to the plate that
locate the panel.  Along the edge the cables leave by (``layout.exit_edge``)
the wall is cut away but for EXIT_TAB at each corner, so the cable is free to
leave into its gutter.  The plate covers the pocket only, not the gutters,
so the cables run past it.

A bare kit's driver board (``Monitor.driver``) has its PCB on the panel side,
``driver_pcb_t`` thick, its parts standing rearward.  The retainer carries
it on four posts, one under each mounting hole (``Monitor.driver_holes``), in
the DRIVER_STANDOFF gap between the panel's back and the PCB: each post runs
from the panel's back to the PCB's panel-side face and nothing of the
retainer enters the board's envelope.  Two carrier bars on the panel's back,
CARRIER_T thick, tie each pair of posts to the side walls.  An M3 screw
(``driver_screw_length``) goes up from the panel side, its head in a
counterbore in the post's foot, through the post and the PCB's hole, into a
nyloc on the component side; fit the board before the panel.  (The 5 mm gap
is too short for a 5.7 mm heat-set insert, hence the nut.)
"""

from __future__ import annotations

import cadquery as cq

from demobox.checks import MIN_BOSS_WALL, button_cutout, monitor_window, panel_in_lid
from demobox.geom import Box, Cyl
from demobox.layout import (DRIVER_STANDOFF, FIT, INSERT_MATERIAL, Layout, exit_edge,
                            insert_stack)
from demobox.parts.monitors import Monitor
from demobox.shared import m3

#: Wall left at each end of the cable-exit edge to locate the panel there.
EXIT_TAB = 15.0
#: Plastic round a driver post's screw counterbore.
POST_WALL = 1.5
#: Counterbore for the M3 screw head in a driver post's foot.
COUNTERBORE_D = 2 * m3.HEAD_R + FIT
COUNTERBORE_H = m3.HEAD_H
#: Carrier bars on the panel's back, tying the driver posts to the walls.
CARRIER_T = 2.0
#: Bezel screws: centre in from the opening's two walls at a corner, and the
#: clearance hole.  The lid's boss under a screw reaches this far from the
#: walls plus its own radius, so a corner within BEZEL_SCREW_INSET + the boss
#: of the pocket has no room.
BEZEL_SCREW_INSET = 4.5
BEZEL_SCREW_D = m3.CLEARANCE_D

if POST_WALL < MIN_BOSS_WALL:
    raise ValueError(f"POST_WALL {POST_WALL} < MIN_BOSS_WALL {MIN_BOSS_WALL}")
if COUNTERBORE_H >= DRIVER_STANDOFF:
    raise ValueError("the driver posts are too short for the screw-head counterbore")


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
    for x, y in bezel_screws(lay):
        plate = plate.cut(cq.Workplane("XY", origin=(x, y, -1.0)).circle(BEZEL_SCREW_D / 2)
                          .extrude(t + 2.0))
    return plate


def bezel_screws(lay: Layout) -> tuple[tuple[float, float], ...]:
    """(x, y) of the bezel's screws, closed lid frame: BEZEL_SCREW_INSET in
    from each corner of the opening whose screw boss (a square of half-side
    BEZEL_SCREW_INSET round the screw, out to the walls) stays out of the
    pocket.  At least three, or the bezel is not held."""
    x0, y0, x1, y1 = lid_opening(lay)
    p, d = lay.lid_pocket, BEZEL_SCREW_INSET
    out = []
    for cx, sx in ((x0, 1), (x1, -1)):
        for cy, sy in ((y0, 1), (y1, -1)):
            x, y = cx + sx * d, cy + sy * d
            bx0, bx1 = sorted((cx, x + sx * d))
            by0, by1 = sorted((cy, y + sy * d))
            if min(bx1, p.x1) - max(bx0, p.x0) > 0 and min(by1, p.y1) - max(by0, p.y0) > 0:
                continue                       # a pocket corner: no room
            out.append((x, y))
    if len(out) < 3:
        raise ValueError(f"only {len(out)} bezel screw corners clear of the pocket")
    return tuple(sorted(out))


def driver_posts(m: Monitor, lay: Layout) -> tuple[Cyl, ...]:
    """The kit's driver-board posts (closed lid frame), from the panel's back
    to the PCB's panel-side face, one under each mounting hole; () for a
    cased monitor."""
    if m.driver is None:
        return ()
    if m.driver_pcb_t is None or not m.driver_holes:
        raise ValueError(f"{m.key}: driver board without PCB thickness or mounting holes")
    W = m.panel[0]
    pb = panel_in_lid(m, lay)
    r = COUNTERBORE_D / 2 + POST_WALL
    # driver holes are in the panel's back frame: u = W - x in the front frame
    return tuple(Cyl(pb.x0 + W - x, pb.y1 - y, pb.z1, pb.z1 + DRIVER_STANDOFF, r,
                     f"{m.key} driver post") for x, y in m.driver_holes)


def driver_envelope(m: Monitor, lay: Layout) -> Box | None:
    """The driver board's envelope (PCB + parts) in the closed lid frame."""
    if m.driver is None:
        return None
    d, W = m.driver, m.panel[0]
    pb = panel_in_lid(m, lay)
    z0 = pb.z1 + DRIVER_STANDOFF
    return Box(pb.x0 + W - d.x1, pb.y1 - d.y1, z0 + d.z0, pb.x0 + W - d.x0, pb.y1 - d.y0,
               z0 + d.z1, f"{m.key} driver board")


def driver_screw_length(m: Monitor) -> int | None:
    """Stock M3 screw through a driver post and the PCB into its nyloc."""
    if m.driver is None:
        return None
    return m3.stock_length(DRIVER_STANDOFF - COUNTERBORE_H + m.driver_pcb_t + m3.NYLOC_H
                           + m3.THREAD_PAST)


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

    posts = driver_posts(m, lay)
    for y in sorted({c.cy for c in posts}):
        r = posts[0].r
        part = part.union(_solid(pb.x0 - t / 2, y - r, pb.z1, pb.x1 + t / 2, y + r,
                                 pb.z1 + CARRIER_T))
    for c in posts:
        part = part.union(cq.Workplane("XY", origin=(c.cx, c.cy, c.z0)).circle(c.r)
                          .extrude(c.z1 - c.z0))
        part = part.cut(cq.Workplane("XY", origin=(c.cx, c.cy, c.z0 - 1.0))
                        .circle(m3.CLEARANCE_D / 2).extrude(c.z1 - c.z0 + 2.0))
        part = part.cut(cq.Workplane("XY", origin=(c.cx, c.cy, c.z0 - 1.0))
                        .circle(COUNTERBORE_D / 2).extrude(COUNTERBORE_H + 1.0))
    return part
