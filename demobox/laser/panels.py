"""The laser-cut body: 3 mm plywood panels, finger-jointed and glued.

``build(lay, t, kerf, bed)`` makes every panel of the route from
``layout(t)``; ``panels(lay, t, kerf)`` is its panel dict.  The frames are
``demobox.layout``'s: base and plinth panels in the base frame, lid panels in
the lid frame (closed); ``fittings.assembly`` places them.  Only
``t == lay.wall`` makes sense (the layout is drawn for the wall it was given),
so ``--thickness`` regenerates the layout too.  No screws, nuts or feet (spec
Decision 9): every joint is glued.

Panels
------
* Base: a box, ``base-floor`` and four walls (``base-front``, ``-back``,
  ``-left``, ``-right``) up to the rim.
* Plinth: an open box standing on the floor under the board
  (``Layout.plinth``): ``plinth-top`` (its top face is the PCB underside) and
  four walls tabbed into the floor and into the top.  A wall comes in from
  the plinth's edge where a board pin's hole would be within a panel
  thickness of it (the MT1 holes are 4 mm from the plinth's front edge), so
  the top overhangs there (``plinth_walls``).  ``plinth_relief`` (R7) is cut out of the top
  and of any wall it reaches.  ``plinth-top`` has a PIN_HOLE_D hole at each
  of ``Layout.pins``: MT2's rod is glued in, the loose MT1 rod is pushed into
  the hole of the board revision fitted.
* Lid: a tray, ``lid-top`` (the outside top, the monitor taped under it) and
  four walls (``lid-front``, ``-back``, ``-left``, ``-right``) down to the seam.

The hinge (``demobox.shared.hinge``) is printed (``fittings``):

* the base's back and right walls are cut away at their top back corner
  round the hinge (``hinge_cutouts``: from FIT before the first knuckle to
  the +X side, ``hinge_depth`` below and in front of the axis), and
  ``knuckles-base`` fills that cut-out flush with the outside faces: the
  base knuckle, the stop blocks and the relief round the lid knuckles;
* the lid's back and right walls likewise at their bottom back corner, filled
  by ``knuckles-lid`` (the lid knuckles and the bridge between them);
* elsewhere along X (open segments, R21) the base's back wall is whole up to
  the rim and carries the printed ``seal-bead`` on its top edge; the lid is
  relieved: ``lid-back``'s bottom edge is raised clear of the relief circle
  (radius ``hinge_relief_r`` about the axis, ``lid_back_z0``) and
  ``lid-left`` has that circle cut from its back bottom corner.

Joints
------
Every panel starts as a *slab*: an axis-aligned box ``t`` thick, as big as the
panel including the joint zones it may own.  Where two slabs overlap is a
*joint zone* (``t`` x ``t`` along their common edge).  Each joint is declared
(``_joint_specs``; an undeclared overlap is an error) and its zone is cut
along the edge into segments, each owned by exactly one panel:

* where a third slab passes through the zone (a corner of three panels), the
  panel of highest ``prio`` owns it: floor and lid top 5, front/back walls 4,
  side walls 3, plinth top 2, plinth walls 1;
* declared exclusions (the hinge cut-outs, the lid's relief, the plinth
  relief) give a stretch to one panel whole, and so does a free stretch too
  short for three fingers a panel thick (MIN_RUN_T): the male owns it;
* the rest is fingered (``joints.finger_count``): the declared male panel
  owns the ends.  For an inner panel (the plinth's walls in the floor, and a
  plinth wall set in from the top's edge) the receiving panel is male, so
  the inner panel's fingers are tabs through mortises.

A panel's shape is its slab's rectangle less the segments others own, less
its feature cuts, with its holes and engraved marks (layer ENGRAVE: the
panel's name and where the magnet blocks are glued).

Bed
---
A panel bigger than the bed (in either orientation, kerf included) is split
by a fingered seam (``_split``): the seam line at the candidate nearest the
middle whose two pieces fit, are each one piece, and whose finger band
(SEAM_DEPTH_T wide) meets no mortise, hole or mark; the pieces are glued
along it.  At 3 mm every panel fits the 300 x 200 bed whole.  A panel that
no seam can split raises ``BedOverflow`` naming it and its size.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

import cadquery as cq
from shapely.geometry import LineString, Polygon, box as sbox
from shapely.ops import unary_union

import demobox  # noqa: F401  (puts the submodule on sys.path)
from demobox.geom import BedOverflow, Box
from demobox.layout import FIT, LASER_BED, PEG_DIA, Layout
from demobox.laser import joints as J
from demobox.shared import hinge as H

#: Default kerf (mm), a CO2 laser in 3 mm plywood.
KERF = 0.15
#: Seam fingers' depth across the seam, in panel thicknesses.
SEAM_DEPTH_T = 2.0
#: Keep a seam's finger band this far from mortises, holes and marks.
SEAM_MARGIN = 2.0
#: A free stretch of a joint shorter than this many panel thicknesses is not
#: fingered (three fingers would each be under a thickness wide): the male
#: panel owns it whole.
MIN_RUN_T = 3.0
#: Engraved label height.
LABEL_H = 4.0
#: The board pins' holes in ``plinth-top``: the PEG_DIA rod's own diameter,
#: so MT2's is a tight fit for the glue and the loose MT1 rod a push fit that
#: holds it at height and pulls out by hand for the other revision.
PIN_HOLE_D = PEG_DIA
#: Segments of the lid's relief circle cut from ``lid-left`` (a polygon
#: round the circle, never inside it).
ARC_SEGMENTS = 64

#: Pairs of assembly names allowed to interpenetrate: only the hinge rod in
#: the lid knuckle block's R24 press fit.  The fingers are modelled nominal,
#: so they interlock face to face; the rods sit in their holes, the magnets
#: in their pockets and the printed blocks in their cut-outs exactly.
DECLARED_OVERLAPS: frozenset[frozenset[str]] = frozenset(
    {frozenset(("hw:hinge-rod", "knuckles-lid"))})

AXES = "xyz"
#: In-plane axes (u, v) of a panel by its normal.
PLANE = {"z": ("x", "y"), "y": ("x", "z"), "x": ("y", "z")}


def _rng(b: Box, a: str) -> tuple[float, float]:
    return {"x": (b.x0, b.x1), "y": (b.y0, b.y1), "z": (b.z0, b.z1)}[a]


def _mk(r: dict[str, tuple[float, float]], what: str = "") -> Box:
    return Box(r["x"][0], r["y"][0], r["z"][0], r["x"][1], r["y"][1], r["z"][1], what)


def _meet(a: Box, b: Box, eps: float = 1e-9) -> Box | None:
    r = {k: (max(_rng(a, k)[0], _rng(b, k)[0]), min(_rng(a, k)[1], _rng(b, k)[1])) for k in AXES}
    if any(hi - lo <= eps for lo, hi in r.values()):
        return None
    return _mk(r)


def _overlap(a: Box, b: Box, eps: float = 1e-6) -> bool:
    return _meet(a, b, eps) is not None


# --- records -------------------------------------------------------------------------

@dataclass(frozen=True, eq=False)
class Panel:
    """One cut panel: its nominal outline (``shape``, in-plane (u, v) of
    ``PLANE[normal]``, which are its frame's coordinates), holes (u, v, d),
    engraved marks, and where it sits: ``frame`` ("base" or "lid"), its
    normal and the low face ``z0`` along it."""

    name: str
    frame: str
    normal: str
    z0: float
    t: float
    shape: Polygon
    holes: tuple[tuple[float, float, float], ...] = ()
    marks: tuple[tuple[tuple[float, float], ...], ...] = ()
    kerf: float = KERF
    note: str = ""

    def cut_shape(self) -> Polygon:
        """The cut path: the outline grown kerf/2 (mortises shrink)."""
        return self.shape.buffer(self.kerf / 2, join_style=2) if self.kerf else self.shape

    def cut_holes(self) -> tuple[tuple[float, float, float], ...]:
        return tuple((u, v, d - self.kerf) for u, v, d in self.holes)

    def cut_size(self) -> tuple[float, float]:
        b = self.cut_shape().bounds
        return b[2] - b[0], b[3] - b[1]

    def point(self, u: float, v: float, w: float) -> tuple[float, float, float]:
        """In-plane (u, v) at ``w`` along the normal -> frame (x, y, z)."""
        a, b = PLANE[self.normal]
        p = {a: u, b: v, self.normal: w}
        return p["x"], p["y"], p["z"]

    def box(self) -> Box:
        u0, v0, u1, v1 = self.shape.bounds
        a, b = PLANE[self.normal]
        return _mk({a: (u0, u1), b: (v0, v1), self.normal: (self.z0, self.z0 + self.t)},
                   self.name)

    def solid(self, holes: bool = True) -> cq.Shape:
        """The panel in its frame (nominal size, no kerf)."""
        n = cq.Vector(*self.point(0, 0, 1)) - cq.Vector(*self.point(0, 0, 0))

        def wire(ring):
            pts = [cq.Vector(*self.point(u, v, self.z0)) for u, v in list(ring.coords)[:-1]]
            return cq.Wire.makePolygon(pts, close=True)

        s = cq.Solid.extrudeLinear(wire(self.shape.exterior),
                                   [wire(r) for r in self.shape.interiors], n * self.t)
        if holes and self.holes:
            cyl = [cq.Solid.makeCylinder(d / 2, self.t + 2.0,
                                         cq.Vector(*self.point(u, v, self.z0 - 1.0)), n)
                   for u, v, d in self.holes]
            s = s.cut(*cyl).clean()
        return s


@dataclass(frozen=True)
class Joint:
    """A glued finger joint between slabs ``a`` and ``b``: its zone, the edge
    ``axis``, the zone's ``interval`` along it cut into ``segments`` (lo, hi,
    owner); ``runs`` are the fingered stretches (the rest is corners and
    exclusions)."""

    a: str
    b: str
    male: str
    frame: str
    axis: str
    zone: Box
    interval: tuple[float, float]
    segments: tuple[tuple[float, float, str], ...]
    runs: tuple[tuple[tuple[float, float, str], ...], ...]

    def segment_box(self, lo: float, hi: float) -> Box:
        r = {k: _rng(self.zone, k) for k in AXES}
        r[self.axis] = (lo, hi)
        return _mk(r, f"{self.a}/{self.b} segment")


@dataclass(frozen=True)
class Seam:
    """A split: panel ``name`` cut at ``axis`` = ``at`` into ``pieces``
    along a glued finger seam (``runs``: the band's segments, owner = piece)."""

    name: str
    axis: str
    at: float
    pieces: tuple[str, str]
    whole: Polygon
    runs: tuple[tuple[tuple[float, float, str], ...], ...]


@dataclass(frozen=True, eq=False)
class LaserBody:
    """Everything ``build`` makes; read-only (it is cached and shared).
    ``slab_cuts`` is each slab's feature cuts, united, in its (u, v)."""

    t: float
    kerf: float
    panels: Mapping[str, Panel]
    slab_panels: Mapping[str, Panel]
    slab_cuts: Mapping[str, Polygon]
    joints: tuple[Joint, ...]
    seams: tuple[Seam, ...]


@dataclass
class _Slab:
    name: str
    frame: str
    normal: str
    box: Box
    prio: int
    cuts: list[Box] = field(default_factory=list)       # feature cuts (through)
    polys: list[list[tuple[float, float]]] = field(default_factory=list)  # (u, v) cuts
    holes: list[tuple[float, float, float]] = field(default_factory=list)
    marks: list[tuple[tuple[float, float], ...]] = field(default_factory=list)
    lost: list[Box] = field(default_factory=list)       # joint segments others own
    note: str = ""

    def rect(self, b: Box) -> Polygon:
        a, c = PLANE[self.normal]
        (u0, u1), (v0, v1) = _rng(b, a), _rng(b, c)
        return sbox(u0, v0, u1, v1)

    def cut_region(self) -> Polygon:
        return unary_union([self.rect(b) for b in self.cuts] + [Polygon(p) for p in self.polys])


@dataclass(frozen=True)
class _Spec:
    a: str
    b: str
    male: str
    excl: tuple[tuple[float, float, str], ...] = ()


# --- the hinge cut-outs ------------------------------------------------------------------

def hinge_depth(lay: Layout, t: float) -> float:
    """How far below (base) or above (lid) the axis, and in front of it, the
    walls are cut away for the knuckle blocks: the relief, FIT, and a wall
    of printed material under it."""
    return lay.hinge_relief_r + FIT + t


def hinge_cutouts(lay: Layout, t: float) -> dict[str, tuple[Box, Box]]:
    """The walls' hinge cut-outs, which the knuckle blocks fill exactly:
    ``"base"`` (base frame) and ``"lid"`` (lid frame, closed), each (the back
    wall's, the right wall's).  Along X they run from FIT before the first
    knuckle (where the base's relief round it starts) to the +X side face."""
    o, lo = lay.outer, lay.lid_outer
    hy, hz = lay.hinge_axis
    d = hinge_depth(lay, t)
    x0 = H.knuckle_plan(lay)[0].x0 - FIT
    return {
        "base": (Box(x0, o.y1 - t, hz - d, o.x1, o.y1, o.z1, "base back wall hinge cut-out"),
                 Box(o.x1 - t, hy - d, hz - d, o.x1, o.y1, o.z1,
                     "base right wall hinge cut-out")),
        "lid": (Box(x0, lo.y1 - t, lo.z0, lo.x1, lo.y1, d, "lid back wall hinge cut-out"),
                Box(lo.x1 - t, -d, lo.z0, lo.x1, lo.y1, d, "lid right wall hinge cut-out")),
    }


def lid_back_z0(lay: Layout, t: float) -> float:
    """``lid-back``'s bottom edge in the open segments (lid frame): clear of
    the relief circle across the wall's thickness."""
    rr = lay.hinge_relief_r
    y_in = lay.lid_outer.y1 - t
    return math.sqrt(rr * rr - y_in * y_in) if 0.0 < y_in < rr else rr


def _relief_polygon(r: float, n: int = ARC_SEGMENTS) -> list[tuple[float, float]]:
    """A regular polygon round the circle of radius ``r`` about the origin
    (its edges tangent to the circle, so nothing inside it is left)."""
    rc = r / math.cos(math.pi / n)
    return [(rc * math.cos(2 * math.pi * (i + 0.5) / n), rc * math.sin(2 * math.pi * (i + 0.5) / n))
            for i in range(n)]


# --- the plinth ---------------------------------------------------------------------------

def plinth_walls(lay: Layout, t: float) -> tuple[float, float, float, float]:
    """(x_left, x_right, y_front, y_back): the plinth walls' outer faces.
    Each is at the plinth's edge unless a pin hole there would come within a
    panel thickness of the wall (its mortises in the top would leave too thin
    a web of plywood by the hole): then the wall comes in to ``t`` past the
    hole."""
    pl = lay.plinth
    keep = PIN_HOLE_D / 2 + t
    pins = list(lay.pins.values())
    yf = max([pl.y0] + [p.cy + keep for p in pins if p.cy - keep < pl.y0 + t])
    yb = min([pl.y1] + [p.cy - keep for p in pins if p.cy + keep > pl.y1 - t])
    inner = [p for p in pins if yf + t < p.cy < yb - t]
    xl = max([pl.x0] + [p.cx + keep for p in inner if p.cx - keep < pl.x0 + t])
    xr = min([pl.x1] + [p.cx - keep for p in inner if p.cx + keep > pl.x1 - t])
    if xr - xl < 3 * t or yb - yf < 3 * t:
        raise ValueError(f"the board pins leave no room for the plinth's walls: "
                         f"x {xl:.2f}..{xr:.2f}, y {yf:.2f}..{yb:.2f}")
    return xl, xr, yf, yb


# --- the slabs ---------------------------------------------------------------------------

def _slabs(lay: Layout, t: float) -> dict[str, _Slab]:
    o, lo = lay.outer, lay.lid_outer
    W, D, Hh = o.x1, o.y1, o.z1
    plan = H.knuckle_plan(lay)
    if plan[0].x0 - FIT < t:
        raise ValueError(f"the first knuckle (x {plan[0].x0:.2f}) reaches the left wall")
    cut = hinge_cutouts(lay, t)
    s: dict[str, _Slab] = {}

    def add(name, frame, normal, box, prio, note=""):
        s[name] = _Slab(name, frame, normal, box, prio, note=note)
        return s[name]

    # --- base -------------------------------------------------------------------------
    add("base-floor", "base", "z", Box(0, 0, 0, W, D, t), 5,
        "Base floor; the plinth's walls are tabbed into it.")
    front = add("base-front", "base", "y", Box(0, 0, 0, W, t, Hh), 4,
                "Base front wall; glue the two magnet blocks in its top corners, on the "
                "engraved outlines, pockets up.")
    back = add("base-back", "base", "y", Box(0, D - t, 0, W, D, Hh), 4,
               "Base back wall: glue knuckles-base into its top right cut-out and the "
               "seal bead along its top edge, flush with the outside face.")
    add("base-left", "base", "x", Box(0, 0, 0, t, D, Hh), 3, "Base left wall.")
    right = add("base-right", "base", "x", Box(W - t, 0, 0, W, D, Hh), 3,
                "Base right wall; knuckles-base fills its top back cut-out.")
    back.cuts.append(cut["base"][0])
    right.cuts.append(cut["base"][1])
    for c in lay.lid_catch:
        b = lay.catch_base_block(c)
        front.marks.append(tuple(sbox(b.x0, b.z0, b.x1, b.z1).exterior.coords))

    # --- plinth -------------------------------------------------------------------------
    pl = lay.plinth
    if pl.z1 - pl.z0 > 0:
        if pl.z1 - pl.z0 <= t:
            raise ValueError(f"the plinth ({pl.z1 - pl.z0:.2f} mm) is no taller than a panel")
        xl, xr, yf, yb = plinth_walls(lay, t)
        z1 = pl.z1
        top = add("plinth-top", "base", "z", Box(pl.x0, pl.y0, z1 - t, pl.x1, pl.y1, z1), 2,
                  "Plinth top: the board lies on it. Glue the MT2 rod in its hole; the "
                  "loose MT1 rod pushes into the hole of the revision fitted.")
        walls = (
            add("plinth-front", "base", "y", Box(xl, yf, 0, xr, yf + t, z1), 1,
                "Plinth front wall."),
            add("plinth-back", "base", "y", Box(xl, yb - t, 0, xr, yb, z1), 1,
                "Plinth back wall."),
            add("plinth-left", "base", "x", Box(xl, yf, 0, xl + t, yb, z1), 1,
                "Plinth left wall."),
            add("plinth-right", "base", "x", Box(xr - t, yf, 0, xr, yb, z1), 1,
                "Plinth right wall."),
        )
        top.holes += [(p.cx, p.cy, PIN_HOLE_D) for p in lay.pins.values()]
        r = lay.plinth_relief
        for sl in (top, *walls):
            if _overlap(sl.box, r):
                sl.cuts.append(r)

    # --- lid ----------------------------------------------------------------------------
    Lz = lo.z1
    add("lid-top", "lid", "z", Box(0, lo.y0, Lz - t, W, lo.y1, Lz), 5,
        "Lid top (outside top); the monitor is taped under it.")
    lfront = add("lid-front", "lid", "y", Box(0, lo.y0, 0, W, lo.y0 + t, Lz), 4,
                 "Lid front wall; glue the two magnet blocks in its bottom corners, on the "
                 "engraved outlines, pockets down.")
    lback = add("lid-back", "lid", "y", Box(0, lo.y1 - t, 0, W, lo.y1, Lz), 4,
                "Lid back wall: glue knuckles-lid into its bottom right cut-out, flush with "
                "the outside face.")
    lleft = add("lid-left", "lid", "x", Box(0, lo.y0, 0, t, lo.y1, Lz), 3,
                "Lid left wall; its back corner is cut round the hinge relief.")
    lright = add("lid-right", "lid", "x", Box(W - t, lo.y0, 0, W, lo.y1, Lz), 3,
                 "Lid right wall; knuckles-lid fills its bottom back cut-out.")
    lback.cuts += [cut["lid"][0],
                   Box(-1.0, lo.y1 - t, -1.0, cut["lid"][0].x0, lo.y1, lid_back_z0(lay, t),
                       "lid relief")]
    lright.cuts.append(cut["lid"][1])
    lleft.polys.append(_relief_polygon(lay.hinge_relief_r))     # (u, v) = (y, z) about the axis
    for c in lay.lid_catch:
        b = lay.catch_lid_block(c)
        lfront.marks.append(tuple(sbox(b.x0, b.z0, b.x1, b.z1).exterior.coords))
    return s


def _joint_specs(lay: Layout, t: float, slabs: dict[str, _Slab]) -> list[_Spec]:
    S = _Spec
    cut = hinge_cutouts(lay, t)
    zc = cut["base"][0].z0
    specs = [
        S("base-floor", "base-front", "base-floor"),
        S("base-floor", "base-back", "base-floor"),
        S("base-floor", "base-left", "base-floor"),
        S("base-floor", "base-right", "base-floor"),
        S("base-front", "base-left", "base-front"),
        S("base-front", "base-right", "base-front"),
        S("base-back", "base-left", "base-back"),
        S("base-back", "base-right", "base-back", ((zc, lay.outer.z1, "base-back"),)),
        S("lid-top", "lid-front", "lid-top"),
        S("lid-top", "lid-back", "lid-top"),
        S("lid-top", "lid-left", "lid-top"),
        S("lid-top", "lid-right", "lid-top"),
        S("lid-front", "lid-left", "lid-front"),
        S("lid-front", "lid-right", "lid-front"),
        S("lid-back", "lid-left", "lid-back", ((0.0, lay.hinge_relief_r, "lid-left"),)),
        S("lid-back", "lid-right", "lid-back", ((0.0, cut["lid"][0].z1, "lid-right"),)),
    ]
    if "plinth-top" in slabs:
        r = lay.plinth_relief
        walls = ("plinth-front", "plinth-back", "plinth-left", "plinth-right")
        for w in walls:
            specs.append(S("base-floor", w, "base-floor"))
            along = "x" if slabs[w].normal == "y" else "y"
            excl = ((*_rng(r, along), "plinth-top"),) if _overlap(slabs[w].box, r) else ()
            specs.append(S("plinth-top", w, "plinth-top", excl))
        for fb in walls[:2]:
            for lr in walls[2:]:
                specs.append(S(fb, lr, fb))
    return specs


# --- the joint engine ------------------------------------------------------------------

def _minus(ivs, lo, hi):
    out = []
    for a, b in ivs:
        if hi <= a or lo >= b:
            out.append((a, b))
            continue
        if lo > a:
            out.append((a, lo))
        if hi < b:
            out.append((hi, b))
    return [(a, b) for a, b in out if b - a > 1e-9]


def _joint(spec: _Spec, slabs: dict[str, _Slab], t: float) -> Joint:
    A, B = slabs[spec.a], slabs[spec.b]
    if A.frame != B.frame:
        raise ValueError(f"joint {spec.a}/{spec.b} across frames")
    zone = _meet(A.box, B.box)
    if zone is None:
        raise ValueError(f"joint {spec.a}/{spec.b}: the slabs do not meet")
    axes = [a for a in AXES if a not in (A.normal, B.normal)]
    if len(axes) != 1:
        raise ValueError(f"joint {spec.a}/{spec.b}: panels are parallel")
    axis = axes[0]
    lo, hi = _rng(zone, axis)
    segs: list[tuple[float, float, str]] = []
    free = [(lo, hi)]
    for R in slabs.values():
        if R.name in (A.name, B.name) or R.frame != A.frame:
            continue
        m = _meet(R.box, zone)
        if m is None:
            continue
        for k in AXES:
            if k != axis and _rng(m, k) != _rng(zone, k):
                raise ValueError(f"{R.name} crosses joint {A.name}/{B.name} partially")
        trio = sorted((A, B, R), key=lambda q: -q.prio)
        if trio[0].prio == trio[1].prio:
            raise ValueError(f"corner of {A.name}, {B.name}, {R.name}: two of equal prio")
        r0, r1 = _rng(m, axis)
        segs.append((r0, r1, trio[0].name))
        free = _minus(free, r0, r1)
    for e0, e1, owner in spec.excl:
        for a, b in list(free):
            c0, c1 = max(a, e0), min(b, e1)
            if c1 - c0 > 1e-9:
                segs.append((c0, c1, owner))
        free = _minus(free, e0, e1)
    runs = []
    female = spec.b if spec.male == spec.a else spec.a
    for a, b in free:
        if b - a < MIN_RUN_T * t:
            segs.append((a, b, spec.male))
            continue
        n = J.finger_count(b - a, t)
        w = (b - a) / n
        run = tuple((a + i * w, b if i == n - 1 else a + (i + 1) * w,
                     spec.male if i % 2 == 0 else female) for i in range(n))
        runs.append(run)
        segs += run
    segs.sort()
    j = Joint(spec.a, spec.b, spec.male, A.frame, axis, zone, (lo, hi), tuple(segs),
              tuple(runs))
    for s0, s1, owner in segs:
        bx = j.segment_box(s0, s1)
        for q in slabs.values():
            if q.name != owner and q.frame == A.frame and _overlap(q.box, bx):
                q.lost.append(bx)
    return j


def _shape(sl: _Slab) -> Polygon:
    shape = sl.rect(sl.box)
    cuts = [sl.rect(b) for b in sl.lost] + [sl.cut_region()]
    shape = shape.difference(unary_union(cuts)).simplify(1e-9)
    if shape.geom_type != "Polygon" or not shape.is_valid or shape.is_empty:
        raise ValueError(f"panel {sl.name} is not one piece: {shape.geom_type}")
    return shape


# --- the bed and seams ------------------------------------------------------------------

def _fits(size, bed) -> bool:
    w, h = sorted(size, reverse=True)
    bw, bh = sorted(bed, reverse=True)
    return w <= bw + 1e-6 and h <= bh + 1e-6


def _overflow(name: str, size, bed, why: str = "") -> BedOverflow:
    return BedOverflow(f"{name} {size[0]:.2f} x {size[1]:.2f} mm does not fit the "
                       f"{bed[0]:g} x {bed[1]:g} mm laser bed{why}")


_PIECES = {("base", "x"): ("left", "right"), ("base", "y"): ("front", "back"),
           ("base", "z"): ("lower", "upper"),
           ("lid", "x"): ("left", "right"), ("lid", "y"): ("front", "back"),
           ("lid", "z"): ("lower", "upper")}


def _split(p: Panel, bed) -> tuple[Seam, Panel, Panel]:
    """Split ``p`` by the fingered seam nearest its middle that leaves two
    pieces fitting the bed (see the module docstring)."""
    shape, t = p.shape, p.t
    d = SEAM_DEPTH_T * t
    u0, v0, u1, v1 = shape.bounds
    keep = [Polygon(r) for r in shape.interiors]
    keep += [sbox(u - dd / 2, v - dd / 2, u + dd / 2, v + dd / 2) for u, v, dd in p.holes]
    keep += [Polygon(m) for m in p.marks]
    keep = unary_union(keep).buffer(SEAM_MARGIN) if keep else None
    best = None
    for i in (0, 1):
        lo, hi = (u0, u1) if i == 0 else (v0, v1)
        mid = (lo + hi) / 2
        cands = sorted((lo + d + k * 0.5 for k in range(int((hi - lo - 2 * d) / 0.5) + 1)),
                       key=lambda c: (abs(c - mid), c))
        for c in cands:
            line = (LineString([(c, v0 - 1), (c, v1 + 1)]) if i == 0
                    else LineString([(u0 - 1, c), (u1 + 1, c)]))
            span = shape.intersection(line)
            if span.geom_type != "LineString" or span.is_empty:
                continue
            (a0, a1) = sorted(q[1 - i] for q in span.coords)
            band = (sbox(c - d / 2, v0 - 1, c + d / 2, v1 + 1) if i == 0
                    else sbox(u0 - 1, c - d / 2, u1 + 1, c + d / 2))
            if keep is not None and band.intersects(keep):
                continue
            n = J.finger_count(a1 - a0, t)
            w = (a1 - a0) / n
            run = [(a0 + k * w, a1 if k == n - 1 else a0 + (k + 1) * w) for k in range(n)]
            if i == 0:
                low = [sbox(lo - 1, v0 - 1, c - d / 2, v1 + 1)]
                low += [sbox(c - d / 2, s0 if k else v0 - 1, c + d / 2,
                             s1 if k < n - 1 else v1 + 1)
                        for k, (s0, s1) in enumerate(run) if k % 2 == 0]
            else:
                low = [sbox(u0 - 1, lo - 1, u1 + 1, c - d / 2)]
                low += [sbox(s0 if k else u0 - 1, c - d / 2, s1 if k < n - 1 else u1 + 1,
                             c + d / 2) for k, (s0, s1) in enumerate(run) if k % 2 == 0]
            region = unary_union(low)
            a = shape.intersection(region).simplify(1e-9)
            b = shape.difference(region).simplify(1e-9)
            if a.geom_type != "Polygon" or b.geom_type != "Polygon":
                continue
            ka, kb = (_kerfed_size(a, p.kerf), _kerfed_size(b, p.kerf))
            if not (_fits(ka, bed) and _fits(kb, bed)):
                continue
            score = (a1 - a0, abs(c - mid))
            if best is None or score < best[0]:
                best = (score, i, c, a, b, run)
            break
    if best is None:
        raise _overflow(p.name, p.cut_size(), bed, ": no seam splits it into pieces that do")
    _, i, c, a, b, run = best
    axis = PLANE[p.normal][i]
    names = _PIECES[(p.frame, axis)]
    pieces = []
    for shape_k, suffix in ((a, names[0]), (b, names[1])):
        holes = tuple(h for h in p.holes if shape_k.buffer(1e-6).contains(
            sbox(h[0] - 1e-3, h[1] - 1e-3, h[0] + 1e-3, h[1] + 1e-3)))
        marks = tuple(m for m in p.marks if shape_k.buffer(1e-6).intersects(Polygon(m)))
        pieces.append(Panel(f"{p.name}-{suffix}", p.frame, p.normal, p.z0, t, shape_k, holes,
                            marks, p.kerf, p.note + f" Glued to {p.name}-"
                            f"{names[1] if suffix == names[0] else names[0]} along a finger "
                            f"seam at {axis} = {c:.2f}."))
    owners = (pieces[0].name, pieces[1].name)
    seam_run = tuple((s0, s1, owners[k % 2]) for k, (s0, s1) in enumerate(run))
    return (Seam(p.name, axis, c, owners, p.shape, (seam_run,)), pieces[0], pieces[1])


def _kerfed_size(shape: Polygon, kerf: float) -> tuple[float, float]:
    b = shape.buffer(kerf / 2, join_style=2).bounds if kerf else shape.bounds
    return b[2] - b[0], b[3] - b[1]


# --- build ------------------------------------------------------------------------------

_BUILT: dict[tuple, LaserBody] = {}


def build(lay: Layout, t: float = 3.0, kerf: float = KERF, bed=LASER_BED) -> LaserBody:
    """Every panel, joint and seam of the laser body for ``lay`` (which must
    be ``layout(t)``).  Cached on the whole layout (R27: another kit never
    gets the design kit's body) and the cut settings."""
    if abs(t - lay.wall) > 1e-9:
        raise ValueError(f"t = {t} but the layout is drawn for a {lay.wall} mm wall: "
                         f"use layout({t})")
    key = (repr(lay), t, kerf, tuple(bed))
    if key in _BUILT:
        return _BUILT[key]

    slabs = _slabs(lay, t)
    specs = _joint_specs(lay, t, slabs)
    declared = {frozenset((s.a, s.b)) for s in specs}
    names = sorted(slabs)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            A, B = slabs[a], slabs[b]
            if A.frame == B.frame and _overlap(A.box, B.box) and frozenset((a, b)) not in declared:
                raise ValueError(f"slabs {a} and {b} overlap with no joint declared")
    joints = tuple(_joint(spec, slabs, t) for spec in specs)
    slab_panels = {n: Panel(n, sl.frame, sl.normal, _rng(sl.box, sl.normal)[0], t, _shape(sl),
                            tuple(sl.holes), tuple(sl.marks), kerf, sl.note)
                   for n, sl in slabs.items()}
    out: dict[str, Panel] = {}
    seams = []
    for n, pn in slab_panels.items():
        if _fits(pn.cut_size(), bed):
            out[n] = pn
            continue
        seam, a, b = _split(pn, bed)
        seams.append(seam)
        out[a.name], out[b.name] = a, b
    body = LaserBody(t, kerf, MappingProxyType(dict(sorted(out.items()))),
                     MappingProxyType(slab_panels),
                     MappingProxyType({n: sl.cut_region() for n, sl in slabs.items()}),
                     joints, tuple(seams))
    _BUILT[key] = body
    return body


def panels(lay: Layout, t: float = 3.0, kerf: float = KERF) -> dict[str, Panel]:
    """The laser route's panels, each within the LASER_BED (split on a glued
    seam, or BedOverflow, otherwise), keyed by name."""
    return dict(build(lay, t, kerf).panels)


__all__ = ["Panel", "Joint", "Seam", "LaserBody", "build", "panels", "hinge_cutouts",
           "hinge_depth", "lid_back_z0", "plinth_walls", "BedOverflow", "KERF",
           "DECLARED_OVERLAPS"]
