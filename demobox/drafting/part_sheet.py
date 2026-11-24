"""Part sheets: the printed route's parts (A4, one each) and the laser
route's printed fittings (A3, all four on one sheet).

Each part is drawn from its hidden-line projection (``hlr.project``), first
angle, in the views that show it best: the principal view is the face that
says most about the part (the hinge edge for the lid), the plan below it, the view from its left beside it where that adds
something.  A ``Part`` turns the solid into its drawing frame (``turn``, then
``shift``) and every point the sheet dimensions is put through the same turn,
so a dimension and the line it measures cannot disagree.

The overall sizes are dimensioned on every sheet; the features a checker
needs are dimensioned on the view that shows them, or tabulated where there
are more of them than a view can carry (pins, holes, pockets).  Every figure
is read off the same layout and part code that builds the STEP.

The fittings sheet (``TDB-FIT-L``) draws each of ``laser.fittings.printed_parts``
as its own small set of views, stacked down the sheet at one scale
(``render_fittings``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import cadquery as cq

import demobox  # noqa: F401  (puts the submodule on sys.path)
from tools.drafting import dims, style

from demobox.drafting import names
from demobox.drafting import sheetkit as K
from demobox.drafting.hlr import project, to_view, view_bbox
from demobox.layout import (LID_OPEN_DEG, MAGNET_D, MAGNET_RECESS, MAGNET_T, PEG_DIA,
                            PEG_HOLE_D, PIN_PROUD, PIN_ROD_D, ROUTES, layout)
from demobox.laser import fittings as LF
from demobox.printed import body as B
from demobox.shared import hinge as H
from demobox.shared import pin as PIN
from demobox.shared import solids as S

F = K.fmt
SRC_BODY = "demobox/printed/body.py"
SRC_LAYOUT = "demobox/layout.py (layout)"
SRC_HINGE = "demobox/shared/hinge.py"

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
    #: The part's name in its route's ``printed_parts``.
    key: str = ""

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
        # a value too long for its span goes outside, past the far end (a
        # vertical one stays centred, its arrows outside)
        t = text.get(key, "")
        if t is not None:
            out.append(K.Dim(*args, text=t or None,
                             text_side="high" if args[3] in ("top", "bottom") else None))

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

def _lay(route: str = "printed"):
    return layout(ROUTES[route])


def _parts():
    return B.printed_parts(_lay())


def _unconf(keys=K.BODY_KEYS) -> str:
    return K.unconfirmed_note(keys)


def _span(a: float, b: float) -> str:
    return f"{F(a)}..{F(b)}"


def callouts(pv: K.PView, items, side: str = "right", gap: float = 10.0,
             step: float = 7.0) -> list:
    """Leaders from view ``pv``'s model points to labels in a column off its
    ``side`` ("right" or "left"), in the tips' up-down order, ``step`` apart
    at least: (tip, text) each."""
    items = sorted(items, key=lambda it: pv.y(it[0][1]))
    ys: list[float] = []
    for tip, _ in items:
        y = pv.y(tip[1])
        ys.append(max(y, ys[-1] + step) if ys else y)
    # centre the column on the tips it serves
    shift = (sum(pv.y(t[1]) for t, _ in items) - sum(ys)) / len(ys)
    x = pv.rect.x1 + gap if side == "right" else pv.rect.x - gap
    return [K.Leader(pv, tip, (x, y + shift), text) for (tip, text), y in zip(items, ys)]


FEATURE_HEAD = ["FEATURE", "X", "Y", "SIZE", "Z"]
FEATURE_ALIGN = ["start", "end", "end", "end", "end"]


# --- base ----------------------------------------------------------------------------------

def base_part(defn) -> Part:
    lay, parts = _lay(), _parts()
    o, w, rim = lay.outer, lay.wall, lay.rim_z
    hy, hz = lay.hinge_axis
    pl, rel, n = lay.plinth, lay.plinth_relief, lay.hinge_notch
    mt2 = lay.pins["MT2"]
    mt1 = {k.split("/")[0]: c for k, c in lay.pins.items() if k.endswith("/MT1")}
    base_kn = [k for k in H.knuckle_plan(lay) if k.part == "base"]
    part = Part(defn, parts["base"].solid, "Printed route: open-top tub, prints floor down",
                "base frame origin, front-left-bottom outside corner", [],
                [f"{SRC_BODY}: base", SRC_LAYOUT, f"{SRC_HINGE}: knuckles, seal_bead"],
                (0.5, 0.4), views=("front", "plan"), hidden=frozenset({"front"}),
                captions={"front": "FRONT", "plan": "PLAN"},
                centres=[("plan", (mt2.cx, mt2.cy, 0.0), PEG_DIA / 2)]
                + [("plan", (c.cx, c.cy, 0.0), PEG_HOLE_D / 2) for c in mt1.values()]
                + [("plan", (c.cx, c.cy, 0.0), S.MAGNET_POCKET_D / 2) for c in lay.lid_catch])

    def ann(pt: Part, v):
        f, p = v["front"], v["plan"]
        q = lambda x, y: pt.V("plan", (x, y, 0.0))      # noqa: E731
        fr = lambda x, z: pt.V("front", (x, 0.0, z))    # noqa: E731
        top = o.y1
        c1, c2 = lay.lid_catch[0], lay.lid_catch[-1]
        return [
            # the plinth across, from the datum
            K.Dim(p, q(0.0, pl.y0), q(pl.x0, pl.y0), "bottom", 1, text_side="low"),
            K.Dim(p, q(pl.x0, pl.y0), q(pl.x1, pl.y0), "bottom", 1),
            # the notch along the back
            K.Dim(p, q(0.0, top), q(n.x0, top), "top", 0, base=p.rect.y1),
            K.Dim(p, q(n.x0, top), q(n.x1, top), "top", 0, base=p.rect.y1, text_side="high"),
            # the rim's height on the front view
            K.Dim(f, fr(o.x1, 0.0), fr(o.x1, rim), "right", 0),
            *callouts(p, [(q(pl.x1 - 8.0, (pl.y0 + pl.y1) / 2), "PLINTH"),
                          (q(mt2.cx, mt2.cy), "MT2 PIN"),
                          (q(max(c.cx for c in mt1.values()), pl.y0 + 4.0), "MT1 HOLES (2)"),
                          (q(c2.cx - c2.r * 0.7, c2.cy + c2.r * 0.7), "MAGNET POCKETS (2)"),
                          (q((n.x0 + n.x1) / 2, (n.y0 + o.y1) / 2), "NOTCH")]),
            K.Leader(f, fr(c1.cx, rim), (f.x(fr(c1.cx, 0)[0]) + 30.0, f.rect.y1 + 8.0),
                     "RIM (SEAM)"),
        ]

    part.annotate = ann
    rows = [
        ["Plinth", _span(pl.x0, pl.x1), _span(pl.y0, pl.y1),
         f"{F(pl.x1 - pl.x0)} x {F(pl.y1 - pl.y0)}", f"top {F(pl.z1)}"],
        ["Plinth relief", _span(rel.x0, rel.x1), _span(rel.y0, rel.y1),
         f"{F(rel.x1 - rel.x0)} x {F(rel.y1 - rel.y0)}", f"from {F(rel.z0)}"],
        ["MT2 pin", F(mt2.cx), F(mt2.cy), f"D{F(PEG_DIA)}", f"top {F(mt2.z1)}"],
        *[[f"MT1 hole, {rev}", F(c.cx), F(c.cy), f"D{F(PEG_HOLE_D)}",
           f"to {F(pl.z1 - PIN.socket_depth(lay))}"] for rev, c in sorted(mt1.items())],
        ["Magnet pockets", ", ".join(F(c.cx) for c in lay.lid_catch),
         F(lay.lid_catch[0].cy), f"D{F(S.MAGNET_POCKET_D)}",
         f"{F(rim - S.MAGNET_POCKET_DEPTH)}..{F(rim)}"],
        ["Notch", _span(n.x0, n.x1), _span(n.y0, o.y1), f"{F(n.x1 - n.x0)} wide",
         f"from {F(rim)}"],
        *[["Base knuckle", _span(k.x0, k.x1), F(hy), f"R{F(H.KNUCKLE_R)}", F(hz)]
          for k in base_kn],
    ]
    part.tables = [K.Table("", FEATURE_HEAD, rows, FEATURE_ALIGN)]
    part.notes = [
        f"Walls and floor {F(w)}; rim (the seam) at Z {F(rim)}. Table: base frame; the "
        "plinth's top is the board's underside; the knuckle's axis is the hinge's.",
        f"The MT2 pin is printed on the plinth, D{F(PEG_DIA)} with a {F(PIN.PIN_CHAMFER)} "
        "lead-in chamfer. Each MT1 hole takes the loose printed pin (TDB-PIN-P) under the "
        "fitted board revision's MT1. The relief clears the v3.2 board's USB plug.",
        f"Magnet pockets: open at the rim, in the catch blocks in the front corners; a "
        f"{F(MAGNET_D)} x {F(MAGNET_T)} magnet sits {F(MAGNET_RECESS)} below the rim. "
        "Notch: the monitor cable passes over the back wall, which is whole below the rim.",
        "Seal bead along the back edge above the rim, X "
        + ", ".join(_span(a, b) for a, b in H.bead_x(lay)) + ": it closes the back under the "
        f"lid's relief. Stop block under each lid knuckle: the lid stops at {LID_OPEN_DEG:g} "
        "deg.",
        parts["base"].note,
        _unconf(),
    ]
    return part


# --- lid ----------------------------------------------------------------------------------

def lid_part(defn) -> Part:
    lay, parts = _lay(), _parts()
    o, w = lay.lid_outer, lay.wall
    lid_kn = [k for k in H.knuckle_plan(lay) if k.part == "lid"]
    mags = [lay.catch_lid_magnet(c) for c in lay.lid_catch]
    part = Part(defn, parts["lid"].solid, "Printed route: a tray, drawn open side up; "
                "prints top plate down", "lid frame origin, on the hinge axis at the left "
                "side face; drawn turned 180 deg about X", [],
                [f"{SRC_BODY}: lid", f"{SRC_HINGE}: knuckles, knuckle_cut, pin_length",
                 SRC_LAYOUT], (0.5, 0.4), views=("front", "plan"),
                turn=(((1.0, 0.0, 0.0), 180.0),), hidden=frozenset({"front"}),
                captions={"front": "HINGE EDGE", "plan": "PLAN, INSIDE THE TRAY"},
                centres=[("plan", (m.cx, m.cy, 0.0), S.MAGNET_POCKET_D / 2) for m in mags])

    def ann(pt: Part, v):
        f, p = v["front"], v["plan"]
        fr = lambda x: pt.V("front", (x, 0.0, -H.KNUCKLE_R))   # noqa: E731  knuckles' edge
        q = lambda x, y: pt.V("plan", (x, y, 0.0))             # noqa: E731
        out = []
        for i, k in enumerate(lid_kn):
            out.append(K.Dim(f, fr(0.0), fr(k.x0), "top", 2 * i, text_side="low"))
            out.append(K.Dim(f, fr(k.x0), fr(k.x1), "top", 2 * i + 1, text=F(k.x1 - k.x0),
                             text_side="low"))
        m = mags[0]
        k = lid_kn[-1]
        out += [
            *callouts(f, [(fr(k.x1 - 2.0), f"KNUCKLES, BORE D{F(H.PIN_HOLE_D)}")]),
            *callouts(p, [(q(mags[-1].cx - m.r * 0.7, m.cy - m.r * 0.7), "MAGNET POCKETS (2)")]),
            K.Dim(p, q(0.0, m.cy), q(m.cx, m.cy), "bottom", 1, text_side="low"),
        ]
        return out

    part.annotate = ann
    rows = [[f"Lid knuckle {i}", _span(k.x0, k.x1), "0.00", f"R{F(H.KNUCKLE_R)}", "0.00"]
            for i, k in enumerate(lid_kn, 1)]
    for m in mags:
        x, y, _ = part.P((m.cx, m.cy, 0.0))
        rows.append(["Magnet pocket", F(x), F(y), f"D{F(S.MAGNET_POCKET_D)}",
                     f"{F(S.MAGNET_POCKET_DEPTH)} deep"])
    part.tables = [K.Table("", FEATURE_HEAD, rows, FEATURE_ALIGN)]
    inside = (o.x1 - o.x0 - 2 * w, o.y1 - o.y0 - 2 * w, o.z1 - w)
    part.notes = [
        f"Tray: top plate and walls {F(w)}; inside {F(inside[0])} x {F(inside[1])}, "
        f"{F(inside[2])} deep. The inside face is flat: the monitor's back is stuck to it "
        "with double-sided foam tape (VHB type)"
        + (", and the boost module beside it in the strip by the hinge." if lay.boost_in_lid
           else "."),
        f"Knuckles bored D{F(H.PIN_HOLE_D)} for the {F(PIN_ROD_D)} rod (slip fit); the first "
        f"knuckle's bore is blind, {F(H.ROD_BLIND)} short of its left face; the last "
        f"{F(H.PRESS_LEN)} of the right knuckle's bore, at the side face, is D{F(H.PRESS_D)}, "
        f"a press fit. Rod {PIN_ROD_D:g} mm x {H.pin_length(lay):.1f} mm, pressed in from the "
        "right side face. "
        f"The back face stops the lid at {LID_OPEN_DEG:g} deg.",
        f"Magnet pockets open at the seam, in the catch blocks over the base's; a "
        f"{F(MAGNET_D)} x {F(MAGNET_T)} magnet sits {F(MAGNET_RECESS)} in. Elsewhere along "
        f"the back the lid is relieved to R{F(lay.hinge_relief_r)} about the axis, clear of "
        "the base's seal bead; the notch passes the monitor cable.",
        parts["lid"].note,
        _unconf(),
    ]
    return part


# --- the loose pin ---------------------------------------------------------------------------

def pin_part(defn) -> Part:
    lay, parts = _lay(), _parts()
    solid = parts["mt1-pin"].solid
    part = Part(defn, solid, "Printed route: loose locating pin for the board's MT1",
                "the pin's axis at its foot", [parts["mt1-pin"].note,
                f"Stands in the plinth's MT1 hole ({F(PIN.socket_depth(lay))} deep, to the "
                f"floor) and {F(PIN_PROUD)} proud of the PCB top through the board's MT1 hole; "
                f"{F(PIN.PIN_CHAMFER)} x 45 deg lead-in chamfer on the top edge.",
                _unconf(("USB_C", "TINYVGA", "TinyVGA", "TALLEST", "battery"))],
                ["demobox/shared/pin.py: locating_pin", SRC_LAYOUT], (5.0, 2.0, 1.0),
                views=("front", "plan"), chord=0.005,
                overall_text={"plan-bottom": None, "plan-left": None, "front-bottom": ""},
                centres=[("plan", (0.0, 0.0, 0.0), PEG_DIA / 2)], key="mt1-pin")

    def ann(pt: Part, v):
        f = v["front"]
        x0, y0, x1, _ = f.bb
        return [K.Dim(f, (x0, y0), (x1, y0), "bottom", 0, text=f"D{F(PEG_DIA)}")]

    part.annotate = ann
    return part


# --- the laser route's printed fittings ------------------------------------------------------

def _fitting(defn, key: str, solid, views, captions_, note: str, annotate=None,
             frame: str = "base frame", hidden: bool = False) -> Part:
    bb = solid.BoundingBox()
    caps = {v: f"{key.upper()}, {captions_[v]}" for v in views}
    return Part(defn, solid, "", f"{key}: its front-left-bottom corner, {frame} axes",
                [note], [], (1.0, 0.5), views=views, shift=(-bb.xmin, -bb.ymin, -bb.zmin),
                hidden=frozenset({"front"} if hidden else ()), captions=caps,
                annotate=annotate, key=key)


def _knuckle_dims(lay, part_name: str):
    """Each knuckle of ``part_name``'s on the front view's top edge, X from
    the block's left end."""
    kn = [k for k in H.knuckle_plan(lay) if k.part == part_name]

    def ann(pt: Part, v):
        f = v["front"]
        z = pt.solid.BoundingBox().zmax
        fr = lambda x: pt.V("front", (x, 0.0, z))   # noqa: E731
        x0 = pt.solid.BoundingBox().xmin
        out = []
        for i, k in enumerate(kn):
            out.append(K.Dim(f, fr(x0), fr(k.x0), "top", 2 * i, text_side="low"))
            out.append(K.Dim(f, fr(k.x0), fr(k.x1), "top", 2 * i + 1, text=F(k.x1 - k.x0)))
        return out

    return ann


def fitting_parts(defn) -> list[Part]:
    """``laser.fittings.printed_parts``, each as a Part, in its order."""
    lay = _lay("laser")
    made = LF.printed_parts(lay, lay.wall)
    out = []
    for key, p in made.items():
        if key == "knuckles-base":
            out.append(_fitting(defn, key, p.solid, ("front", "side", "plan"),
                                {"front": "FRONT", "side": "FROM LEFT", "plan": "PLAN"},
                                p.note, _knuckle_dims(lay, "base"), hidden=True))
        elif key == "knuckles-lid":
            out.append(_fitting(defn, key, p.solid, ("front", "side", "plan"),
                                {"front": "FRONT", "side": "FROM LEFT", "plan": "PLAN"},
                                p.note, _knuckle_dims(lay, "lid"), frame="lid frame (closed)",
                                hidden=True))
        elif key.startswith("seal-bead"):
            out.append(_fitting(defn, key, p.solid, ("front", "side"),
                                {"front": "FRONT", "side": "PROFILE"}, p.note))
        elif key == "magnet-block":
            def ann(pt: Part, v):
                pl = v["plan"]
                c = pt.V("plan", (pt.solid.BoundingBox().center.x,
                                  pt.solid.BoundingBox().center.y, 0.0))
                r = S.MAGNET_POCKET_D / 2
                return [K.Leader(pl, (c[0] + r * 0.7, c[1] + r * 0.7),
                                 (pl.rect.x1 + 10.0, pl.rect.y1 + 4.0),
                                 f"POCKET D{F(S.MAGNET_POCKET_D)} x "
                                 f"{F(S.MAGNET_POCKET_DEPTH)} DEEP")]
            out.append(_fitting(defn, key, p.solid, ("front", "plan"),
                                {"front": "FRONT", "plan": "PLAN"}, p.note, ann,
                                frame="its own"))
        else:
            raise ValueError(f"no drawing for the laser fitting {key!r}")
    return out


def render_fittings(defn: names.SheetDef):
    """Every fitting's views at one scale, stacked down the sheet's left,
    a new column when one runs out of paper; the notes in what is left."""
    lay = _lay("laser")
    parts = fitting_parts(defn)
    projs = {p.key: {v: project(p.shape(), v, chord=p.chord) for v in p.views} for p in parts}
    bbs = {p.key: part_bbs(p) for p in parts}

    def build(sheet, s):
        frame = sheet.frame
        left, top = frame.x + 6.5, frame.y1 - 6.5
        col_right = left
        views_all: dict[str, K.PView] = {}
        ann_all: list = []
        placed = []
        def place(p, at):
            def make(views):
                a = _overall(views, p.overall_text)
                if p.annotate:
                    a += p.annotate(p, views)
                return K.captioned(views, a, p.captions)

            views, ann = K.solve(projs[p.key], s, make, frame, bbs=bbs[p.key], anchor=at)
            used = K._union([K._rect_box(v.rect) for v in views.values()]
                            + [a.extent() for a in ann])
            return views, ann, used

        for p in parts:
            views, ann, used = place(p, (left, top))
            if used[1] < frame.y + 6.0 and top < frame.y1 - 6.5:
                # off the bottom: a new column, right of everything so far
                left, top = col_right + 12.0, frame.y1 - 6.5
                views, ann, used = place(p, (left, top))
            col_right = max(col_right, used[2])
            top = used[1] - 8.0
            for k, v in views.items():
                views_all[f"{p.key}:{k}"] = v
            ann_all += ann
            placed.append((p, views))
        lay_ = K.Layout(views_all, ann_all)

        def draw(sh):
            for p, views in placed:
                for k, v in views.items():
                    K.draw_view(sh.canvas, v, hidden=k in p.hidden)
                K.datum_mark(sh.canvas, views)

        notes = ["Datum (target): each part's front-left-bottom corner, in the base frame's "
                 "axes (knuckles-lid: the lid frame's, closed; magnet-block: as printed)."]
        notes += [p.notes[0] for p in parts]
        notes += [
            f"Rod bore D{F(H.PIN_HOLE_D)} (slip) for the {F(PIN_ROD_D)} hinge rod; in "
            f"knuckles-lid the first knuckle's bore is blind, {F(H.ROD_BLIND)} short of its "
            f"left face, and the last {F(H.PRESS_LEN)} at the right side face is "
            f"D{F(H.PRESS_D)}, a press fit. The stop blocks in knuckles-base stop the lid at "
            f"{LID_OPEN_DEG:g} deg.",
            f"Board pins: {F(PIN_ROD_D)} mm rod, {LF.board_pin_length(lay):.1f} long, bought "
            "(not drawn).",
            _unconf(),
        ]
        sources = ["demobox/laser/fittings.py (printed_parts)",
                   f"{SRC_HINGE} (knuckles, knuckle_cut, seal_bead)", SRC_LAYOUT]
        legend = K.Legend([K.L_VISIBLE, K.L_HIDDEN, K.L_DIM])
        return lay_, [], legend, notes, sources, draw

    return K.render(defn, build, subtitle="Laser route: the printed knuckle blocks, seal bead "
                    "and magnet block", material=K.PRINTED_MATERIAL, tolerance=K.PRINTED_TOL,
                    scales=(1.0, 0.5))


BUILDERS = {"base": base_part, "lid": lid_part, "mt1-pin": pin_part}


def render(defn: names.SheetDef):
    if defn.kind == "fittings":
        return render_fittings(defn)
    return render_part(BUILDERS[defn.subject](defn))
