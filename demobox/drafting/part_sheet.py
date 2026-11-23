"""A4 part sheets for the printed route's parts.

Each part is drawn from its hidden-line projection (``hlr.project``), first
angle, in the views that show it best: the principal view is the face that
says most about the part (the drawer opening for the base, the hinge edge for
the lid), the plan below it, the view from its left beside it where that adds
something.  A ``Part`` turns the solid into its drawing frame (``turn``, then
``shift``) and every point the sheet dimensions is put through the same turn,
so a dimension and the line it measures cannot disagree.

The overall sizes are dimensioned on every sheet; the features a checker
needs are dimensioned on the view that shows them, or tabulated where there
are more of them than a view can carry (inserts, holes, bosses).  Every figure
is read off the same layout and part code that builds the STEP.

The packing, one U per power bank, is a tabulated drawing: one set of views
with lettered dimensions, and a table of each bank's letters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import cadquery as cq

import demobox  # noqa: F401  (puts the submodule on sys.path)
from tools.drafting import dims, style

from demobox.drafting import names
from demobox.drafting import sheetkit as K
from demobox.drafting.hlr import project, to_view, view_bbox
from demobox.layout import (FIT, HEATSET_DEPTH, HEATSET_HOLE_D, PEG_DIA, PEG_HEIGHT, PEG_HOLE_D,
                            ROUTES, layout)
from demobox.parts.batteries import BATTERIES
from demobox.printed import body as B
from demobox.shared import hinge as H
from demobox.shared import packing as PK
from demobox.shared import pin as PIN

F = K.fmt
SRC_BODY = "demobox/printed/body.py"
SRC_LAYOUT = "demobox/layout.py (layout(2.4))"
SRC_HINGE = "demobox/shared/hinge.py"
HEATSET = (f"M3 heat-set inserts: hole D{HEATSET_HOLE_D:.1f} x {HEATSET_DEPTH:.1f} deep, "
           "pressed in after printing.")

#: Scales tried, largest first, for each size class of part.
BIG = (0.4, 0.2)
MID = (1.0, 0.5, 0.4)
SMALL = (5.0, 2.0)

Turn = tuple[tuple[tuple[float, float, float], float], ...]


@dataclass
class Part:
    defn: names.SheetDef
    solid: cq.Shape                      # in its design frame
    subtitle: str
    datum: str
    notes: list[str]
    sources: list[str]
    scales: tuple[float, ...]
    views: tuple[str, ...] = ("front", "side", "plan")
    #: Rotations (axis, degrees) about the origin, then a shift, taking the
    #: design frame to the drawing frame.
    turn: Turn = ()
    shift: tuple[float, float, float] = (0.0, 0.0, 0.0)
    hidden: frozenset[str] = frozenset()
    captions: dict[str, str] = field(default_factory=dict)
    annotate: Callable[["Part", dict[str, K.PView]], list] | None = None
    tables: list[K.Table] = field(default_factory=list)
    material: str = K.PRINTED_MATERIAL
    tolerance: str = K.PRINTED_TOL
    extra_lines: Callable[["Part", object, dict[str, K.PView]], None] | None = None
    legend: list = field(default_factory=list)
    #: Discretising chord for the projection (finer for an enlarged part).
    chord: float = 0.1
    #: Overall dimensions to letter or leave out: "front-left", "front-bottom",
    #: "plan-bottom", "plan-left", "side-bottom" -> text, or None to omit.
    overall_text: dict = field(default_factory=dict)
    #: Holes to mark with centre lines: (view, design-frame point, radius).
    centres: list = field(default_factory=list)

    def shape(self) -> cq.Shape:
        s = self.solid
        for axis, deg in self.turn:
            s = s.rotate(cq.Vector(0, 0, 0), cq.Vector(*axis), deg)
        return s.translate(cq.Vector(*self.shift))

    def P(self, p) -> tuple[float, float, float]:
        """A design-frame point in the drawing frame."""
        v = cq.Vector(*p)
        for axis, deg in self.turn:
            v = cq.Vertex.makeVertex(*v.toTuple()).rotate(
                cq.Vector(0, 0, 0), cq.Vector(*axis), deg).Center()
        return tuple(round(a + b, 9) for a, b in zip(v.toTuple(), self.shift))

    def V(self, view: str, p) -> tuple[float, float]:
        """A design-frame point in ``view``'s (across, up)."""
        return to_view(view, self.P(p))


CAPTIONS = {"front": "FRONT", "side": "FROM LEFT", "plan": "PLAN"}


def _overall(views: dict[str, K.PView], text: dict) -> list:
    """Every view's extent once: height on the principal view's left, the
    plan's across and depth below and left of it (or the principal view's
    across below it, and the side view's, when there is no plan)."""
    out = []

    def dim(key, *args):
        t = text.get(key, "")
        if t is not None:
            out.append(K.Dim(*args, text=t or None))

    f = views["front"]
    x0, y0, x1, y1 = f.bb
    dim("front-left", f, (x0, y0), (x0, y1), "left", 0)
    if "plan" in views:
        p = views["plan"]
        px0, py0, px1, py1 = p.bb
        dim("plan-bottom", p, (px0, py0), (px1, py0), "bottom", 0)
        dim("plan-left", p, (px0, py0), (px0, py1), "left", 0)
    else:
        dim("front-bottom", f, (x0, y0), (x1, y0), "bottom", 0)
        if "side" in views:
            s = views["side"]
            sx0, sy0, sx1, _ = s.bb
            dim("side-bottom", s, (sx0, sy0), (sx1, sy0), "bottom", 0)
    return out


def part_bbs(part: Part) -> dict[str, tuple[float, float, float, float]]:
    """Each view's extent: the drawn solid's exact bounding box in its axes."""
    shape = part.shape()
    return {v: view_bbox(shape, v) for v in part.views}


def overall_dims(part: Part) -> list:
    """The overall dimension records a sheet draws, placed at 1:1 (for the
    tests: their values are the solid's sizes)."""
    projs = {v: project(part.shape(), v, chord=part.chord) for v in part.views}
    views = K.first_angle(projs, 1.0, 0.0, 0.0, bbs=part_bbs(part))
    return _overall(views, part.overall_text)


def render_part(part: Part):
    shape = part.shape()
    projs = {v: project(shape, v, chord=part.chord) for v in part.views}
    # the views' extents, and so the overall dimensions, are the solid's own
    bbs = part_bbs(part)
    caps = {k: v for k, v in {**CAPTIONS, **part.captions}.items() if k in part.views}
    entries = [K.L_VISIBLE] + ([K.L_HIDDEN] if part.hidden else []) + list(part.legend)
    entries.append(K.L_DIM)

    def make_ann(views):
        ann = _overall(views, part.overall_text)
        if part.annotate:
            ann += part.annotate(part, views)
        return K.captioned(views, ann, caps)

    def build(sheet, s):
        views, ann = K.solve(projs, s, make_ann, sheet.frame, bbs=bbs)
        lay = K.Layout(views, ann)

        def draw(sh):
            for k, v in views.items():
                K.draw_view(sh.canvas, v, hidden=k in part.hidden)
            if part.extra_lines:
                part.extra_lines(part, sh.canvas, views)
            for view, at, r in part.centres:
                if view in views:
                    v = views[view]
                    dims.centre_mark(sh.canvas, *v.pt(*part.V(view, at)), v.scale * r,
                                     colour=style.C_LINE)
            K.datum_mark(sh.canvas, views)

        notes = [f"Datum (target): {part.datum}."] + part.notes
        # a key only where a line type needs one: visible edges and dimensions
        # explain themselves
        legend = K.Legend(entries) if len(entries) > 2 else None
        return lay, list(part.tables), legend, notes, part.sources, draw

    return K.render(part.defn, build, subtitle=part.subtitle, material=part.material,
                    tolerance=part.tolerance, scales=part.scales)


# --- shared -----------------------------------------------------------------------------

def _lay():
    return layout(ROUTES["printed"])


def _parts():
    return B.printed_parts(_lay())


def _unconf(keys=K.BODY_KEYS) -> str:
    return K.unconfirmed_note(keys)


def _insert_rows(part: Part, heatsets) -> list[list[str]]:
    """One row per kind of insert, its positions' distinct X, Y and Z."""
    kinds: dict[str, list] = {}
    for h in heatsets:
        kinds.setdefault(h.what, []).append(part.P(h.at))
    rows = []
    for what, pts in kinds.items():
        cols = [", ".join(F(v) for v in sorted({round(p[i], 2) for p in pts}))
                for i in range(3)]
        rows.append([f"{what.replace(' screw', '')} ({len(pts)})", *cols])
    return rows


INSERT_HEAD = ["M3 INSERT", "X", "Y", "Z"]
INSERT_ALIGN = ["start", "end", "end", "end"]


# --- base ----------------------------------------------------------------------------------

def base_part(defn) -> Part:
    lay, parts = _lay(), _parts()
    w = lay.wall
    hy, hz = lay.hinge_axis
    prof = B.opening_profile(lay)
    oy0, oy1 = min(p[0] for p in prof), max(p[0] for p in prof)
    oz0, ozs = min(p[1] for p in prof), max(p[1] for p in prof)
    eaves = prof[2][1]
    ch, _ = B.channel_parts(lay)
    groups = H.hinge_groups(lay)
    deck_bot = lay.deck_z - w
    pitch = (oy1 - oy0) / math.ceil((oy1 - oy0) / B.OPENING_PITCH)

    def ann(pt: Part, v):
        f = v["front"]
        fx = lambda y, z: pt.V("front", (0.0, y, z))   # noqa: E731  the left wall
        out = [
            K.Dim(f, fx(oy1, oz0), fx(oy0, oz0), "bottom", 0),
            K.Dim(f, fx(0.0, 0.0), fx(oy0, 0.0), "bottom", 1, text_side="high"),
            K.Dim(f, fx(0.0, 0.0), fx(0.0, eaves), "right", 0),
            K.Dim(f, fx(0.0, 0.0), fx(0.0, ozs), "right", 1),
            K.Leader(f, fx(hy, hz), (f.x(fx(hy, hz)[0]) + 8.0, f.y(hz) + 8.0),
                     f"HINGE AXIS Y {F(hy)} Z {F(hz)}", dot=True),
        ]
        return out

    det, rails, dr = B._detent(lay), B._rails(lay), B._drawer_box(lay)
    part = Part(defn, parts["base"].solid, "Printed route: open-top tub, prints floor down",
                "base frame origin, front-left-bottom outside corner", [],
                [f"{SRC_BODY}: base_tub, opening_profile", SRC_LAYOUT],
                BIG, views=("front", "plan"),
                # principal view: the left wall with the drawer opening
                turn=(((0.0, 0.0, 1.0), 90.0),),
                captions={"front": "FROM LEFT (DRAWER OPENING)", "plan": "PLAN"},
                annotate=ann)
    ident = Part(defn, None, "", "", [], [], ())     # the base frame, unturned
    part.tables = [K.Table("", INSERT_HEAD, _insert_rows(ident, parts["base"].heatsets),
                           INSERT_ALIGN)]
    part.notes = [
        f"Walls and floor {F(w)}. Table: base frame, hole mouths; deck corner inserts point "
        f"down, leaf ones into the back wall. {HEATSET}",
        "Features, base frame: "
        f"deck ledge top Z {F(deck_bot)}, {F(B.LEDGE)} wide; "
        f"cable channel through the back wall X {F(ch.x0)}..{F(ch.x1)}, from Z {F(ch.z0)}; "
        f"floor rails Y {F(rails[0])}, {F(rails[1])}, {F(B.RAIL_W)} x {F(B.RAIL_H)} high; "
        f"stop bar X {F(dr.x1 + FIT)}, {F(B.STOP_BAR_T)} x {F(B.STOP_BAR_H)} high; "
        f"detent groove X {F(det['g0'])}..{F(det['g1'])}, {F(B.GROOVE_D)} deep, its pad "
        f"{F(B.PAD_T)} proud outside; knuckle reliefs R{F(H.KNUCKLE_R + FIT)} at X "
        + ", ".join(f"{F(g0 - FIT)}..{F(g1 + FIT)}" for g0, g1 in groups) + ".",
        f"Drawer opening from the floor's top (Z {F(oz0)}), topped by 45 deg peaks at "
        f"{F(pitch)} pitch.",
        _unconf(),
    ]
    return part


# --- deck ----------------------------------------------------------------------------------

def deck_part(defn) -> Part:
    lay, parts = _lay(), _parts()
    o, w = lay.outer, lay.wall
    x0, y0, z0 = w + FIT, w + FIT, lay.deck_z - w
    us = lay.usb_slot
    ch, _ = B.channel_parts(lay)
    D = o.y1
    bl = B._leaf_boss_len(lay)
    part = Part(defn, parts["deck"].solid, "Printed route: on the base's ledge, prints "
                "plate down", f"plate's front-left-bottom corner (base frame X {F(x0)}, "
                f"Y {F(y0)}, Z {F(z0)})", [], [f"{SRC_BODY}: deck", SRC_LAYOUT], BIG,
                views=("front", "plan"), shift=(-x0, -y0, -z0))
    P = part.P
    rows = []
    for c in lay.standoffs:
        x, y, _ = P((c.cx, c.cy, 0))
        rows.append(["MT2 standoff, insert", F(x), F(y), f"D{F(2 * c.r)}", F(c.z1 - z0)])
    b = lay.mt1_boss
    for k, pg in lay.pegs.items():
        x, y, _ = P((pg.cx, pg.cy, 0))
        rows.append([f"MT1 boss, peg hole {k}", F(x), F(y), f"D{F(PEG_HOLE_D)}", F(b.z1 - z0)])
    for c in lay.supports:
        x, y, _ = P((c.cx, c.cy, 0))
        rows.append([c.what.replace("edge support", "Support"), F(x), F(y),
                     f"D{F(2 * c.r)}", F(c.z1 - z0)])
    xs = sorted({round(P((cx, cy, 0))[0], 2) for cx, cy in B._deck_corners(lay)})
    ys = sorted({round(P((cx, cy, 0))[1], 2) for cx, cy in B._deck_corners(lay)})
    rows.append(["Corner screw holes (4)", ", ".join(F(v) for v in xs),
                 ", ".join(F(v) for v in ys), f"D{F(B.SCREW_CLEAR_D)}", "-"])
    ux0, uy0, _ = P((us.x0, us.y0, 0))
    ux1, uy1, _ = P((us.x1, us.y1, 0))
    rows.append(["USB-C slot", f"{F(ux0)}..{F(ux1)}", f"{F(max(uy0, 0.0))}..{F(uy1)}",
                 "", ""])
    part.tables = [K.Table("", ["FEATURE", "X", "Y", "SIZE", "TOP"], rows,
                           ["start", "end", "end", "end", "end"])]

    def ann(pt: Part, v):
        f, p = v["front"], v["plan"]
        q = lambda x, y: pt.V("plan", (x, y, lay.deck_z))   # noqa: E731
        return [
            K.Dim(f, pt.V("front", (o.x1 - w - FIT, 0, z0)),
                  pt.V("front", (o.x1 - w - FIT, 0, lay.deck_z)), "right", 0, text_side="high"),
            K.Dim(p, q(x0, D - w - FIT), q(ch.x0, D - w - FIT), "top", 0, base=p.rect.y1),
            K.Dim(p, q(ch.x0, D - w - FIT), q(ch.x1, D - w - FIT), "top", 1, base=p.rect.y1,
                  text_side="high"),
        ]

    part.annotate = ann
    part.notes = [
        "Table: centres from the datum; TOP is the boss top above the plate's underside "
        f"(the board rests there); MT2 takes an M3 insert. {HEATSET}",
        f"Notches round the hinge leaf bosses {F(2 * (B.BOSS_R + FIT))} wide, "
        f"{F(bl + FIT)} deep. Channel notch {F(ch.x1 - ch.x0)} wide, {F(D - w - FIT - ch.y0)} "
        "deep: the DC lead comes up through it. Peg holes take "
        "the loose MT1 pin (TDB-PIN-P), the fitted revision's only.",
        _unconf(),
    ]
    return part


# --- lid ----------------------------------------------------------------------------------

def lid_part(defn) -> Part:
    lay, parts = _lay(), _parts()
    o, w, pk = lay.lid_outer, lay.wall, lay.lid_pocket
    gut = lay.lid_cable_gutters
    from demobox.shared import inserts as I
    ox0, oy0, ox1, oy1 = I.lid_opening(lay)
    _, ch = B.channel_parts(lay)
    cells = B.front_cavities(lay)
    part = Part(defn, parts["lid"].solid, "Printed route: drawn screen side up; prints "
                "back down", "lid frame origin, on the hinge axis at the left end of the "
                "screen face; drawn turned 180 deg about X", [],
                [f"{SRC_BODY}: lid, front_cavities", "demobox/shared/inserts.py: lid_opening",
                 SRC_LAYOUT], BIG, views=("front", "plan"),
                turn=(((1.0, 0.0, 0.0), 180.0),),
                captions={"front": "HINGE EDGE", "plan": "PLAN, SCREEN SIDE"})

    def ann(pt: Part, v):
        f, p = v["front"], v["plan"]
        q = lambda x, y: pt.V("plan", (x, y, 0.0))   # noqa: E731
        fr = lambda x, z: pt.V("front", (x, 0.0, z))  # noqa: E731
        return [
            # the opening: pocket and gutters, open on the screen side
            K.Dim(p, q(0.0, oy0), q(ox0, oy0), "bottom", 1, text_side="low"),
            K.Dim(p, q(ox0, oy0), q(ox1, oy0), "bottom", 2),
            K.Dim(p, q(o.x1, 0.0), q(o.x1, oy1), "right", 0, text_side="low"),
            K.Dim(p, q(o.x1, oy1), q(o.x1, oy0), "right", 1),
            # the cable channel, on the hinge edge
            K.Dim(f, fr(0.0, 0.0), fr(ch.x0, 0.0), "bottom", 0),
            K.Dim(f, fr(ch.x0, 0.0), fr(ch.x1, 0.0), "bottom", 1, text_side="high"),
        ]

    part.annotate = ann
    gw = {k: (g.x1 - g.x0) if k != "hinge" else (g.y1 - g.y0) for k, g in gut.items()}
    rows = [[r[0], r[1], r[2], ", ".join(F(-float(z)) for z in r[3].split(", "))]
            for r in _insert_rows(part, parts["lid"].heatsets)]
    part.tables = [K.Table("", ["M3 INSERT", "X", "Y", "DEPTH"], rows, INSERT_ALIGN)]
    part.notes = [
        f"Walls and back {F(w)}. Opening: pocket {F(pk.x1 - pk.x0)} x {F(pk.y1 - pk.y0)} "
        "plus cable gutters (" + ", ".join(f"{k} {F(gw[k])}" for k in gut) + " wide), all "
        f"{F(pk.z1)} deep. Front band hollow, {len(cells)} cells, ribs along X (R18).",
        f"Table: hole mouths, X and Y from the datum, DEPTH below the screen face. {HEATSET}",
        f"Knuckle reliefs R{F(H.KNUCKLE_R + FIT)} about the hinge axis.",
        _unconf(),
    ]
    return part


# --- drawer --------------------------------------------------------------------------------

def drawer_part(defn) -> Part:
    lay, parts = _lay(), _parts()
    d = B._drawer_box(lay)
    w = lay.wall
    fh = lay.drawer_face_hole
    det = B._detent(lay)
    rails = B._rails(lay)
    cy, cz = (fh.x0 + fh.x1) / 2, (fh.y0 + fh.y1) / 2     # the slot (along X): (y, z)
    part = Part(defn, parts["drawer"].solid, "Printed route: slides out of the base's "
                "left side; prints floor down", "the drawer's front-left-bottom corner "
                "(face, front side, floor)", [], [f"{SRC_BODY}: drawer, _detent", SRC_LAYOUT],
                MID, shift=(-d.x0, -d.y0, -d.z0),
                captions={"front": "FRONT (DETENT SIDE)", "side": "FROM LEFT (FACE)"},
                centres=[("side", (d.x0, cy, cz), fh.r)])

    def ann(pt: Part, v):
        f, s, p = v["front"], v["side"], v["plan"]
        sd = lambda y, z: pt.V("side", (d.x0, y, z))    # noqa: E731
        fr = lambda x, z: pt.V("front", (x, d.y0, z))   # noqa: E731
        q = lambda x, y: pt.V("plan", (x, y, d.z1))     # noqa: E731
        # on the slot's edge, up and back from its upper centre
        ey, ez = max(((fh.x0, fh.y0), (fh.x1, fh.y1)), key=lambda c: c[1])
        tip = sd(ey + fh.r * math.sqrt(0.5), ez + fh.r * math.sqrt(0.5))
        return [
            K.Dim(s, sd(d.y0, d.z0), sd(cy, d.z0), "bottom", 0, text_side="high"),
            K.Dim(s, sd(d.y1, d.z0), sd(d.y1, cz), "left", 0),
            K.Leader(s, tip, (s.x(tip[0]) - 4.0, s.rect.y - 16.0),
                     f"FINGER SLOT {F(fh.width)} x {F(fh.length)}"),
            # detent tongue on the front side
            K.Dim(f, fr(d.x0, det["tz0"]), fr(det["tx0"], det["tz0"]), "bottom", 0,
                  text_side="low"),
            K.Dim(f, fr(det["tx0"], det["tz0"]), fr(det["tx1"], det["tz0"]), "bottom", 1,
                  text_side="high"),
            K.Dim(f, fr(d.x1, d.z0), fr(d.x1, det["tz0"]), "right", 0, text_side="high"),
            K.Dim(f, fr(d.x1, det["tz0"]), fr(d.x1, det["tz1"]), "right", 1, text_side="high"),
            # the cavity
            K.Dim(p, q(d.x0 + w, d.y1), q(lay.bay.x1, d.y1), "top", 0, base=p.rect.y1),
            K.Dim(p, q(d.x1, lay.bay.y0), q(d.x1, lay.bay.y1), "right", 0),
        ]

    part.annotate = ann
    part.notes = [
        _parts()["drawer"].note,
        f"Walls and floor {F(w)}. Cavity: cable bay {F(lay.cable_bay.x1 - lay.cable_bay.x0)} "
        f"+ battery bay {F(lay.bay.x1 - lay.bay.x0)}, {F(lay.bay.z1 - lay.bay.z0)} deep (spec). "
        f"Floor grooves at Y {F(rails[0] - d.y0)}, {F(rails[1] - d.y0)}, "
        f"{F(B.RAIL_W + 2 * FIT)} wide x {F(B.RAIL_H + B.GROOVE_CLEAR)} deep. Tongue "
        f"{F(B.TONGUE_LEN)} x {F(B.TONGUE_H)}, {F(B.TONGUE_T)} thick, in {F(B.TONGUE_SLOT)} "
        f"slots; bump at X {F(det['bx0'] - d.x0)}, {F(B.BUMP_W)} + {F(B.BUMP_H)} ramp, "
        f"{F(B.BUMP_H)} proud. The face is the opening's peaked profile, {F(FIT)} smaller.",
        K.unconfirmed_note(("button",)) + " They place the finger hole.",
    ]
    return part


# --- hinges -------------------------------------------------------------------------------

def _hinge_part(defn, which: str) -> Part:
    lay, parts = _lay(), _parts()
    name = f"hinge-{which}"
    solid = parts[name].solid
    bb = solid.BoundingBox()
    hy, hz = lay.hinge_axis
    axis = (hy, hz) if which == "base" else (0.0, 0.0)
    knuckles = H._knuckles(lay, which)
    groups = H.hinge_groups(lay)
    screws = H.base_leaf_screws(lay) if which == "base" else H.lid_leaf_screws(lay)
    frame = "base" if which == "base" else "lid (closed)"
    y_face = hy if which == "base" else 0.0
    part = Part(defn, solid, f"Printed route: one part, {len(groups)} knuckle groups; "
                f"drawn in the {frame} frame", "the part's front-left-bottom corner", [],
                [f"{SRC_HINGE}: hinge_{which}_knuckles", SRC_LAYOUT], (1.0, 0.5),
                views=("front", "side"), shift=(-bb.xmin, -bb.ymin, -bb.zmin),
                captions={"front": "FRONT (LEAF FACE)", "side": "FROM LEFT (PROFILE)"},
                centres=[("front", (x, y_face, z), H.SCREW_HOLE_D / 2) for x, z in screws]
                + [("side", (bb.xmin, *axis), H.KNUCKLE_R)])

    def ann(pt: Part, v):
        f, s = v["front"], v["side"]
        fr = lambda x, z: pt.V("front", (x, y_face, z))   # noqa: E731
        ax = pt.V("side", (bb.xmin, *axis))
        k0, k1 = knuckles[0], knuckles[1]
        # the knuckles' edge: the top for the base half, the bottom for the lid's
        side, z, lane = ("top", bb.zmax, 0) if which == "base" else ("bottom", bb.zmin, 1)
        out = [
            K.Leader(s, (ax[0] + H.KNUCKLE_R * 0.7, ax[1] + H.KNUCKLE_R * 0.7),
                     (s.rect.x1 + 10.0, s.rect.y1 + 6.0),
                     f"R{F(H.KNUCKLE_R)}, PIN HOLE D{F(H.PIN_HOLE_D)}"),
            K.Dim(f, fr(k0[0], z), fr(k0[1], z), side, lane,
                  text_side="low" if which == "base" else "high"),
            K.Dim(f, fr(k0[0], z), fr(k1[0], z), side, lane + 1),
            # the screw holes from the leaf's own end: its foot on the base half,
            # its top on the lid's (the lid half's foot is the knuckles')
            K.Dim(f, fr(bb.xmax, bb.zmin if which == "base" else bb.zmax),
                  fr(bb.xmax, screws[0][1]), "right", 0,
                  text_side=None if which == "base" else "low"),
        ]
        if k0[0] - bb.xmin > 0.01:
            out.append(K.Dim(f, fr(bb.xmin, z), fr(k0[0], z), side, lane + 2,
                             text_side="high"))
        if which == "base":
            out.append(K.Dim(s, pt.V("side", (bb.xmin, axis[0], bb.zmin)), ax, "right", 0))
        return out

    part.annotate = ann
    part.notes = [
        parts[name].note,
        f"Leaf {F(H.LEAF_T)} thick. Knuckles {F(H.KNUCKLE_LEN)} long, {F(FIT)} apart, "
        f"groups of three ({'outer two' if which == 'base' else 'middle one'} on this half); "
        f"the second group repeats the first. Screw holes D{F(H.SCREW_HOLE_D)}, one at the "
        f"middle of each knuckle. Pin: M3 x {H.hinge_bolt_length(lay)} bolt and nyloc per group.",
    ]
    if which == "base":
        part.notes.append(f"Stop shelf {F(H.STOP_REACH)} reach, {F(H.STOP_T)} thick: the lid "
                          "leaf lands on it at 100 deg open.")
    part.notes.append(_unconf())
    return part


def hinge_base_part(defn):
    return _hinge_part(defn, "base")


def hinge_lid_part(defn):
    return _hinge_part(defn, "lid")


# --- small parts -------------------------------------------------------------------------

def clip_part(defn) -> Part:
    lay, parts = _lay(), _parts()
    solid = parts["bezel-clip"].solid
    bb = solid.BoundingBox()
    (sx, sy), = B.clip_screws(lay)[:1]
    r = B.SCREW_CLEAR_D / 2
    part = Part(defn, solid, "Printed route: holds the bezel corner with no screw",
                "the clip's front-left-bottom corner", [parts["bezel-clip"].note],
                [f"{SRC_BODY}: bezel_clip, clip_screws"], SMALL, views=("front", "plan"),
                shift=(-bb.xmin, -bb.ymin, -bb.zmin), chord=0.01,
                centres=[("plan", (sx, sy, 0.0), r)])

    def ann(pt: Part, v):
        p = v["plan"]
        c = pt.V("plan", (sx, sy, 0.0))
        return [
            K.Dim(p, (0.0, p.bb[3]), (c[0], p.bb[3]), "top", 0),
            K.Dim(p, (0.0, 0.0), (0.0, c[1]), "left", 1),
            K.Leader(p, (c[0] + r * 0.7, c[1] + r * 0.7),
                     (p.x(c[0]) + 16.0, p.rect.y1 + 6.0), f"D{F(B.SCREW_CLEAR_D)} THRU"),
        ]

    part.annotate = ann
    part.notes.append(_unconf(("monitor",)))
    return part


def pin_part(defn) -> Part:
    parts = _parts()
    solid = parts["mt1-pin"].solid
    part = Part(defn, solid, "Printed route: loose locating pin for the board's MT1",
                "the pin's axis at its foot", [parts["mt1-pin"].note,
                f"Stands {F(PEG_HEIGHT)} proud of the MT1 boss into the board's MT1 hole; "
                f"{F(PIN.PIN_CHAMFER)} x 45 deg lead-in chamfer on the top edge.",
                _unconf(("USB_C", "TINYVGA", "TinyVGA", "TALLEST"))],
                ["demobox/shared/pin.py: locating_pin", SRC_LAYOUT], (10.0, 5.0),
                views=("front", "plan"), chord=0.005,
                overall_text={"plan-bottom": None, "plan-left": None, "front-bottom": ""},
                centres=[("plan", (0.0, 0.0, 0.0), PEG_DIA / 2)])

    def ann(pt: Part, v):
        f = v["front"]
        x0, y0, x1, _ = f.bb
        return [K.Dim(f, (x0, y0), (x1, y0), "bottom", 0, text=f"D{F(PEG_DIA)}")]

    part.annotate = ann
    return part


# --- packing (tabulated) --------------------------------------------------------------------

def packing_part(defn) -> Part:
    lay, parts = _lay(), _parts()
    b = BATTERIES["xiaomi-pb2020"]
    solid = parts[f"packing-{b.key}"].solid
    bay = lay.bay
    bl, bw, _ = bay.size

    def letters(bank):
        L_, W_, H_ = bank.size
        return {"A": bl - L_ - FIT, "B": W_ + 2 * FIT, "C": (bw - W_ - 2 * FIT) / 2, "H": H_}

    part = Part(defn, solid, f"One per power bank; drawn for {b.key}",
                "the packing's front-left-bottom corner (the battery bay's)",
                [], ["demobox/shared/packing.py: battery_packing",
                     "demobox/parts/batteries.py, docs/superpowers/specs/battery-survey.md",
                     SRC_LAYOUT], MID, shift=(-bay.x0, -bay.y0, -bay.z0),
                captions={"side": "FROM LEFT (OPEN END)"},
                overall_text={"front-left": "H"})

    def ann(pt: Part, v):
        p = v["plan"]
        lt = letters(b)
        q = lambda x, y: pt.V("plan", (x, y, 0))   # noqa: E731
        cy = (bay.y0 + bay.y1) / 2
        return [
            K.Dim(p, q(bay.x1 - lt["A"], bay.y1), q(bay.x1, bay.y1), "top", 0,
                  base=p.rect.y1, text="A"),
            K.Dim(p, q(bay.x0, cy - lt["B"] / 2), q(bay.x0, cy + lt["B"] / 2), "left", 1,
                  text="B"),
            K.Dim(p, q(bay.x0, bay.y0), q(bay.x0, bay.y0 + lt["C"]), "left", 2, text="C",
                  text_side="low"),
        ]

    part.annotate = ann
    rows = []
    for k, bank in BATTERIES.items():
        lt = letters(bank)
        rows.append([k, F(lt["A"]), F(lt["B"]), F(lt["C"]), F(lt["H"])])
    part.tables = [K.Table("", ["BANK (ENGRAVED)", "A", "B", "C", "H"], rows,
                           ["start", "end", "end", "end", "end"])]
    part.notes = [
        f"Outside {F(bl)} x {F(bw)} (the battery bay) x H, the bank's height. The bank lies "
        f"in the U, {F(FIT)} clear at its far end and each side.",
        f"The BANK key is engraved {F(PK.ENGRAVE_DEPTH)} deep in the end-stop's top, up to "
        f"{F(PK.ENGRAVE_SIZE)} high. Prints flat, engraved face up.",
        K.unconfirmed_note(("battery", "button")),
    ]
    return part


BUILDERS = {
    "base": base_part, "deck": deck_part, "lid": lid_part, "drawer": drawer_part,
    "hinge-base": hinge_base_part, "hinge-lid": hinge_lid_part, "bezel-clip": clip_part,
    "mt1-pin": pin_part,
}


def render(defn: names.SheetDef):
    if defn.kind == "packing":
        return render_part(packing_part(defn))
    return render_part(BUILDERS[defn.subject](defn))
