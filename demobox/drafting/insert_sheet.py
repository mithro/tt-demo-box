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
from demobox.drafting.hlr import project, to_view, view_bbox
from demobox.drafting.part_sheet import Part
from demobox.layout import (FIT, HEATSET_DEPTH, INSERT_MATERIAL, ROUTES, exit_edge, insert_stack,
                            layout)
from demobox.parts.monitors import MONITORS
from demobox.printed import body as B
from demobox.shared import inserts as I
from demobox.shared import hinge as H
from demobox.shared import m3

F = K.fmt
TURN = (((1.0, 0.0, 0.0), 180.0),)


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

    edge = exit_edge(m)
    cut = button_cutout(m)

    def bxy(x, y):
        """A closed-lid-frame point in the bezel plan, from the bezel datum."""
        return to_view("plan", bz.P((x, y, 0.0)))

    r0 = view_bbox(rt.shape(), "plan")

    def rxy(x, y):
        """A closed-lid-frame point in the retainer plan, from its own lower-left."""
        a, b = to_view("plan", rt.P((x, y, 0.0)))
        return a - r0[0], b - r0[1]

    def span(f, x0, y0, x1, y1):
        (a0, b0), (a1, b1) = f(x0, y0), f(x1, y1)
        return (f"{F(min(a0, a1))}..{F(max(a0, a1))}", f"{F(min(b0, b1))}..{F(max(b0, b1))}")

    rows = []
    for i, (x, y) in enumerate(I.bezel_screws(lay)):
        a, b = bxy(x, y)
        rows.append([f"Bezel hole {i + 1}", F(a), F(b), f"D{F(I.BEZEL_SCREW_D)} thru"])
    # the knuckle relief notches in the bezel's hinge edge, at its screen face
    rr = H.KNUCKLE_R + FIT
    depth = rr - abs(oy1 - FIT)
    for i, (g0, g1) in enumerate(H.hinge_groups(lay)):
        xs, _ = span(bxy, g0 - FIT, 0.0, g1 + FIT, 0.0)
        rows.append([f"Bezel notch {i + 1}", xs, f"0.00..{F(depth)}",
                     f"R{F(rr)}, hinge edge"])
    if cut is not None:
        cw, chh, cx, cy = cut
        xs, ys = span(bxy, *lid_pt(cx, cy)[:2], *lid_pt(cx + cw, cy + chh)[:2])
        rows.append(["Bezel button cut-out", xs, ys, f"{F(cw)} square"])
    t = INSERT_MATERIAL                      # the wall the cut goes through
    if edge in ("bottom", "top"):
        y0, y1 = (pb.y1, pb.y1 + t) if edge == "bottom" else (pb.y0 - t, pb.y0)
        xs, ys = span(rxy, pb.x0 + I.EXIT_TAB, y0, pb.x1 - I.EXIT_TAB, y1)
    else:
        x0, x1 = (pb.x1, pb.x1 + t) if edge == "right" else (pb.x0 - t, pb.x0)
        xs, ys = span(rxy, x0, pb.y0 + I.EXIT_TAB, x1, pb.y1 - I.EXIT_TAB)
    rows.append([f"Retainer exit cut ({edge})", xs, ys,
                 f"{F(I.EXIT_TAB)} end tabs"])
    posts = I.driver_posts(m, lay)
    if posts:
        # the four posts stand on a rectangle: their X and Y, each pair once
        pts = [rxy(c.cx, c.cy) for c in posts]
        xs = sorted({round(a, 2) for a, _ in pts})
        ys = sorted({round(b, 2) for _, b in pts})
        if len(xs) * len(ys) != len(pts):
            raise ValueError(f"{m.key}: driver posts are not on a rectangle")
        rows.append([f"Retainer posts ({len(pts)})", ", ".join(F(v) for v in xs),
                     ", ".join(F(v) for v in ys),
                     f"D{F(2 * posts[0].r)}, D{F(m3.CLEARANCE_D)} thru"])
    table = K.Table("", ["FEATURE", "X", "Y", "SIZE"], rows, ["start", "end", "end", "start"])

    stack = insert_stack(m)
    rb = ret.solid.BoundingBox()
    ret_h = rb.zmax - rb.zmin

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

        bviews, bann_ = K.solve(bproj, s, bann, sheet.frame,
                                bbs={"front": view_bbox(bz.shape(), "plan")})
        by0 = K._union([K._rect_box(bviews["front"].rect)] + [a.extent() for a in bann_])[1]

        def rann(views):
            return K.captioned(views, ret_ann(views), {"front": "RETAINER, SCREEN SIDE"})

        # below the bezel, so the paper right of both is one column for the
        # table and the notes
        rviews, rann_ = K.solve(rproj, s, rann, sheet.frame,
                                bbs={"front": view_bbox(rt.shape(), "plan")},
                                anchor=(sheet.frame.x + 6.5, by0 - 6.0))
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
            rv = rviews["front"]
            dims.datum_marker(c, *rv.pt(r0[0], r0[1]), label="")

        # one line type needs saying, and the note says it: no legend
        legend = None
        notes = [
            "Datums (targets): bezel and retainer hinge-end left corners. Screen side up.",
            f"Phantom: the panel, {F(W)} x {F(Hp)}, and its active area. The window shows "
            "the whole active area"
            + (" and the monitor's own window" if m.window else "")
            + " and stays 1.00 or more inside the panel's edge.",
            f"Bezel {F(INSERT_MATERIAL)} thick, flat: M3 x "
            f"{m3.insert_screw(INSERT_MATERIAL, HEATSET_DEPTH)} pan-heads into the lid's "
            "inserts; the clip (TDB-CLIP-P) holds the fourth corner.",
            f"Retainer {F(ret_h)} deep (stack {F(stack)}), {F(INSERT_MATERIAL)} plate and walls."
            + (f" Driver board: M3 x {I.driver_screw_length(m)} + nyloc per post."
               if m.driver is not None else ""),
            K.unconfirmed_note((m.key,)),
        ]
        refs = []
        for src in m.sources:
            if src.ref not in refs:
                refs.append(src.ref)
        sources = ["docs/: " + ", ".join(r.split("/")[-1] for r in refs),
                   "demobox/shared/inserts.py, demobox/checks.py"]
        return lay_, [table], legend, notes, sources, draw

    return K.render(defn, build, subtitle=m.title if len(m.title) < 60 else m.key,
                    material=K.PRINTED_MATERIAL, tolerance=K.PRINTED_TOL,
                    scales=(0.4, 0.2))
