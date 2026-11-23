"""A4 insert sheets: one per monitor, its bezel and its retainer.

The bezel is drawn screen side up (turned 180 degrees about X from the closed
lid frame, so the panel's bottom edge, the hinge end, is at the bottom and its
left is on the left, as a visitor sees the open lid).  The monitor's panel is
drawn round the window in phantom line, with its active area, so the window's
size and its position against the panel's edges are dimensioned from the
panel: that is what decides whether the bezel hides the panel's edge and shows
the whole picture (``checks.monitor_window``, R4).

The retainer is drawn the same way up, beside the bezel: its plan and the
view of its hinge-end edge, which shows its depth and the cable-exit cut-out.

Every figure comes from ``demobox.shared.inserts`` and ``demobox.checks``
against ``layout(2.4)``; the laser route's bezel is the same but for its
outline (``layout(3.0)``).
"""

from __future__ import annotations

import demobox  # noqa: F401  (puts the submodule on sys.path)
from tools.drafting import dims, style

from demobox.checks import button_cutout, monitor_window, panel_in_lid
from demobox.drafting import names
from demobox.drafting import sheetkit as K
from demobox.drafting.hlr import project, to_view
from demobox.drafting.part_sheet import Part
from demobox.layout import FIT, INSERT_MATERIAL, ROUTES, exit_edge, insert_stack, layout
from demobox.parts.monitors import MONITORS
from demobox.printed import body as B
from demobox.shared import inserts as I
from demobox.shared import m3

F = K.fmt
TURN = (((1.0, 0.0, 0.0), 180.0),)
SURVEY = "docs/superpowers/specs/monitor-survey.md"


def render(defn: names.SheetDef):
    m = MONITORS[defn.subject]
    lay = layout(ROUTES["printed"])
    parts = B.printed_parts(lay)
    bezel = parts[f"bezel-{m.key}"]
    ret = parts[f"retainer-{m.key}"]
    pb = panel_in_lid(m, lay)
    ox0, oy0, ox1, oy1 = I.lid_opening(lay)
    datum = (ox0 + FIT, oy1 - FIT, 0.0)          # the bezel's hinge-end left corner
    tb = Part(defn, bezel.solid, "", "", [], [], (), turn=TURN)
    shift = tuple(-v for v in tb.P(datum))
    bz = Part(defn, bezel.solid, "", "", [], [], (), turn=TURN, shift=shift)
    rt = Part(defn, ret.solid, "", "", [], [], (), turn=TURN, shift=shift)
    bproj = {"front": project(bz.shape(), "plan")}     # the bezel: its plan only
    rproj = {"front": project(rt.shape(), "plan")}    # the retainer: its plan only

    w, h, wx, wy = monitor_window(m)
    W, Hp, T = m.panel
    ax, ay = m.active_offset
    aw, ah = m.active
    # panel front frame (u right, v up from its lower-left) -> lid frame
    def lid_pt(u, v):
        return pb.x0 + u, pb.y1 - v, 0.0

    def bq(u, v):
        """A panel-frame point in the bezel plan's coordinates."""
        return to_view("plan", bz.P(lid_pt(u, v)))

    stack = insert_stack(m)
    rb = ret.solid.BoundingBox()
    ret_h = rb.zmax - rb.zmin
    edge = exit_edge(m)
    cut = button_cutout(m)

    def bezel_ann(v):
        p = v["front"]
        out = [
            # window against the panel: size, then position from the panel's edges
            K.Dim(p, bq(wx, wy), bq(wx + w, wy), "bottom", 0),
            K.Dim(p, bq(0.0, wy), bq(wx, wy), "bottom", 1, text_side="low"),
            K.Dim(p, bq(wx + w, wy), bq(W, wy), "bottom", 1, text_side="high"),
            K.Dim(p, bq(wx + w, wy), bq(wx + w, wy + h), "right", 0),
            K.Dim(p, bq(wx + w, 0.0), bq(wx + w, wy), "right", 1, text_side="low"),
            K.Dim(p, bq(wx + w, wy + h), bq(wx + w, Hp), "right", 1, text_side="high"),
            # the panel against the bezel plate's datum corner
            K.Dim(p, (0.0, 0.0), (0.0, bq(0.0, 0.0)[1]), "left", 0, text_side="high"),
            K.Dim(p, (0.0, p.bb[3]), (bq(0.0, 0.0)[0], p.bb[3]), "top", 0, base=p.rect.y1,
                  text_side="low"),
            # the plate
            K.Dim(p, (p.bb[0], p.bb[3]), (p.bb[2], p.bb[3]), "top", 1, base=p.rect.y1),
            K.Dim(p, (p.bb[0], p.bb[1]), (p.bb[0], p.bb[3]), "left", 1),
        ]
        return out

    def ret_ann(v):
        p = v["front"]
        x0, y0, x1, y1 = p.bb
        return [
            K.Dim(p, (x0, y0), (x1, y0), "bottom", 0),
            K.Dim(p, (x1, y0), (x1, y1), "right", 0),
        ]

    def build(sheet, s):
        def bann(views):
            return K.captioned(views, bezel_ann(views), {"front": "BEZEL, SCREEN SIDE"})

        bviews, bann_ = K.solve(bproj, s, bann, sheet.frame)
        bx1 = K._union([K._rect_box(bviews["front"].rect)] + [a.extent() for a in bann_])[2]

        def rann(views):
            return K.captioned(views, ret_ann(views), {"front": "RETAINER, SCREEN SIDE"})

        rviews, rann_ = K.solve(rproj, s, rann, sheet.frame,
                                anchor=(bx1 + 10.0, sheet.frame.y1 - 6.5))
        views = {"bezel": bviews["front"], **{f"ret-{k}": v for k, v in rviews.items()}}
        lay_ = K.Layout(views, bann_ + rann_)

        def draw(sh):
            c = sh.canvas
            K.draw_view(c, bviews["front"], hidden=False)
            for k, v in rviews.items():
                K.draw_view(c, v, hidden=False)
            pv = bviews["front"]
            # the panel and its active area, adjacent parts, in phantom
            for (u0, v0, u1, v1) in ((0.0, 0.0, W, Hp), (ax, ay, ax + aw, ay + ah)):
                pts = [bq(u0, v0), bq(u1, v0), bq(u1, v1), bq(u0, v1), bq(u0, v0)]
                c.polyline([pv.pt(*q) for q in pts], **K.PHANTOM)
            for xy in I.bezel_screws(lay):
                cx, cy = to_view("plan", bz.P((*xy, 0.0)))
                dims.centre_mark(c, *pv.pt(cx, cy), pv.scale * I.BEZEL_SCREW_D / 2,
                                 colour=style.C_LINE)
            K.datum_mark(c, {"b": pv})

        # one line type needs saying, and the note says it: no legend
        legend = None
        cut_note = (f" Button cut-out {F(cut[0])} square, centre {F(cut[2] + cut[0] / 2)} "
                    f"from the panel's left, {F(cut[3] + cut[1] / 2)} up.") if cut else ""
        notes = [
            "Datum (target): the bezel's hinge-end left corner. Drawn screen side up, the "
            "panel's bottom edge at the hinge.",
            f"Phantom (grey, chain double-dot): the panel, {F(W)} x {F(Hp)}, and its active "
            f"area, {F(aw)} x {F(ah)}. "
            f"Window {F(w)} x {F(h)}: the whole active area"
            + (f" and at least the monitor's own window ({F(m.window[0])} x "
               f"{F(m.window[1])}), centred on the active area" if m.window else "")
            + "; at least 1.00 inside the panel's edge." + cut_note,
            f"Bezel {F(INSERT_MATERIAL)} thick, prints flat: {len(I.bezel_screws(lay))} "
            f"D{F(I.BEZEL_SCREW_D)} holes for M3 x "
            f"{m3.stock_length(INSERT_MATERIAL + 5.7 - 1.0)} pan-heads into the lid's "
            "inserts; the bezel clip (TDB-CLIP-P) holds the fourth corner.",
            f"Retainer {F(ret_h)} deep (stack {F(stack)}), {F(INSERT_MATERIAL)} plate and walls; "
            f"walls open on the {edge} edge but {F(I.EXIT_TAB)} tabs. Prints back down."
            + (f" Driver board on {len(I.driver_posts(m, lay))} posts, M3 x "
               f"{I.driver_screw_length(m)} + nyloc." if m.driver is not None else ""),
            K.unconfirmed_note((m.key,)),
        ]
        refs = []
        for src in m.sources:
            if src.ref not in refs:
                refs.append(src.ref)
        sources = refs + ["demobox/shared/inserts.py, demobox/checks.py (monitor_window)"]
        return lay_, [], legend, notes, sources, draw

    return K.render(defn, build, subtitle=m.title if len(m.title) < 60 else m.key,
                    material=K.PRINTED_MATERIAL, tolerance=K.PRINTED_TOL,
                    scales=(0.4, 0.2))
