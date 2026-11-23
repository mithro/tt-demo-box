"""What every sheet in the set shares: views placed first-angle, dimensions
and callouts reserved before they are drawn, free-space bookkeeping for the
tables and notes, the title block, the UNCONFIRMED list, and the files.

Built on the submodule's ``tools.drafting``: its ``Sheet`` draws the frame,
the zones, the title block, the tables and the note flow; its ``dims`` the
dimensions, leaders and balloons; its ``style`` every weight, line type and
lettering size.  Nothing here draws text below its 2.5 mm floor.

Reserve, then draw (the submodule's README): every dimension, callout and
caption is a record whose paper (``extent``) is known before anything is
drawn.  The views and their annotation are laid out first, the paper they
take is subtracted from the frame, and the tables and notes are flowed into
what is left; only then is anything drawn.  A sheet whose notes do not fit
steps the views down a scale and tries again, and fails loudly if nothing
fits rather than letting text run off the frame.
"""

from __future__ import annotations

import functools
import itertools
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import demobox  # noqa: F401  (puts the submodule on sys.path)
from tools import reproducible
from tools.drafting import dims, style
from tools.drafting.sheet import Rect, Sheet, TitleBlock
from tools.drafting.view import STANDARD_SCALES, scale_text

from demobox._paths import ROOT
from demobox.drafting import names
from demobox.drafting.hlr import Projection

# --- line work -----------------------------------------------------------------------

VISIBLE = dict(w=style.W_OUTLINE, colour=style.C_LINE)
HIDDEN = dict(w=style.W_HIDDEN, colour=style.C_LINE, dash=style.D_HIDDEN)
PHANTOM = dict(w=style.W_PHANTOM, colour=style.C_PHANTOM, dash=style.D_PHANTOM)
CENTRE = dict(w=style.W_CENTRE, colour=style.C_LINE, dash=style.D_CENTRE)

#: Gap between two views, for the caption and a dimension lane.
GAP = 16.0
#: A dimension lane: the first sits LANE0 off the view, the next DIM_STEP on.
LANE0 = 7.0

DRAWN = "generated"
REV = "A"
PRINTED_MATERIAL = "PETG or PLA"
PRINTED_TOL = "+/-0.3 unless noted"


# --- the version stamp ------------------------------------------------------------------

#: Everything that is not build product: a commit that only regenerates
#: output/ must not change the version the sheets carry, or committing the
#: sheets would change the sheets (see ``tools.reproducible.source_version``,
#: whose pathspec is the submodule's layout, not this repository's).
SOURCE_ONLY = (".", ":(exclude)output")


@functools.lru_cache(maxsize=1)
def version() -> str:
    """The abbreviated hash of the last commit that changed a source file,
    with ``+`` when sources are modified and uncommitted.  The hash alone, not
    ``git describe``: the tag adds nothing a hash does not say, and on an A4
    title block it does not fit the VERSION cell."""
    commit = reproducible._git(ROOT, "log", "-1", "--format=%h", "--", *SOURCE_ONLY)
    if not commit:
        return reproducible.UNVERSIONED
    dirty = reproducible._git(ROOT, "status", "--porcelain", "--", *SOURCE_ONLY)
    return commit + (reproducible.DIRTY_MARK if dirty else "")


# --- UNCONFIRMED ------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def unconfirmed() -> tuple[tuple[str, str], ...]:
    """verify.py's UNCONFIRMED list, (what, detail), both routes."""
    from demobox import checks
    from demobox import layout as L
    out = checks.Unconfirmed()
    for wall in L.ROUTES.values():
        report = checks.Report()
        lay = L.layout(wall)
        for proof in checks.PROOFS:
            proof(report, lay)
        for item in report.unconfirmed:
            out(*item)
    return tuple(out)


def _group(what: str) -> tuple[str, str]:
    """An UNCONFIRMED item's group and its short name in that group."""
    from demobox.parts.batteries import BATTERIES
    from demobox.parts.cables import CABLES
    from demobox.parts.monitors import MONITORS
    for k in MONITORS:
        if k in what:
            return "monitors", k
    for k in BATTERIES:
        if k in what:
            return "power banks", k
    for k in CABLES:
        if k in what:
            return "cables", k
    return "board", what


GROUP_ORDER = ("monitors", "power banks", "board", "cables")


def unconfirmed_note(keys: tuple[str, ...] | None = None, lead: str = "") -> str:
    """One note naming the UNCONFIRMED inputs whose name mentions any of
    ``keys`` (all of them for None), grouped by what they belong to: each
    monitor, bank and cable once, however many of its figures are
    placeholders (``make verify`` lists every figure)."""
    items = [w for w, _ in unconfirmed()
             if keys is None or any(k.lower() in w.lower() for k in keys)]
    if not items:
        return "UNCONFIRMED inputs: none feed this part."
    groups: dict[str, list[str]] = {}
    for w in items:
        g, short = _group(w)
        if short not in groups.setdefault(g, []):
            groups[g].append(short)
    from demobox.parts.batteries import BATTERIES
    from demobox.parts.cables import CABLES
    from demobox.parts.monitors import MONITORS
    every = {"monitors": MONITORS, "power banks": BATTERIES, "cables": CABLES}

    def say(g):
        names_ = groups[g]
        if g in every and set(names_) == set(every[g]):
            return f"all {len(names_)} {g}"
        return f"{g} " + ", ".join(names_)

    body = "; ".join(say(g) for g in GROUP_ORDER if g in groups)
    return f"UNCONFIRMED inputs{lead} (placeholders; make verify lists each): {body}."


#: The UNCONFIRMED names that feed the box's own size: every monitor (the
#: lid pocket), the board and TinyVGA heights (the deck and the lid's
#: clearance) and the cables (bend radii size the deck cavity and gutters).
BODY_KEYS = ("monitor", "USB_C", "TINYVGA", "TinyVGA", "TALLEST", "cable", "length",
             "connector", "pigtail")


# --- placed views ----------------------------------------------------------------------

@dataclass
class PView:
    """A projection placed on the sheet: sheet = (ox, oy) + scale * model."""

    name: str
    proj: Projection
    scale: float
    ox: float
    oy: float
    bb: tuple[float, float, float, float]

    def x(self, m: float) -> float:
        return self.ox + m * self.scale

    def y(self, m: float) -> float:
        return self.oy + m * self.scale

    def pt(self, a: float, b: float) -> tuple[float, float]:
        return self.x(a), self.y(b)

    @property
    def rect(self) -> Rect:
        x0, y0, x1, y1 = self.bb
        return Rect(self.x(x0), self.y(y0), (x1 - x0) * self.scale, (y1 - y0) * self.scale)


def first_angle(projs: dict[str, Projection], scale: float, left: float, top: float,
                gap_x: float = GAP, gap_y: float = GAP,
                bbs: dict[str, tuple] | None = None) -> dict[str, PView]:
    """Place the front at (left, top), the side to its right and the plan below
    it, aligned as first-angle projection puts them.  Any of the three may be
    missing (but the front)."""
    bbs = bbs or {}
    bb = {k: bbs.get(k) or p.bbox() for k, p in projs.items()}
    out: dict[str, PView] = {}
    fx0, fy0, fx1, fy1 = bb["front"]
    ox = left - fx0 * scale
    oy = top - fy1 * scale
    out["front"] = PView("front", projs["front"], scale, ox, oy, bb["front"])
    if "side" in projs:
        sx0 = bb["side"][0]
        sox = left + (fx1 - fx0) * scale + gap_x - sx0 * scale
        out["side"] = PView("side", projs["side"], scale, sox, oy, bb["side"])
    if "plan" in projs:
        py1 = bb["plan"][3]
        poy = oy + fy0 * scale - gap_y - py1 * scale
        out["plan"] = PView("plan", projs["plan"], scale, ox, poy, bb["plan"])
    return out


def draw_lines(c, pv: PView, polylines, **kw) -> None:
    for pl in polylines:
        c.polyline([pv.pt(a, b) for a, b in pl], **kw)


def datum_mark(c, views: dict[str, "PView"]) -> None:
    """The datum target at the drawing frame's origin, in every view."""
    for v in views.values():
        dims.datum_marker(c, *v.pt(0.0, 0.0), label="")


def draw_view(c, pv: PView, hidden: bool = True) -> None:
    if hidden:
        draw_lines(c, pv, pv.proj.hidden, **HIDDEN)
    draw_lines(c, pv, pv.proj.visible, **VISIBLE)


def _owner(a):
    return getattr(a, "pv", None)


def _overlaps(a: "Box4", b: "Box4") -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def captioned(views: dict[str, "PView"], ann: list, captions: dict[str, str]) -> list:
    """``ann`` plus a caption above each view, lifted clear of anything of
    that view's own that stands above it under the caption."""
    out = list(ann)
    for k, v in views.items():
        if k not in captions:
            continue
        r = v.rect
        w = style.text_width(captions[k], style.T_LABEL, bold=True) / 2 + 1.0
        tops = [e[3] for e in (a.extent() for a in ann if _owner(a) is v)
                if e[3] > r.y1 + 0.5 and e[0] < r.cx + w and e[2] > r.cx - w]
        lift = max([0.0] + [t - r.y1 + 1.0 for t in tops])
        out.append(Caption(v, captions[k], lift=lift))
    return out


def solve(projs: dict[str, Projection], scale: float, make_ann, frame,
          bbs: dict | None = None, gap: float = 10.0, anchor=None):
    """Place the views first-angle with the gaps between them just wide
    enough for each view's own annotation, then move the whole block to the
    top-left of the frame.  ``make_ann(views)`` gives the annotation records.
    Returns (views, annotations)."""
    gx = gy = gap
    for _ in range(6):
        views = first_angle(projs, scale, 0.0, 0.0, gx, gy, bbs)
        ann = make_ann(views)
        grp = {k: _union([_rect_box(v.rect)] + [a.extent() for a in ann if _owner(a) is v])
               for k, v in views.items()}
        grown = False
        if "side" in views:
            f, s = grp["front"], grp["side"]
            if f[1] < s[3] and s[1] < f[3] and f[2] + 4.0 > s[0]:
                gx += f[2] + 4.0 - s[0]
                grown = True
        if "plan" in views:
            f, p = grp["front"], grp["plan"]
            if f[0] < p[2] and p[0] < f[2] and p[3] + 4.0 > f[1]:
                gy += p[3] + 4.0 - f[1]
                grown = True
            if "side" in views and _overlaps(grp["side"], grp["plan"]):
                gx += grp["plan"][2] + 4.0 - grp["side"][0]
                grown = True
        if not grown:
            break
    used = _union([g for g in grp.values()] + [a.extent() for a in ann])
    # clear of the frame, and of the centring marks running 5 mm in from it;
    # or with the block's paper starting at ``anchor`` (left, top)
    left, top = anchor or (frame.x + 6.5, frame.y1 - 6.5)
    views = first_angle(projs, scale, left - used[0], top - used[3], gx, gy, bbs)
    return views, make_ann(views)


# --- annotation records: reserve, then draw ---------------------------------------------

Box4 = tuple[float, float, float, float]


def _union(boxes) -> Box4:
    boxes = list(boxes)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def text_box(x, y, s, size=style.T_LABEL, anchor="start", bold=False) -> Box4:
    w = style.text_width(s, size, bold=bold)
    x0 = {"start": x, "middle": x - w / 2, "end": x - w}[anchor]
    return (x0, y - style.descender(size), x0 + w, y + style.text_height(size))


@dataclass
class Dim:
    """A linear dimension between model points ``a`` and ``b`` of view
    ``pv``, on a lane off one ``side`` of the view's rectangle."""

    pv: PView
    a: tuple[float, float]
    b: tuple[float, float]
    side: str                    # "top", "bottom", "left", "right"
    lane: int = 0
    text: str | None = None
    text_side: str | None = None
    #: Lanes are counted from this sheet coordinate instead of the view's edge.
    base: float | None = None

    def _geom(self):
        p1, p2 = self.pv.pt(*self.a), self.pv.pt(*self.b)
        r = self.pv.rect
        horizontal = self.side in ("top", "bottom")
        d = LANE0 + self.lane * style.DIM_STEP
        if self.side == "bottom":
            line = (r.y if self.base is None else self.base) - d
            off = line - min(p1[1], p2[1])
        elif self.side == "top":
            line = (r.y1 if self.base is None else self.base) + d
            off = line - max(p1[1], p2[1])
        elif self.side == "left":
            line = (r.x if self.base is None else self.base) - d
            off = line - min(p1[0], p2[0])
        else:
            line = (r.x1 if self.base is None else self.base) + d
            off = line - max(p1[0], p2[0])
        value = abs(self.b[0] - self.a[0]) if horizontal else abs(self.b[1] - self.a[1])
        text = self.text if self.text is not None else f"{value:.2f}"
        g = dims.linear_geometry(p1, p2, off, horizontal=horizontal, text=text,
                                 text_side=self.text_side)
        return p1, p2, off, horizontal, text, g

    def extent(self) -> Box4:
        p1, p2, _, horizontal, _, g = self._geom()
        tail = 0.0 if g.inside else style.ARROW_LEN * 2.2
        if horizontal:
            box = (g.lo - tail, min(g.line, p1[1], p2[1]), g.hi + tail, max(g.line, p1[1], p2[1]))
        else:
            box = (min(g.line, p1[0], p2[0]), g.lo - tail, max(g.line, p1[0], p2[0]), g.hi + tail)
        return _union([box, g.text_box])

    def label_box(self) -> Box4:
        return self._geom()[5].text_box

    def draw(self, c) -> None:
        p1, p2, off, horizontal, text, _ = self._geom()
        dims.linear(c, p1, p2, off, horizontal=horizontal, text=text,
                    text_side=self.text_side)


@dataclass
class Leader:
    """A leader from a model point of ``pv`` to a label at sheet ``elbow``."""

    pv: PView | None
    tip: tuple[float, float]     # model (view) coordinates, or sheet if pv is None
    elbow: tuple[float, float]   # sheet
    text: str
    dot: bool = False

    def _tip(self):
        return self.pv.pt(*self.tip) if self.pv else self.tip

    def extent(self) -> Box4:
        tx, ty = self._tip()
        ex, ey = self.elbow
        right = ex >= tx
        end = ex + (dims.LEADER_TAIL if right else -dims.LEADER_TAIL)
        tb = text_box(end + (1.2 if right else -1.2), ey + 0.9, self.text,
                      anchor="start" if right else "end")
        return _union([(min(tx, ex, end), min(ty, ey), max(tx, ex, end), max(ty, ey)), tb])

    def label_box(self) -> Box4:
        ex, ey = self.elbow
        right = ex >= self._tip()[0]
        end = ex + (dims.LEADER_TAIL if right else -dims.LEADER_TAIL)
        return text_box(end + (1.2 if right else -1.2), ey + 0.9, self.text,
                        anchor="start" if right else "end")

    def draw(self, c) -> None:
        dims.leader(c, self._tip(), self.elbow, self.text, dot=self.dot)


@dataclass
class Caption:
    """A view's name, centred above (or below) it."""

    pv: PView
    text: str
    below: bool = False
    #: Extra lift off the view, for a view with dimensions above it.
    lift: float = 0.0

    def _at(self):
        r = self.pv.rect
        y = (r.y - 2.5 - style.T_LABEL - self.lift) if self.below else (r.y1 + 2.5 + self.lift)
        return r.cx, y

    def extent(self) -> Box4:
        x, y = self._at()
        return text_box(x, y, self.text, anchor="middle", bold=True)

    label_box = extent

    def draw(self, c) -> None:
        x, y = self._at()
        c.text(x, y, self.text, size=style.T_LABEL, anchor="middle", bold=True)


@dataclass
class Balloon:
    pv: PView
    tip: tuple[float, float]       # model
    centre: tuple[float, float]    # sheet
    label: str
    R = 3.2

    def extent(self) -> Box4:
        tx, ty = self.pv.pt(*self.tip)
        cx, cy = self.centre
        return (min(tx, cx - self.R), min(ty, cy - self.R), max(tx, cx + self.R),
                max(ty, cy + self.R))

    def label_box(self) -> Box4:
        cx, cy = self.centre
        return (cx - self.R, cy - self.R, cx + self.R, cy + self.R)

    def draw(self, c) -> None:
        dims.balloon(c, self.pv.pt(*self.tip), self.centre, self.label, radius=self.R)


@dataclass
class Free:
    """Free text on the sheet (a label inside or beside a view)."""

    x: float
    y: float
    text: str
    anchor: str = "start"
    colour: str = style.C_NOTE

    def extent(self) -> Box4:
        return text_box(self.x, self.y, self.text, anchor=self.anchor)

    label_box = extent

    def draw(self, c) -> None:
        c.text(self.x, self.y, self.text, size=style.T_LABEL, anchor=self.anchor,
               colour=self.colour)


# --- free space ------------------------------------------------------------------------

def _rect_box(r: Rect) -> Box4:
    return (r.x, r.y, r.x1, r.y1)


def _box_rect(b: Box4) -> Rect:
    return Rect(b[0], b[1], b[2] - b[0], b[3] - b[1])


def subtract(free: list[Box4], used: Box4, pad: float = 0.0) -> list[Box4]:
    """The maximal free rectangles left once ``used`` (grown by ``pad``) is taken."""
    ux0, uy0, ux1, uy1 = used[0] - pad, used[1] - pad, used[2] + pad, used[3] + pad
    out: list[Box4] = []
    for f in free:
        x0, y0, x1, y1 = f
        if ux0 >= x1 or ux1 <= x0 or uy0 >= y1 or uy1 <= y0:
            out.append(f)
            continue
        if ux0 > x0:
            out.append((x0, y0, ux0, y1))
        if ux1 < x1:
            out.append((ux1, y0, x1, y1))
        if uy0 > y0:
            out.append((x0, y0, x1, uy0))
        if uy1 < y1:
            out.append((x0, uy1, x1, y1))
    keep = []
    for i, a in enumerate(out):
        if any(j != i and b[0] <= a[0] and b[1] <= a[1] and b[2] >= a[2] and b[3] >= a[3]
               and (b != a or j < i) for j, b in enumerate(out)):
            continue
        keep.append(a)
    return keep


# --- the sheet ------------------------------------------------------------------------------

#: Title block width on an A4 sheet; A3 keeps the submodule's 165 mm.  Wide
#: enough for the PROJECTION cell (0.16 of the block) to hold its label, drawn
#: 1.6 in, with 0.8 to spare: 120 mm put "PROJECTION" across the cell's rule
#: and the frame line.  No wider, or the block reaches the bottom centring
#: mark at the sheet's middle (148.5 mm): 139 mm put it through MATERIAL.
A4_TITLE_W = math.ceil((style.text_width("PROJECTION", style.T_TINY) + 1.6 + 0.8) / 0.16)


def new_sheet(defn: names.SheetDef, *, subtitle: str, material: str, tolerance: str,
              scale: str, projection: bool = True) -> Sheet:
    cw = A4_TITLE_W if defn.size == "A4" else Sheet.COLUMN_WIDTH
    tb = TitleBlock(title=defn.title, subtitle=subtitle, drawing_no=defn.name, rev=REV,
                    scale=scale, version=version(), drawn_by=DRAWN, material=material,
                    tolerance=tolerance, projection="first angle" if projection else "")
    return Sheet(defn.size, tb, column_width=cw, notes_band_height=40.0)


def centring_marks(sheet: Sheet) -> list[Box4]:
    """The paper the ISO 5457 centring marks take inside the frame (they run
    5 mm in from it at the middle of each side)."""
    f = sheet.frame
    cx, cy = sheet.w / 2, sheet.h / 2
    return [(cx - 0.5, f.y, cx + 0.5, f.y + 5.0), (cx - 0.5, f.y1 - 5.0, cx + 0.5, f.y1),
            (f.x, cy - 0.5, f.x + 5.0, cy + 0.5), (f.x1 - 5.0, cy - 0.5, f.x1, cy + 0.5)]


def initial_free(sheet: Sheet) -> list[Box4]:
    f = sheet.frame
    inner = (f.x + 3.0, f.y + 3.0, f.x1 - 3.0, f.y1 - 3.0)
    t = sheet.title_rect
    free = subtract([inner], (t.x, t.y, t.x1, t.y1), pad=4.0)
    for m in centring_marks(sheet):
        free = subtract(free, m, pad=1.0)
    return free


def scale_label(s: float) -> str:
    for num, den in STANDARD_SCALES:
        if abs(num / den - s) < 1e-9:
            return scale_text(num, den)
    return f"{s:g}:1" if s >= 1 else f"1:{1 / s:g}"


@dataclass
class Table:
    title: str
    headers: list[str]
    rows: list[list[str]]
    aligns: list[str] | None = None

    def width(self) -> float:
        """As ``Sheet.table`` sizes its columns: the widest cell plus padding."""
        pad = 1.8
        return sum(max([style.text_width(h, style.T_TABLE, bold=True)]
                       + [style.text_width(r[k], style.T_TABLE) for r in self.rows]) + 2 * pad
                   for k, h in enumerate(self.headers))

    def height(self, sheet: Sheet) -> float:
        return sheet.table_height(self.title, len(self.rows))


@dataclass
class Legend:
    entries: list[tuple[tuple, str]]
    ROW = 4.6
    SWATCH = 12.0

    def height(self) -> float:
        return Sheet.HEADING_HEIGHT + len(self.entries) * self.ROW + 0.5

    def width(self) -> float:
        return self.SWATCH + 3.0 + max(style.text_width(t, style.T_NOTE) for _, t in self.entries)

    def draw(self, sheet: Sheet, rect: Rect) -> None:
        c = sheet.canvas
        y = sheet.heading(rect, "LEGEND")
        for (w, colour, dash, arrow), label in self.entries:
            cy = y - self.ROW / 2
            c.line(rect.x, cy, rect.x + self.SWATCH, cy, w=w, colour=colour, dash=dash)
            if arrow:
                c.arrow(rect.x + self.SWATCH, cy, 0, colour=colour)
            c.text(rect.x + self.SWATCH + 3.0, cy - style.T_NOTE / 2, label, size=style.T_NOTE)
            y -= self.ROW


L_VISIBLE = ((style.W_OUTLINE, style.C_LINE, None, False), "Visible edge")
L_HIDDEN = ((style.W_HIDDEN, style.C_LINE, style.D_HIDDEN, False), "Hidden edge")
L_PHANTOM = ((style.W_PHANTOM, style.C_PHANTOM, style.D_PHANTOM, False), "")
L_CENTRE = ((style.W_CENTRE, style.C_LINE, style.D_CENTRE, False), "Centre line, axis")
L_DIM = ((style.W_THIN, style.C_DIM, None, True), "Dimension, leader")


def phantom_entry(label: str):
    return (L_PHANTOM[0], label)


@dataclass
class Layout:
    """Everything a sheet places, before any of it is drawn."""

    views: dict[str, PView]
    annotations: list = field(default_factory=list)
    #: Paper taken by drawn geometry beyond the views (a phantom lid, say).
    extra: list[Box4] = field(default_factory=list)

    def used(self) -> list[Box4]:
        out = [_rect_box(v.rect) for v in self.views.values()]
        out += [a.extent() for a in self.annotations]
        return out + list(self.extra)


#: The least a free rectangle must offer to take a column of notes: a
#: sliver between two views would split a note from its heading's column.
COL_MIN_W = 80.0
COL_MIN_H = 18.0
#: Wider than this, a free rectangle takes two columns of notes.
COL_MAX_W = 170.0

#: Why the last layout failed to fit, for the error message.
WHY: list[str] = []


def _why(reason: str) -> bool:
    WHY.append(reason)
    return False


def place_blocks(sheet: Sheet, lay: Layout, tables: list[Table], legend: Legend | None,
                 notes: list[str], sources: list[str], dry: bool) -> bool:
    """Put the tables, the legend and the notes into the paper the layout
    leaves.  With ``dry``, only say whether they fit."""
    frame = sheet.frame
    free = initial_free(sheet)
    for u in lay.used():
        if u[0] < frame.x + 1 or u[1] < frame.y + 1 or u[2] > frame.x1 - 1 or u[3] > frame.y1 - 1:
            return _why(f"annotation {tuple(round(v, 1) for v in u)} runs off the frame")
        if any(_overlaps(u, m) for m in centring_marks(sheet)):
            return _why(f"annotation {tuple(round(v, 1) for v in u)} meets a centring mark")
        free = subtract(free, u, pad=3.0)
    blocks: list[tuple[str, object, float, float]] = []
    for t in tables:
        blocks.append(("table", t, t.width(), t.height(sheet)))
    if legend is not None:
        blocks.append(("legend", legend, legend.width(), legend.height()))
    placed = []
    for kind, obj, w, h in blocks:
        # top-most, then left-most, free rectangle it fits in
        fits = [f for f in free if f[2] - f[0] >= w and f[3] - f[1] >= h]
        if not fits:
            return _why(f"no room for the {kind} {getattr(obj, 'title', '')} {w:.0f} x {h:.0f}")
        f = max(fits, key=lambda f: (f[3], -f[0]))
        r = Rect(f[0], f[3] - h, w, h)
        placed.append((kind, obj, r))
        free = subtract(free, (r.x, r.y, r.x1, r.y1), pad=4.0)
    # the notes flow down columns: the free rectangles, biggest first, until
    # the flow fits; then drawn in reading order
    nb = [("NOTES", notes, style.T_NOTE)]
    if sources:
        nb.append(("SOURCES", sources, style.T_TINY))
    cols: list[Rect] = []
    ok = False
    pool = [f for f in free if f[2] - f[0] >= COL_MIN_W and f[3] - f[1] >= COL_MIN_H]
    while pool:
        f = max(pool, key=lambda f: (f[2] - f[0]) * (f[3] - f[1]))
        if f[2] - f[0] > COL_MAX_W:
            # two columns of readable measure rather than one line across a sheet
            half = (f[2] - f[0] - 8.0) / 2
            cols += [_box_rect((f[0], f[1], f[0] + half, f[3])),
                     _box_rect((f[2] - half, f[1], f[2], f[3]))]
        else:
            cols.append(_box_rect(f))
        pool = [g for g in subtract(pool, f, pad=4.0)
                if g[2] - g[0] >= COL_MIN_W and g[3] - g[1] >= COL_MIN_H]
        # reading order first; the flow keeps a block whole by moving it on, so
        # another order can fit where reading order does not
        reading = sorted(cols, key=lambda r: (round(-r.y1 / 20), r.x))
        for order in [reading] + [list(o) for o in itertools.permutations(reading)
                                  if list(o) != reading][:5]:
            if sheet.notes_columns(order, nb, dry=True):
                ok = True
                cols = order
                break
        if ok:
            break
    if not ok:
        return _why(f"the notes do not fit {len(cols)} free columns")
    if dry:
        return True
    for kind, obj, r in placed:
        if kind == "table":
            sheet.table(r, obj.title, obj.headers, obj.rows, obj.aligns)
        else:
            obj.draw(sheet, r)
    sheet.notes_columns(cols, nb)
    return True


def render(defn: names.SheetDef, build, *, subtitle: str, material: str, tolerance: str,
           scales, projection: bool = True) -> Sheet:
    """Lay the sheet out at the largest of ``scales`` at which everything
    fits, then draw it.  ``build(sheet, scale)`` returns (Layout, tables,
    legend, notes, sources, draw), where ``draw(sheet)`` draws the geometry.

    Nothing fitting is an error.  For working on a layout, ``SHEET_FORCE=1``
    in the environment draws the largest scale's views and annotation anyway,
    without the tables and notes, so the crowding can be seen."""
    for s in scales:
        sheet = new_sheet(defn, subtitle=subtitle, material=material, tolerance=tolerance,
                          scale=scale_label(s), projection=projection)
        lay, tables, legend, notes, sources, draw = build(sheet, s)
        if not place_blocks(sheet, lay, tables, legend, notes, sources, dry=True):
            print(f"  {defn.name} at {scale_label(s)}: {WHY[-1]}")
            if os.environ.get("SHEET_FORCE") and s == scales[-1]:
                # debugging only: draw the largest scale's layout, unfitted
                sheet = new_sheet(defn, subtitle=subtitle, material=material,
                                  tolerance=tolerance, scale=scale_label(scales[0]),
                                  projection=projection)
                lay, tables, legend, notes, sources, draw = build(sheet, scales[0])
                sheet.draw_frame()
                draw(sheet)
                for a in lay.annotations:
                    a.draw(sheet.canvas)
                sheet.draw_title_block()
                return sheet
            continue
        sheet.draw_frame()
        draw(sheet)
        for a in lay.annotations:
            a.draw(sheet.canvas)
        place_blocks(sheet, lay, tables, legend, notes, sources, dry=False)
        sheet.draw_title_block()
        return sheet
    raise SystemExit(f"{defn.name}: nothing fits the {defn.size} sheet at any of the scales "
                     f"{[scale_label(s) for s in scales]}; shorten the notes or the tables")


# --- output -------------------------------------------------------------------------------------

#: Preview width in pixels: big enough to read a dimension on screen.
PREVIEW_W = {"A3": 2000, "A4": 1600}


def write(defn: names.SheetDef, sheet: Sheet) -> Path:
    from tools import render_svg
    svg = names.svg_path(defn.name)
    svg.parent.mkdir(parents=True, exist_ok=True)
    sheet.canvas.save(str(svg))
    render_svg.to_pdf(svg)
    render_svg.to_preview(svg, names.preview_path(defn.name), width=PREVIEW_W[defn.size])
    return svg


def fmt(v: float) -> str:
    """Two places, as every dimension on these sheets; never "-0.00"."""
    s = f"{v:.2f}"
    return "0.00" if s == "-0.00" else s


def angle_arc(c, centre, r, a0, a1, text, colour=style.C_DIM) -> None:
    """An angular dimension: an arc of radius ``r`` (sheet mm) about ``centre``
    from ``a0`` to ``a1`` degrees (anticlockwise), arrows at both ends, the
    value at the arc's middle, outside it."""
    cx, cy = centre
    pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
           for a in [a0 + (a1 - a0) * i / 48 for i in range(49)]]
    c.polyline(pts, w=style.W_THIN, colour=colour)
    c.arrow(*pts[0], a0 - 90, colour=colour)
    c.arrow(*pts[-1], a1 + 90, colour=colour)


def angle_label_box(centre, r, a0, a1, text) -> tuple[float, float, Box4]:
    mid = math.radians((a0 + a1) / 2)
    cx, cy = centre
    x = cx + (r + 3.0) * math.cos(mid)
    y = cy + (r + 3.0) * math.sin(mid)
    anchor = "start" if math.cos(mid) > 0.2 else ("end" if math.cos(mid) < -0.2 else "middle")
    return x, y, text_box(x, y, text, anchor=anchor)


@dataclass
class Angle:
    """An angular dimension about a sheet point."""

    centre: tuple[float, float]
    r: float
    a0: float
    a1: float
    text: str

    def extent(self) -> Box4:
        cx, cy = self.centre
        xs = [cx + self.r * math.cos(math.radians(a)) for a in range(int(self.a0), int(self.a1) + 1)]
        ys = [cy + self.r * math.sin(math.radians(a)) for a in range(int(self.a0), int(self.a1) + 1)]
        return _union([(min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1), self.label_box()])

    def label_box(self) -> Box4:
        return angle_label_box(self.centre, self.r, self.a0, self.a1, self.text)[2]

    def draw(self, c) -> None:
        angle_arc(c, self.centre, self.r, self.a0, self.a1, self.text)
        x, y, _ = angle_label_box(self.centre, self.r, self.a0, self.a1, self.text)
        mid = math.cos(math.radians((self.a0 + self.a1) / 2))
        anchor = "start" if mid > 0.2 else ("end" if mid < -0.2 else "middle")
        c.text(x, y, self.text, size=style.T_DIM, colour=style.C_DIM, anchor=anchor)
