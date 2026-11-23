"""The lid hinge: two printed parts on an M3 bolt + nyloc per knuckle group.

Frames are ``demobox.layout``'s.  ``hinge_base_knuckles`` is built in the base
frame; ``hinge_lid_knuckles`` in the lid frame (closed), so
``lay.lid_location(a)`` places it at ``a`` degrees open.  Both are prisms
along X of profiles in the YZ plane about the hinge axis, which runs along the
base's back-top edge, (y, z) = ``lay.hinge_axis``.  Below, (u, v) is a point
of that plane relative to the axis: u backwards (+Y, away from the visitor),
v up (+Z).

Groups
------
Two knuckle groups, one each side of the hinge cable channel (the cables
cross the axis there, so no knuckle may), each centred in the free run of the
back edge on its side.  A group is base | lid | base knuckle, KNUCKLE_LEN
each, FIT apart, with one M3 bolt through it: the head on one base knuckle's
outer face, the nyloc on the other's (``hinge_bolt_length``).  Both parts
have a PIN_HOLE_D clearance hole along the axis.

Leaves
------
Each part's knuckles hang off a leaf plate LEAF_T thick that runs from the
first group to the last, against the back face of its body (the plane
u = 0 .. LEAF_T, which is the base's back face and, closed, the lid's
hinge-end face): the base leaf below the axis, the lid leaf above it.  Away
from its own knuckles a leaf stops R + FIT short of the axis, so it clears the
other part's knuckles; it is screwed to its body through SCREW_HOLE_D holes.

Stop
----
The base leaf carries a stop shelf behind the base: its top face is the
plane the lid leaf's outer face (lid y = LEAF_T) lies in at LID_OPEN_DEG, cut
back to STOP_R0 round the axis.  Every point of the lid part, at any angle
up to the stop, lies on the near side of that plane (its leaf and knuckle webs
are at lid y <= LEAF_T, z >= 0, and turning them back from the stop only
lowers y), so the lid leaf lands flat on the shelf exactly at LID_OPEN_DEG
and the shelf meets nothing before.  The lid leaf's screw heads sit above the
shelf's reach.

The base and lid bodies relieve their back-top edges by
``knuckle_relief``, a radius KNUCKLE_R + FIT round the axis along each group:
closed, each part's knuckles sit in the other body's corner.  So does the
monitor bezel, whose hinge-end edge is nearer the axis than KNUCKLE_R.
"""

from __future__ import annotations

import math

import cadquery as cq

from demobox.layout import FIT, LID_OPEN_DEG, Layout
from demobox.shared import m3

#: Knuckle radius round the axis and length along it.
KNUCKLE_R = 4.0
KNUCKLE_LEN = 10.0
#: Leaf plate thickness.
LEAF_T = 3.0
#: M3 clearance: the pin hole along the axis and the leaves' screw holes.
PIN_HOLE_D = m3.CLEARANCE_D
SCREW_HOLE_D = m3.CLEARANCE_D
SCREW_HEAD_R = m3.HEAD_R
NYLOC_H = m3.NYLOC_H
THREAD_PAST = m3.THREAD_PAST
M3_LENGTHS = m3.LENGTHS
#: The stop shelf: how far it reaches behind the base leaf, and its thickness
#: under the stop face at its outer edge; a 45 degree gusset carries it back
#: to the leaf.  Its face starts STOP_R0 from the axis, so a degree short of
#: the stop the lid leaf is already ~STOP_R0 x 1 degree (> 0.1 mm) off it.
STOP_REACH = 12.0
STOP_T = 2.5
STOP_R0 = 7.0

_CLEAR_R = KNUCKLE_R + FIT     # a leaf stops this far from the axis off its knuckles


def hinge_groups(lay: Layout) -> tuple[tuple[float, float], ...]:
    """X range of each knuckle group (base frame), left to right."""
    ch = lay.hinge_cable_channel
    span = 3 * KNUCKLE_LEN + 2 * FIT
    zones = ((lay.outer.x0 + lay.wall, ch.x0 - FIT), (ch.x1 + FIT, lay.outer.x1 - lay.wall))
    groups = []
    for z0, z1 in zones:
        if z1 - z0 < span:
            raise ValueError(f"hinge group {span} mm does not fit the {z1 - z0:.2f} mm "
                             f"of back edge at x {z0:.2f}..{z1:.2f}")
        c = (z0 + z1) / 2
        groups.append((c - span / 2, c + span / 2))
    return tuple(groups)


def _knuckles(lay: Layout, which: str) -> list[tuple[float, float]]:
    """X ranges of the base (outer two) or lid (middle) knuckles of each group."""
    out = []
    for x0, _ in hinge_groups(lay):
        ks = [(x0 + i * (KNUCKLE_LEN + FIT), x0 + i * (KNUCKLE_LEN + FIT) + KNUCKLE_LEN)
              for i in range(3)]
        out += [ks[0], ks[2]] if which == "base" else [ks[1]]
    return out


def hinge_bolt_length(lay: Layout) -> float:
    """The stock M3 bolt that passes a group and its nyloc with thread to spare."""
    return m3.stock_length(max(x1 - x0 for x0, x1 in hinge_groups(lay)) + NYLOC_H
                           + THREAD_PAST)


def _prism(origin: tuple[float, float, float], x0: float, x1: float,
           pts: list[tuple[float, float]] | None = None, r: float | None = None) -> cq.Workplane:
    """A polygon (``pts``) or a circle of radius ``r`` about (0, 0) in the YZ
    plane through ``origin``, extruded along X from x0 to x1."""
    wp = cq.Workplane("YZ", origin=(x0, origin[1], origin[2]))
    wp = wp.circle(r) if r is not None else wp.polyline(pts).close()
    return wp.extrude(x1 - x0)


def _rect(u0, v0, u1, v1):
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def _axis_hole(origin, x0, x1, d) -> cq.Workplane:
    return _prism(origin, x0 - 1.0, x1 + 1.0, r=d / 2)


def _stop_plane_v(u: float) -> float:
    """v of the stop face at u: where the lid leaf's outer face, lid y =
    LEAF_T, lies at LID_OPEN_DEG (lid y = u cos A - v sin A)."""
    a = math.radians(LID_OPEN_DEG)
    return (u * math.cos(a) - LEAF_T) / math.sin(a)


def _stop_reach_z() -> float:
    """How far up the lid leaf (lid z) the shelf reaches at the stop."""
    a = math.radians(LID_OPEN_DEG)
    return STOP_REACH * math.sin(a) + _stop_plane_v(STOP_REACH) * math.cos(a)


def _shelf_bottom_v() -> float:
    return _stop_plane_v(STOP_REACH) - STOP_T - STOP_REACH


def knuckle_relief(lay: Layout, axis_yz: tuple[float, float]) -> list[cq.Solid]:
    """What a body (or anything else beside the axis) must give up so the
    knuckles turn: a radius KNUCKLE_R + FIT cylinder round the hinge axis at
    ``axis_yz`` (the frame's (y, z) of it), along each knuckle group, FIT
    beyond its ends."""
    r = _CLEAR_R
    return [cq.Solid.makeCylinder(r, x1 - x0 + 2 * FIT, cq.Vector(x0 - FIT, *axis_yz),
                                  cq.Vector(1, 0, 0))
            for x0, x1 in hinge_groups(lay)]


def _base_hole_v() -> float:
    """v of the base leaf's screw holes: below the stop shelf, clear of its
    underside by a screw head and 2 FIT."""
    return _shelf_bottom_v() - SCREW_HEAD_R - 2 * FIT


def base_leaf_screws(lay: Layout) -> tuple[tuple[float, float], ...]:
    """(x, z) of the base leaf's screws, base frame: one per base knuckle,
    through the leaf along Y into the base's back face (Y = hinge y)."""
    hz = lay.hinge_axis[1]
    return tuple(((k0 + k1) / 2, hz + _base_hole_v()) for k0, k1 in _knuckles(lay, "base"))


def lid_leaf_screws(lay: Layout) -> tuple[tuple[float, float], ...]:
    """(x, z) of the lid leaf's screws, lid frame (closed): one per lid
    knuckle, through the leaf along Y into the lid's hinge-end face (y = 0),
    half-way between the shelf's reach (plus a head and FIT) and the lid top."""
    top = lay.lid_outer.z1
    z = (_stop_reach_z() + SCREW_HEAD_R + FIT + top) / 2
    if top - z < SCREW_HEAD_R + FIT:
        raise ValueError(f"lid {top} mm deep leaves no room for the hinge leaf screws")
    return tuple(((k0 + k1) / 2, z) for k0, k1 in _knuckles(lay, "lid"))


def hinge_base_knuckles(lay: Layout) -> cq.Workplane:
    """The base half: leaf down the base's back face, stop shelf, and the two
    outer knuckles of each group.  Base frame."""
    hy, hz = lay.hinge_axis
    o = (0.0, hy, hz)
    groups = hinge_groups(lay)
    xa, xb = groups[0][0], groups[-1][1]
    hole_v = _base_hole_v()
    depth = -hole_v + SCREW_HOLE_D / 2 + 2 * LEAF_T          # leaf bottom below the axis

    part = _prism(o, xa, xb, _rect(0.0, -depth, LEAF_T, -_CLEAR_R))
    shelf = _prism(o, xa, xb, [(0.0, _stop_plane_v(0.0)),
                               (STOP_REACH, _stop_plane_v(STOP_REACH)),
                               (STOP_REACH, _stop_plane_v(STOP_REACH) - STOP_T),
                               (0.0, _shelf_bottom_v())])
    part = part.union(shelf.cut(_prism(o, xa - 1.0, xb + 1.0, r=STOP_R0)))
    for k0, k1 in _knuckles(lay, "base"):
        part = part.union(_prism(o, k0, k1, r=KNUCKLE_R))
        part = part.union(_prism(o, k0, k1, _rect(0.0, -_CLEAR_R - 0.1, LEAF_T, 0.0)))
    part = part.cut(_axis_hole(o, xa, xb, PIN_HOLE_D))
    for x, z in base_leaf_screws(lay):
        hole = (cq.Workplane("XZ", origin=(x, 0.0, z))
                .circle(SCREW_HOLE_D / 2).extrude(-(hy + LEAF_T + 1.0)))
        part = part.cut(hole)
    return part


def hinge_lid_knuckles(lay: Layout) -> cq.Workplane:
    """The lid half: leaf up the lid's hinge-end face and the middle knuckle
    of each group.  Lid frame, closed."""
    o = (0.0, 0.0, 0.0)
    groups = hinge_groups(lay)
    xa, xb = groups[0][0], groups[-1][1]
    top = lay.lid_outer.z1

    part = _prism(o, xa, xb, _rect(0.0, _CLEAR_R, LEAF_T, top))
    for k0, k1 in _knuckles(lay, "lid"):
        part = part.union(_prism(o, k0, k1, r=KNUCKLE_R))
        part = part.union(_prism(o, k0, k1, _rect(0.0, 0.0, LEAF_T, _CLEAR_R + 0.1)))
    part = part.cut(_axis_hole(o, xa, xb, PIN_HOLE_D))
    for x, z in lid_leaf_screws(lay):
        hole = (cq.Workplane("XZ", origin=(x, 0.0, z))
                .circle(SCREW_HOLE_D / 2).extrude(-(LEAF_T + 1.0)))
        part = part.cut(hole.translate((0, -1.0, 0)))
    return part
