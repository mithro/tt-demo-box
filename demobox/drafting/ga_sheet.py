"""A3 sheets for a whole route: the general arrangements and the laser cut list.

General arrangement (``TDB-GA-P``, ``TDB-GA-L``): the closed box in three
views, first angle, projected from the made parts of ``assembly(route, 0,
False)`` (the bought blocks inside and the ``hw:`` solids left out); in the
view from the left, the lid at its LID_OPEN_DEG stop in phantom line (the
parts ``assembly(route, LID_OPEN_DEG, False)`` moves), the angle dimensioned
about the hinge axis.  Overall sizes closed and open, the hinge axis'
position, balloons on the made parts a view shows, and the parts list: the
route's printed parts (``printed.body.printed_parts`` or
``laser.fittings.printed_parts``, each counted in the assembly) with the
sheet that draws it, the laser panels, the route's ``hardware``, and the
design kit's bought parts.  The notes give the closed size and volume
(``layout``'s, as ``checks.size_budget`` proves them) and how the box goes
together.

Cut list (``TDB-CUT-L``): every laser panel outline flat, at one scale, with
its name and cut size; the DXFs are the cutting files.
"""

from __future__ import annotations

import math
import re

import cadquery as cq

import demobox  # noqa: F401  (puts the submodule on sys.path)
from tools.drafting import style

from demobox import checks
from demobox.drafting import names
from demobox.drafting import sheetkit as K
from demobox.drafting.hlr import project, to_view
from demobox.layout import (LASER_BED, LID_OPEN_DEG, MAGNET_D,
                            MAGNET_T, PIN_ROD_D, ROUTES, SLACK, layout)
from demobox.parts.batteries import BATTERIES
from demobox.parts.monitors import MONITORS
from demobox.printed import body as B
from demobox.shared import hinge as H

F = K.fmt
#: The assembly's bought parts, drawn as plain blocks: inside the closed box,
#: so a GA view of the outside leaves them out.
BOUGHT_BLOCKS = frozenset(("board", "tinyvga", "vga-plug", "monitor", "boost", "bank"))


def _where(sources, pattern=r"(AliExpress \d+|[a-z]+\.com)") -> str:
    """Where to buy it, as the part's sources say: a listing number or a site."""
    for s in sources:
        m = re.search(pattern, f"{s.label} {s.note}")
        if m:
            return next(g for g in m.groups() if g)
    return "survey"


def _made(route: str, angle_deg: float) -> list[tuple[str, cq.Shape]]:
    """The route's made parts (printed parts, panels), assembled at ``angle_deg``."""
    return [(n, s) for n, s, _ in B.assembly(route, angle_deg, False)
            if not n.startswith("hw:") and n not in BOUGHT_BLOCKS]


def _count(names_: list[str], part: str) -> int:
    """How many of ``part`` an assembly holds: its own name, or its name with
    a ``-<where>`` suffix (``magnet-block-lid-1``)."""
    return sum(1 for n in names_ if n == part or n.startswith(part + "-"))


def _part_sheets() -> dict[str, str]:
    """The printed route's part -> the sheet that draws it."""
    return {s.subject: n for n, s in names.SHEETS.items() if s.kind == "part"}


def parts_rows(route: str, lay) -> tuple[list[list[str]], dict[str, int]]:
    """The parts list rows (ITEM, QTY, PART, DRAWING/SOURCE) and each
    ballooned part's item number: the printed parts counted in the closed
    assembly, the laser panels, the route's hardware, and the bought kit."""
    from demobox.laser import fittings as LF
    from demobox.laser import panels as P
    rows: list[list[str]] = []
    item: dict[str, int] = {}

    def add(key, qty, part, ref):
        rows.append([str(len(rows) + 1), str(qty), part, ref])
        if key:
            item[key] = len(rows)

    in_box = [n for n, _, _ in B.assembly(route, 0.0, False)]
    if route == "printed":
        sheets = _part_sheets()
        for key in B.printed_parts(lay):
            add(key, _count(in_box, key), key, sheets[key])
        hw = B.hardware(lay)
    else:
        add("panels", len(P.panels(lay, lay.wall)), f"plywood panels, {lay.wall:g} mm",
            "TDB-CUT-L")
        for key in LF.printed_parts(lay, lay.wall):
            add(key, _count(in_box, key), key, "TDB-FIT-L")
        hw = LF.hardware(lay, lay.wall)
    for what, n in hw.items():
        add("", n, what, "bought")
    add("", 1, "TT demo board v3.2 or v3.3", "Tiny Tapeout")
    add("", 1, "TinyVGA Pmod", "mole99/tiny-vga")
    m, b = MONITORS[lay.monitor], BATTERIES[lay.bank]
    add("", 1, f"Monitor {lay.monitor}", _where(m.sources, r"AliExpress (\d+)|(Taobao)"))
    add("", 1, f"Power bank {lay.bank}", _where(b.sources))
    for c in (checks.usb_cable(lay), checks.ADAPTER, checks.BOOST):
        if c.key != "bank-built-in":         # the bank's own cable comes with it
            add("", 1, re.sub(r" \(.*?\)", "", c.title), "spec")
    return rows, item


def render(defn: names.SheetDef):
    if defn.kind == "cutlist":
        return render_cutlist(defn)
    return render_ga(defn)


def _projections(route: str):
    closed = _made(route, 0.0)
    comp = cq.Compound.makeCompound([s for _, s in closed])
    projs = {v: project(comp, v) for v in ("front", "side", "plan")}
    # the lid's parts: whatever opening the lid moves
    still = {n: s.BoundingBox().center for n, s in closed}
    opened = [s for n, s in _made(route, LID_OPEN_DEG)
              if (s.BoundingBox().center - still[n]).Length > 1e-6]
    lid_open = project(cq.Compound.makeCompound(opened), "side")
    return projs, lid_open


def rod_text(lay) -> str:
    """The hinge rod as the hardware lists it: ``3 mm steel rod x 40.8 mm``."""
    return f"{PIN_ROD_D:g} mm steel rod x {H.pin_length(lay):.1f} mm"


def size_note(lay) -> str:
    """The closed size and volume, as ``checks.size_budget`` proves them."""
    report = checks.Report()
    checks.size_budget(report, lay)
    if report.failures:
        raise ValueError(f"size budget fails: {report.results}")
    o, lid = lay.outer, lay.lid_outer
    h = o.size[2] + lid.size[2]
    litres = o.size[0] * o.size[1] * h / 1e6
    return (f"Closed {F(o.size[0])} x {F(o.size[1])} x {F(h)} mm (base {F(o.size[2])} high, "
            f"lid {F(lid.size[2])}), {litres:.2f} L: the contents plus {SLACK:g} mm slack a "
            "side plus the walls (make verify, size budget).")


def render_ga(defn: names.SheetDef):
    from demobox.laser import fittings as LF
    route = defn.subject
    lay = layout(ROUTES[route])
    projs, lid_open = _projections(route)
    o, lo = lay.outer, lay.lid_outer
    hy, hz = lay.hinge_axis
    W, D, Hb = o.x1, o.y1, o.z1
    Hc = Hb + lo.z1                                   # closed height
    bb_open = lid_open.bbox()
    top_open = max((pt for pl in lid_open.visible for pt in pl), key=lambda q: q[1])
    rows, item = parts_rows(route, lay)

    def ann(views):
        f, s, p = views["front"], views["side"], views["plan"]
        ax = to_view("side", (0.0, hy, hz))
        out = [
            K.Dim(f, (0.0, 0.0), (0.0, Hb), "left", 0),
            K.Dim(f, (0.0, 0.0), (0.0, Hc), "left", 1),
            K.Dim(p, (0.0, 0.0), (W, 0.0), "bottom", 0),
            K.Dim(p, (0.0, 0.0), (0.0, D), "left", 0),
            # open: the height to the lid's top, and how far it reaches behind the
            # base's back face
            K.Dim(s, (-D, 0.0), top_open, "left", 0),
            K.Dim(s, (bb_open[0], 0.0), (-D, 0.0), "bottom", 0, text_side="low"),
            K.Leader(s, ax, (s.x(ax[0]) + 8.0, s.y(ax[1]) - 10.0), "HINGE AXIS", dot=True),
            K.Angle(s.pt(*ax), 26.0, 0.0, LID_OPEN_DEG, f"{LID_OPEN_DEG:g}\N{DEGREE SIGN}"),
        ]
        # balloons below the view for the base, above the closed lid for the
        # lid, so the paper right of the view stays free for the parts list
        below = s.y(0.0) - 13.0
        spots = [("base", to_view("side", (0.0, D * 0.3, Hb * 0.4)), 0.0, below),
                 ("lid", to_view("side", (0.0, D * 0.25, Hb + lo.z1 / 2)), 6.0,
                  s.y(Hc) + 13.0),
                 ("panels", to_view("side", (0.0, D * 0.3, Hb * 0.4)), 0.0, below)]
        for key, tip, dx, y in spots:
            if key in item:
                out.append(K.Balloon(s, tip, (s.x(tip[0]) + dx, y), str(item[key])))
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
        n_mag = 2 * len(lay.lid_catch)
        if route == "printed":
            made = list(B.printed_parts(lay))
            build_note = (
                f"{len(made)} printed parts: {', '.join(made)}. Board: MT2 pin + loose MT1 pin: "
                "the MT2 pin is printed on the plinth, the loose printed MT1 pin (TDB-PIN-P) "
                "goes in the fitted revision's hole (v3.2 or v3.3).")
            catch = (f"Lid catch: {n_mag} magnets, {MAGNET_D:g} x {MAGNET_T:g} mm, pressed flush "
                     "into pockets in the front corners, poled to pull.")
        else:
            build_note = (
                f"{lay.wall:g} mm plywood panels, finger-jointed and glued (TDB-CUT-L); the "
                "hinge knuckle blocks, the seal bead and the magnet blocks are printed and "
                "glued in (TDB-FIT-L). Board: MT2 pin + loose MT1 pin, two "
                f"{PIN_ROD_D:g} mm rods {LF.board_pin_length(lay):.1f} mm long standing on "
                "the floor through plinth-top: MT2's glued, MT1's loose in the fitted "
                "revision's hole (v3.2 or v3.3).")
            catch = (f"Lid catch: {n_mag} magnets, {MAGNET_D:g} x {MAGNET_T:g} mm, pressed flush "
                     "into the printed magnet blocks, two glued in the base's front corners "
                     "and two in the lid's, poled to pull.")
        route_word = "3D-printed" if route == "printed" else "laser-cut plywood"
        notes = [
            f"The {route_word} demo box, closed; base frame datum (target) at the "
            "front-left-bottom outside corner, X to the visitor's right, Y away, Z up.",
            size_note(lay),
            f"The lid turns {LID_OPEN_DEG:g} deg about the hinge axis (Y {F(hy)}, Z {F(hz)}) "
            "to its stop, where the view from the left shows it in phantom. Hinge: printed "
            f"knuckles on one {rod_text(lay)}, pressed in from the "
            f"right side face: the last {H.PRESS_LEN:g} mm of its bore there is a press fit "
            "and the first knuckle's bore is blind.",
            "Monitor: double-sided foam tape (VHB type) on its back, to the lid's flat "
            "inside face" + ("; the boost module is taped beside it in the lid strip."
                             if lay.boost_in_lid else "."),
            build_note,
            "The bank lifts out with the lid open: it stands loose on the floor of its bay, "
            "behind the board.",
            catch,
            "Parts list: the route's made parts and hardware from its data; the monitor and "
            "the power bank are the design kit the box is sized for.",
            K.unconfirmed_note(None),
        ]
        sources = ["demobox/layout.py (layout), demobox/checks.py (size_budget)",
                   ("demobox/printed/body.py (printed_parts, hardware, assembly)"
                    if route == "printed" else
                    "demobox/laser/panels.py, fittings.py (printed_parts, hardware, assembly)"),
                   "demobox/shared/hinge.py (pin_length, PRESS_LEN)",
                   "docs/superpowers/specs/2026-11-24-compact-box-design.md"]
        return lay_, [table], legend, notes, sources, draw

    material = "PETG or PLA" if route == "printed" else f"{lay.wall:g} mm plywood"
    tol = K.PRINTED_TOL if route == "printed" else "+/-0.2 unless noted"
    return K.render(defn, build, subtitle=f"General arrangement, {route} route",
                    material=material, tolerance=tol, scales=(0.5, 0.4, 0.2))


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
        bed = (f"laser bed {F(LASER_BED[0])} x {F(LASER_BED[1])}: "
               + (f"panels split to fit it are glued along a finger seam: {seams}."
                  if body.seams else "every panel fits it whole."))
        notes = [
            f"Every panel of the laser route, flat, at {K.scale_label(s)}, numbered as in the "
            f"table; CUT SIZE is the outline grown by half the {F(P.KERF)} kerf. The DXFs in "
            "output/laser are the cutting files: cut from them, not from this sheet.",
            f"{lay.wall:g} mm plywood; {bed}",
            "Finger joints are drawn as cut, and glued: no screws or nuts. The holes are "
            f"the board pins' in plinth-top: MT2 D{F(P.MT2_HOLE_D)}, tight for its glued rod; "
            f"MT1 D{F(P.MT1_HOLE_D)}, a slip fit for the loose rod, one per board revision. "
            "Engraved marks (layer ENGRAVE: names, magnet-block outlines) are not drawn.",
            K.unconfirmed_note(None),
        ]
        sources = ["demobox/laser/panels.py (panels, build)", "output/laser/*.dxf"]
        return lay_, [table], None, notes, sources, draw

    return K.render(defn, build, subtitle="Every laser-cut panel, flat",
                    material=f"{lay.wall:g} mm plywood", tolerance="+/-0.2 unless noted",
                    scales=(0.5, 0.4, 0.2), projection=False)


#: The cut list leaves the annotation column's width for the panel table.
Sheet_COL = 165.0
