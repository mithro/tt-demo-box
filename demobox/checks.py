"""The fit proofs, one function per claim, each ``(report, lay) -> None``.

``verify.py`` runs every proof against ``layout(wall)`` for each build route
and prints the ``Report``.  A proof records ``report.check(ok, what, detail)``
for each claim and ``report.unconfirmed(what, detail)`` for every placeholder
figure it leans on: an UNCONFIRMED figure is printed, never trusted silently
and never a failure on its own.

Where a figure can be reached two ways, the proof takes the way ``layout.py``
did not: board positions come from ``board_origin`` and the submodule's hole
table rather than from the keep-outs; the tallest component is read live from
``demobox.parts.board``; the lid's swing is rotated here independently and
compared with ``Layout.lid_profile_yz``.

Rules owned here (later tasks import them rather than restate them):

* ``monitor_window(m)``: the bezel window covers the whole active area and,
  for a cased monitor, at least the monitor's own window; it stays
  ``WINDOW_INSET`` inside the panel edge on every side so the panel's edges
  stay hidden (R4).
* ``button_cutout(m)``: a ``BUTTON_CUTOUT`` square in the bezel round a front
  button that the window does not already expose.
* ``panel_in_lid(m, lay)``: where the panel sits in the closed lid.
* ``connector_opening(m, lay)``: the lid-wall opening the monitor's cable or
  plug leaves through.

Frames are layout.py's.  Monitor placement in the lid (lid frame, closed):
the screen faces -Z (down onto the deck), the bezel plate fills Z 0 ..
``INSERT_MATERIAL`` and the panel's front face is at Z = ``INSERT_MATERIAL``.
The panel is mounted buttons-down: its bottom edge is at the hinge end (lid
Y = 0 side), so panel x runs along lid +X (the visitor's right, with the lid
open) and panel y runs along lid -Y.  It is centred in X and sits FIT +
INSERT_MATERIAL off the pocket's hinge-end wall, where its cable leaves.
"""

from __future__ import annotations

import math

import demobox  # noqa: F401  (puts the submodule on sys.path)
from shapely.geometry import Point, box as sbox

from demobox import layout as L
from demobox.geom import Box
from demobox.layout import FIT, INSERT_MATERIAL, Layout, exit_edge
from demobox.parts import board as board_mod
from demobox.parts.batteries import BATTERIES
from demobox.parts.board import BOARD_KEYS, board_spec
from demobox.parts.cables import CABLES
from demobox.parts.monitors import MONITORS, Monitor
from demobox.parts.tinyvga import TINYVGA

#: Floating point slack on equalities between derived figures.
EPS = 1e-6
#: Overlap area (mm^2) below which two YZ profiles only touch.  The closed lid
#: rests on the base, so their profiles share an edge: the intersection has
#: zero area (a line), which is contact, not a collision.  1e-6 mm^2 is far
#: below any real interference and far above floating-point noise.
AREA_TOL = 1e-6
#: The bezel window stays this far inside the panel edge on every side.
WINDOW_INSET = 1.0
#: Side of the square cut-out round a front button the window does not reach.
BUTTON_CUTOUT = 10.0
#: A fingertip, as the disc that must reach a button.
FINGERTIP_D = 16.0
#: Least plastic round an M3 heat-set insert in a standoff.
MIN_BOSS_WALL = 1.0
#: Spec: a slim VGA cable <= 0.5 m.
VGA_MAX_LEN = 500.0

VGA = CABLES["vga-slim"]
VGA_PLUG = VGA.plug
BOARD_CABLE = CABLES["usb-c-right-angle"]     # bank to J1 (layout's USB cable)
BOOST = CABLES["usb-12v-boost"]
POWER_CABLE = {"12V-boost": BOOST}            # monitor power_in -> bank-side cable


# --- the report ---------------------------------------------------------------

class Unconfirmed(list):
    """The UNCONFIRMED list of ``(what, detail)``.  Calling it records an item
    (once); being a list, it is also what ``verify.py`` prints."""

    def __call__(self, what: str, detail: str) -> None:
        if (what, detail) not in self:
            self.append((what, detail))


class Report:
    def __init__(self) -> None:
        self.results: list[tuple[bool, str, str]] = []
        self.unconfirmed = Unconfirmed()

    def check(self, ok: bool, what: str, detail: str) -> None:
        self.results.append((bool(ok), what, detail))

    @property
    def failures(self) -> int:
        return sum(1 for ok, _, _ in self.results if not ok)


def _placeholders(sources) -> str:
    notes = [f"{s.label}: {s.note}" for s in sources if "placeholder" in s.label.lower()]
    return "; ".join(notes or [s.label for s in sources])


def _f(x: float) -> str:
    return f"{x:.2f}"


# --- rules shared with the made parts --------------------------------------------

def monitor_window(m: Monitor) -> tuple[float, float, float, float]:
    """The bezel window (w, h, x, y), relative to the panel's lower-left.

    It covers the whole active area; for a cased monitor it is at least the
    monitor's own window (so the bezel hides nothing that monitor shows),
    centred on the active area (the own window's position is not measured).
    ``monitors_fit`` proves it stays ``WINDOW_INSET`` inside the panel edge.
    """
    aw, ah = m.active
    ax, ay = m.active_offset
    w, h = aw, ah
    if m.window is not None:
        w, h = max(w, m.window[0]), max(h, m.window[1])
    return (w, h, ax - (w - aw) / 2, ay - (h - ah) / 2)


def _inside(px: float, py: float, rect, margin: float) -> bool:
    w, h, x, y = rect
    return (x + margin - EPS <= px <= x + w - margin + EPS
            and y + margin - EPS <= py <= y + h - margin + EPS)


def button_cutout(m: Monitor) -> tuple[float, float, float, float] | None:
    """The bezel cut-out (w, h, x, y) round the monitor's front button, panel
    lower-left frame; None with no button, or when the window exposes it."""
    if m.button is None or _inside(*m.button, monitor_window(m), BUTTON_CUTOUT / 2):
        return None
    bx, by = m.button
    s = BUTTON_CUTOUT
    return (s, s, bx - s / 2, by - s / 2)


def panel_in_lid(m: Monitor, lay: Layout) -> Box:
    """The panel body in the closed lid frame (see the module docstring)."""
    p = lay.lid_pocket
    w, h, t = m.panel
    edge = exit_edge(m)
    if edge == "right":                      # pushed away from its exit side
        x0 = p.x0 + FIT + INSERT_MATERIAL
    elif edge == "left":
        x0 = p.x1 - FIT - INSERT_MATERIAL - w
    else:
        x0 = (p.x0 + p.x1) / 2 - w / 2
    bottom = p.y1 - FIT - INSERT_MATERIAL
    return Box(x0, bottom - h, INSERT_MATERIAL, x0 + w, bottom,
               INSERT_MATERIAL + t, f"{m.key} panel")


def _panel_point(m: Monitor, lay: Layout, u: float, v: float) -> tuple[float, float]:
    """Panel front-frame (u, v) to closed lid-frame (x, y)."""
    pb = panel_in_lid(m, lay)
    return pb.x0 + u, pb.y1 - v


def connector_opening(m: Monitor, lay: Layout) -> Box | None:
    """Where the monitor's cables and plugs go as they leave it (closed lid
    frame): for the hinge-end (bottom) edge, the hinge cable channel's crossing
    of the lid's hinge-end wall; for a side edge, the space from the panel edge
    to the far side of that side's cable gutter (R13: the cable stays in the
    lid).  None when the lid has no gutter on that side (a top exit)."""
    lid, pocket = lay.lid_outer, lay.lid_pocket
    edge = exit_edge(m)
    if edge == "bottom":
        c = lay.hinge_cable_channel
        hz = lay.hinge_axis[1]
        return Box(c.x0, lid.y1 - lay.wall, 0.0, c.x1, lid.y1, min(c.z1 - hz, pocket.z1),
                   f"{m.key} cable opening (hinge channel)")
    g = lay.lid_cable_gutters.get(edge)
    if g is None:
        return None
    pb = panel_in_lid(m, lay)
    x0, x1 = (pb.x1, g.x1) if edge == "right" else (g.x0, pb.x0)
    return Box(x0, g.y0, g.z0, x1, g.y1, g.z1, f"{m.key} cable space ({edge} gutter)")


def lid_point_open(lay: Layout, y: float, z: float, angle_deg: float) -> tuple[float, float]:
    """Lid-frame (y, z) to base-frame (Y, Z) at ``angle_deg`` open, worked
    here from the frame definitions (a turn about the hinge axis lifting the
    front edge, -Y, up and over), independently of ``Layout._open_yz``."""
    hy, hz = lay.hinge_axis
    t = math.radians(angle_deg)
    return (hy + y * math.cos(t) + z * math.sin(t),
            hz - y * math.sin(t) + z * math.cos(t))


def _yz(b: Box):
    return sbox(b.y0, b.z0, b.y1, b.z1)


# --- the proofs ------------------------------------------------------------------

def monitors_fit(report: Report, lay: Layout) -> None:
    """Every monitor in the lid: window, insert material, depth, cable opening."""
    pocket = lay.lid_pocket
    for m in MONITORS.values():
        if not m.confirmed:
            report.unconfirmed(f"monitor {m.key}", _placeholders(m.sources))
        W, H, _ = m.panel
        w, h, x, y = monitor_window(m)
        ax, ay = m.active_offset
        aw, ah = m.active
        covers = x <= ax + EPS and y <= ay + EPS and x + w >= ax + aw - EPS \
            and y + h >= ay + ah - EPS
        own = m.window is None or (w >= m.window[0] - EPS and h >= m.window[1] - EPS)
        inset = min(x, y, W - x - w, H - y - h)
        report.check(covers and own and inset >= WINDOW_INSET - EPS,
                     f"{m.key}: bezel window covers the active area, {WINDOW_INSET} mm inside "
                     "the panel edge",
                     f"window {_f(w)} x {_f(h)} at ({_f(x)}, {_f(y)}) on a {_f(W)} x {_f(H)} "
                     f"panel; active {_f(aw)} x {_f(ah)} at ({_f(ax)}, {_f(ay)}); "
                     f"least inset {_f(inset)} mm"
                     + ("" if m.window is None else f"; own window {m.window[0]} x {m.window[1]}"))

        pb = panel_in_lid(m, lay)
        sides = {"left": pb.x0 - FIT - pocket.x0, "right": pocket.x1 - pb.x1 - FIT,
                 "front": pb.y0 - FIT - pocket.y0, "hinge end": pocket.y1 - pb.y1 - FIT}
        least = min(sides, key=sides.get)
        report.check(sides[least] >= INSERT_MATERIAL - EPS,
                     f"{m.key}: insert leaves >= {INSERT_MATERIAL} mm of material round the panel",
                     f"pocket {_f(pocket.size[0])} x {_f(pocket.size[1])}, panel {_f(W)} x {_f(H)}, "
                     f"FIT {FIT}: least {_f(sides[least])} mm ({least})")
        stack = L.insert_stack(m)
        report.check(pocket.size[2] >= stack + FIT - EPS,
                     f"{m.key}: insert stack fits the pocket depth",
                     f"stack {_f(stack)} + FIT {FIT} <= pocket {_f(pocket.size[2])} mm")
        if m.driver is not None:
            d = m.driver
            report.check(d.x0 >= 0 and d.y0 >= 0 and d.x1 <= W and d.y1 <= H,
                         f"{m.key}: driver board behind the panel, under the retainer",
                         f"board {_f(d.x0)}..{_f(d.x1)} x {_f(d.y0)}..{_f(d.y1)} on the "
                         f"{_f(W)} x {_f(H)} panel back")

        _connector_opening_fits(report, lay, m)


def _connector_opening_fits(report: Report, lay: Layout, m: Monitor) -> None:
    pocket = lay.lid_pocket
    o = connector_opening(m, lay)
    _, pw, ph = VGA_PLUG
    edge = exit_edge(m)
    if o is None:
        report.check(False, f"{m.key}: lid opening passes the VGA plug",
                     f"no cable gutter on the {edge} edge")
        return
    across, tall = o.size[0], o.size[2]
    if edge == "bottom":
        into = o.x0 >= pocket.x0 - EPS and o.x1 <= pocket.x1 + EPS
        where = "hinge channel"
    else:
        into = True
        where = f"{edge} gutter"
    in_depth = o.z0 >= pocket.z0 - EPS and o.z1 <= pocket.z1 + EPS
    ok = across >= pw + 2 * FIT - EPS and tall >= ph + 2 * FIT - EPS and into and in_depth
    report.check(ok, f"{m.key}: lid {where} opening passes the VGA plug",
                 f"exit {m.connector_exit}/{edge}: opening {_f(across)} x {_f(tall)} "
                 f"(z {_f(o.z0)}..{_f(o.z1)}, pocket depth {_f(pocket.z1)}) for a "
                 f"{pw} x {ph} plug + FIT {FIT} each side; within the pocket's span: {into}")
    if m.connector_exit == "board":
        report.unconfirmed(f"{m.key} connector exit",
                           "driver-board connector positions unmeasured; the cable is "
                           "assumed to leave at the hinge end through the hinge channel")
    elif m.connector_exit == "pigtail":
        report.unconfirmed(f"{m.key} pigtail",
                           f"cable leaves the {edge} edge; its position along the edge and "
                           "the pigtail's length are unmeasured")


def batteries_fit(report: Report, lay: Layout) -> None:
    """Every bank in the bay with its packing, port end at the cable-bay wall."""
    bl, bw, bh = lay.bay.size
    for b in BATTERIES.values():
        if not b.confirmed:
            report.unconfirmed(f"battery {b.key}", _placeholders(b.sources))
        L_, W_, H_ = b.size
        packing = bl - L_ - FIT
        report.check(packing >= -EPS and W_ + 2 * FIT <= bw + EPS and H_ + FIT <= bh + EPS,
                     f"{b.key}: bank + packing fills the bay",
                     f"bank {L_} x {W_} x {H_} in bay {_f(bl)} x {_f(bw)} x {_f(bh)}: end-stop "
                     f"{_f(packing)} mm (+ FIT {FIT}), side spacers {_f((bw - W_) / 2)} mm each, "
                     f"headroom {_f(bh - H_)} mm")
        if b.port_face == "end":
            report.check(True, f"{b.key}: port end against the cable-bay wall",
                         f"ports face -X into the {_f(lay.cable_bay.size[0])} mm cable bay; "
                         "the end-stop sits at the far end")
        elif b.port_face == "top":
            plug_h = BOARD_CABLE.plug[2]
            room = (lay.deck_z - lay.wall) - (lay.bay.z0 + H_)
            report.check(room >= plug_h - EPS,
                         f"{b.key}: plugs on the top face clear the deck",
                         f"{_f(room)} mm from the bank's top face to the deck underside >= "
                         f"{plug_h} mm right-angle plug")
            report.unconfirmed(f"{b.key} top-face ports",
                               "plugs stand above the drawer rim; the drawer opening in the "
                               "base's left wall must pass them")
        else:
            report.check(False, f"{b.key}: port face reachable",
                         f"ports on the {b.port_face} face meet the packing's side spacer")


def buttons_reachable(report: Report, lay: Layout) -> None:
    """Each bank's button with the drawer out (R10); each monitor's front button
    exposed by the bezel and reachable with the lid open."""
    out = lay.outer.x0
    travel = lay.drawer_travel
    hole = lay.drawer_face_hole
    for b in BATTERIES.values():
        if b.button is None:
            continue
        face, u, v = b.button
        W_ = b.size[1]
        y = lay.bay.y0 + (lay.bay.size[1] - W_) / 2 + u
        if face == "end":
            z = lay.bay.z0 + v
            behind = lay.bay.x0 - out
            open_end = lay.cable_bay.x1 - travel
            report.check(hole.y0 < y < hole.y1 and hole.z0 < z < hole.z1,
                         f"{b.key}: end button under the drawer-face finger hole",
                         f"button (y {_f(y)}, z {_f(z)}) in hole y {_f(hole.y0)}..{_f(hole.y1)}, "
                         f"z {_f(hole.z0)}..{_f(hole.z1)}")
            report.check(open_end <= out + EPS,
                         f"{b.key}: end button reachable with the drawer out",
                         f"{_f(behind)} mm behind the drawer face when shut; drawer out "
                         f"{_f(travel)} mm: the cable bay in front of the button ends at x "
                         f"{_f(open_end)}, outside the base face (x {_f(out)})")
            report.unconfirmed(f"{b.key} button",
                               "on the port end, behind the cable bay, out of reach with the "
                               "drawer shut: press with drawer open")
        elif face == "top":
            reach = lay.bay.x0 + u + FINGERTIP_D / 2 - travel
            report.check(reach <= out + EPS,
                         f"{b.key}: top-face button uncovered with the drawer out",
                         f"drawer out {_f(travel)} mm: button + fingertip reach x {_f(reach)}, "
                         f"outside the base face (x {_f(out)})")
            report.unconfirmed(f"{b.key} button",
                               "on the top face, under the deck with the drawer shut: "
                               "press with drawer open")
        else:
            report.check(False, f"{b.key}: button reachable with the drawer out",
                         f"a {face}-face button stays covered by the packing's side spacer")

    o = lay.outer
    base = sbox(o.y0, o.z0, o.y1, o.z1)
    r = FINGERTIP_D / 2
    for m in MONITORS.values():
        if m.button is None:
            continue
        bx, by = m.button
        win, cut = monitor_window(m), button_cutout(m)
        exposed = _inside(bx, by, win, BUTTON_CUTOUT / 2) or (
            cut is not None and _inside(bx, by, cut, BUTTON_CUTOUT / 2))
        report.check(exposed, f"{m.key}: front button not covered by the bezel",
                     f"button ({bx}, {by}); " + (
                         "inside the window" if cut is None else
                         f"cut-out {_f(cut[0])} x {_f(cut[1])} at ({_f(cut[2])}, {_f(cut[3])})"))
        _, ly = _panel_point(m, lay, bx, by)
        fy, fz = lid_point_open(lay, ly, -r, L.LID_OPEN_DEG)   # fingertip on the screen face
        hit = Point(fy, fz).buffer(r).intersection(base).area
        report.check(hit <= AREA_TOL,
                     f"{m.key}: front button reachable with the lid open",
                     f"at {L.LID_OPEN_DEG:g} deg a {FINGERTIP_D:g} mm fingertip on the button "
                     f"(lid y {_f(ly)}) sits {_f(fz - r - o.z1)} mm above the base top; "
                     f"overlap {hit:.3g} mm^2")


def _base_xy(lay: Layout, x: float, y: float) -> tuple[float, float]:
    ox, oy, _ = lay.board_origin
    return ox - x, oy - y


def boards_seat(report: Report, lay: Layout) -> None:
    """Both board revisions on the deck: on their supports, pegged, screwed,
    inside the walls, USB-C cable through the deck slot."""
    for name, value, src in L.UNCONFIRMED:
        report.unconfirmed(name, f"{value}: {src.note}")
    if not TINYVGA.confirmed:
        report.unconfirmed("TinyVGA heights", _placeholders(TINYVGA.sources))
    o, m = lay.outer, lay.wall + FIT
    under = lay.board_origin[2]
    for k in BOARD_KEYS:
        spec = board_spec(k)
        for part in ("envelope", "usb_plug", "tinyvga"):
            b = lay.board_keepouts[f"{k}/{part}"]
            inside = (b.x0 >= o.x0 + m - EPS and b.x1 <= o.x1 - m + EPS
                      and b.y0 >= o.y0 + m - EPS and b.y1 <= o.y1 - m + EPS)
            report.check(inside and b.z0 >= lay.deck_z - EPS,
                         f"{k}: {part} inside the walls, above the deck",
                         f"x {_f(b.x0)}..{_f(b.x1)}, y {_f(b.y0)}..{_f(b.y1)} within "
                         f"{_f(m)} mm of the {_f(o.size[0])} x {_f(o.size[1])} base; "
                         f"z0 {_f(b.z0)} >= deck {_f(lay.deck_z)}")
        env = lay.board_keepouts[f"{k}/envelope"]
        tops = [(c.what, c.z1) for c in lay.standoffs + lay.supports]
        tops.append((lay.mt1_boss.what, lay.mt1_boss.z1))
        worst = max(tops, key=lambda t: abs(t[1] - under))
        report.check(abs(env.z0 - under) <= EPS and abs(worst[1] - under) <= EPS,
                     f"{k}: PCB underside on every support",
                     f"underside z {_f(under)}; envelope z0 {_f(env.z0)}; furthest support "
                     f"top {worst[0]} at {_f(worst[1])}")

        holes = {h.label: h for h in spec.holes}
        mt1, mt2 = holes["MT1"], holes["MT2"]
        peg = lay.pegs[k]
        px, py = _base_xy(lay, mt1.x, mt1.y)
        off = math.dist((peg.cx, peg.cy), (px, py))
        report.check(off <= EPS and 2 * peg.r < mt1.dia and abs(peg.z0 - under) <= EPS
                     and peg.z1 - peg.z0 < spec.outline.thickness
                     and lay.mt1_boss.covers(px, py),
                     f"{k}: MT1 locating peg in its hole, on the MT1 boss",
                     f"peg {_f(2 * peg.r)} in a {mt1.dia} hole, {_f(off)} off centre, "
                     f"{_f(peg.z1 - peg.z0)} tall in a {spec.outline.thickness} PCB")
        sx, sy = _base_xy(lay, mt2.x, mt2.y)
        s = min(lay.standoffs, key=lambda c: math.dist((c.cx, c.cy), (sx, sy)))
        off = math.dist((s.cx, s.cy), (sx, sy))
        boss_wall = s.r - L.HEATSET_HOLE_D / 2
        report.check(off <= EPS and s.z1 - s.z0 >= L.HEATSET_DEPTH - EPS
                     and boss_wall >= MIN_BOSS_WALL - EPS,
                     f"{k}: MT2 screwed to a heat-set standoff",
                     f"standoff {_f(off)} off MT2, {_f(s.z1 - s.z0)} tall for a "
                     f"{L.HEATSET_DEPTH} deep insert, {_f(boss_wall)} mm round its "
                     f"{L.HEATSET_HOLE_D} hole")

        ol = spec.outline
        rr = ol.corner_radius
        ox, oy, _ = lay.board_origin
        outline = sbox(ox - ol.width + rr, oy - ol.height + rr, ox - rr, oy - rr).buffer(rr)
        feet = [Point(c.cx, c.cy).buffer(c.r) for c in lay.standoffs + lay.supports + (peg,)]
        report.check(all(f.within(outline) for f in feet),
                     f"{k}: standoffs, pads and peg under the PCB",
                     f"{len(feet)} footprints within the {ol.width} x {ol.height} outline")

        plug = lay.board_keepouts[f"{k}/usb_plug"]
        slot = lay.usb_slot
        report.check(slot.x0 < plug.x0 and slot.x1 > plug.x1 and slot.y0 < plug.y0 < slot.y1,
                     f"{k}: USB-C cable drops through the deck slot",
                     f"plug x {_f(plug.x0)}..{_f(plug.x1)}, cable end y {_f(plug.y0)}; slot "
                     f"x {_f(slot.x0)}..{_f(slot.x1)}, y {_f(slot.y0)}..{_f(slot.y1)}")


def lid_closed_clears(report: Report, lay: Layout) -> None:
    """Closed, the lid's underside clears the tallest thing on the deck by
    CLOSED_CLEARANCE.  The tallest component is read live from the board data,
    not from the keep-outs the layout was sized with."""
    if not board_mod.TALLEST_COMPONENT_CONFIRMED:
        report.unconfirmed("TALLEST_COMPONENT", f"{board_mod.TALLEST_COMPONENT} mm: "
                           f"{board_mod.TALLEST_COMPONENT_SOURCE.note}")
    lid_under = lay.lid_profile_yz(0.0).bounds[1]
    need = L.CLOSED_CLEARANCE
    for k in BOARD_KEYS:
        top = lay.board_origin[2] + board_mod.TALLEST_COMPONENT
        report.check(lid_under - top >= need - EPS, f"{k}: closed lid clears the tallest component",
                     f"lid underside z {_f(lid_under)}, component top {_f(top)}: "
                     f"{_f(lid_under - top)} >= {need} mm")
        for part in ("usb_plug", "tinyvga"):
            b = lay.board_keepouts[f"{k}/{part}"]
            report.check(lid_under - b.z1 >= need - EPS, f"{k}: closed lid clears the {part}",
                         f"lid underside z {_f(lid_under)}, {part} top {_f(b.z1)}: "
                         f"{_f(lid_under - b.z1)} >= {need} mm")


def sweep_angles() -> list[float]:
    """Every whole degree from 0 to LID_OPEN_DEG, and the stop itself."""
    angles = [float(a) for a in range(0, int(math.floor(L.LID_OPEN_DEG)) + 1)]
    if angles[-1] != L.LID_OPEN_DEG:
        angles.append(float(L.LID_OPEN_DEG))
    return angles


def hinge_sweep(report: Report, lay: Layout) -> None:
    """The lid's YZ profile at each degree from closed to the stop meets
    neither the base nor any board keep-out (wherever their X ranges overlap)
    by more than AREA_TOL; at 0 it rests on the base, which is contact."""
    lid = lay.lid_outer
    obstacles = {"base": lay.outer, **lay.board_keepouts}
    obstacles = {n: b for n, b in obstacles.items()
                 if min(b.x1, lid.x1) - max(b.x0, lid.x0) > EPS}
    shapes = {n: _yz(b) for n, b in obstacles.items()}
    worst = {n: (0.0, 0.0) for n in shapes}
    corners = ((lid.y0, lid.z0), (lid.y1, lid.z0), (lid.y1, lid.z1), (lid.y0, lid.z1))
    drift = 0.0
    angles = sweep_angles()
    for a in angles:
        prof = lay.lid_profile_yz(a)
        drift = max(drift, max(prof.exterior.distance(Point(lid_point_open(lay, y, z, a)))
                               for y, z in corners))
        for n, s in shapes.items():
            area = prof.intersection(s).area
            if area > worst[n][0]:
                worst[n] = (area, a)
    report.check(drift <= EPS, "lid profile turns about the hinge axis",
                 f"lid_profile_yz agrees with an independent rotation to {drift:.2g} mm "
                 f"over {len(angles)} angles")
    for n, (area, a) in worst.items():
        report.check(area <= AREA_TOL,
                     f"lid swing 0..{L.LID_OPEN_DEG:g} deg clears {n}",
                     f"{len(angles)} angles; largest YZ overlap {area:.3g} mm^2"
                     + (f" at {a:g} deg" if area > 0 else "")
                     + f" (contact below {AREA_TOL:g} mm^2 is not a collision)")


def cables_route(report: Report, lay: Layout) -> None:
    """Drawer travel, the bank cables' slack loop, every bend radius, and the
    VGA path length.

    Slack loop: each bank-side cable lies in a flat rolling loop in the cavity
    over the drawer (Z from the bay top + FIT to the deck underside), runs
    along X, its moving end over the cable bay and its fixed end where it
    leaves the cavity (the deck slot for the board cable, the boost pocket for
    the monitor's boost cable).  Opening the drawer by T moves the loop's bend
    T/2, so the loop reaches T while 2 * (x_max - x_fixed) >= T, where x_max
    keeps the bend (radius min_bend_r) inside the cavity.

    VGA path: DE-15 face, the plug's run behind it, along the deck to the hinge
    axis at the channel (where the cable crosses, so its length barely changes
    with the angle), then in the lid to the monitor's exit point and its plug.
    Legs are summed as X + Y + Z (an upper bound on any smooth route)."""
    out, travel = lay.outer.x0, lay.drawer_travel
    for b in BATTERIES.values():
        need = (lay.bay.x0 - out) + b.size[0] + FIT
        report.check(travel >= need - EPS, f"{b.key}: drawer travel lifts the bank out",
                     f"travel {_f(travel)} >= face to port end {_f(lay.bay.x0 - out)} + bank "
                     f"{b.size[0]} + FIT {FIT} = {_f(need)} mm")
    back = lay.bay.x1 + lay.wall - travel
    report.check(back > out + lay.wall,
                 "drawer travel keeps the drawer in its runners",
                 f"drawer back at x {_f(back)} after {_f(travel)} mm, inside the left wall "
                 f"(x {_f(out + lay.wall)})")

    cavity = Box(lay.outer.x0 + lay.wall, lay.bay.y0, lay.bay.z1 + FIT,
                 lay.outer.x1 - lay.wall, lay.bay.y1, lay.deck_z - lay.wall, "slack cavity")
    moving = (lay.cable_bay.x0 + lay.cable_bay.x1) / 2
    loops = [(BOARD_CABLE, (lay.usb_slot.x0 + lay.usb_slot.x1) / 2, "deck slot")]
    for p in sorted({m.power_in for m in MONITORS.values()}):
        c = POWER_CABLE.get(p)
        if c is None:
            report.check(False, f"monitor power {p}: bank-side cable",
                         "no cable in demobox.parts.cables for this power input")
            continue
        loops.append((c, (lay.boost_pocket.x0 + lay.boost_pocket.x1) / 2, "boost pocket"))
    for c, fixed, where in loops:
        x_max = cavity.x1 - c.min_bend_r - c.dia / 2
        reach = 2 * (x_max - fixed)
        report.check(reach >= travel - EPS, f"{c.key}: slack loop reaches the drawer travel",
                     f"fixed at the {where} (x {_f(fixed)}), bend r {c.min_bend_r} up to x "
                     f"{_f(x_max)}: reach {_f(reach)} >= travel {_f(travel)} mm")
        bend0 = max(fixed + travel / 2, moving)
        # the two runs, the bend, and a cavity height each to rise and to drop
        length = (bend0 - moving) + math.pi * c.min_bend_r + (bend0 - fixed) + 2 * cavity.size[2]
        report.check(2 * c.min_bend_r + c.dia <= cavity.size[1] + EPS,
                     f"{c.key}: slack loop bend lies flat over the drawer",
                     f"loop width 2 x {c.min_bend_r} + {c.dia} <= cavity {_f(cavity.size[1])} mm; "
                     f"loop needs ~{_f(length)} mm of cable")
        report.unconfirmed(f"{c.key} length", "not in the cable data; buy one long enough "
                           f"for the slack loop to the {where} (see its check)")
    stack = sum(c.dia for c, _, _ in loops)
    report.check(stack <= cavity.size[2] + EPS, "slack loops stack in the cavity height",
                 f"{' + '.join(str(c.dia) for c, _, _ in loops)} <= {_f(cavity.size[2])} mm")
    report.check(cavity.size[2] >= BOARD_CABLE.min_bend_r + BOARD_CABLE.dia - EPS,
                 f"{BOARD_CABLE.key}: bend from the deck slot into the cavity",
                 f"cavity {_f(cavity.size[2])} >= bend r {BOARD_CABLE.min_bend_r} + dia "
                 f"{BOARD_CABLE.dia} mm")

    ch = lay.hinge_cable_channel
    hy, hz = lay.hinge_axis
    for c in [VGA] + sorted({POWER_CABLE[m.power_in] for m in MONITORS.values()
                             if m.power_in in POWER_CABLE}, key=lambda c: c.key):
        report.check(ch.size[1] >= c.min_bend_r - EPS and ch.size[2] >= c.min_bend_r - EPS,
                     f"{c.key}: bend through the hinge channel",
                     f"channel {_f(ch.size[1])} deep (Y) x {_f(ch.size[2])} tall (Z) >= bend r "
                     f"{c.min_bend_r} mm")
    for c in CABLES.values():
        if not c.confirmed:
            report.unconfirmed(f"cable {c.key}", _placeholders(c.sources))

    for m in MONITORS.values():
        _in_lid_route(report, lay, m)

    run = TINYVGA.plug_keepout(L.VGA_PLUG_STRAIGHT).size[1]
    p1 = ((ch.x0 + ch.x1) / 2, hy, hz)
    for m in MONITORS.values():
        legs = []
        for k in BOARD_KEYS:
            v = lay.board_keepouts[f"{k}/tinyvga"]
            p0 = ((v.x0 + v.x1) / 2, v.y1, (v.z0 + v.z1) / 2)
            legs.append(sum(abs(a - b) for a, b in zip(p0, p1)))
        base_leg = max(legs)
        x2, y2, z2 = _exit_point(m, lay)
        lid_leg = abs(x2 - p1[0]) + abs(y2) + abs(z2)
        total = run + base_leg + lid_leg + VGA_PLUG[0]
        report.check(total <= VGA_MAX_LEN + EPS, f"{m.key}: VGA path within the cable",
                     f"plug run {_f(run)} + deck to hinge {_f(base_leg)} + lid to the "
                     f"{exit_edge(m)} exit {_f(lid_leg)} + plug {VGA_PLUG[0]} = {_f(total)} "
                     f"<= {VGA_MAX_LEN:g} mm")


def _in_lid_route(report: Report, lay: Layout, m: Monitor) -> None:
    """R13: the monitor's cable bundle (``lid_cable_bundle``: width d, bend r)
    goes exit -> gutter -> hinge channel inside the lid.

    * Every gutter on the way is open to the pocket (or to the gutter before
      it) and at least d + FIT wide and deep.
    * Leaving a panel edge square into a gutter and turning along it, the
      bundle needs r + d/2 + FIT from the panel edge to the gutter's far side.
      A bottom exit over the channel's X span goes straight in, no turn.
    * A side gutter runs from the exit to the hinge gutter.  The corner into
      the hinge gutter needs nothing more: with r + d/2 of room on the side,
      the turn's centre lies beyond the inner corner, so a d-wide hinge gutter
      takes it.  The hinge gutter spans the channel's X range and reaches the
      hinge-end wall, where the channel takes the bundle down into the base
      (that bend is the hinge-channel check above).
    """
    d, r = L.lid_cable_bundle()
    run, turn = d + FIT, r + d / 2 + FIT
    edge = exit_edge(m)
    g = lay.lid_cable_gutters
    h = g.get("hinge")
    pb = panel_in_lid(m, lay)
    ch = lay.hinge_cable_channel
    pocket = lay.lid_pocket
    what = f"{m.key}: in-lid cable route to the hinge channel"
    problems: list[str] = []
    notes: list[str] = [f"bundle {_f(d)} mm, bend r {r}"]
    if h is None:
        report.check(False, what, "no hinge-end gutter")
        return
    if h.size[1] < run - EPS or h.size[2] < run - EPS:
        problems.append(f"hinge gutter {_f(h.size[1])} x {_f(h.size[2])} < {_f(run)}")
    if h.y0 > pocket.y1 + EPS:
        problems.append(f"hinge gutter (y0 {_f(h.y0)}) not open to the pocket (y1 {_f(pocket.y1)})")
    if h.x0 > ch.x0 + EPS or h.x1 < ch.x1 - EPS or h.y1 < lay.lid_outer.y1 - lay.wall - EPS:
        problems.append("hinge gutter does not reach the hinge channel")
    if edge == "bottom":
        x = (pb.x0 + pb.x1) / 2
        if m.connector_exit == "board" and m.driver is not None:
            x = pb.x0 + m.panel[0] - (m.driver.x0 + m.driver.x1) / 2
        if ch.x0 + d / 2 <= x <= ch.x1 - d / 2:
            notes.append(f"exit at x {_f(x)} straight into the channel")
        else:
            room = h.y1 - pb.y1
            notes.append(f"turn into the hinge gutter: {_f(room)} >= {_f(turn)} mm")
            if room < turn - EPS:
                problems.append(f"turn room {_f(room)} < {_f(turn)}")
    elif edge in ("left", "right"):
        s = g.get(edge)
        if s is None:
            problems.append(f"no {edge} gutter")
        else:
            room = s.x1 - pb.x1 if edge == "right" else pb.x0 - s.x0
            opens = (s.x0 <= pocket.x1 + EPS) if edge == "right" else (s.x1 >= pocket.x0 - EPS)
            yc = (pb.y0 + pb.y1) / 2
            notes.append(f"{edge} gutter {_f(s.size[0])} wide; turn {_f(room)} >= {_f(turn)} mm")
            if s.size[0] < run - EPS or s.size[2] < run - EPS:
                problems.append(f"{edge} gutter {_f(s.size[0])} x {_f(s.size[2])} < {_f(run)}")
            if not opens:
                problems.append(f"{edge} gutter not open to the pocket")
            if room < turn - EPS:
                problems.append(f"turn room {_f(room)} < {_f(turn)}")
            if s.y0 > yc - d / 2 + EPS or s.y1 < h.y0 - EPS:
                problems.append(f"{edge} gutter does not run from the exit to the hinge gutter")
            if (edge == "right" and h.x1 < s.x1 - EPS) or (edge == "left" and h.x0 > s.x0 + EPS):
                problems.append(f"hinge gutter does not reach the {edge} gutter")
        report.unconfirmed(f"{m.key} side connectors",
                           "plug bodies assumed within the rim's footprint (on the rear hump); "
                           "the cable's turn is counted from the panel edge")
    else:
        problems.append(f"no gutter route from the {edge} edge")
    report.check(not problems, what, "; ".join(problems or notes))


def _exit_point(m: Monitor, lay: Layout) -> tuple[float, float, float]:
    """Where the monitor's VGA leaves it, closed lid frame."""
    pb = panel_in_lid(m, lay)
    zc = (pb.z0 + pb.z1) / 2
    if m.connector_exit == "board" and m.driver is not None:
        d, W = m.driver, m.panel[0]
        x, y = _panel_point(m, lay, W - (d.x0 + d.x1) / 2, (d.y0 + d.y1) / 2)  # back frame
        return x, y, pb.z1 + L.DRIVER_STANDOFF + (d.z0 + d.z1) / 2
    edge = exit_edge(m)
    cx, cy = (pb.x0 + pb.x1) / 2, (pb.y0 + pb.y1) / 2
    return {"bottom": (cx, pb.y1, zc), "top": (cx, pb.y0, zc),
            "left": (pb.x0, cy, zc), "right": (pb.x1, cy, zc)}[edge]


#: Every proof, in the order verify.py prints them.
PROOFS = (monitors_fit, batteries_fit, buttons_reachable, boards_seat,
          lid_closed_clears, hinge_sweep, cables_route)
