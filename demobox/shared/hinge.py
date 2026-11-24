"""The lid hinge: printed knuckles on one straight rod, no screws.

Frames are ``demobox.layout``'s.  ``knuckles(lay, "base")``,
``knuckle_cut(lay, "base")`` and ``seal_bead`` are in the base frame; the
lid's are in the lid frame (closed), so ``lay.lid_location(a)`` places them
``a`` degrees open.  Every solid here is a prism along X of a profile in the
YZ plane about the hinge axis, which is on the seam, ``KNUCKLE_R`` in from
the back face (``lay.hinge_axis``).  Below, (u, v) is a point of that plane
relative to the axis: u backwards (+Y, away from the visitor), v up (+Z).
Opening turns the lid's (u, v) by -angle about the axis.

Each part is built as ``(body - knuckle_cut(lay, part)) | knuckles(lay,
part)``, and the base also ``| seal_bead(lay)``.

Segments (rulings R15, R21)
---------------------------
Along X there are three kinds of segment:

* lid knuckle: the lid whole, plus its knuckle; the base cut back to
  ``lay.hinge_relief_r`` round the axis (the whole lid's back corner swings
  through there), FIT past each end of the knuckle, less the stop block the
  base keeps under the knuckle;
* base knuckle: the base whole, plus its knuckle; the lid cut back;
* open: the lid cut back; the base whole, its back wall intact, with the
  seal bead filling the lid's relief above the seam.

``knuckle_plan`` (R19) fills each ``lay.knuckle_x`` range (no base content,
nor the bank bay, within the relief radius; not the pigtail's notch) that is
at least KNUCKLE_LEN long with as many knuckles of at least KNUCKLE_LEN as
fit, sharing it equally, FIT apart; every other X is open.  Along X they
alternate, lid first: with an odd count both ends are lid knuckles, each
carrying a stop, and every base knuckle is caught between two lid knuckles.
``knuckle_cut(lay, part)`` is the relief, a radius ``hinge_relief_r``
cylinder -- the base's at each lid knuckle (FIT past its ends), the lid's
everywhere along X but at its own knuckles -- with the rod's bore along the
rod.

Knuckles and rod
----------------
A knuckle is a radius KNUCKLE_R disc round the axis, bored PIN_HOLE_D for the
rod, with a web to its part's hinge-end wall: the base knuckle's web is the
square u 0..R, v -R..0 under the axis; the lid knuckle's is its tab, u 0..R,
v 0..TAB_H over it.  The disc reaches the back face (u = R) and is half in
the base, half in the lid, so nothing is proud of the closed box.  The rod
(R22) runs from the first knuckle's -X end to the +X side face, flush there
and pushed in from there, one piece across the notch: ``pin_length``.  It is
in a knuckle all along but the notch and the FIT gaps.  (A full-width rod
would cross the port room and the bank bay, which reach 0.5 mm in front of
the axis: the bank, slid back in its SLACK, would hit it.)

Seal bead
---------
``seal_bead`` (R21) fills the lid's relief in the open segments so the closed
box's back is shut: its profile is the disc of radius ``hinge_relief_r -
FIT`` about the axis, above the seam (v >= 0), no further back than the
outline (u <= R) and -- so the bank still lifts straight out (R12) -- not
over the bank row (Y >= its back edge; u >= -0.5 in the design kit).  It
runs along X wherever there is no knuckle (nor FIT either side of one) and
no notch: the pigtail drops through the notch.  The lid's relief is FIT
outside it all the way round, at every angle.

Stop
----
The lid's back face (lid u = R, which the tab's back face lies in) is a plane
tangent to the knuckle disc.  At LID_OPEN_DEG it lies along the line tangent
to the disc at polar angle -LID_OPEN_DEG.  Under each lid knuckle the base
keeps a stop block in its relief: the quadrilateral from that line (from
STOP_R0 out to the back face) down to FIT below the relief, where it fuses
with the base's uncut back wall.  At angle ``a`` open every lid point at
radius r > R near the axis is at polar angle >= acos(R / r) - a, and every
block point at <= acos(R / r) - LID_OPEN_DEG, so they meet exactly at
LID_OPEN_DEG, face on face, and not before.  A degree short, a block point
sqrt(r^2 - R^2) along the face is that times sin 1 deg off the lid: STOP_R0
= R + 2 FIT keeps the gap over 0.05 mm.  ``stop_faces`` gives each stop's tab
(lid frame) and block (base frame) profiles for ``checks.hinge_sweep``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import cadquery as cq

from demobox.layout import FIT, KNUCKLE_LEN, KNUCKLE_R, LID_OPEN_DEG, PIN_ROD_D, Layout

Part = Literal["base", "lid"]

#: The rod's bore: PIN_ROD_D plus a slip clearance, so the rod pushes through.
PIN_HOLE_D = PIN_ROD_D + 0.2
#: The lid knuckle's tab, u 0..KNUCKLE_R, v 0..TAB_H: up to where the lid's
#: back face crosses the base's back face at the stop, R tan(A / 2), plus FIT.
TAB_H = KNUCKLE_R * math.tan(math.radians(LID_OPEN_DEG) / 2) + FIT
#: The stop block's face starts this far from the axis: FIT clear of the
#: turning knuckle disc, and FIT more so the faces are over 0.05 mm apart a
#: degree short of the stop.
STOP_R0 = KNUCKLE_R + 2 * FIT
#: The first knuckle from -X; they alternate from it.
FIRST_PART: Part = "lid"
#: Segments of the seal bead's arc (a polygon inscribed in its circle).
BEAD_ARC_SEGMENTS = 32

_EPS = 1e-6
_PARTS: tuple[Part, Part] = ("base", "lid")


@dataclass(frozen=True)
class Knuckle:
    """One knuckle: its X range (base frame; the same in the lid frame) and
    the part it belongs to."""
    x0: float
    x1: float
    part: Part


@dataclass(frozen=True)
class Stop:
    """One stop, under a lid knuckle over X ``x0..x1``: ``tab`` is the lid
    knuckle's tab, a YZ polygon in the lid frame (closed); ``block`` is the
    base's stop block, a YZ polygon in the base frame.  At LID_OPEN_DEG the
    tab's back face lies on the block's top face."""
    x0: float
    x1: float
    tab: tuple[tuple[float, float], ...]
    block: tuple[tuple[float, float], ...]


def _check_part(part: str) -> None:
    if part not in _PARTS:
        raise ValueError(f"part must be one of {_PARTS}, not {part!r}")


def knuckle_plan(lay: Layout) -> tuple[Knuckle, ...]:
    """Every knuckle, left to right (see the module docstring)."""
    spans: list[tuple[float, float]] = []
    for x0, x1 in sorted(lay.knuckle_x):
        n = math.floor((x1 - x0 + FIT) / (KNUCKLE_LEN + FIT) + _EPS)
        if n:
            length = (x1 - x0 - (n - 1) * FIT) / n
            spans += [(x0 + i * (length + FIT), x0 + i * (length + FIT) + length)
                      for i in range(n)]
    first = _PARTS.index(FIRST_PART)
    plan = tuple(Knuckle(a, b, _PARTS[(first + i) % 2]) for i, (a, b) in enumerate(spans))
    for a, b in zip(plan, plan[1:]):
        if b.x0 - a.x1 < FIT - _EPS:
            raise ValueError(f"knuckles at x {a.x0:.2f} and {b.x0:.2f} are under FIT apart")
    if {k.part for k in plan} != set(_PARTS):
        raise ValueError(f"knuckle_x {lay.knuckle_x} holds {len(plan)} knuckle(s) of at "
                         f"least KNUCKLE_LEN {KNUCKLE_LEN:g}: the hinge needs a base and a "
                         "lid one")
    return plan


def pin_length(lay: Layout) -> float:
    """The rod (R22): from the first knuckle's -X end to the +X side face."""
    return lay.outer.x1 - knuckle_plan(lay)[0].x0


def _dir(deg: float) -> tuple[float, float]:
    return math.cos(math.radians(deg)), math.sin(math.radians(deg))


def _tab_uv() -> tuple[tuple[float, float], ...]:
    return ((0.0, 0.0), (KNUCKLE_R, 0.0), (KNUCKLE_R, TAB_H), (0.0, TAB_H))


def _block_uv(relief_r: float) -> tuple[tuple[float, float], ...]:
    """The stop block's profile about the axis (base side): the line the
    lid's back face lies on at LID_OPEN_DEG, from STOP_R0 out to the back
    face (u = R), then down to FIT below the relief."""
    r, a = KNUCKLE_R, LID_OPEN_DEG
    tu, tv = (r * c for c in _dir(-a))          # the tangent point
    du, dv = _dir(90.0 - a)                     # along the face, outwards
    s0 = math.sqrt(STOP_R0 ** 2 - r ** 2)
    s1 = r * math.tan(math.radians(a) / 2)      # where the face meets u = R
    if s1 <= s0:
        raise ValueError(f"at LID_OPEN_DEG {a:g} the stop face (to {s1:.2f} mm) is no "
                         f"longer than STOP_R0 leaves ({s0:.2f} mm)")
    p1 = (tu + s0 * du, tv + s0 * dv)
    p2 = (tu + s1 * du, tv + s1 * dv)
    bottom = -(relief_r + FIT)
    if bottom >= p2[1]:
        raise ValueError(f"hinge relief {relief_r:.2f} leaves no stop block under the face")
    return (p1, p2, (r, bottom), (p1[0], bottom))


def stop_faces(lay: Layout) -> tuple[Stop, ...]:
    """One stop per lid knuckle: the tab in the lid frame (closed), the block
    in the base frame, both YZ polygons."""
    hy, hz = lay.hinge_axis
    block = tuple((hy + u, hz + v) for u, v in _block_uv(lay.hinge_relief_r))
    return tuple(Stop(k.x0, k.x1, _tab_uv(), block)
                 for k in knuckle_plan(lay) if k.part == "lid")


def bead_yz(lay: Layout) -> tuple[tuple[float, float], ...]:
    """The seal bead's YZ profile, base frame (see the module docstring): a
    polygon inscribed in the radius ``hinge_relief_r - FIT`` circle."""
    hy, hz = lay.hinge_axis
    rb = lay.hinge_relief_r - FIT
    u0 = max(lay.bank_bay.y1, lay.port_room.y1) - hy      # the bank row's back edge
    u1 = min(KNUCKLE_R, rb)
    if not -rb < u0 < u1:
        raise ValueError(f"the bank row's back edge (u {u0:.2f}) leaves no seal bead "
                         f"inside radius {rb:.2f}, u < {u1:.2f}")
    t1, t0 = math.acos(u1 / rb), math.acos(u0 / rb)
    ts = [t1 + (t0 - t1) * i / BEAD_ARC_SEGMENTS for i in range(BEAD_ARC_SEGMENTS + 1)]
    uv = [(u0, 0.0), (u1, 0.0), *((rb * math.cos(t), rb * math.sin(t)) for t in ts)]
    return tuple((hy + u, hz + v) for u, v in uv)


def bead_x(lay: Layout) -> tuple[tuple[float, float], ...]:
    """The seal bead's X ranges: the box's width less each knuckle (FIT past
    its ends) and the pigtail's notch."""
    n = lay.hinge_notch
    blocked = sorted([(k.x0 - FIT, k.x1 + FIT) for k in knuckle_plan(lay)] + [(n.x0, n.x1)])
    out, x = [], lay.outer.x0
    for a, b in blocked:
        if a > x + _EPS:
            out.append((x, min(a, lay.outer.x1)))
        x = max(x, b)
    if x < lay.outer.x1 - _EPS:
        out.append((x, lay.outer.x1))
    return tuple(out)


def _axis_yz(lay: Layout, part: Part) -> tuple[float, float]:
    return lay.hinge_axis if part == "base" else (0.0, 0.0)


def _prism(axis_yz: tuple[float, float], x0: float, x1: float,
           pts=None, r: float | None = None) -> cq.Solid:
    """A polygon (``pts``, (u, v) about the axis) or a radius ``r`` circle
    about the axis, extruded along X from x0 to x1."""
    wp = cq.Workplane("YZ", origin=(x0, *axis_yz))
    wp = wp.circle(r) if r is not None else wp.polyline(list(pts)).close()
    return wp.extrude(x1 - x0).val()


def knuckles(lay: Layout, part: Part) -> cq.Workplane:
    """``part``'s knuckles, each bored PIN_HOLE_D on the axis, in its frame;
    the base's also include the stop block under each lid knuckle."""
    _check_part(part)
    ax = _axis_yz(lay, part)
    r = KNUCKLE_R
    web = ((0.0, -r), (r, -r), (r, 0.0), (0.0, 0.0)) if part == "base" else _tab_uv()
    out = []
    for k in knuckle_plan(lay):
        if k.part == part:
            s = _prism(ax, k.x0, k.x1, r=r).fuse(_prism(ax, k.x0, k.x1, web))
            out.append(s.cut(_prism(ax, k.x0 - 1.0, k.x1 + 1.0, r=PIN_HOLE_D / 2)).clean())
        elif part == "base":
            out.append(_prism(ax, k.x0, k.x1, _block_uv(lay.hinge_relief_r)))
    return cq.Workplane("XY").newObject(out)


def knuckle_cut(lay: Layout, part: Part) -> cq.Workplane:
    """What ``part`` gives up so the other part's knuckles (and its whole
    body there) turn: the relief cylinder, radius ``hinge_relief_r`` about
    the axis -- the base's at each lid knuckle, FIT past its ends; the lid's
    everywhere along X but at its own knuckles (so at the base knuckles, in
    the FIT gaps and in the open segments), 1 mm past each side face -- and
    the rod's bore along the rod (1 mm past the +X face)."""
    _check_part(part)
    ax = _axis_yz(lay, part)
    plan = knuckle_plan(lay)
    x0, x1 = lay.outer.x0 - 1.0, lay.outer.x1 + 1.0
    rr = lay.hinge_relief_r
    cuts = [_prism(ax, lay.outer.x1 - pin_length(lay), x1, r=PIN_HOLE_D / 2)]
    if part == "base":
        cuts += [_prism(ax, k.x0 - FIT, k.x1 + FIT, r=rr) for k in plan if k.part == "lid"]
    else:
        x = x0
        for k in plan:
            if k.part == "lid":
                if k.x0 > x:
                    cuts.append(_prism(ax, x, k.x0, r=rr))
                x = k.x1
        if x < x1:
            cuts.append(_prism(ax, x, x1, r=rr))
    cut = cuts[0]
    for c in cuts[1:]:
        cut = cut.fuse(c)
    return cq.Workplane("XY").newObject([cut.clean()])


def seal_bead(lay: Layout) -> cq.Workplane:
    """The base's seal bead (base frame): ``bead_yz`` along each of
    ``bead_x``."""
    hy, hz = lay.hinge_axis
    uv = [(y - hy, z - hz) for y, z in bead_yz(lay)]
    return cq.Workplane("XY").newObject([_prism((hy, hz), a, b, uv) for a, b in bead_x(lay)])
