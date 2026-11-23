"""The 3D-printed body: base tub, deck, lid and drawer, and the assembly.

Frames are ``demobox.layout``'s: the base, deck and drawer are built in the
base frame (drawer shut), the lid in the lid frame (closed); ``assembly``
places everything in the base frame.

Base (``base_tub``)
-------------------
A tub: floor and four walls, ``wall`` thick, open at the top, printed floor
down.  The deck is a separate part (``deck``) because a deck moulded into the
tub would be a 205 x 210 mm ceiling over the drawer cavity in any print
orientation; it rests on a LEDGE all round the walls (45 degree undersides,
so they print without support) and is screwed into a heat-set insert in a
block in each corner.  The tub has:

* the drawer opening in the left wall: the drawer's section plus FIT, its
  top a row of 45 degree peaks (``opening_profile``) so it prints with no
  bridge (a flat 88 mm top would sag onto the drawer); the drawer's face has
  the same peaks, FIT smaller, so the face still fills the opening;
* two floor rails (RAIL_W x RAIL_H) the drawer's floor grooves run on, and
  an inward stop bar behind the drawer;
* the drawer detent: a groove in the front wall's inner face that the drawer's
  bump runs in, a ramped ridge that the bump clicks over into the closed
  position, and the groove's square far end, which the bump's square face
  meets with the drawer out by ``drawer_travel`` (the end stop).  A pad
  PAD_T proud on the wall's outer face behind the groove keeps the wall
  ``wall`` thick there (the inner face is the drawer's running face, so the
  pad cannot go inside).  The pad's face is at y = -PAD_T (-1.0): it stands
  outside ``Layout.outer``, whose front stays at y = 0;
* a fence round ``boost_pocket`` on the floor behind the drawer (the left wall
  is its fourth side, the drawer its open front);
* the hinge cable channel's base part (``channel_parts``): deck to the axis,
  through the back wall;
* a KNUCKLE_R + FIT relief round the hinge axis along each knuckle group, so
  the shared knuckles can turn (they sit in the body's back-top corner);
* a boss behind each of the base hinge leaf's screws with a heat-set insert
  (the 2.4 mm wall is too thin for the 5.7 mm insert).

Deck (``deck``)
---------------
The plate FIT inside the walls, with the USB-C slot, the hinge channel's
footprint (so the boost cable's DC lead comes up from the converter below),
notches round the leaf-screw bosses, the MT2 standoff with its heat-set
insert, the MT1 boss with a PEG_DIA hole per revision for the loose pin, and
the plain supports.

Drawer (``drawer``)
-------------------
Face, floor, sides and back round ``cable_bay`` + ``bay``; the face is the
base's left wall at the opening and carries the finger hole.  Floor grooves
for the rails.  The detent: a tongue cut free in the front side wall (slots
round three sides, thinned on its inside), with the bump on its free end:
square on the -X side (the stop face), a 45 degree ramp on the +X side so it
cams over the opening's edge when the drawer is first pushed in.  The drawer
is captive: to take it out, pull it to the stop, lift out the bank and its
packing, and pull the tongue in (towards the bay) with a fingertip while
sliding the drawer out.

Lid (``lid``)
-------------
The lid outer box less the pocket and gutters (open on the screen side),
less the hinge cable channel's lid part, the knuckle relief, a boss with a
heat-set insert behind each lid leaf screw, and a corner boss with a heat-set
insert under each of the bezel's screws (``inserts.bezel_screws``, R15).

The band between the opening's front edge and the lid's front wall is hollow
(R18, ``front_cavities``): ``wall`` all round, closed, with ribs ``wall``
thick running along X so no cell is wider than RIB_SPAN_MAX; printed back
down, the screen-side skin bridges one cell.  Nothing else in the lid is
thicker than ``wall`` except the bosses.

Bezel clip (R17).  The opening corner that has no bezel screw (the pocket's
front-left corner: the panel leaves no room for a boss) is held by
``bezel_clip``, a flat printed plate CLIP_T thick lying on the lid's screen
face over the bezel's corner (CLIP_OVER onto it), screwed into a heat-set
insert in a column in the band (``clip_screw``).  The bezel drops straight in;
the clip clamps its corner face to face (the bezel's front is flush with the
lid's face).  Fit the bezel, screw its three corners, then the clip.  (A lip
moulded on the lid would have been a cantilever over air when the lid prints
screen side up.)

Thickness (R18)
---------------
No body is a solid lump: ``mean_thickness`` (2 V / A) of a shell of uniform
thickness t is t (the two faces share the volume), and the bodies' bosses,
ledges and ribs lift it a little (lid 1.03 x wall, base 1.00).  A solid
region of any size lifts it a lot: the lid with its front band left solid
scores 2.71 x wall.  ``MAX_MEAN_THICKNESS`` = 1.25 x wall sits between.

Bed
---
``printed_parts`` returns every printed part with the turn that lays it on
the bed (``print_orientation``, from ``PRINT_POSE``) and checks it against
the bed: a base or lid that does not
fit is split (``split_base``/``split_lid``) at the shortest section into two
pieces joined by M3 screws into heat-set inserts plus two dowel pins per
joint block; any other part, or a piece that still does not fit, raises
``BedOverflow`` naming the part and its size.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq

import demobox  # noqa: F401  (puts the submodule on sys.path)
from demobox.checks import MIN_BOSS_WALL, panel_in_lid
from demobox.geom import BedOverflow, Box
from demobox.layout import (FIT, HEATSET_DEPTH, HEATSET_HOLE_D, INSERT_MATERIAL, PEG_DIA,
                            PRINT_BED, ROUTES, Layout, layout)
from demobox.parts.batteries import BATTERIES
from demobox.parts.board import board_spec
from demobox.parts.monitors import MONITORS
from demobox.shared import hinge as H
from demobox.shared import inserts as I
from demobox.shared import m3
from demobox.shared.packing import battery_packing
from demobox.shared.pin import locating_pin

# --- design choices ------------------------------------------------------------
#: Plastic round a heat-set insert's hole, and beyond its end.
BOSS_WALL = 1.6
INSERT_FLOOR = 1.5
BOSS_R = HEATSET_HOLE_D / 2 + BOSS_WALL
#: Deck ledge round the tub walls (45 degree underside) and the corner blocks
#: the deck is screwed to (side, height).
LEDGE = 3.0
DECK_BLOCK = 10.0
DECK_BLOCK_H = 16.0
#: Drawer floor rails: width, height, distance in from the bay's sides; the
#: drawer's grooves are FIT wider each side and GROOVE_CLEAR above the rail.
RAIL_W = 3.0
RAIL_H = 0.8
RAIL_INSET = 10.0
GROOVE_CLEAR = 0.4
#: Inward stop bar behind the drawer (thickness, height).
STOP_BAR_T = 3.0
STOP_BAR_H = 8.0
#: Boost converter fence (thickness, height).
FENCE_T = 1.6
FENCE_H = 6.0
#: Detent.  The tongue: length (root at +X), height, thickness left after
#: thinning, slot width round it, how far up the drawer wall it starts.  The
#: bump: width of its square-faced top, how far it stands off the drawer side
#: (FIT + into the groove), its height margin inside the tongue.  The groove
#: in the base's front wall, and the ridge in it (45 degree flanks).
TONGUE_LEN = 22.0
TONGUE_H = 12.0
TONGUE_T = 1.4
TONGUE_SLOT = 1.0
TONGUE_Z = 10.0
BUMP_W = 2.0
BUMP_H = 1.3
BUMP_MARGIN = 2.0
GROOVE_D = 1.0
RIDGE_H = 0.6
#: The groove's end (the stop) stays this far in from the left wall.
DETENT_MARGIN = 3.0
#: Pad on the front wall's outer face behind the detent groove, so the wall
#: there is still ``wall`` thick (GROOVE_D thick, PAD_MARGIN beyond the
#: groove, 45 degree top and bottom).  It goes outside because the inner face
#: is the drawer's running face (FIT from the drawer's side).
PAD_T = GROOVE_D
PAD_MARGIN = 3.0
#: Bezel clip (R17): plate thickness, overlap onto the bezel, length along the
#: opening's edge, margin round its screw.
CLIP_T = 1.2
CLIP_OVER = 3.0
CLIP_LEN = 20.0
CLIP_MARGIN = 4.0
#: Lid front band ribs: no cell of the cavity wider than this (the skin's
#: bridge when printed).
RIB_SPAN_MAX = 25.0
#: Drawer opening top: 45 degree peaks no wider than this.
OPENING_PITCH = 10.0
#: Split joints: a block JOINT_B across the wall, JOINT_L each side of the
#: plane; floor blocks JOINT_H tall, hanging (under-deck, under the lid's back
#: plate) blocks JOINT_HANG tall with a 45 degree underside.  Steel dowels
#: PIN_D x 2 PIN_DEPTH in PIN_HOLE_D holes.
JOINT_B = 10.0
JOINT_L = 8.0
JOINT_H = 18.0
JOINT_HANG = 23.0
PIN_D = 3.0
PIN_HOLE_D = 3.2
PIN_DEPTH = 5.0
SCREW_CLEAR_D = m3.CLEARANCE_D
#: Head access pocket behind a lid joint screw (length along the screw).
ACCESS_L = 14.0
#: Candidate split planes are tried this far apart.
SPLIT_STEP = 5.0

if BOSS_WALL < MIN_BOSS_WALL:
    raise ValueError(f"BOSS_WALL {BOSS_WALL} < MIN_BOSS_WALL {MIN_BOSS_WALL}")

#: The assembly's default monitor, bank and board revision.
ASSEMBLY_MONITOR = "taobao-tim"
ASSEMBLY_BANK = "xiaomi-pb2020"
ASSEMBLY_BOARD = "v3.2"
#: Pairs of assembly names allowed to interpenetrate (fasteners).  None are
#: modelled -- screws, inserts, the hinge bolts and dowels are bought parts --
#: so nothing is declared.
DECLARED_OVERLAPS: frozenset[frozenset[str]] = frozenset()

COLOURS: dict[str, tuple[float, float, float]] = {
    "base": (0.22, 0.24, 0.28), "deck": (0.30, 0.32, 0.36), "lid": (0.22, 0.24, 0.28),
    "drawer": (0.90, 0.45, 0.10), "hinge-base": (0.62, 0.62, 0.62),
    "hinge-lid": (0.62, 0.62, 0.62), "bezel": (0.08, 0.08, 0.08),
    "bezel-clip": (0.08, 0.08, 0.08), "hw": (0.75, 0.75, 0.78),
    "retainer": (0.35, 0.35, 0.35), "packing": (0.20, 0.50, 0.85),
    "mt1-pin": (0.95, 0.85, 0.20), "bank": (0.85, 0.85, 0.85), "panel": (0.02, 0.02, 0.05),
    "monitor-driver": (0.10, 0.45, 0.20), "board": (0.05, 0.40, 0.15),
}


# --- records -------------------------------------------------------------------------

@dataclass(frozen=True)
class HeatSet:
    """An M3 heat-set insert hole: its mouth, the unit direction into it."""

    at: tuple[float, float, float]
    axis: tuple[float, float, float]
    what: str


@dataclass(frozen=True)
class Printed:
    """A printed part in its design frame, the turn (axis, degrees about the
    origin) that lays it flat on the bed, a print note, and its inserts."""

    solid: cq.Shape
    print_orientation: tuple[tuple[float, float, float], float]
    note: str
    heatsets: tuple[HeatSet, ...] = ()


@dataclass(frozen=True)
class Joint:
    """One joint block of a split: the wall it is on, its level, the screw's
    and the dowel's points on the split plane, and the block."""

    wall: str
    level: str
    screw: tuple[float, float, float]
    pin: tuple[float, float, float]
    block: Box


@dataclass(frozen=True)
class Split:
    axis: str                         # "x" or "y": the split plane is axis = at
    at: float
    joints: tuple[Joint, ...]
    candidates: tuple[float, ...]     # every plane tried that could be joined


# --- small solids --------------------------------------------------------------------

def _box(x0, y0, z0, x1, y1, z1) -> cq.Solid:
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def _bx(b: Box) -> cq.Solid:
    return _box(b.x0, b.y0, b.z0, b.x1, b.y1, b.z1)


def _cyl(p, d, r, length) -> cq.Solid:
    return cq.Solid.makeCylinder(r, length, cq.Vector(*p), cq.Vector(*d))


def _prism_x(pts, x0, x1) -> cq.Solid:
    """A (y, z) polygon extruded along X from x0 to x1."""
    return cq.Workplane("YZ", origin=(x0, 0, 0)).polyline(pts).close().extrude(x1 - x0).val()


def _prism_y(pts, y0, y1) -> cq.Solid:
    """An (x, z) polygon extruded along Y from y0 to y1."""
    return cq.Workplane("XZ", origin=(0, y0, 0)).polyline(pts).close().extrude(-(y1 - y0)).val()


def _prism_z(pts, z0, z1) -> cq.Solid:
    """An (x, y) polygon extruded along Z from z0 to z1."""
    return cq.Workplane("XY", origin=(0, 0, z0)).polyline(pts).close().extrude(z1 - z0).val()


def _fuse(a: cq.Shape, *others: cq.Shape) -> cq.Shape:
    return a.fuse(*others).clean() if others else a


def _cut(a: cq.Shape, *others: cq.Shape) -> cq.Shape:
    return a.cut(*others).clean() if others else a


def _heatset_hole(h: HeatSet) -> cq.Solid:
    """The insert's hole, from 1 mm outside its mouth to HEATSET_DEPTH in."""
    d = cq.Vector(*h.axis)
    start = cq.Vector(*h.at) - d
    return _cyl(start.toTuple(), h.axis, HEATSET_HOLE_D / 2, HEATSET_DEPTH + 1.0)


def _one(shape: cq.Shape, what: str) -> cq.Solid:
    solids = shape.Solids()
    if len(solids) != 1:
        raise ValueError(f"{what}: {len(solids)} solids, expected one")
    return solids[0]


_CACHE: dict[tuple[str, float], object] = {}


def _cached(name: str, lay: Layout, build):
    key = (name, lay.wall)
    if key not in _CACHE:
        _CACHE[key] = build()
    return _CACHE[key]


# --- shared derived geometry ---------------------------------------------------------

def channel_parts(lay: Layout) -> tuple[Box, Box]:
    """The hinge cable channel split for cutting (carry-forward 5): the base
    part, base frame, from the deck to the axis; the lid part, lid frame
    (closed), from the lid's screen face up."""
    c = lay.hinge_cable_channel
    hy, hz = lay.hinge_axis
    base = Box(c.x0, c.y0, c.z0, c.x1, c.y1, hz, "hinge cable channel (base part)")
    lid = Box(c.x0, c.y0 - hy, 0.0, c.x1, c.y1 - hy, c.z1 - hz, "hinge cable channel (lid part)")
    return base, lid


def _drawer_box(lay: Layout) -> Box:
    """The drawer's outside, base frame, shut."""
    w, bay = lay.wall, lay.bay
    return Box(lay.cable_bay.x0 - w, bay.y0 - w, bay.z0 - w, bay.x1 + w, bay.y1 + w, bay.z1,
               "drawer")


def _rails(lay: Layout) -> tuple[float, ...]:
    """Y centres of the floor rails."""
    return (lay.bay.y0 + RAIL_INSET, lay.bay.y1 - RAIL_INSET)


def _detent(lay: Layout) -> dict[str, float]:
    """The detent's X and Z positions, drawer shut."""
    d = _drawer_box(lay)
    bx0 = lay.drawer_travel + lay.wall + DETENT_MARGIN        # bump's square face
    tz0 = lay.bay.z0 + TONGUE_Z
    out = {"bx0": bx0, "bx1": bx0 + BUMP_W, "tx0": bx0 - 1.0, "tx1": bx0 - 1.0 + TONGUE_LEN,
           "tz0": tz0, "tz1": tz0 + TONGUE_H, "bz0": tz0 + BUMP_MARGIN,
           "bz1": tz0 + TONGUE_H - BUMP_MARGIN, "tip_y": d.y0 - BUMP_H}
    out["g0"] = bx0 - lay.drawer_travel                          # the end stop
    out["g1"] = out["bx1"] + BUMP_H + FIT
    out["rx1"] = bx0 - FIT
    out["rx0"] = out["rx1"] - 2 * RIDGE_H
    if out["tx1"] > lay.bay.x1 - 1.0:
        raise ValueError("detent tongue runs into the drawer's back wall")
    if out["tip_y"] < lay.wall - GROOVE_D + 0.1:
        raise ValueError("detent bump deeper than its groove")
    return out


def _deck_corners(lay: Layout) -> tuple[tuple[float, float], ...]:
    o, w, c = lay.outer, lay.wall, DECK_BLOCK / 2
    return ((w + c, w + c), (o.x1 - w - c, w + c), (w + c, o.y1 - w - c),
            (o.x1 - w - c, o.y1 - w - c))


def _leaf_boss_len(lay: Layout) -> float:
    """How far a leaf-screw boss stands in from the wall's inner face."""
    return HEATSET_DEPTH + INSERT_FLOOR - lay.wall


# --- base tub ------------------------------------------------------------------------

def _tub(lay: Layout) -> tuple[cq.Solid, tuple[HeatSet, ...]]:
    o, w = lay.outer, lay.wall
    W, D, Z = o.x1, o.y1, o.z1
    hy, hz = lay.hinge_axis
    deck_bot = lay.deck_z - w
    dr = _drawer_box(lay)
    det = _detent(lay)
    heatsets: list[HeatSet] = []

    shell = _cut(_box(0, 0, 0, W, D, Z), _box(w, w, w, W - w, D - w, Z + 1.0))
    adds: list[cq.Shape] = [
        _prism_x([(w, deck_bot), (w + LEDGE, deck_bot), (w, deck_bot - LEDGE)], w, W - w),
        _prism_x([(D - w, deck_bot), (D - w - LEDGE, deck_bot), (D - w, deck_bot - LEDGE)],
                 w, W - w),
        _prism_y([(w, deck_bot), (w + LEDGE, deck_bot), (w, deck_bot - LEDGE)], w, D - w),
        _prism_y([(W - w, deck_bot), (W - w - LEDGE, deck_bot), (W - w, deck_bot - LEDGE)],
                 w, D - w),
    ]
    # deck corner blocks, 45 degree undersides, an insert from the top
    B, Hb = DECK_BLOCK, DECK_BLOCK_H
    for cx, cy in _deck_corners(lay):
        yw, s = (w, 1) if cy < D / 2 else (D - w, -1)
        adds.append(_prism_x([(yw, deck_bot), (yw + s * B, deck_bot),
                              (yw + s * B, deck_bot - Hb + B), (yw, deck_bot - Hb)],
                             cx - B / 2, cx + B / 2))
        heatsets.append(HeatSet((cx, cy, deck_bot), (0.0, 0.0, -1.0), "deck corner screw"))
    # hinge leaf screw bosses on the back wall, standing on the ledge
    bl = _leaf_boss_len(lay)
    for x, z in H.base_leaf_screws(lay):
        adds.append(_box(x - BOSS_R, D - w - bl, deck_bot, x + BOSS_R, D - w, z + BOSS_R))
        heatsets.append(HeatSet((x, D, z), (0.0, -1.0, 0.0), "hinge leaf screw"))
    # drawer floor rails and the inward stop bar
    for yc in _rails(lay):
        adds.append(_box(w, yc - RAIL_W / 2, w, dr.x1 + FIT, yc + RAIL_W / 2, w + RAIL_H))
    adds.append(_box(dr.x1 + FIT, dr.y0, w, dr.x1 + FIT + STOP_BAR_T, dr.y1, w + STOP_BAR_H))
    # boost converter fence (the left wall is its fourth side)
    bp = lay.boost_pocket
    adds.append(_box(w, bp.y1, w, bp.x1 + FENCE_T, bp.y1 + FENCE_T, w + FENCE_H))
    adds.append(_box(bp.x1, bp.y0, w, bp.x1 + FENCE_T, bp.y1 + FENCE_T, w + FENCE_H))
    # pad outside the detent groove: the wall keeps ``wall`` behind it
    zb, zt = det["bz0"] - FIT - PAD_MARGIN, det["bz1"] + FIT + PAD_MARGIN
    adds.append(_prism_x([(0.0, zb - PAD_T), (-PAD_T, zb), (-PAD_T, zt), (0.0, zt + PAD_T),
                          (0.1, zt + PAD_T), (0.1, zb - PAD_T)],
                         det["g0"] - PAD_MARGIN, det["g1"] + PAD_MARGIN))
    tub = _fuse(shell, *adds)

    base_ch, _ = channel_parts(lay)
    us = lay.usb_slot
    cuts: list[cq.Shape] = [
        # drawer opening, peaked top
        _prism_x(opening_profile(lay), -1.0, w + 1.0),
        # USB-C cable drop: the ledge under the deck's slot
        _box(us.x0, us.y0 - 1.0, deck_bot - LEDGE - 1.0, us.x1, us.y1, deck_bot + 1.0),
        # hinge cable channel, base part, through the back wall
        _box(base_ch.x0, base_ch.y0, base_ch.z0, base_ch.x1, base_ch.y1 + 1.0, base_ch.z1 + 1.0),
        # detent groove in the front wall's inner face
        _box(det["g0"], w - GROOVE_D, det["bz0"] - FIT, det["g1"], w + 0.1, det["bz1"] + FIT),
        *H.knuckle_relief(lay, (hy, hz)),
        *(_heatset_hole(h) for h in heatsets),
    ]
    tub = _cut(tub, *cuts)
    gy = w - GROOVE_D
    ridge = _prism_z([(det["rx0"], gy - 0.1), (det["rx1"], gy - 0.1), (det["rx1"], gy),
                      ((det["rx0"] + det["rx1"]) / 2, gy + RIDGE_H), (det["rx0"], gy)],
                     det["bz0"] - FIT, det["bz1"] + FIT)
    tub = _fuse(tub, ridge)
    return _one(tub, "base"), tuple(heatsets)


def opening_profile(lay: Layout) -> list[tuple[float, float]]:
    """(y, z) outline of the drawer opening in the left wall: the drawer's
    section plus FIT, topped by a row of 45 degree peaks at most
    OPENING_PITCH wide, so its top has no horizontal bridge."""
    w, dr = lay.wall, _drawer_box(lay)
    y0, y1, z0, zt = w, dr.y1 + FIT, w, dr.z1 + FIT
    n = math.ceil((y1 - y0) / OPENING_PITCH)
    p = (y1 - y0) / n
    pts = [(y0, z0), (y1, z0)]
    for i in range(n, 0, -1):
        pts += [(y0 + i * p, zt), (y0 + (i - 0.5) * p, zt + p / 2)]
    pts.append((y0, zt))
    return pts


def _drawer_face_profile(lay: Layout) -> list[tuple[float, float]]:
    """The drawer face: the opening FIT smaller all round but at the floor,
    where the drawer sits."""
    from shapely.geometry import Polygon, box
    d = _drawer_box(lay)
    face = Polygon(opening_profile(lay)).buffer(-FIT, join_style=2)
    face = face.union(box(d.y0, d.z0, d.y1, d.z1)).simplify(1e-6)
    return list(face.exterior.coords)[:-1]


def base_tub(lay: Layout) -> cq.Solid:
    return _cached("tub", lay, lambda: _tub(lay))[0]


# --- deck ------------------------------------------------------------------------------

def _deck(lay: Layout) -> tuple[cq.Solid, tuple[HeatSet, ...]]:
    o, w = lay.outer, lay.wall
    D = o.y1
    deck_bot, top = lay.deck_z - w, lay.deck_z
    plate = _box(w + FIT, w + FIT, deck_bot, o.x1 - w - FIT, D - w - FIT, top)
    heatsets: list[HeatSet] = []
    adds: list[cq.Shape] = []
    for c in lay.standoffs:
        adds.append(_cyl((c.cx, c.cy, c.z0), (0, 0, 1), c.r, c.z1 - c.z0))
        heatsets.append(HeatSet((c.cx, c.cy, c.z1), (0.0, 0.0, -1.0), c.what))
    for c in lay.supports:
        adds.append(_cyl((c.cx, c.cy, c.z0), (0, 0, 1), c.r, c.z1 - c.z0))
    b = lay.mt1_boss
    length = math.hypot(b.x1 - b.x0, b.y1 - b.y0)
    angle = math.degrees(math.atan2(b.y1 - b.y0, b.x1 - b.x0))
    adds.append(cq.Workplane("XY", origin=((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, b.z0))
                .slot2D(length + 2 * b.r, 2 * b.r, angle).extrude(b.z1 - b.z0).val())
    deck = _fuse(plate, *adds)

    us = lay.usb_slot
    base_ch, _ = channel_parts(lay)
    bl = _leaf_boss_len(lay)
    cuts: list[cq.Shape] = [
        _box(us.x0, us.y0 - 1.0, deck_bot - 1.0, us.x1, us.y1, top + 1.0),
        _box(base_ch.x0, base_ch.y0, deck_bot - 1.0, base_ch.x1, D, top + 1.0),
        *(_box(x - BOSS_R - FIT, D - w - bl - FIT, deck_bot - 1.0, x + BOSS_R + FIT, D,
               top + 1.0) for x, _ in H.base_leaf_screws(lay)),
        *(_cyl((x, y, deck_bot - 1.0), (0, 0, 1), SCREW_CLEAR_D / 2, w + 2.0)
          for x, y in _deck_corners(lay)),
        *(_cyl((p.cx, p.cy, b.z0), (0, 0, 1), PEG_DIA / 2, b.z1 - b.z0 + 1.0)
          for p in lay.pegs.values()),
        *(_heatset_hole(h) for h in heatsets),
    ]
    return _one(_cut(deck, *cuts), "deck"), tuple(heatsets)


def deck(lay: Layout) -> cq.Solid:
    return _cached("deck", lay, lambda: _deck(lay))[0]


# --- drawer ------------------------------------------------------------------------------

def _drawer(lay: Layout) -> cq.Solid:
    d, w = _drawer_box(lay), lay.wall
    det = _detent(lay)
    body = _cut(_bx(d), _box(lay.cable_bay.x0, lay.bay.y0, lay.bay.z0, lay.bay.x1, lay.bay.y1,
                             d.z1 + 1.0))
    body = _fuse(body, _prism_x(_drawer_face_profile(lay), d.x0, d.x0 + w))
    fh = lay.drawer_face_hole
    cuts: list[cq.Shape] = [_box(fh.x0 - 1.0, fh.y0, fh.z0, fh.x1 + 1.0, fh.y1, fh.z1)]
    for yc in _rails(lay):
        half = RAIL_W / 2 + FIT
        cuts.append(_box(d.x0 - 1.0, yc - half, d.z0 - 1.0, d.x1 + 1.0, yc + half,
                         d.z0 + RAIL_H + GROOVE_CLEAR))
    # the tongue: slots round three sides, thinned on the inside
    y0, y1 = d.y0 - 1.0, d.y0 + w + 1.0
    s = TONGUE_SLOT
    tx0, tx1, tz0, tz1 = det["tx0"], det["tx1"], det["tz0"], det["tz1"]
    cuts += [_box(tx0 - s, y0, tz0 - s, tx1, y1, tz0),
             _box(tx0 - s, y0, tz1, tx1, y1, tz1 + s),
             _box(tx0 - s, y0, tz0, tx0, y1, tz1),
             _box(tx0, d.y0 + TONGUE_T, tz0, tx1, y1, tz1)]
    body = _cut(body, *cuts)
    bx0, bx1, tip = det["bx0"], det["bx1"], det["tip_y"]
    bump = _prism_z([(bx0, d.y0 + 0.1), (bx0, tip), (bx1, tip), (bx1 + BUMP_H, d.y0),
                     (bx1 + BUMP_H, d.y0 + 0.1)], det["bz0"], det["bz1"])
    return _one(_fuse(body, bump), "drawer")


def drawer(lay: Layout) -> cq.Solid:
    return _cached("drawer", lay, lambda: _drawer(lay))


# --- lid -----------------------------------------------------------------------------------

def _lid(lay: Layout) -> tuple[cq.Solid, tuple[HeatSet, ...]]:
    o, w, p = lay.lid_outer, lay.wall, lay.lid_pocket
    heatsets: list[HeatSet] = []
    body = _cut(_bx(o), _box(p.x0, p.y0, -1.0, p.x1, p.y1, p.z1),
                *(_box(g.x0, g.y0, -1.0, g.x1, g.y1, g.z1)
                  for g in lay.lid_cable_gutters.values()),
                # R18: the band in front of the opening is a ribbed, closed shell
                *(_bx(c) for c in front_cavities(lay)))
    adds: list[cq.Shape] = []
    bl = _leaf_boss_len(lay)
    for x, z in H.lid_leaf_screws(lay):
        adds.append(_box(x - BOSS_R, -w - bl, z - BOSS_R, x + BOSS_R, -w, p.z1))
        heatsets.append(HeatSet((x, 0.0, z), (0.0, -1.0, 0.0), "hinge leaf screw"))
    ox0, oy0, ox1, oy1 = I.lid_opening(lay)
    for x, y in I.bezel_screws(lay):
        cx = ox0 if x < (ox0 + ox1) / 2 else ox1
        cy = oy0 if y < (oy0 + oy1) / 2 else oy1
        ex = x + math.copysign(BOSS_R, x - cx)
        ey = y + math.copysign(BOSS_R, y - cy)
        adds.append(_box(min(cx, ex), min(cy, ey), INSERT_MATERIAL, max(cx, ex), max(cy, ey),
                         p.z1))
        heatsets.append(HeatSet((x, y, INSERT_MATERIAL), (0.0, 0.0, 1.0), "bezel screw"))
    for x, y in clip_screws(lay):
        adds.append(_bx(clip_boss(lay, x, y)))
        heatsets.append(HeatSet((x, y, 0.0), (0.0, 0.0, 1.0), "clip screw (bezel corner)"))
    body = _fuse(body, *adds)
    _, ch = channel_parts(lay)
    body = _cut(body, _box(ch.x0, ch.y0, -1.0, ch.x1, ch.y1 + 1.0, ch.z1),
                *H.knuckle_relief(lay, (0.0, 0.0)), *(_heatset_hole(h) for h in heatsets))
    return _one(body, "lid"), tuple(heatsets)


def _clip_corners(lay: Layout) -> list[float]:
    """X of each front corner of the opening without a bezel screw.  Only the
    front edge (lid y0) may go without one: behind it is the band, where the
    clip's screw goes; behind the hinge-end edge is only the hinge wall."""
    ox0, oy0, ox1, oy1 = I.lid_opening(lay)
    near = 2 * I.BEZEL_SCREW_INSET
    out = []
    for cx in (ox0, ox1):
        for cy in (oy0, oy1):
            if any(abs(x - cx) <= near and abs(y - cy) <= near for x, y in I.bezel_screws(lay)):
                continue
            if cy != oy0:
                raise ValueError(f"opening corner ({cx:.2f}, {cy:.2f}) has neither a bezel "
                                 "screw nor room for a clip")
            out.append(cx)
    return out


def clip_screws(lay: Layout) -> tuple[tuple[float, float], ...]:
    """(x, y) of each bezel clip's screw, closed lid frame: in the band, its
    insert's boss clear of the opening's front face and the side wall."""
    ox0, oy0, ox1, _ = I.lid_opening(lay)
    out = []
    for cx in _clip_corners(lay):
        x = cx + BOSS_R + 1.0 if cx == ox0 else cx - BOSS_R - 1.0
        out.append((x, oy0 - BOSS_R - 0.5))
    return tuple(out)


def clip_boss(lay: Layout, x: float, y: float) -> Box:
    """The column carrying a clip screw's insert: from the screen face to the
    back plate, out to the side wall and the opening's front wall."""
    o, w, p = lay.lid_outer, lay.wall, lay.lid_pocket
    ox0, oy0, _, _ = I.lid_opening(lay)
    x0, x1 = (o.x0 + w, x + BOSS_R) if x < (o.x0 + o.x1) / 2 else (x - BOSS_R, o.x1 - w)
    return Box(x0, y - BOSS_R, 0.0, x1, oy0, p.z1, "bezel clip boss")


def bezel_clip(lay: Layout, x: float, y: float) -> cq.Solid:
    """The clip for the clip screw at (x, y), closed lid frame: a plate on the
    lid's screen face (z -CLIP_T .. 0) from round its screw over the bezel's
    corner, CLIP_OVER onto it, CLIP_LEN along the edge."""
    ox0, oy0, ox1, _ = I.lid_opening(lay)
    x0 = ox0 + FIT if x < (ox0 + ox1) / 2 else ox1 - FIT - CLIP_LEN
    plate = _box(x0, y - CLIP_MARGIN, -CLIP_T, x0 + CLIP_LEN, oy0 + FIT + CLIP_OVER, 0.0)
    return _one(_cut(plate, _cyl((x, y, -CLIP_T - 1.0), (0, 0, 1), SCREW_CLEAR_D / 2,
                                 CLIP_T + 2.0)), "bezel clip")


def front_cavities(lay: Layout) -> tuple[Box, ...]:
    """The cells of the hollow band in front of the opening (R18), closed lid
    frame: ``wall`` from the outside faces and the opening, split along Y by
    ``wall`` ribs running along X into the fewest cells no wider than
    RIB_SPAN_MAX."""
    o, w = lay.lid_outer, lay.wall
    _, oy0, _, _ = I.lid_opening(lay)
    y0, y1 = o.y0 + w, oy0 - w
    n = 1
    while (y1 - y0 - (n - 1) * w) / n > RIB_SPAN_MAX:
        n += 1
    span = (y1 - y0 - (n - 1) * w) / n
    return tuple(Box(o.x0 + w, y0 + i * (span + w), w, o.x1 - w, y0 + i * (span + w) + span,
                     lay.lid_pocket.z1, f"lid front band cell {i + 1}") for i in range(n))


def lid(lay: Layout) -> cq.Solid:
    return _cached("lid", lay, lambda: _lid(lay))[0]


# --- thickness ---------------------------------------------------------------------

#: Bound on ``mean_thickness`` / wall for the bodies (see the module docstring).
MAX_MEAN_THICKNESS = 1.25


def mean_thickness(solid: cq.Shape) -> float:
    """2 V / A: a shell's thickness; a solid lump's is much more."""
    return 2 * solid.Volume() / solid.Area()


# --- print orientation and the bed ------------------------------------------------------

#: Turns (axis, degrees) about the origin.
FLAT = ((1.0, 0.0, 0.0), 0.0)
FLIP = ((1.0, 0.0, 0.0), 180.0)
#: How each kind of part is laid on the bed: floors, plates and the packing's
#: U on their bottoms; the lid and retainers on their back plates; the hinge
#: halves standing on their leaves' edges, so the stop shelf's 45 degree
#: gusset and the knuckles' axes print as designed (knuckles need supports
#: either way).
PRINT_POSE: dict[str, tuple[tuple[float, float, float], float]] = {
    "base": FLAT, "deck": FLAT, "drawer": FLAT, "lid": FLIP, "hinge-base": FLAT,
    "hinge-lid": FLIP, "bezel": FLAT, "bezel-clip": FLAT, "retainer": FLIP, "packing": FLAT,
    "mt1-pin": FLAT,
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


def _overflow(name: str, shape: cq.Shape, bed, why: str = "") -> BedOverflow:
    x, y = _footprint(shape)
    return BedOverflow(f"{name} {x:.2f} x {y:.2f} mm does not fit the {bed[0]:g} x {bed[1]:g} "
                       f"mm print bed{why}")


def check_bed(name: str, shape: cq.Shape, bed=PRINT_BED) -> None:
    """Raise BedOverflow when ``shape`` (posed) is bigger than the bed."""
    x, y = _footprint(shape)
    if x > bed[0] + 1e-6 or y > bed[1] + 1e-6:
        raise _overflow(name, shape, bed)


def _printed(kind: str, solid: cq.Shape, note: str, heatsets=()) -> Printed:
    return Printed(solid, PRINT_POSE[kind], note, tuple(heatsets))


# --- split ---------------------------------------------------------------------------

def section_area(solid: cq.Shape, axis: str, at: float, t: float = 0.2) -> float:
    """Area of the solid's section by the plane axis = ``at``."""
    bb = solid.BoundingBox()
    lo = (bb.xmin - 1, bb.ymin - 1, bb.zmin - 1)
    hi = (bb.xmax + 1, bb.ymax + 1, bb.zmax + 1)
    i = "xy".index(axis)
    lo = tuple(at - t / 2 if k == i else v for k, v in enumerate(lo))
    hi = tuple(at + t / 2 if k == i else v for k, v in enumerate(hi))
    return solid.intersect(_box(*lo, *hi)).Volume() / t


def _map(axis: str, along: float, across: float, z: float) -> tuple[float, float, float]:
    return (along, across, z) if axis == "x" else (across, along, z)


def _site_box(axis, at, a0, a1, z0, z1) -> Box:
    x0, y0, _ = _map(axis, at - JOINT_L, a0, z0)
    x1, y1, _ = _map(axis, at + JOINT_L, a1, z1)
    return Box(min(x0, x1), min(y0, y1), z0, max(x0, x1), max(y0, y1), z1, "joint block")


def _clear(b: Box, keepouts) -> bool:
    return all(min(b.x1, k.x1) - max(b.x0, k.x0) <= -FIT or min(b.y1, k.y1) - max(b.y0, k.y0)
               <= -FIT or min(b.z1, k.z1) - max(b.z0, k.z0) <= -FIT for k in keepouts)


@dataclass(frozen=True)
class _Site:
    """A joint site on one wall: ``face`` is the wall's inner face (across
    coordinate), ``sign`` points into the body, ``level`` names it, ``z0``/
    ``z1`` its Z, ``hang`` whether it hangs from z1 (45 degree underside)."""

    wall: str
    face: float
    sign: float
    level: str
    z0: float
    z1: float
    hang: bool
    deck_screws: bool = False

    def block_box(self, axis, at) -> Box:
        a = sorted((self.face, self.face + self.sign * JOINT_B))
        return _site_box(axis, at, a[0], a[1], self.z0, self.z1)

    def solid(self, axis, at) -> cq.Solid:
        f, s, B = self.face, self.sign, JOINT_B
        if self.hang:
            pts = [(f, self.z1), (f + s * B, self.z1), (f + s * B, self.z0 + B), (f, self.z0)]
        else:
            pts = [(f, self.z1), (f + s * B, self.z1), (f + s * B, self.z0), (f, self.z0)]
        mk = _prism_x if axis == "x" else _prism_y
        return mk(pts, at - JOINT_L, at + JOINT_L)

    def points(self) -> tuple[float, float, float, float]:
        """(across, z) of the screw and of the dowel."""
        if self.hang:
            return (self.face + self.sign * 4.0, self.z1 - 14.0,
                    self.face + self.sign * 5.0, self.z1 - 8.5)
        return (self.face + self.sign * 5.0, self.z0 + 5.0,
                self.face + self.sign * 5.0, self.z0 + 13.0)


def _choose_plane(solid, axis, bed_len, lo, hi, sites_at, valid) -> tuple[float, list]:
    """The plane with the smallest section among those both pieces fit and
    that can be joined; and every candidate tried."""
    a0 = max(hi - bed_len, lo + JOINT_L + 2.0)
    a1 = min(lo + bed_len, hi - JOINT_L - 2.0)
    if a1 < a0:
        return None, []
    n = int(math.floor((a1 - a0) / SPLIT_STEP))
    planes = [a0 + i * SPLIT_STEP for i in range(n + 1)] + ([a1] if a1 > a0 else [])
    cands = [s for s in planes if valid(s) and _walls_covered(sites_at(s))]
    if not cands:
        return None, []
    mid = (lo + hi) / 2
    areas = {s: section_area(solid, axis, s) for s in cands}
    best = min(cands, key=lambda s: (round(areas[s], 3), abs(s - mid)))
    return best, cands


def _walls_covered(sites) -> bool:
    return len({s.wall for s in sites}) >= 2


def _cut_pieces(name, solid, heatsets, axis, at, sites, access_z=None):
    """Fuse the joint blocks, cut at the plane, drill: clearance + head on
    the low piece, heat-set insert on the high piece, dowels in both."""
    solid = _fuse(solid, *(s.solid(axis, at) for s in sites))
    bb = solid.BoundingBox()
    big = (bb.xmin - 1, bb.ymin - 1, bb.zmin - 1, bb.xmax + 1, bb.ymax + 1, bb.zmax + 1)
    i = "xy".index(axis)
    lo_box = list(big)
    lo_box[3 + i] = at
    hi_box = list(big)
    hi_box[i] = at
    low, high = solid.intersect(_box(*lo_box)), solid.intersect(_box(*hi_box))
    d = (1.0, 0.0, 0.0) if axis == "x" else (0.0, 1.0, 0.0)
    nd = tuple(-v for v in d)
    joints, low_cuts, high_cuts, low_hs, high_hs = [], [], [], [], []
    for s in sites:
        sa, sz, pa, pz = s.points()
        screw, dowel = _map(axis, at, sa, sz), _map(axis, at, pa, pz)
        joints.append(Joint(s.wall, s.level, screw, dowel, s.block_box(axis, at)))
        low_cuts.append(_cyl(_map(axis, at + 0.5, sa, sz), nd, SCREW_CLEAR_D / 2, JOINT_L + 1.5))
        hs = HeatSet(screw, d, f"joint screw ({s.wall}, {s.level})")
        high_hs.append(hs)
        high_cuts.append(_heatset_hole(hs))
        for piece_cuts, direc in ((low_cuts, nd), (high_cuts, d)):
            # from 0.5 outside the piece's cut face to PIN_DEPTH into it
            piece_cuts.append(_cyl(_map(axis, at - 0.5 * direc["xy".index(axis)], pa, pz),
                                   direc, PIN_HOLE_D / 2, PIN_DEPTH + 0.5))
        if access_z is not None:
            r = m3.HEAD_R + FIT
            p0 = _map(axis, at - JOINT_L - ACCESS_L, sa - r, access_z)
            p1 = _map(axis, at - JOINT_L, sa + r, sz + r)
            low_cuts.append(_box(min(p0[0], p1[0]), min(p0[1], p1[1]), access_z,
                                 max(p0[0], p1[0]), max(p0[1], p1[1]), sz + r))
        if s.deck_screws:
            for piece_hs, off in ((low_hs, -JOINT_L / 2), (high_hs, JOINT_L / 2)):
                piece_hs.append(HeatSet(_map(axis, at + off, s.face + s.sign * JOINT_B / 2, s.z1),
                                        (0.0, 0.0, -1.0), f"joint deck screw ({s.wall})"))
    low_cuts += [_heatset_hole(h) for h in low_hs]
    high_cuts += [_heatset_hole(h) for h in high_hs if h.what.startswith("joint deck")]
    low, high = _cut(low, *low_cuts), _cut(high, *high_cuts)
    coord = "xyz".index(axis)
    low_hs += [h for h in heatsets if h.at[coord] < at]
    high_hs += [h for h in heatsets if h.at[coord] >= at]
    names = ("left", "right") if axis == "x" else ("front", "back")
    return ({f"{name}-{names[0]}": (_one(low, f"{name}-{names[0]}"), tuple(low_hs)),
             f"{name}-{names[1]}": (_one(high, f"{name}-{names[1]}"), tuple(high_hs))},
            tuple(joints))


def _split_axis(name, solid, bed) -> str:
    x, y = _footprint(solid)
    over = [a for a, n, b in (("x", x, bed[0]), ("y", y, bed[1])) if n > b + 1e-6]
    if len(over) != 1:
        raise _overflow(name, solid, bed, ": it would need splitting both ways" if over else "")
    return over[0]


def _base_sites(lay: Layout, axis: str) -> list[_Site]:
    o, w = lay.outer, lay.wall
    deck_bot = lay.deck_z - w
    walls = ((("front", w, 1.0), ("back", o.y1 - w, -1.0)) if axis == "x"
             else (("left", w, 1.0), ("right", o.x1 - w, -1.0)))
    out = []
    for wall, face, sign in walls:
        out.append(_Site(wall, face, sign, "floor", w, w + JOINT_H, False))
        out.append(_Site(wall, face, sign, "under-deck", deck_bot - JOINT_HANG, deck_bot, True,
                         deck_screws=True))
    return out


def _base_keepouts(lay: Layout) -> list[Box]:
    d, w = _drawer_box(lay), lay.wall
    us = lay.usb_slot
    base_ch, _ = channel_parts(lay)
    keep = [Box(d.x0 - lay.drawer_travel - 1.0, w, w, d.x1 + FIT + STOP_BAR_T, d.y1 + FIT,
                d.z1 + FIT, "drawer sweep"),
            lay.boost_pocket, base_ch,
            Box(us.x0, us.y0, d.z1 + FIT, us.x1, us.y1, lay.deck_z, "USB-C cable drop")]
    B = DECK_BLOCK
    for cx, cy in _deck_corners(lay):
        keep.append(Box(cx - B / 2, cy - B / 2, lay.deck_z - w - DECK_BLOCK_H, cx + B / 2,
                        cy + B / 2, lay.deck_z, "deck corner block"))
    return keep


def split_base(lay: Layout, bed=PRINT_BED) -> tuple[dict[str, Printed], Split | None]:
    """The tub and the deck, split at the same plane when the tub is bigger
    than the bed (names ``base-left``/``base-right``, ``deck-left``/
    ``deck-right``; front/back for a split across Y)."""
    tub, tub_hs = _cached("tub", lay, lambda: _tub(lay))
    dk, dk_hs = _cached("deck", lay, lambda: _deck(lay))
    note_t = ("Base tub: print floor down, no supports (the drawer opening's top is "
              "45 degree peaks). Heat-set M3 inserts: ")
    note_d = "Deck: print flat, standoffs up. Heat-set M3 insert in the MT2 standoff."
    x, y = _footprint(tub)
    if x <= bed[0] + 1e-6 and y <= bed[1] + 1e-6:
        check_bed("deck", dk, bed)
        return ({"base": _printed("base", tub, note_t + _count(tub_hs), tub_hs),
                 "deck": _printed("deck", dk, note_d, dk_hs)}, None)
    axis = _split_axis("base", tub, bed)
    o = lay.outer
    lo, hi = (o.x0, o.x1) if axis == "x" else (o.y0, o.y1)
    keep = _base_keepouts(lay)
    sites_all = _base_sites(lay, axis)
    deck_feats = [Box(c.cx - c.r, c.cy - c.r, 0, c.cx + c.r, c.cy + c.r, 1, c.what)
                  for c in (*lay.standoffs, *lay.supports)]
    b = lay.mt1_boss
    deck_feats.append(Box(min(b.x0, b.x1) - b.r, min(b.y0, b.y1) - b.r, 0,
                          max(b.x0, b.x1) + b.r, max(b.y0, b.y1) + b.r, 1, b.what))

    def sites_at(s):
        return [t for t in sites_all if _clear(t.block_box(axis, s), keep)]

    def valid(s):
        k = "xy".index(axis)
        return all(s < (f.x0, f.y0)[k] - FIT or s > (f.x1, f.y1)[k] + FIT for f in deck_feats)

    at, cands = _choose_plane(tub, axis, bed["xy".index(axis)], lo, hi, sites_at, valid)
    if at is None:
        raise _overflow("base", tub, bed, ": no plane splits it into two pieces that fit and "
                        "can be joined")
    sites = sites_at(at)
    pieces, joints = _cut_pieces("base", tub, tub_hs, axis, at, sites)
    # the deck: same plane; its pieces screw down into the under-deck joint blocks
    i = "xy".index(axis)
    bb = dk.BoundingBox()
    big = [bb.xmin - 1, bb.ymin - 1, bb.zmin - 1, bb.xmax + 1, bb.ymax + 1, bb.zmax + 1]
    lo_b, hi_b = list(big), list(big)
    lo_b[3 + i], hi_b[i] = at, at
    names = ("left", "right") if axis == "x" else ("front", "back")
    holes = [_cyl((h.at[0], h.at[1], h.at[2] - 1.0), (0, 0, 1), SCREW_CLEAR_D / 2,
                  lay.wall + 2.0)
             for _, (_, hs) in pieces.items() for h in hs if h.what.startswith("joint deck")]
    d_lo = _cut(dk.intersect(_box(*lo_b)), *holes)
    d_hi = _cut(dk.intersect(_box(*hi_b)), *holes)
    coord = "xyz".index(axis)
    out = {}
    for key, (solid, hs) in pieces.items():
        out[key] = _printed("base", solid, note_t + _count(hs) + f" Joined at {axis} = {at:.2f} by "
                            f"M3 x {_joint_screw()} screws and {PIN_D:g} x "
                            f"{2 * PIN_DEPTH - FIT:g} mm dowels.", hs)
    for key, solid, side in ((f"deck-{names[0]}", d_lo, -1), (f"deck-{names[1]}", d_hi, 1)):
        hs = tuple(h for h in dk_hs if (h.at[coord] - at) * side > 0)
        out[key] = _printed("deck", _one(solid, key), note_d, hs)
    for key, p in out.items():
        check_bed(key, posed(p), bed)
    return out, Split(axis, at, joints, tuple(cands))


def _joint_screw() -> int:
    return m3.insert_screw(JOINT_L, HEATSET_DEPTH)


def _count(hs) -> str:
    return f"{len(hs)}." if hs else "none."


def _lid_sites(lay: Layout, axis: str) -> list[_Site]:
    o, w, p = lay.lid_outer, lay.wall, lay.lid_pocket
    walls = ((("front", o.y0 + w, 1.0), ("hinge", o.y1 - w, -1.0)) if axis == "x"
             else (("left", o.x0 + w, 1.0), ("right", o.x1 - w, -1.0)))
    return [_Site(wall, face, sign, "back plate", p.z1 - JOINT_H, p.z1, True)
            for wall, face, sign in walls]


def split_lid(lay: Layout, bed=PRINT_BED) -> tuple[dict[str, Printed], Split | None]:
    """The lid, split like the base when bigger than the bed (``lid-left``/
    ``lid-right``...).  Joint blocks hang from the back plate; the low piece's
    screws are reached through pockets from the screen side (under the bezel
    in the gutters, open beside the pocket otherwise)."""
    solid, hs = _cached("lid", lay, lambda: _lid(lay))
    note = ("Lid: print on its back (screen side up), no supports; the front band is "
            "hollow and ribbed, its screen-side skin bridges "
            f"{max(c.size[1] for c in front_cavities(lay)):.1f} mm cells. Heat-set M3 "
            "inserts: ")
    x, y = _footprint(solid)
    if x <= bed[0] + 1e-6 and y <= bed[1] + 1e-6:
        return {"lid": _printed("lid", solid, note + _count(hs), hs)}, None
    axis = _split_axis("lid", solid, bed)
    o = lay.lid_outer
    lo, hi = (o.x0, o.x1) if axis == "x" else (o.y0, o.y1)
    _, ch = channel_parts(lay)
    keep = [lay.lid_pocket, ch]
    keep += [Box(h.at[0] - BOSS_R, h.at[1] - BOSS_R - _leaf_boss_len(lay) - lay.wall,
                 h.at[2] - BOSS_R, h.at[0] + BOSS_R, h.at[1] + BOSS_R, o.z1, h.what)
             for h in hs]
    sites_all = _lid_sites(lay, axis)

    def sites_at(s):
        return [t for t in sites_all if _clear(t.block_box(axis, s), keep)]

    at, cands = _choose_plane(solid, axis, bed["xy".index(axis)], lo, hi, sites_at,
                              lambda s: True)
    if at is None:
        raise _overflow("lid", solid, bed, ": no plane splits it into two pieces that fit and "
                        "can be joined")
    pieces, joints = _cut_pieces("lid", solid, hs, axis, at, sites_at(at), access_z=-1.0)
    out = {k: _printed("lid", s, note + _count(h) + f" Joined at {axis} = {at:.2f}.", h)
           for k, (s, h) in pieces.items()}
    for key, p in out.items():
        check_bed(key, posed(p), bed)
    return out, Split(axis, at, joints, tuple(cands))


# --- the parts ------------------------------------------------------------------------

def printed_parts(lay: Layout, bed=PRINT_BED) -> dict[str, Printed]:
    """Every printed part, bed-checked: the bodies (split if they must be) and
    the shared parts.  Raises BedOverflow naming the part that does not fit."""
    parts: dict[str, Printed] = {}
    det = _detent(lay)
    parts["drawer"] = _printed("drawer", drawer(lay), (
        "Drawer: print floor down, no supports. The detent tongue is cut free in the "
        f"front side; its bump clicks over the base's ridge at the closed position and "
        f"stops on the groove's end with the drawer out {lay.drawer_travel:.1f} mm "
        f"(groove x {det['g0']:.1f}..{det['g1']:.1f}). To take the drawer out: pull it "
        "to the stop, lift out the bank and packing, press the tongue in (towards the "
        "bay) with a fingertip and slide the drawer out."))
    parts["hinge-base"] = _printed("hinge-base", H.hinge_base_knuckles(lay).val(), (
        f"Hinge, base half, with the stop shelf. M3 x {H.hinge_bolt_length(lay)} bolt + "
        "nyloc per knuckle group; leaf screws M3 into the base's heat-set inserts. "
        "Prints standing on its leaf's 3 mm edge: use a brim. Supports under the knuckles."))
    parts["hinge-lid"] = _printed("hinge-lid", H.hinge_lid_knuckles(lay).val(), (
        "Hinge, lid half. Leaf screws M3 into the lid's heat-set inserts. Prints standing "
        "on its leaf's 3 mm edge: use a brim. Supports under the knuckles."))
    for k, m in MONITORS.items():
        parts[f"bezel-{k}"] = _printed("bezel", I.monitor_bezel(m, lay).val(), (
            f"Bezel for {m.title}: print flat. Screwed to the lid's inserts by "
            f"{len(I.bezel_screws(lay))} M3 x "
            f"{m3.insert_screw(INSERT_MATERIAL, HEATSET_DEPTH)} pan-head screws."))
        parts[f"retainer-{k}"] = _printed("retainer", I.monitor_retainer(m, lay).val(), (
            f"Retainer for {m.title}: print back plate down."))
    for k, b in BATTERIES.items():
        parts[f"packing-{k}"] = _printed("packing", battery_packing(b, lay).val(), (
            f"Packing for {b.title}: print flat, engraved face up."))
    for i, (x, y) in enumerate(clip_screws(lay)):
        parts[f"bezel-clip-{i + 1}" if i else "bezel-clip"] = _printed("bezel-clip", bezel_clip(
            lay, x, y), (f"Bezel clip: print flat. Holds the bezel's corner that has no screw; "
                         f"one M3 x {m3.insert_screw(CLIP_T, HEATSET_DEPTH)} pan-head "
                         "screw into the lid's heat-set insert. Fit after the bezel."))
    parts["mt1-pin"] = _printed("mt1-pin", locating_pin(lay).val(), (
        "MT1 locating pin: print standing; print spares, it is loose."))
    for name, p in parts.items():
        check_bed(name, posed(p), bed)
    base, _ = split_base(lay, bed)
    lid_parts, _ = split_lid(lay, bed)
    out = {**base, **lid_parts, **parts}
    return dict(sorted(out.items()))


@dataclass(frozen=True)
class InsertScrew:
    """M3 screws of one use into the printed route's heat-set inserts: what
    they clamp (mm of parts above the insert's mouth), their stock length and
    how many."""

    what: str
    clamp: float
    length: int
    count: int

    @property
    def engagement(self) -> float:
        """Thread inside the insert hole."""
        return self.length - self.clamp


def screw_clamp(lay: Layout, what: str) -> tuple[str, float]:
    """(label, clamp) of the screw into a heat-set insert of kind ``what``
    (a ``HeatSet.what``): the mm of parts its head clamps above the insert's
    mouth."""
    from demobox.parts.board import BOARD_KEYS
    if what == "deck corner screw" or what.startswith("joint deck screw"):
        return ("deck corners" if what == "deck corner screw" else "deck at a joint"), lay.wall
    if what == "hinge leaf screw":
        return "hinge leaves", H.LEAF_T
    if what == "bezel screw":
        return "bezel", INSERT_MATERIAL
    if what == "clip screw (bezel corner)":
        return "bezel clip", CLIP_T
    if what.startswith("joint screw"):
        return "split joints", JOINT_L
    if what.startswith("standoff"):
        return "board, MT2", max(board_spec(k).outline.thickness for k in BOARD_KEYS)
    raise ValueError(f"no screw known for the heat-set insert {what!r}")


def insert_screws(lay: Layout, heatsets=None) -> tuple[InsertScrew, ...]:
    """Every screw that goes into a heat-set insert of the printed route (or
    of ``heatsets``), sized by ``m3.insert_screw``: the longest stock length
    that stops short of the hole's floor.  Counts come from the parts' own
    HeatSet records."""
    if heatsets is None:
        heatsets = [h for p in printed_parts(lay).values() for h in p.heatsets]
    groups: dict[tuple[str, float], int] = {}
    for h in heatsets:
        key = screw_clamp(lay, h.what)
        groups[key] = groups.get(key, 0) + 1
    return tuple(InsertScrew(label, clamp, m3.insert_screw(clamp, HEATSET_DEPTH), n)
                 for (label, clamp), n in sorted(groups.items()))


def hardware(lay: Layout) -> dict[str, int]:
    """Bought hardware for the printed route (name -> count): the heat-set
    inserts, the screw into each, and the hinge bolts and nylocs."""
    parts = printed_parts(lay)
    hw: dict[str, int] = {}

    def add(k, n):
        hw[k] = hw.get(k, 0) + n

    add(f"M3 heat-set insert, D{HEATSET_HOLE_D:.1f} x {HEATSET_DEPTH:.1f}",
        sum(len(p.heatsets) for p in parts.values()))
    for s in insert_screws(lay):
        add(f"M3 x {s.length} pan-head ({s.what})", s.count)
    add(f"M3 x {H.hinge_bolt_length(lay)} bolt + nyloc (hinge pin)", len(H.hinge_groups(lay)))
    return dict(sorted(hw.items()))


# --- assembly ------------------------------------------------------------------------

def _board_pcb(lay: Layout, key: str) -> cq.Shape:
    spec = board_spec(key)
    ox, oy, oz = lay.board_origin
    W, Hh, t = spec.outline.width, spec.outline.height, spec.outline.thickness
    pcb = _box(ox - W, oy - Hh, oz, ox, oy, oz + t)
    return _cut(pcb, *(_cyl((ox - h.x, oy - h.y, oz - 1.0), (0, 0, 1), h.dia / 2, t + 2.0)
                       for h in spec.holes))


def assembly(route: str, angle_deg: float, drawer_out: float,
             monitor: str = ASSEMBLY_MONITOR, bank: str = ASSEMBLY_BANK,
             board: str = ASSEMBLY_BOARD) -> list[tuple[str, cq.Shape, tuple[float, float, float]]]:
    """The box in the base frame: lid ``angle_deg`` open, drawer pulled
    ``drawer_out`` mm along ``drawer_out``'s direction, with ``monitor``,
    ``bank`` and ``board`` fitted (bought parts as plain blocks).  The one
    entry point for both routes: ``"laser"`` is ``demobox.laser.fittings``'."""
    if route == "laser":
        from demobox.laser.fittings import assembly as laser_assembly
        return laser_assembly(angle_deg, drawer_out, monitor=monitor, bank=bank, board=board)
    if route != "printed":
        raise ValueError(f"unknown route {route!r}; routes are {sorted(ROUTES)}")
    lay = layout(ROUTES[route])
    m, b = MONITORS[monitor], BATTERIES[bank]
    loc = lay.lid_location(angle_deg)
    shift = cq.Vector(*(v * drawer_out for v in lay.drawer_out))

    bay = lay.bay
    L_, W_, H_ = b.size
    cy = (bay.y0 + bay.y1) / 2
    bank_box = _box(bay.x0, cy - W_ / 2, bay.z0, bay.x0 + L_, cy + W_ / 2, bay.z0 + H_)
    peg = lay.pegs[board]
    pin = locating_pin(lay).val().translate(cq.Vector(peg.cx, peg.cy, lay.mt1_boss.z0))

    base_items = [("base", base_tub(lay)), ("deck", deck(lay)),
                  ("hinge-base", H.hinge_base_knuckles(lay).val()), ("mt1-pin", pin),
                  ("board", _board_pcb(lay, board))]
    drawer_items = [("drawer", drawer(lay)), ("packing", battery_packing(b, lay).val()),
                    ("bank", bank_box)]
    lid_items = [("lid", lid(lay)), ("hinge-lid", H.hinge_lid_knuckles(lay).val()),
                 ("bezel", I.monitor_bezel(m, lay).val()),
                 ("retainer", I.monitor_retainer(m, lay).val()),
                 ("panel", _bx(panel_in_lid(m, lay)))]
    env = I.driver_envelope(m, lay)
    if env is not None:
        lid_items.append(("monitor-driver", _bx(env)))
    lid_items += [(f"bezel-clip-{i + 1}" if i else "bezel-clip", bezel_clip(lay, x, y))
                  for i, (x, y) in enumerate(clip_screws(lay))]
    # bought hardware standing proud of the screen face: screw-head keep-outs
    lid_items += [(f"hw:bezel-screw-head-{i + 1}", _screw_head(x, y, 0.0))
                  for i, (x, y) in enumerate(I.bezel_screws(lay))]
    lid_items += [(f"hw:clip-screw-head-{i + 1}", _screw_head(x, y, -CLIP_T))
                  for i, (x, y) in enumerate(clip_screws(lay))]

    def colour(n):
        if n.startswith("hw:"):
            return COLOURS["hw"]
        return COLOURS["bezel-clip" if n.startswith("bezel-clip") else n]

    out = [(n, s, colour(n)) for n, s in base_items]
    out += [(n, s.translate(shift), colour(n)) for n, s in drawer_items]
    out += [(n, s.moved(loc), colour(n)) for n, s in lid_items]
    return out


def _screw_head(x: float, y: float, face_z: float) -> cq.Solid:
    """An M3 pan head's keep-out on a face at lid z ``face_z``, standing
    towards the screen side (-Z)."""
    return _cyl((x, y, face_z - m3.HEAD_H), (0, 0, 1), m3.HEAD_R, m3.HEAD_H)
