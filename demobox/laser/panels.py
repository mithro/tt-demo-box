"""The laser-cut body: 3 mm plywood panels, finger-jointed, M3 T-slots.

``build(lay, t, kerf)`` makes every panel of the route from ``layout(t)``;
``panels(lay, t, kerf)`` is its panel dict.  The frames are
``demobox.layout``'s: base and drawer panels in the base frame (drawer shut),
lid panels in the lid frame (closed); ``assembly`` places them.  Only
``t == lay.wall`` makes sense (the layout is drawn for the wall it was given),
so ``--thickness`` regenerates the layout too.

Panels and joints
-----------------
Every panel starts as a *slab*: an axis-aligned box ``t`` thick, as big as the
panel including the joint zones it may own.  Where two slabs overlap is a
*joint zone* (``t`` x ``t`` along their common edge).  Each joint is declared
(``_joint_specs``; an undeclared overlap is an error) and its zone is cut
along the edge into segments, each owned by exactly one panel:

* where a third slab passes through the zone (a corner of three panels, or an
  interior panel crossing a corner), the panel of highest ``prio`` owns it:
  floor and lid back 5, front/back walls 4, side walls 3, then the inner
  panels;
* declared exclusions (an opening, a notch, the hinge channel) give a stretch
  to one panel whole;
* the rest is fingered (``joints.finger_segments``): the declared male panel
  owns the ends.  For an inner panel (deck, runners, band wall) the receiving
  panel is male, so the inner panel's fingers are tabs through mortises.

A panel's shape is its slab's rectangle less the segments others own, less its
feature cuts (openings, the channel, the knuckle relief, notches, T-slots),
with its clearance holes and engraved marks (layer ENGRAVE: the panel's name
and where printed parts are glued).

T-slots
-------
The outer boxes are screwed: on each declared joint, through the panel named
in the spec into its mate, one screw per finger run under 80 mm and two over,
at the owned fingers nearest the run's middle (or quarters) whose nut and
head stand clear of everything (``_occupied``).  The nut stands proud of the
plywood (``joints``), so where it would meet the drawer, the bank, the
retainer or a glued block, the next finger is taken.  The inner panels are
glued, held by their tabs.

Bed (R9)
--------
A panel bigger than the LASER_BED (in either orientation, kerf included) is
split by a fingered seam (``_split``): the seam line at the candidate nearest
the middle whose two pieces fit, are each one piece, and whose finger band
(SEAM_DEPTH wide) meets no mortise, hole or mark.  The base floor, the deck
and the lid back are split this way and glued along the seam; each piece is
also held at its edges by the walls.  A panel that no seam can split raises
``BedOverflow`` naming it and its size.

Functions (the printed route's, ``demobox.printed.body``)
---------------------------------------------------------
* Deck: a panel tabbed into all four walls at ``deck_z``, with the USB-C
  slot, the hinge channel's footprint (the DC lead comes up from the boost
  converter), notches round the hinge-leaf nut blocks, and a clearance hole at
  MT2.  The board stands on printed mounts glued on engraved outlines: the MT2
  standoff (screwed: M3 down through the board, the standoff and the deck into
  a square nut in a printed cup glued under the deck), the MT1 boss with a
  peg hole per revision for the loose pin, and the two plain supports.
* Heat-set inserts do not go in plywood: every screw that has one in the
  printed route goes into a square nut in a printed block glued to the panel
  (``fittings``): the hinge leaves' (base back wall, lid hinge wall), the
  bezel's three corners (blocks in the lid's gutter corners), the bezel clip's
  (a block in the band).
* Hinge: the shared knuckles, screwed through the walls; the back wall's top
  edge and the lid hinge wall's bottom edge are notched KNUCKLE_R + FIT deep
  along each knuckle group (the relief).
* Cable channel: through the back wall from the deck up, and between the two
  lid hinge-wall panels (the channel divides that wall).
* Lid: back, four walls, a band face over the band in front of the opening
  and a band wall forming the opening's front edge (the printed lid's ribbed
  band, here a closed box).
* Drawer: a finger-jointed tray.  It runs between the base's front wall and
  the drawer guide, held down by two runners over its sides.  An ear on its
  back panel runs in a slot in runner-back: the slot's ends are the cut end
  stop at ``drawer_travel`` and the stop flush when shut.  The latch is two
  MAGNET_D x MAGNET_T disc magnets pressed into printed corner blocks, one in
  the drawer's front corner (magnet up), one in the base's front corner over
  it (magnet down): FIT apart when shut, they hold it by their shear pull.
  The drawer is captive (runner-back is tabbed into both side walls): at the
  stop the bank and its packing lift out, which is what the travel is for.
  To take the drawer out the floor comes off (``DRAWER_REMOVAL``), so the
  guide's tabs are not glued into the floor.
* The boost converter sits on the floor behind the drawer in an engraved
  outline, held by hook-and-loop tape (the guide is its front fence).
* Feet (R19): the floor's screw heads stand m3.HEAD_H below it, so the box
  stands on four self-adhesive rubber feet FOOT_H tall (>= HEAD_H + FOOT_CLEAR)
  on engraved circles FOOT_INSET in from the floor's corners.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq
from shapely.geometry import LineString, Polygon, box as sbox
from shapely.ops import unary_union

import demobox  # noqa: F401  (puts the submodule on sys.path)
from demobox.geom import BedOverflow, Box
from demobox.layout import FIT, LASER_BED, MAGNET_D, MAGNET_T, Layout
from demobox.laser import joints as J
from demobox.shared import hinge as H
from demobox.shared import m3

#: Default kerf (mm), a CO2 laser in 3 mm plywood.
KERF = 0.15
#: Seam fingers' depth across the seam, in panel thicknesses.
SEAM_DEPTH_T = 2.0
#: Keep a seam's finger band this far from mortises, holes and marks.
SEAM_MARGIN = 2.0
#: Runners: how far each reaches over the drawer side it holds down.
RUNNER_LIP = 4.0
#: The drawer back's ear (in runner-back's slot): its width along Y.
EAR_W = 6.0
#: The drawer latch's printed magnet blocks (cubes); the magnets are layout.MAGNET_D x _T.
MAGNET_BLOCK = 10.0
#: Printed nut blocks: across the screw, along it; the nut's pocket from the
#: block's entry face; and the wall under it.
NUT_BLOCK = 10.0
NUT_BLOCK_D = 8.0
NUT_DEPTH = (2.0, 2.0 + J.NUT_T + 2 * J.NUT_FIT)
#: The clip's nut block (a cube on the band face).
CLIP_BLOCK = 10.0
#: The MT2 nut cup under the deck (side; height below the deck).
CUP = 10.0
CUP_H = NUT_DEPTH[1] + 2.0
#: Two screws on a finger run at least this long, else one.
TWO_SCREWS = 80.0
#: Engraved label height.
LABEL_H = 4.0
#: Self-adhesive rubber feet (bought; R19): diameter, height, centre in from
#: the floor's outside corners; they must stand FOOT_CLEAR below the heads.
FOOT_D = 12.0
FOOT_H = 4.0
FOOT_INSET = 12.0
FOOT_CLEAR = 1.0
if FOOT_H < m3.HEAD_H + FOOT_CLEAR:
    raise ValueError(f"feet {FOOT_H} mm do not clear the floor's {m3.HEAD_H} mm screw heads")
#: How to take the drawer out (its note and the docstring).
DRAWER_REMOVAL = ("To take the drawer out: empty it, stand the box on the table edge, unscrew "
                  "the floor's T-slot screws from below and lower the floor out of the walls "
                  "(its fingers and the guide's tabs slide straight out downward) with the "
                  "drawer on it. Do not glue the guide's tabs into the floor.")


def feet(lay: Layout) -> tuple[tuple[float, float], ...]:
    """(x, y) of the four feet under the base floor, base frame."""
    o, i = lay.outer, FOOT_INSET
    return ((o.x0 + i, o.y0 + i), (o.x1 - i, o.y0 + i), (o.x0 + i, o.y1 - i),
            (o.x1 - i, o.y1 - i))

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
    ``PLANE[normal]``, which are its frame's coordinates), clearance holes
    (u, v, d), engraved marks and label, and where it sits: ``frame`` ("base",
    "drawer" or "lid"), its normal and the low face ``z0`` along it."""

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
    """A joint between slabs ``a`` and ``b``: its zone, the edge ``axis``,
    the zone's ``interval`` along it cut into ``segments`` (lo, hi, owner);
    ``runs`` are the fingered stretches (the rest is corners and exclusions)."""

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
class Screw:
    """An M3 x TSLOT_SCREW T-slot screw: through panel ``through`` into
    ``into``'s edge at ``at`` (the entry point, mid-thickness of ``into``),
    going ``direction``.  ``nut`` and ``head`` are its keep-outs."""

    through: str
    into: str
    frame: str
    at: tuple[float, float, float]
    direction: tuple[float, float, float]
    nut: Box
    head: Box


@dataclass(frozen=True)
class Seam:
    """A split (R9): panel ``name`` cut at ``axis`` = ``at`` into ``pieces``
    along a finger seam (``runs``: the band's segments, owner = piece)."""

    name: str
    axis: str
    at: float
    pieces: tuple[str, str]
    whole: Polygon
    runs: tuple[tuple[tuple[float, float, str], ...], ...]


@dataclass
class _Slab:
    name: str
    frame: str
    normal: str
    box: Box
    prio: int
    cuts: list[Box] = field(default_factory=list)       # feature cuts (through)
    polys: list[list[tuple[float, float]]] = field(default_factory=list)  # (u, v) cuts
    adds: list[Box] = field(default_factory=list)
    holes: list[tuple[float, float, float]] = field(default_factory=list)
    marks: list[tuple[tuple[float, float], ...]] = field(default_factory=list)
    lost: list[Box] = field(default_factory=list)       # joint segments others own
    note: str = ""

    @property
    def t(self) -> float:
        lo, hi = _rng(self.box, self.normal)
        return hi - lo

    def rect(self, b: Box) -> Polygon:
        a, c = PLANE[self.normal]
        (u0, u1), (v0, v1) = _rng(b, a), _rng(b, c)
        return sbox(u0, v0, u1, v1)

    def uv(self, p) -> tuple[float, float]:
        a, c = PLANE[self.normal]
        d = dict(zip(AXES, p))
        return d[a], d[c]


@dataclass(frozen=True)
class _Spec:
    a: str
    b: str
    male: str
    excl: tuple[tuple[float, float, str], ...] = ()
    screws: str | None = None


@dataclass
class LaserBody:
    """Everything ``build`` makes."""

    t: float
    kerf: float
    panels: dict[str, Panel]
    slab_panels: dict[str, Panel]
    slab_cuts: dict[str, list[Box]]
    joints: tuple[Joint, ...]
    screws: tuple[Screw, ...]
    seams: tuple[Seam, ...]
    placed: tuple[tuple[str, str, str, cq.Shape], ...]   # (part, instance, frame, solid)
    printed: dict[str, cq.Shape]                         # laser-only printed part -> solid

    def panel_at(self, prefix: str, p) -> Panel:
        """The panel named ``prefix`` (or a piece of it, ``prefix-*``)
        whose box holds point ``p``."""
        for n, pn in self.panels.items():
            if n == prefix or n.startswith(prefix + "-"):
                b = pn.box()
                if all(lo - 1e-6 <= v <= hi + 1e-6 for v, (lo, hi) in
                       zip(p, (_rng(b, a) for a in AXES))):
                    return pn
        raise KeyError(f"no panel {prefix!r} at {p}")


# --- the geometry ---------------------------------------------------------------------

def _drawer_box(lay: Layout) -> Box:
    w, bay = lay.wall, lay.bay
    return Box(lay.cable_bay.x0 - w, bay.y0 - w, bay.z0 - w, bay.x1 + w, bay.y1 + w, bay.z1,
               "drawer")


def _opening(lay: Layout) -> Box:
    """The drawer opening in the base's left wall (through its front corner
    column: the front wall owns that column there)."""
    d = _drawer_box(lay)
    return Box(0.0, 0.0, 0.0, lay.wall, d.y1 + FIT, d.z1 + FIT, "drawer opening")


def _runner_z(lay: Layout) -> tuple[float, float]:
    z0 = _drawer_box(lay).z1 + FIT
    return z0, z0 + lay.wall


def _ear(lay: Layout) -> Box:
    d, w = _drawer_box(lay), lay.wall
    z0, z1 = _runner_z(lay)
    return Box(d.x1 - w, lay.bay.y1 - EAR_W, d.z1, d.x1, lay.bay.y1, z1, "drawer stop ear")


def _magnet_xy(lay: Layout) -> tuple[float, float]:
    d, w = _drawer_box(lay), lay.wall
    return w + MAGNET_BLOCK / 2, d.y0 + w + MAGNET_BLOCK / 2


def clip_screws(lay: Layout, t: float) -> tuple[tuple[float, float], ...]:
    """(x, y) of the bezel clip's screw, closed lid frame: in the middle of
    its nut block, which sits on the band face in the corner of the lid's
    left wall and the band wall."""
    p = lay.lid_pocket
    return ((t + CLIP_BLOCK / 2, p.y0 - t - CLIP_BLOCK / 2),)


def _slabs(lay: Layout, t: float) -> dict[str, _Slab]:
    W, D, Hh = lay.outer.x1, lay.outer.y1, lay.outer.z1
    hy, hz = lay.hinge_axis
    dz = lay.deck_z
    d = _drawer_box(lay)
    op = _opening(lay)
    rz0, rz1 = _runner_z(lay)
    us, ch = lay.usb_slot, lay.hinge_cable_channel
    ear = _ear(lay)
    gy0 = d.y1 + FIT
    s: dict[str, _Slab] = {}

    def add(name, frame, normal, box, prio, note=""):
        s[name] = _Slab(name, frame, normal, box, prio, note=note)
        return s[name]

    # --- base -------------------------------------------------------------------------
    floor = add("base-floor", "base", "z", Box(0, 0, 0, W, D, t), 5,
                "Base floor. T-slot screws up through it into the walls; rubber feet on the "
                "engraved circles underneath. Comes off to take the drawer out.")
    bp = lay.boost_pocket
    floor.marks.append(tuple(sbox(bp.x0, bp.y0, bp.x1, bp.y1).exterior.coords))
    floor.marks += [_circle(x, y, FOOT_D / 2) for x, y in feet(lay)]
    add("base-front", "base", "y", Box(0, 0, 0, W, t, Hh), 4, "Base front wall.")
    back = add("base-back", "base", "y", Box(0, D - t, 0, W, D, Hh), 4,
               "Base back wall: hinge leaf screws into nut blocks behind it.")
    left = add("base-left", "base", "x", Box(0, 0, 0, t, D, Hh), 3,
               "Base left wall, with the drawer opening.")
    add("base-right", "base", "x", Box(W - t, 0, 0, W, D, Hh), 3, "Base right wall.")
    deck = add("deck", "base", "z", Box(0, 0, dz - t, W, D, dz), 1,
               "Deck: board mounts glued on the engraved outlines.")
    guide = add("drawer-guide", "base", "y", Box(bp.x1 + FIT, gy0, 0, W, gy0 + t, rz1), 1,
                "Drawer guide: the drawer's back side runs along it. Glue it to runner-back "
                "and the right wall, not to the floor.")
    rb = add("runner-back", "base", "z", Box(0, ear.y0 - FIT - RUNNER_LIP, rz0, W, gy0 + t, rz1),
             1, "Runner over the drawer's back side; its slot takes the drawer's ear (the "
                "stops). Screwed down to the guide; the drawer is captive.")
    add("runner-front", "base", "z",
        Box(t + MAGNET_BLOCK, 0, rz0, us.x0 - FIT, d.y0 + t + RUNNER_LIP, rz1), 1,
        "Runner over the drawer's front side.")

    left.cuts.append(op)
    back.cuts.append(Box(ch.x0, D - t, dz, ch.x1, D, Hh, "hinge cable channel"))
    for g0, g1 in H.hinge_groups(lay):
        back.cuts.append(Box(g0 - FIT, D - t, hz - H.KNUCKLE_R - FIT, g1 + FIT, D, Hh,
                             "knuckle relief"))
    for x, z in H.base_leaf_screws(lay):
        back.holes.append((x, z, m3.CLEARANCE_D))
    deck.cuts += [Box(us.x0, 0, dz - t, us.x1, us.y1, dz, "USB-C slot"),
                  Box(ch.x0, ch.y0, dz - t, ch.x1, D, dz, "hinge cable channel")]
    for x, _ in H.base_leaf_screws(lay):
        deck.cuts.append(Box(x - NUT_BLOCK / 2 - FIT, D - t - NUT_BLOCK_D - FIT, dz - t,
                             x + NUT_BLOCK / 2 + FIT, D, dz, "nut block notch"))
    for c in lay.standoffs:
        deck.holes.append((c.cx, c.cy, m3.CLEARANCE_D))
    for c in (*lay.standoffs, *lay.supports):
        deck.marks.append(_circle(c.cx, c.cy, c.r))
    b = lay.mt1_boss
    deck.marks.append(tuple(LineString([(b.x0, b.y0), (b.x1, b.y1)]).buffer(b.r, 16)
                            .exterior.coords))
    slot_x0 = d.x1 - t - lay.drawer_travel
    rb.cuts.append(Box(slot_x0, ear.y0 - FIT, rz0, d.x1, ear.y1 + FIT, rz1, "ear slot"))
    guide.note += " Guide x0 clears the boost converter."

    # --- drawer -----------------------------------------------------------------------
    add("drawer-floor", "drawer", "z", Box(d.x0, d.y0, d.z0, d.x1, d.y1, d.z0 + t), 5,
        "Drawer floor. " + DRAWER_REMOVAL)
    face = add("drawer-face", "drawer", "x", Box(d.x0, d.y0, d.z0, d.x0 + t, d.y1, d.z1), 4,
               "Drawer face, with the finger hole over the bank's button.")
    dback = add("drawer-back", "drawer", "x", Box(d.x1 - t, d.y0, d.z0, d.x1, d.y1, d.z1), 4,
                "Drawer back; its ear runs in runner-back's slot.")
    add("drawer-side-front", "drawer", "y", Box(d.x0, d.y0, d.z0, d.x1, d.y0 + t, d.z1), 3,
        "Drawer front side.")
    add("drawer-side-back", "drawer", "y", Box(d.x0, d.y1 - t, d.z0, d.x1, d.y1, d.z1), 3,
        "Drawer back side.")
    fh = lay.drawer_face_hole              # a Stadium along X: centres (y, z) = (u, v)
    if fh.axis != face.normal:
        raise ValueError(f"{fh.what} runs along {fh.axis}, the face's normal is {face.normal}")
    hole = LineString([(fh.x0, fh.y0), (fh.x1, fh.y1)]).buffer(fh.r, 16)
    face.polys.append(list(hole.exterior.coords)[:-1])
    dback.adds.append(ear)

    # --- lid ----------------------------------------------------------------------------
    lo, p = lay.lid_outer, lay.lid_pocket
    Lz = lo.z1
    add("lid-back", "lid", "z", Box(0, -D, Lz - t, W, 0, Lz), 5, "Lid back (outside top).")
    add("lid-front", "lid", "y", Box(0, -D, 0, W, -D + t, Lz), 4, "Lid front wall.")
    hl = add("lid-hinge-left", "lid", "y", Box(0, -t, 0, ch.x0, 0, Lz), 4,
             "Lid hinge wall, left of the cable channel.")
    hr = add("lid-hinge-right", "lid", "y", Box(ch.x1, -t, 0, W, 0, Lz), 4,
             "Lid hinge wall, right of the cable channel.")
    add("lid-left", "lid", "x", Box(0, -D, 0, t, 0, Lz), 3, "Lid left wall.")
    add("lid-right", "lid", "x", Box(W - t, -D, 0, W, 0, Lz), 3, "Lid right wall.")
    bf = add("lid-band-face", "lid", "z", Box(0, -D, 0, W, p.y0, t), 2,
             "Lid band face (screen side, in front of the opening).")
    add("lid-band-wall", "lid", "y", Box(0, p.y0 - t, 0, W, p.y0, Lz), 1,
        "Lid band wall: the opening's front edge.")
    for g0, g1 in H.hinge_groups(lay):
        for sl in (hl, hr):
            if g0 < sl.box.x1 and g1 > sl.box.x0:
                sl.cuts.append(Box(g0 - FIT, -t, 0, g1 + FIT, 0, H.KNUCKLE_R + FIT,
                                   "knuckle relief"))
    for x, z in H.lid_leaf_screws(lay):
        sl = hl if x < ch.x0 else hr
        sl.holes.append((x, z, m3.CLEARANCE_D))
    for x, y in clip_screws(lay, t):
        bf.holes.append((x, y, m3.CLEARANCE_D))
    for c in lay.lid_catch:        # the lid catch's magnets press into the band face
        m = lay.catch_lid_magnet(c)
        bf.holes.append((m.cx, m.cy, MAGNET_D))
    return s


def _circle(x, y, r, n=48) -> tuple[tuple[float, float], ...]:
    pts = tuple((x + r * math.cos(2 * math.pi * i / n), y + r * math.sin(2 * math.pi * i / n))
                for i in range(n))
    return pts + (pts[0],)


def _joint_specs(lay: Layout, t: float) -> list[_Spec]:
    op = _opening(lay)
    us, ch = lay.usb_slot, lay.hinge_cable_channel
    leaf = tuple((x - NUT_BLOCK / 2 - FIT, x + NUT_BLOCK / 2 + FIT, "base-back")
                 for x, _ in H.base_leaf_screws(lay))
    S = _Spec
    return [
        # base box, screwed
        S("base-floor", "base-front", "base-floor", screws="base-floor"),
        S("base-floor", "base-back", "base-floor", screws="base-floor"),
        S("base-floor", "base-left", "base-floor", ((0.0, op.y1, "base-floor"),),
          screws="base-floor"),
        S("base-floor", "base-right", "base-floor", screws="base-floor"),
        S("base-front", "base-left", "base-front", ((0.0, op.z1, "base-front"),),
          screws="base-front"),
        S("base-front", "base-right", "base-front", screws="base-front"),
        S("base-back", "base-left", "base-back", screws="base-back"),
        S("base-back", "base-right", "base-back", screws="base-back"),
        # inner panels, tabbed and glued
        S("deck", "base-front", "base-front", ((us.x0, us.x1, "base-front"),)),
        S("deck", "base-back", "base-back", ((ch.x0, ch.x1, "base-back"),) + leaf),
        S("deck", "base-left", "base-left"),
        S("deck", "base-right", "base-right"),
        S("drawer-guide", "base-floor", "base-floor"),
        S("drawer-guide", "base-right", "base-right"),
        S("drawer-guide", "runner-back", "runner-back", screws="runner-back"),
        S("runner-back", "base-left", "base-left"),
        S("runner-back", "base-right", "base-right"),
        S("runner-front", "base-front", "base-front"),
        # drawer tray, glued
        S("drawer-floor", "drawer-face", "drawer-floor"),
        S("drawer-floor", "drawer-back", "drawer-floor"),
        S("drawer-floor", "drawer-side-front", "drawer-floor"),
        S("drawer-floor", "drawer-side-back", "drawer-floor"),
        S("drawer-face", "drawer-side-front", "drawer-face"),
        S("drawer-face", "drawer-side-back", "drawer-face"),
        S("drawer-back", "drawer-side-front", "drawer-back"),
        S("drawer-back", "drawer-side-back", "drawer-back"),
        # lid box, screwed
        S("lid-back", "lid-front", "lid-back", screws="lid-back"),
        S("lid-back", "lid-hinge-left", "lid-back", screws="lid-back"),
        S("lid-back", "lid-hinge-right", "lid-back", screws="lid-back"),
        S("lid-back", "lid-left", "lid-back", screws="lid-back"),
        S("lid-back", "lid-right", "lid-back", screws="lid-back"),
        S("lid-front", "lid-left", "lid-front", screws="lid-front"),
        S("lid-front", "lid-right", "lid-front", screws="lid-front"),
        S("lid-hinge-left", "lid-left", "lid-hinge-left", screws="lid-left"),
        S("lid-hinge-right", "lid-right", "lid-hinge-right", screws="lid-right"),
        # lid band, tabbed and glued
        S("lid-band-face", "lid-front", "lid-front"),
        S("lid-band-face", "lid-left", "lid-left"),
        S("lid-band-face", "lid-right", "lid-right"),
        S("lid-band-wall", "lid-band-face", "lid-band-face"),
        S("lid-band-wall", "lid-back", "lid-back"),
        S("lid-band-wall", "lid-left", "lid-left"),
        S("lid-band-wall", "lid-right", "lid-right"),
    ]


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
        n = J.finger_count(b - a, t)
        w = (b - a) / n
        run = tuple((a + i * w, b if i == n - 1 else a + (i + 1) * w,
                     spec.male if i % 2 == 0 else female) for i in range(n))
        runs.append(run)
        segs += run
    segs.sort()
    j = Joint(spec.a, spec.b, spec.male, A.frame, axis, zone, (lo, hi), tuple(segs),
              tuple(runs))
    # the panels in the zone lose what they do not own
    for s0, s1, owner in segs:
        bx = j.segment_box(s0, s1)
        for q in slabs.values():
            if q.name != owner and q.frame == A.frame and _overlap(q.box, bx):
                q.lost.append(bx)
    return j


def _screws(spec: _Spec, j: Joint, slabs: dict[str, _Slab], occupied) -> list[Screw]:
    """T-slot screws on a joint (see the module docstring)."""
    if spec.screws is None:
        return []
    A = slabs[spec.screws]
    B = slabs[spec.b if spec.screws == spec.a else spec.a]
    na, nb = A.normal, B.normal
    a0, a1 = _rng(A.box, na)
    sign = 1.0 if _rng(B.box, na)[1] > a1 + 1e-9 else -1.0
    entry = a1 if sign > 0 else a0
    b0, b1 = _rng(j.zone, nb)
    bmid = (b0 + b1) / 2
    y0, y1 = J.nut_pocket(A.t)
    out = []
    for run in j.runs:
        lo, hi = run[0][0], run[-1][1]
        targets = ([(lo + hi) / 2] if hi - lo < TWO_SCREWS
                   else [lo + (hi - lo) / 4, lo + 3 * (hi - lo) / 4])
        owned = [((s0 + s1) / 2) for s0, s1, o in run if o == A.name]
        used: set[float] = set()
        for tgt in targets:
            for m in sorted(owned, key=lambda c: (abs(c - tgt), c)):
                if m in used:
                    continue
                at = {j.axis: m, nb: bmid, na: entry}
                nut = _mk({j.axis: (m - J.NUT_W / 2, m + J.NUT_W / 2),
                           nb: (bmid - J.NUT_W / 2, bmid + J.NUT_W / 2),
                           na: tuple(sorted((entry + sign * (y0 + J.NUT_FIT),
                                             entry + sign * (y1 - J.NUT_FIT))))}, "nut")
                face = entry - sign * A.t
                head = _mk({j.axis: (m - m3.HEAD_R, m + m3.HEAD_R),
                            nb: (bmid - m3.HEAD_R, bmid + m3.HEAD_R),
                            na: tuple(sorted((face, face - sign * m3.HEAD_H)))}, "head")
                if any(_overlap(k, nut) or _overlap(k, head) for k in occupied(A, B)):
                    continue
                used.add(m)
                d = {na: sign, nb: 0.0, j.axis: 0.0}
                out.append(Screw(A.name, B.name, A.frame, (at["x"], at["y"], at["z"]),
                                 (d["x"], d["y"], d["z"]), nut, head))
                # the T-slot in B (edge-local x along the axis, y along the screw)
                pts = []
                for x, y in J.tslot(m, A.t):
                    p = {j.axis: x, na: entry + sign * y, nb: bmid}
                    pts.append(B.uv((p["x"], p["y"], p["z"])))
                B.polys.append(pts)
                pa = {j.axis: m, nb: bmid, na: entry}
                A.holes.append((*A.uv((pa["x"], pa["y"], pa["z"])), m3.CLEARANCE_D))
                break
    return out


def _shape(sl: _Slab) -> Polygon:
    shape = sl.rect(sl.box)
    if sl.adds:
        shape = unary_union([shape, *(sl.rect(b) for b in sl.adds)])
    cuts = [sl.rect(b) for b in (*sl.lost, *sl.cuts)] + [Polygon(p) for p in sl.polys]
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
           ("lid", "x"): ("left", "right"), ("lid", "y"): ("front", "hinge"),
           ("drawer", "x"): ("left", "right"), ("drawer", "y"): ("front", "back")}


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
    """Every panel, joint, screw, seam and glued printed part of the laser
    body for ``lay`` (which must be ``layout(t)``)."""
    if abs(t - lay.wall) > 1e-9:
        raise ValueError(f"t = {t} but the layout is drawn for a {lay.wall} mm wall: "
                         f"use layout({t})")
    key = (lay.wall, t, kerf, tuple(bed))
    if key in _BUILT:
        return _BUILT[key]
    from demobox.laser import fittings as F

    slabs = _slabs(lay, t)
    specs = _joint_specs(lay, t)
    declared = {frozenset((s.a, s.b)) for s in specs}
    names = sorted(slabs)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            A, B = slabs[a], slabs[b]
            if A.frame == B.frame and _overlap(A.box, B.box) and frozenset((a, b)) not in declared:
                raise ValueError(f"slabs {a} and {b} overlap with no joint declared")
    placed = F.placed(lay, t)
    keepouts = F.keepouts(lay, t)

    def occupied(A, B):
        out = [q.box for q in slabs.values() if q.frame == A.frame and q.name not in
               (A.name, B.name)]
        out += [b for f, b in keepouts if f == A.frame]
        out += [Box(*_bb(s)) for _, _, f, s in placed if f == A.frame]
        return out

    joints, screws = [], []
    for spec in specs:
        j = _joint(spec, slabs, t)
        joints.append(j)
    for spec, j in zip(specs, joints):
        screws += _screws(spec, j, slabs, occupied)
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
    body = LaserBody(t, kerf, dict(sorted(out.items())), slab_panels,
                     {n: list(sl.cuts) for n, sl in slabs.items()}, tuple(joints),
                     tuple(screws), tuple(seams), tuple(placed), F.laser_printed(lay, t))
    _BUILT[key] = body
    return body


def _bb(s: cq.Shape) -> tuple[float, ...]:
    b = s.BoundingBox()
    return b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax


def panels(lay: Layout, t: float = 3.0, kerf: float = KERF) -> dict[str, Panel]:
    """The laser route's panels, each within the LASER_BED (BedOverflow
    otherwise), keyed by name."""
    return build(lay, t, kerf).panels


# --- re-exported for the route's users ------------------------------------------------

#: Pairs of assembly names allowed to interpenetrate.  None: the fingers are
#: modelled nominal, so they interlock face to face; the screws are not
#: modelled (their nuts and heads are ``hw:`` keep-outs); the magnets sit in
#: their blocks' holes exactly.
DECLARED_OVERLAPS: frozenset[frozenset[str]] = frozenset()


def assembly(angle_deg: float, drawer_out: float, **kw):
    from demobox.laser import fittings as F
    return F.assembly(angle_deg, drawer_out, **kw)


def printed_parts(lay: Layout, t: float = 3.0):
    from demobox.laser import fittings as F
    return F.printed_parts(lay, t)


def hardware(lay: Layout, t: float = 3.0) -> dict[str, int]:
    from demobox.laser import fittings as F
    return F.hardware(lay, t)


__all__ = ["Panel", "Joint", "Screw", "Seam", "LaserBody", "build", "panels", "assembly",
           "printed_parts", "hardware", "clip_screws", "KERF", "MAGNET_D", "MAGNET_T",
           "DECLARED_OVERLAPS"]
