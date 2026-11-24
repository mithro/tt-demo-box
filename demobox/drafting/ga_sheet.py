"""A3 sheets for a whole route: the general arrangements and the laser cut list.

General arrangement (``TDB-GA-P``, ``TDB-GA-L``): the closed box in three
views, first angle, projected from ``assembly(route, 0, 0)`` with its bought
hardware (the ``hw:`` solids) left out; in the view from the left, the lid at
its 100 degree stop in phantom line (``assembly(route, 100, 0)``'s lid), the
angle dimensioned about the hinge axis.  Overall sizes closed and open, the
hinge axis' position, balloons on the made parts a view shows, and the parts
list: every made part with the sheet that draws it, and the bought parts,
counted from the route's own data (``laser.fittings.hardware`` for the laser
route; the printed route's inserts, screws and bolts from its parts' records,
the screw-head ``hw:`` solids cross-checking the bezel and clip screws).

Cut list (``TDB-CUT-L``): every laser panel outline flat, at one scale, with
its name and cut size; the DXFs are the cutting files.
"""

from __future__ import annotations

import math
import re
from collections import Counter

import cadquery as cq

import demobox  # noqa: F401  (puts the submodule on sys.path)
from tools.drafting import style

from demobox.drafting import names
from demobox.drafting import sheetkit as K
from demobox.drafting.hlr import project, to_view
from demobox.layout import LASER_BED, LID_OPEN_DEG, ROUTES, layout
from demobox.parts.batteries import BATTERIES
from demobox.parts.cables import CABLES
from demobox.parts.monitors import MONITORS
from demobox.printed import body as B
from demobox.shared import hinge as H
from demobox.shared import inserts as I

F = K.fmt
#: Room in the parts list's PART column, mm.
PART_W = 56.0
#: The lid's parts, for the open-lid phantom.
LID_PARTS = ("lid", "hinge-lid", "bezel", "retainer", "panel", "monitor-driver")


def _where(sources, pattern=r"(AliExpress \d+|[a-z]+\.com)") -> str:
    """Where to buy it, as the part's sources say: a listing number or a site."""
    for s in sources:
        m = re.search(pattern, f"{s.label} {s.note}")
        if m:
            return next(g for g in m.groups() if g)
    return "survey"


def printed_hardware(lay) -> dict[str, int]:
    """The printed route's bought hardware (``body.hardware``), plus the
    board's screw check: the assembly's screw-head ``hw:`` solids are the
    bezel's and the clip's, and must agree with them (the catch magnets are
    counted by ``body.hardware``)."""
    heads = [n for n, _, _ in B.assembly("printed", 0.0, 0.0)
             if n.startswith("hw:") and "magnet" not in n]
    if len(heads) != len(I.bezel_screws(lay)) + len(B.clip_screws(lay)):
        raise ValueError(f"hw: solids {heads} disagree with the bezel and clip screws")
    return B.hardware(lay)


def _parts_rows(route: str, lay) -> tuple[list[list[str]], dict[str, int]]:
    """The parts list rows and each ballooned part's item number."""
    rows: list[list[str]] = []
    item: dict[str, int] = {}

    def add(key, qty, part, ref):
        rows.append([str(len(rows) + 1), str(qty), part, ref])
        if key:
            item[key] = len(rows)

    if route == "printed":
        for key, part, ref in (("base", "Base tub", "TDB-BASE-P"), ("deck", "Deck", "TDB-DECK-P"),
                               ("lid", "Lid", "TDB-LID-P"), ("drawer", "Drawer", "TDB-DRW-P"),
                               ("hinge-base", "Hinge, base half", "TDB-HGB-P"),
                               ("hinge-lid", "Hinge, lid half", "TDB-HGL-P"),
                               ("bezel-clip", "Bezel clip", "TDB-CLIP-P"),
                               ("mt1-pin", "MT1 locating pin", "TDB-PIN-P"),
                               ("packing", "Battery packing, per bank", "TDB-PKG-P")):
            add(key, 1, part, ref)
        add("insert", 1, "Bezel + retainer, per monitor", "TDB-INS-*")
        hw = printed_hardware(lay)
    else:
        from demobox.laser import fittings as LF
        from demobox.laser import panels as P
        add("panels", len(P.panels(lay, lay.wall)), "Plywood panels, 3 mm", "TDB-CUT-L")
        counts = Counter(p for p, *_ in LF.placed(lay, lay.wall))
        add("fittings", sum(counts.values()), "Printed fittings (blocks)", "STEP")
        for key, part in (("hinge-base", "Hinge, base half"), ("hinge-lid", "Hinge, lid half"),
                          ("bezel-clip", "Bezel clip"), ("mt1-pin", "MT1 locating pin"),
                          ("packing", "Battery packing, per bank")):
            add(key, 1, part, "STEP")
        add("insert", 1, "Bezel + retainer, per monitor", "STEP")
        hw = P.hardware(lay, lay.wall)
    for what, n in hw.items():
        # the column holds PART_W; a long name says "pan-head", and then loses
        # its "(where it goes)"
        if style.text_width(what, style.T_TABLE) > PART_W:
            what = what.replace(" pan-head screw", " pan-head")
        if style.text_width(what, style.T_TABLE) > PART_W:
            what = re.sub(r" \(.*\)$", "", what)
        add("", n, what, "bought")
    add("", 1, "TT demo board v3.2 or v3.3", "Tiny Tapeout")
    add("", 1, "TinyVGA Pmod", "mole99/tiny-vga")
    for k, m in MONITORS.items():
        add("", "1*", f"Monitor {k}", _where(m.sources, r"AliExpress (\d+)|(Taobao)"))
    for k, b in BATTERIES.items():
        add("", "1*", f"Power bank {k}", _where(b.sources))
    for c in CABLES.values():
        add("", 1, re.sub(r" \(.*?\)", "", c.title).replace("Slim VGA cable, <= 0.5 m",
                                                            "VGA cable, slim, <= 0.5 m"), "spec")
    return rows, item


def render(defn: names.SheetDef):
    if defn.kind == "cutlist":
        return render_cutlist(defn)
    return render_ga(defn)


def _projections(route: str):
    closed = [(n, s) for n, s, _ in B.assembly(route, 0.0, 0.0) if not n.startswith("hw:")]
    comp = cq.Compound.makeCompound([s for _, s in closed])
    projs = {v: project(comp, v) for v in ("front", "side", "plan")}
    opened = [s for n, s, _ in B.assembly(route, LID_OPEN_DEG, 0.0)
              if n in LID_PARTS or n.startswith("bezel-clip")]
    lid_open = project(cq.Compound.makeCompound(opened), "side")
    return projs, lid_open, dict(closed)


def render_ga(defn: names.SheetDef):
    route = defn.subject
    lay = layout(ROUTES[route])
    projs, lid_open, solids = _projections(route)
    o, lo = lay.outer, lay.lid_outer
    hy, hz = lay.hinge_axis
    W, D, Hb = o.x1, o.y1, o.z1
    Hc = Hb + lo.z1                                   # closed height
    bb_open = lid_open.bbox()
    top_open = max((pt for pl in lid_open.visible for pt in pl), key=lambda q: q[1])
    rows, item = _parts_rows(route, lay)

    def ann(views):
        f, s, p = views["front"], views["side"], views["plan"]
        ax = to_view("side", (0.0, hy, hz))
        out = [
            K.Dim(f, (0.0, 0.0), (0.0, Hb), "left", 0),
            K.Dim(f, (0.0, 0.0), (0.0, Hc), "left", 1),
            K.Dim(p, (0.0, 0.0), (W, 0.0), "bottom", 0),
            K.Dim(p, (0.0, 0.0), (0.0, D), "left", 0),
            # open: the height to the lid's top, and how far it reaches behind
            K.Dim(s, (-D, 0.0), top_open, "left", 0),
            K.Dim(s, (bb_open[0], 0.0), (-hy, 0.0), "bottom", 0, text_side="low"),
            # on the base's side face, clear of its edges: the paper left of the view
            # is the open-height dimension's and the gap's
            K.Leader(s, ax, (s.x(ax[0]) + 8.0, s.y(ax[1]) - 10.0), "HINGE AXIS", dot=True),
            K.Angle(s.pt(*ax), 26.0, 0.0, LID_OPEN_DEG, f"{LID_OPEN_DEG:g}\N{DEGREE SIGN}"),
        ]
        # balloons on what the views show
        # below the view for the base and the drawer, above the closed lid for the
        # lid, so the paper right of the view stays free for the parts list
        below = s.y(0.0) - 13.0
        spots = [("drawer", to_view("side", (0.0, lay.bay.y0 + 12.0, lay.bay.z0 + 4.0)),
                  0.0, below),
                 ("base", to_view("side", (0.0, D * 0.55, 12.0)), 0.0, below),
                 ("lid", to_view("side", (0.0, D * 0.25, Hb + lo.z1 / 2)), 6.0,
                  s.y(Hc) + 13.0)]
        if "panels" in item:
            spots.append(("panels", to_view("side", (0.0, D * 0.55, 12.0)), 0.0, below))
        for key, tip, dx, y in spots:
            if key in item:
                out.append(K.Balloon(s, tip, (s.x(tip[0]) + dx, y), str(item[key])))
        kn = H._knuckles(lay, "base")[-1]
        if "hinge-base" in item:
            tip = to_view("plan", ((kn[0] + kn[1]) / 2, hy + 1.0, 0.0))
            out.append(K.Balloon(p, tip, (p.rect.x1 + 14.0, p.y(tip[1]) + 4.0),
                                 str(item["hinge-base"])))
        return out

    def build(sheet, s):
        def make(views):
            return K.captioned(views, ann(views), {"front": "FRONT", "side": "FROM LEFT",
                                                   "plan": "PLAN"})

        bbs = {"side": (min(projs["side"].bbox()[0], bb_open[0]), projs["side"].bbox()[1],
                        projs["side"].bbox()[2], max(projs["side"].bbox()[3], bb_open[3]))}
        views, a = K.solve(projs, s, make, sheet.frame, bbs=bbs)
        lay_ = K.Layout(views, a)

        def draw(sh):
            for v in views.values():
                K.draw_view(sh.canvas, v, hidden=False)
            K.draw_lines(sh.canvas, views["side"], lid_open.visible, **K.PHANTOM)
            sv = views["side"]
            ax = sv.pt(*to_view("side", (0.0, hy, hz)))
            # the closed lid's top face and the open lid's, as axes for the angle
            ln = 30.0
            sh.canvas.line(ax[0] - 4.0, ax[1], ax[0] + ln, ax[1], **K.CENTRE)
            a = math.radians(LID_OPEN_DEG)
            sh.canvas.line(ax[0], ax[1], ax[0] + ln * math.cos(a), ax[1] + ln * math.sin(a),
                           **K.CENTRE)
            K.datum_mark(sh.canvas, views)

        legend = K.Legend([K.L_VISIBLE, K.phantom_entry(f"Lid at the {LID_OPEN_DEG:g} deg stop"),
                           K.L_CENTRE, K.L_DIM])
        table = K.Table("PARTS LIST", ["ITEM", "QTY", "PART", "DRAWING, SOURCE"], rows,
                        ["end", "end", "start", "start"])
        route_word = "3D-printed" if route == "printed" else "laser-cut 3 mm plywood"
        notes = [
            f"The {route_word} demo box, closed, drawer shut; base frame datum (target) at "
            "the front-left-bottom outside corner, X to the visitor's right, Y away, Z up.",
            f"The lid turns {LID_OPEN_DEG:g} deg about the hinge axis to its stop (just past "
            "upright); the view from the left shows it there in phantom.",
            f"Bay {' x '.join(F(v) for v in lay.bay.size)} inside plus a "
            f"{F(lay.cable_bay.x1 - lay.cable_bay.x0)} cable bay; the drawer slides out of "
            f"the left side by {F(lay.drawer_travel)}.",
            "Bought parts are counted from the route's data; monitor sources are listing "
            "numbers or shops. 1*: fit one monitor and one "
            "power bank of those listed, with its insert and its packing. Hinge axis: the "
            f"base's back-top edge, Y {F(hy)}, Z {F(hz)}.",
            K.unconfirmed_note(None),
        ]
        sources = ["demobox/layout.py (layout), demobox/checks.py (verify.py)",
                   ("demobox/printed/body.py (assembly)" if route == "printed" else
                    "demobox/laser/panels.py, fittings.py (assembly, hardware)"),
                   "docs/superpowers/specs/2026-11-23-tt-demo-box-design.md",
                   "docs/superpowers/specs/monitor-survey.md, battery-survey.md"]
        return lay_, [table], legend, notes, sources, draw

    material = "PETG or PLA" if route == "printed" else "3 mm plywood"
    tol = K.PRINTED_TOL if route == "printed" else "+/-0.2 unless noted"
    return K.render(defn, build, subtitle=f"General arrangement, {route} route",
                    material=material, tolerance=tol, scales=(0.4, 0.2))


# --- the cut list ------------------------------------------------------------------------

def render_cutlist(defn: names.SheetDef):
    from demobox.laser import panels as P
    lay = layout(ROUTES["laser"])
    panels = P.panels(lay, lay.wall)
    body = P.build(lay, lay.wall)

    def build(sheet, s):
        # shelf-pack the outlines, largest first, into the drawing area left of
        # the column, each with its number above it
        area_x0, area_x1 = sheet.frame.x + 6.0, sheet.frame.x1 - Sheet_COL - 8.0
        top = sheet.frame.y1 - 8.0
        order = sorted(panels.items(), key=lambda kv: -kv[1].cut_size()[1])
        x, y, row_h = area_x0, top, 0.0
        placed = []
        for i, (n, pn) in enumerate(order):
            cw, ch = pn.cut_size()
            w, h = cw * s, ch * s
            if x + w > area_x1:
                x, y, row_h = area_x0, y - row_h - 12.0, 0.0
            placed.append((n, pn, x, y - h))
            x += w + 10.0
            row_h = max(row_h, h)
        bottom = y - row_h
        num = {n: str(i + 1) for i, (n, _, _, _) in enumerate(placed)}
        ann = []
        for n, pn, px, py in placed:
            b = pn.cut_shape().bounds
            ann.append(K.Free(px, py + (b[3] - b[1]) * s + 1.5, num[n]))
        lay_ = K.Layout({}, ann, extra=[(min(px for _, _, px, _ in placed), bottom,
                                         max(px + p.cut_size()[0] * s for _, p, px, _ in placed),
                                         top + 1.0)])

        def draw(sh):
            c = sh.canvas
            for n, pn, px, py in placed:
                shape = pn.cut_shape()
                b = shape.bounds
                for ring in [shape.exterior, *shape.interiors]:
                    c.polyline([(px + (u - b[0]) * s, py + (v - b[1]) * s)
                                for u, v in ring.coords], **K.VISIBLE)
                for u, v, d in pn.cut_holes():
                    c.circle(px + (u - b[0]) * s, py + (v - b[1]) * s, max(d / 2 * s, 0.3),
                             w=style.W_HIDDEN)

        rows = []
        for n, pn, _, _ in placed:
            cw, ch = pn.cut_size()
            rows.append([num[n], n, f"{F(cw)} x {F(ch)}", str(len(pn.holes))])
        table = K.Table("PANELS", ["NO", "PANEL (DXF)", "CUT SIZE", "HOLES"], rows,
                        ["end", "start", "end", "end"])
        seams = ", ".join(f"{sm.name} ({' + '.join(sm.pieces)})" for sm in body.seams)
        notes = [
            f"Every panel of the laser route, flat, at {K.scale_label(s)}, numbered as in the "
            f"table; CUT SIZE is the outline grown by half the {F(P.KERF)} kerf. The DXFs in "
            "output/laser are the cutting files: cut from them, not from this sheet.",
            f"3 mm plywood; laser bed {F(LASER_BED[0])} x {F(LASER_BED[1])}. Panels split to "
            f"fit the bed and glued along a finger seam: {seams}.",
            "Finger joints and T-slots are drawn as cut; holes are M3 clearance less the "
            "kerf; engraved marks (layer ENGRAVE) are not drawn.",
            K.unconfirmed_note(None),
        ]
        sources = ["demobox/laser/panels.py (panels, build)", "output/laser/*.dxf"]
        return lay_, [table], None, notes, sources, draw

    return K.render(defn, build, subtitle="Every laser-cut panel, flat", material="3 mm plywood",
                    tolerance="+/-0.2 unless noted", scales=(0.2, 0.1), projection=False)


#: The cut list leaves the annotation column's width for the panel table.
Sheet_COL = 165.0
