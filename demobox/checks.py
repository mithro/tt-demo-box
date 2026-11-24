"""The fit proofs, one function per claim, each ``(report, lay) -> None``.

``verify.py`` runs every proof in ``PROOFS`` against ``layout(wall)`` for each
build route and prints the ``Report``.  A proof records
``report.check(ok, what, detail)`` for each claim and
``report.unconfirmed(what, detail)`` for every placeholder figure it leans on:
an UNCONFIRMED figure is printed, never trusted silently and never a failure
on its own.

The box is sized for one kit (``layout.DESIGN_MONITOR``, ``DESIGN_BANK``, both
board revisions), so the proofs are about that kit.  ``monitor_fit_report``
and ``bank_fit_report`` say which of the other listed parts would also fit;
they are information, never a failure.

Where a figure can be reached two ways, the proof takes the way ``layout.py``
did not: hole and plug positions come from ``board_origin`` and the part data
rather than from the keep-outs; the closed monitor face from the lid depth
and the monitor's own depth rather than from ``monitor_space``; the lid's
swing is rotated here independently (``lid_point_open``) and compared with
``Layout.lid_profile_yz``; the size budget is recomputed from the part data.

Cable routes (``pigtail_path``, ``usb_path``) are polylines in the base frame.
A route's length is bounded above by summing each leg's |dx| + |dy| + |dz|;
its bends are checked by ``max_bend_r``, the largest radius of arc that can
round every counted corner of the polyline without two arcs overlapping.
"""

from __future__ import annotations

import math

import demobox  # noqa: F401  (puts the submodule on sys.path)
from shapely.geometry import Point, box as sbox

from demobox import layout as L
from demobox.geom import Box, overlaps
from demobox.layout import FINGERTIP_D, SLACK, Layout, exit_edge, tinyvga_offset
from demobox.parts import board as board_mod
from demobox.parts.batteries import BATTERIES
from demobox.parts.board import BOARD_KEYS, board_spec
from demobox.parts.cables import CABLES
from demobox.parts.monitors import MONITORS
from demobox.parts.tinyvga import TINYVGA

#: Floating point slack on equalities between derived figures.
EPS = 1e-6
#: Overlap area (mm^2) below which two YZ profiles only touch.  The closed lid
#: rests on the base, so their profiles share an edge: the intersection has
#: zero area (a line), which is contact, not a collision.  1e-6 mm^2 is far
#: below any real interference and far above floating-point noise.
AREA_TOL = 1e-6
#: The lid catch's magnets may be this far apart with the lid shut (R22).
CATCH_MAX_GAP = 1.0
#: The bank-to-board USB cable: the longest this box asks for (a short
#: right-angle cable; the spec's "USB: short right-angle cables").
USB_MAX_LEN = 300.0
#: Closed, the pins stay at least this deep in the PCB holes however far the
#: board can lift (``layout.PIN_PROUD`` is sized for it).
PIN_ENGAGE = 1.0
#: The size budget's tolerance on each dimension against its formula.
SIZE_TOL = 0.01

PIGTAIL = CABLES["monitor-pigtail"]   # the monitor's own VGA cable (ruling R13)
BOOST = CABLES["usb-12v-boost"]


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


def _xy_overlap(a: Box, b: Box) -> bool:
    return min(a.x1, b.x1) - max(a.x0, b.x0) > EPS and min(a.y1, b.y1) - max(a.y0, b.y0) > EPS


# --- frames and paths ---------------------------------------------------------------

def lid_point_open(lay: Layout, y: float, z: float, angle_deg: float) -> tuple[float, float]:
    """Lid-frame (y, z) to base-frame (Y, Z) at ``angle_deg`` open, worked
    here from the frame definitions (a turn about the hinge axis lifting the
    front edge, -Y, up and over), independently of ``Layout._open_yz``."""
    hy, hz = lay.hinge_axis
    t = math.radians(angle_deg)
    return (hy + y * math.cos(t) + z * math.sin(t),
            hz - y * math.sin(t) + z * math.cos(t))


def _lid_to_base(lay: Layout, p, angle_deg: float) -> tuple[float, float, float]:
    y, z = lid_point_open(lay, p[1], p[2], angle_deg)
    return (p[0], y, z)


def _to_base(lay: Layout, bx: float, by: float, bz: float) -> tuple[float, float, float]:
    """Board frame to base frame: base = (ox - by, oy + bx, oz + bz)."""
    ox, oy, oz = lay.board_origin
    return (ox - by, oy + bx, oz + bz)


def path_length(pts) -> float:
    """The polyline's own length (sum of straight legs)."""
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def manhattan_length(pts) -> float:
    """An upper bound on any smooth route through the same points: each leg
    counted as |dx| + |dy| + |dz|."""
    return sum(sum(abs(p - q) for p, q in zip(a, b)) for a, b in zip(pts, pts[1:]))


def _turn(a, b, c) -> float:
    """The turn (radians) a polyline makes at ``b``: 0 straight on, pi back."""
    u = [q - p for p, q in zip(a, b)]
    v = [q - p for p, q in zip(b, c)]
    nu, nv = math.hypot(*u), math.hypot(*v)
    cos = sum(p * q for p, q in zip(u, v)) / (nu * nv)
    return math.acos(max(-1.0, min(1.0, cos)))


def max_bend_r(pts, stiff_last: bool = False) -> float:
    """The largest radius every interior corner of the polyline can be rounded
    to.  An arc of radius r round a corner turning by phi starts and ends
    r * tan(phi / 2) from the corner, along each leg; the two arcs at a leg's
    ends must not overlap, so each leg bounds r by its length over the sum of
    its ends' tan(phi / 2).  inf for a straight line.  A point the polyline
    passes straight through is no corner and is dropped first.  With
    ``stiff_last`` the last leg can't bend (a plug's stiff run): the cable
    must meet it in line, else no radius will do (0)."""
    if stiff_last and len(pts) > 2:
        if _turn(*pts[-3:]) > 1e-9:
            return 0.0
        pts = pts[:-1]          # met in line: the cable ends straight at the stiff leg
    pts = [pts[0]] + [b for a, b, c in zip(pts, pts[1:], pts[2:]) if _turn(a, b, c) > 1e-9] \
        + [pts[-1]]
    k = [0.0] + [math.tan(_turn(a, b, c) / 2) for a, b, c in zip(pts, pts[1:], pts[2:])] + [0.0]
    r = math.inf
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        s = k[i] + k[i + 1]
        if s > EPS:
            r = min(r, math.dist(a, b) / s)
    return r


#: R16a: the left/right-angle 90 degree VGA adapter (its figures, assumed
#: orientation in its Source).
ADAPTER = CABLES["vga-90-adapter"]


def _plug_frame() -> tuple[float, float, float, float]:
    """The monitor's VGA plug in the adapter, TinyVGA frame, from the part data
    (not the keep-outs): ``(socket face x, axis y, axis z, hood width)``.  The
    adapter (``ADAPTER.plug`` = 35 along the D-sub's long axis, 17 out of the
    DE-15 face) has its socket on its +x end; the plug goes in along -x."""
    span, out, _ = ADAPTER.plug
    d = TINYVGA.de15
    return ((d.x0 + d.x1) / 2 + span / 2, d.y0 - out / 2,
            (TINYVGA.plug_z0 + TINYVGA.plug_z1) / 2, TINYVGA.plug_width)


def _plug_ends(lay: Layout, rev: str):
    """The monitor's VGA plug, base frame, on its axis: ``(cable end of the
    stiff run, back of the plug body, plug face in the adapter's socket)``.
    The run (``STRAIGHT_RUN``) and the body (``PLUG_BODY_LEN``) head +Y into
    the bank row's +X back corner."""
    sx, ay, az, _ = _plug_frame()
    dx, dy, dz = tinyvga_offset(rev)
    t = TINYVGA
    face = _to_base(lay, sx + dx, ay + dy, az + dz)
    back = _to_base(lay, sx + t.plug_body_len + dx, ay + dy, az + dz)
    end = _to_base(lay, sx + t.plug_body_len + t.straight_run + dx, ay + dy, az + dz)
    return end, back, face


def vga_plug_box(lay: Layout, rev: str) -> Box:
    """The plug + stiff run keep-out, base frame, from the part data."""
    end, _, face = _plug_ends(lay, rev)
    w = _plug_frame()[3]
    return Box(face[0] - w / 2, face[1], TINYVGA.plug_z0 + lay.board_origin[2],
               face[0] + w / 2, end[1], TINYVGA.plug_z1 + lay.board_origin[2],
               f"{rev} VGA plug + stiff run")


def pigtail_exit(lay: Layout) -> tuple[float, float, float]:
    """Where the monitor's cable leaves its panel (lid frame, closed): on the
    cable edge (the hinge side of the panel), ``pigtail_exit_u`` from the
    panel's left, half-way through the panel's depth."""
    m = MONITORS[L.DESIGN_MONITOR]
    ms = lay.monitor_space
    return (ms.x0 + SLACK + m.pigtail_exit_u, ms.y1 - SLACK, (ms.z0 + ms.z1) / 2)


def _lid_from_base(lay: Layout, p, angle_deg: float) -> tuple[float, float, float]:
    """Base-frame point to the lid frame at ``angle_deg`` (``lid_point_open``
    inverted)."""
    hy, hz = lay.hinge_axis
    t = math.radians(angle_deg)
    y, z = p[1] - hy, p[2] - hz
    return (p[0], y * math.cos(t) - z * math.sin(t), y * math.sin(t) + z * math.cos(t))


#: Heights above the seam (mm, cable centre) of the points straight over the
#: pigtail's drop that a route through them is tried at.
PIGTAIL_OVER_DROP = tuple(2.5 * i for i in range(1, 25))


#: R18: the pigtail's centre keeps this far from the hinge axis: cable radius
#: + the full-width hinge rod's radius + FIT.
ROD_CLEAR = PIGTAIL.dia / 2 + L.PIN_ROD_D / 2 + L.FIT


def _drop_xy(lay: Layout, rev: str) -> tuple[float, float]:
    """Where the pigtail goes down to the plug: straight over the plug's run
    axis, ``ROD_CLEAR`` in front of the hinge axis (the rod is full width, and
    the axis is only ``KNUCKLE_R`` from the back face, so the cable can't
    pass behind it)."""
    end = _plug_ends(lay, rev)[0]
    return end[0], lay.hinge_axis[0] - ROD_CLEAR


def rod_distance(lay: Layout, pts) -> float:
    """The least YZ distance of a base-frame polyline from the hinge axis
    (the rod runs the full width, so X doesn't matter)."""
    hy, hz = lay.hinge_axis
    best = math.inf
    for (_, ay, az), (_, by, bz) in zip(pts, pts[1:]):
        dy, dz = by - ay, bz - az
        n = dy * dy + dz * dz
        t = 0.0 if n == 0 else max(0.0, min(1.0, ((hy - ay) * dy + (hz - az) * dz) / n))
        best = min(best, math.hypot(ay + t * dy - hy, az + t * dz - hz))
    return best


def _in_free_room(lay: Layout, p_lid, angle_deg: float) -> bool:
    """A lid-frame point the pigtail may pass: in the lid strip, or (lid
    open) out past the lid's open face and above the rim, in free air."""
    r = PIGTAIL.dia / 2
    s = lay.lid_strip
    x, y, z = p_lid
    if not (s.x0 + r <= x <= s.x1 - r and y <= s.y1 - r):
        return False
    if r <= z <= s.z1 - r:
        return True
    return z < 0.0 and _lid_to_base(lay, p_lid, angle_deg)[2] >= lay.rim_z + r


def _pigtail_routes(lay: Layout, rev: str, angle_deg: float):
    """Candidate pigtail routes at ``angle_deg``: ``(lid points, lid frame;
    base points, base frame)`` (see ``pigtail_path``)."""
    r = PIGTAIL.dia / 2
    ex = pigtail_exit(lay)
    hz = lay.hinge_axis[1]
    x, yd = _drop_xy(lay, rev)
    end, back, face = _plug_ends(lay, rev)
    tail = [(x, yd, hz), (x, yd, end[2]), end, back, face]
    yield [ex], tail
    for d in PIGTAIL_OVER_DROP + (lay.lid_strip.z1 - r,):
        v = (x, yd, hz + d)
        vl = _lid_from_base(lay, v, angle_deg)
        if not _in_free_room(lay, vl, angle_deg):
            continue
        yield [ex], [v] + tail
        w = (x, ex[1] + (vl[1] - ex[1]) / 4, vl[2])        # level with it, a quarter along
        if ex[1] < vl[1] and _in_free_room(lay, w, angle_deg):
            yield [ex, w], [v] + tail


def _pigtail_best(lay: Layout, angle_deg: float, rev: str):
    """The candidate route with the widest bends at ``angle_deg``:
    ``(lid points, base points, base-frame path)``."""
    best = None
    for lid, base in _pigtail_routes(lay, rev, angle_deg):
        path = [_lid_to_base(lay, p, angle_deg) for p in lid] + base
        # a route through the hinge rod ranks below every route clear of it
        key = (rod_distance(lay, path) >= ROD_CLEAR - EPS,
               max_bend_r(path[:-1], stiff_last=True))
        if best is None or key[0] > best[0][0] or (key[0] == best[0][0]
                                                   and key[1] > best[0][1] + EPS):
            best = (key, lid, base, path)
    return best[1:]


def pigtail_path(lay: Layout, angle_deg: float,
                 rev: str = BOARD_KEYS[0]) -> list[tuple[float, float, float]]:
    """The monitor's VGA pigtail with the lid ``angle_deg`` open, base frame:

    * the exit on the panel's cable edge (in the lid);
    * along ``lid_strip`` towards the hinge, either straight to the notch or
      to a point straight over the drop (closed: up at the lid's inside face;
      open: wherever over the drop is still in the strip or in the free air
      past the lid's open face), perhaps through a point level with it a
      quarter of the way along;
    * through ``hinge_notch`` at the seam, on the VGA plug's run axis, as
      far back as the back wall allows;
    * down to the run's height and forward (-Y) into the end of the plug's
      stiff run (R16a: the plug sits in the bank row's +X back corner);
    * along the stiff run and the plug body to the plug's face in the
      adapter's socket.

    The cable is free in the lid strip, so at each angle the route taken is
    the one whose bends round widest (``max_bend_r``, every bend after the
    stiff run; the run itself is stiff).  Closed, the widest is a U-turn from
    the lid's inside face to the run's height, in the plane over the run."""
    return _pigtail_best(lay, angle_deg, rev)[2]


def pigtail_length_bound(lay: Layout, angle_deg: float, rev: str = BOARD_KEYS[0]) -> float:
    """An upper bound on the cable ``pigtail_path`` needs at ``angle_deg``:
    |dx| + |dy| + |dz| per leg, the lid legs measured in the lid frame (where
    they are rigid) up to the first base point, the rest in the base frame."""
    lid, base, _ = _pigtail_best(lay, angle_deg, rev)
    return manhattan_length(lid + [_lid_from_base(lay, base[0], angle_deg)]) \
        + manhattan_length(base)


def usb_path(lay: Layout, rev: str) -> list[tuple[float, float, float]]:
    """The bank-to-board USB cable, base frame, from the bank's port to J1:

    0. the bank's port, on its end face at the port room (centred on it);
    1. across the port room to the left wall, SLACK off it, at the plug's
       height;
    2. forward along the wall, 1.25 bend radii;
    3. a shallow jog to the plug's X (none when it is in line), one cable
       diameter behind the plug;
    4. into the right-angle plug's far end, whose cable leaves towards the
       bank row (the builder turns the plug that way: the shortest run);
    5. along the plug to J1.

    The legs 0..4 are cable; 4..5 is the plug."""
    b = BATTERIES[L.DESIGN_BANK]
    c = usb_cable()
    bay, k = lay.bank_bay, lay.board_keepouts[f"{rev}/usb_plug"]
    port = (bay.x0 + SLACK, bay.y0 + SLACK + b.size[1] / 2, bay.z0 + b.size[2] / 2)
    zc = (k.z0 + k.z1) / 2
    xw = lay.port_room.x0 + SLACK + c.dia / 2
    exit_ = (k.x0 + c.dia / 2, k.y1, zc)
    return [port, (xw, port[1], zc), (xw, port[1] - 1.25 * c.min_bend_r, zc),
            (exit_[0], exit_[1] + c.dia, zc), exit_, (k.x1, (k.y0 + k.y1) / 2, zc)]


def usb_cable():
    """The design bank's cable to the board: its own built-in cable, or the
    box's right-angle USB-C cable in its socket."""
    b = BATTERIES[L.DESIGN_BANK]
    return CABLES["bank-built-in" if b.cable == "built-in" else "usb-c-right-angle"]


# --- fit reports (information, never a failure) --------------------------------------

def monitor_fit_report(lay: Layout) -> list[tuple[str, bool, str]]:
    """``(key, fits, detail)`` for every listed monitor: its panel within
    ``monitor_space`` less SLACK a side in W and H, and within its depth."""
    ms = lay.monitor_space
    aw, ah, ad = ms.size[0] - 2 * SLACK, ms.size[1] - 2 * SLACK, ms.size[2]
    out = []
    for m in MONITORS.values():
        w, h, d = m.panel
        ok = w <= aw + EPS and h <= ah + EPS and d <= ad + EPS
        out.append((m.key, ok, f"panel {_f(w)} x {_f(h)} x {_f(d)} in {_f(aw)} x {_f(ah)} x "
                    f"{_f(ad)}; cable leaves its {exit_edge(m)} edge"))
    return out


def bank_fit_report(lay: Layout) -> list[tuple[str, bool, str]]:
    """``(key, fits, detail)`` for every listed bank: within ``bank_bay`` less
    SLACK a side in L and W, and SLACK under the rim."""
    bay = lay.bank_bay
    al, aw, ah = bay.size[0] - 2 * SLACK, bay.size[1] - 2 * SLACK, bay.size[2] - SLACK
    out = []
    for b in BATTERIES.values():
        l_, w, h = b.size
        ok = l_ <= al + EPS and w <= aw + EPS and h <= ah + EPS
        out.append((b.key, ok, f"bank {_f(l_)} x {_f(w)} x {_f(h)} in {_f(al)} x {_f(aw)} x "
                    f"{_f(ah)}"))
    return out


# --- the proofs ------------------------------------------------------------------

def kit_fits(report: Report, lay: Layout) -> None:
    """The design monitor in ``monitor_space`` and the design bank in
    ``bank_bay``, each with SLACK."""
    m = MONITORS[L.DESIGN_MONITOR]
    if not m.confirmed:
        report.unconfirmed(f"monitor {m.key}", _placeholders(m.sources))
    ms = lay.monitor_space
    w, h, d = m.panel
    room = (ms.size[0] - w, ms.size[1] - h, ms.size[2] - d)
    report.check(room[0] >= 2 * SLACK - EPS and room[1] >= 2 * SLACK - EPS and room[2] >= -EPS,
                 f"{m.key}: panel in the monitor space with SLACK",
                 f"panel {_f(w)} x {_f(h)} x {_f(d)} in {_f(ms.size[0])} x {_f(ms.size[1])} x "
                 f"{_f(ms.size[2])}: {_f(room[0] / 2)}, {_f(room[1] / 2)} a side >= {SLACK}, "
                 f"depth {_f(room[2])} to spare")

    b = BATTERIES[L.DESIGN_BANK]
    if not b.confirmed:
        report.unconfirmed(f"battery {b.key}", _placeholders(b.sources))
    bay = lay.bank_bay
    l_, w, h = b.size
    room = (bay.size[0] - l_, bay.size[1] - w, bay.size[2] - h)
    report.check(room[0] >= 2 * SLACK - EPS and room[1] >= 2 * SLACK - EPS
                 and room[2] >= SLACK - EPS,
                 f"{b.key}: bank in the bank bay with SLACK",
                 f"bank {_f(l_)} x {_f(w)} x {_f(h)} in {_f(bay.size[0])} x {_f(bay.size[1])} x "
                 f"{_f(bay.size[2])}: {_f(room[0] / 2)}, {_f(room[1] / 2)} a side, "
                 f"{_f(room[2])} under the rim >= {SLACK}")


def _pcb_base(lay: Layout, rev: str) -> Box:
    ol = board_spec(rev).outline
    x0, y0, z0 = _to_base(lay, 0.0, ol.height, 0.0)
    x1, y1, z1 = _to_base(lay, ol.width, 0.0, ol.thickness)
    return Box(x0, y0, z0, x1, y1, z1, f"{rev} PCB")


def boards_seat(report: Report, lay: Layout) -> None:
    """Both revisions on the plinth, inside the walls, each pin in its PCB
    hole and its plinth hole, and nothing in the base overlapping anything
    else (the plinth only where its relief takes the J1 plug)."""
    for name, value, src in L.UNCONFIRMED:
        report.unconfirmed(name, f"{value}: {src.note}")
    if not TINYVGA.confirmed:
        report.unconfirmed("TinyVGA heights", _placeholders(TINYVGA.sources))
    o, w, pl = lay.outer, lay.wall, lay.plinth
    base_row = {"bank bay": lay.bank_bay, "port room": lay.port_room}
    if not lay.boost_in_lid:
        base_row["boost pocket"] = lay.boost_pocket
    for i, c in enumerate(lay.lid_catch, 1):
        base_row[f"lid catch block {i}"] = lay.catch_base_block(c)

    for k in BOARD_KEYS:
        spec = board_spec(k)
        pcb = _pcb_base(lay, k)
        on = (abs(pcb.z0 - pl.z1) <= EPS and pcb.x0 >= pl.x0 - EPS and pcb.x1 <= pl.x1 + EPS
              and pcb.y0 >= pl.y0 - EPS and pcb.y1 <= pl.y1 + EPS)
        report.check(on, f"{k}: PCB on the plinth",
                     f"PCB {_f(pcb.x0)}..{_f(pcb.x1)} x {_f(pcb.y0)}..{_f(pcb.y1)}, underside z "
                     f"{_f(pcb.z0)}; plinth {_f(pl.x0)}..{_f(pl.x1)} x {_f(pl.y0)}..{_f(pl.y1)}, "
                     f"top z {_f(pl.z1)}")
        parts = {key.split("/", 1)[1]: b for key, b in lay.board_keepouts.items()
                 if key.startswith(f"{k}/")}
        for p, b in parts.items():
            inside = (b.x0 >= o.x0 + w - EPS and b.x1 <= o.x1 - w + EPS and b.y0 >= o.y0 + w - EPS
                      and b.y1 <= o.y1 - w + EPS and b.z0 >= w - EPS and b.z1 <= lay.rim_z + EPS)
            report.check(inside, f"{k}: {p} inside the walls, floor and rim",
                         f"{_f(b.x0)}..{_f(b.x1)} x {_f(b.y0)}..{_f(b.y1)} x {_f(b.z0)}..{_f(b.z1)} "
                         f"in the {_f(o.size[0])} x {_f(o.size[1])} x {_f(lay.rim_z)} base, "
                         f"wall {w}")
            hits = [n for n, x in base_row.items() if overlaps(b, x, EPS)]
            cut = Box(max(b.x0, pl.x0), max(b.y0, pl.y0), max(b.z0, pl.z0),
                      min(b.x1, pl.x1), min(b.y1, pl.y1), min(b.z1, pl.z1)) \
                if overlaps(b, pl, EPS) else None
            r = lay.plinth_relief
            if cut is not None and not (cut.x0 >= r.x0 - EPS and cut.x1 <= r.x1 + EPS
                                        and cut.y0 >= r.y0 - EPS and cut.y1 <= r.y1 + EPS
                                        and cut.z0 >= r.z0 - EPS):
                hits.append("plinth (outside its relief)")
            report.check(not hits, f"{k}: {p} overlaps nothing in the base",
                         "clear of " + ", ".join(list(base_row) + ["plinth"])
                         if not hits else "overlaps " + ", ".join(hits))

        holes = {h.label: h for h in spec.holes}
        top = pcb.z1
        for label, key in (("MT2", "MT2"), ("MT1", f"{k}/MT1")):
            h, pin = holes[label], lay.pins[key]
            hx, hy, _ = _to_base(lay, h.x, h.y, 0.0)
            off = math.dist((pin.cx, pin.cy), (hx, hy))
            ok = (off + pin.r <= h.dia / 2 + EPS and h.dia > L.PEG_DIA and L.PEG_HOLE_D > L.PEG_DIA
                  and abs(2 * pin.r - L.PEG_DIA) <= EPS and abs(pin.z0 - pl.z1) <= EPS
                  and pin.z1 > top + EPS)
            report.check(ok, f"{k}: {pin.what} in its {label} hole",
                         f"{_f(2 * pin.r)} pin {_f(off)} off the {h.dia} hole's centre (room "
                         f"{_f(h.dia / 2 - pin.r)}); plinth hole {L.PEG_HOLE_D} > pin {L.PEG_DIA}; "
                         f"pin z {_f(pin.z0)}..{_f(pin.z1)}, plinth top {_f(pl.z1)}, PCB top "
                         f"{_f(top)}")
            r = lay.plinth_relief
            hole = Point(pin.cx, pin.cy).buffer(L.PEG_HOLE_D / 2)
            in_plinth = hole.within(sbox(pl.x0, pl.y0, pl.x1, pl.y1)) and \
                not hole.intersects(sbox(r.x0, r.y0, r.x1, r.y1))
            report.check(in_plinth, f"{k}: {pin.what} hole whole in the plinth",
                         f"{L.PEG_HOLE_D} hole at ({_f(pin.cx)}, {_f(pin.cy)}) inside the plinth "
                         f"and clear of its relief")

    rows = list(base_row.items())
    hits = [f"{a} / {b}" for i, (a, x) in enumerate(rows) for b, y in rows[i + 1:]
            if overlaps(x, y, EPS)]
    report.check(not hits, "bank row and catch blocks overlap nothing else",
                 "overlaps " + ", ".join(hits) if hits else
                 ", ".join(n for n, _ in rows) + " clear of each other")


def packed_bank(lay: Layout) -> Box:
    """The design bank as packed: on the bay floor, centred in the bay in X
    and Y (SLACK each side), base frame."""
    b, bay = BATTERIES[L.DESIGN_BANK], lay.bank_bay
    l_, w, h = b.size
    x0, y0 = (bay.x0 + bay.x1 - l_) / 2, (bay.y0 + bay.y1 - w) / 2
    return Box(x0, y0, bay.z0, x0 + l_, y0 + w, bay.z0 + h, f"bank {b.key}")


def bank_lifts_out(report: Report, lay: Layout) -> None:
    """R12: with the lid at LID_OPEN_DEG nothing (the lid included) is over
    the design bank's own footprint, as packed in the bay, above the rim: the
    bank lifts straight out.  (The swinging lid against the bank, and every
    other base content, is ``hinge_sweep``'s.)"""
    bank, a = packed_bank(lay), L.LID_OPEN_DEG
    lid, rim = lay.lid_outer, lay.rim_z
    big = 10 * (lid.size[1] + lid.size[2] + lay.outer.size[1])
    prof = lay.lid_profile_yz(a)
    over = prof.intersection(sbox(bank.y0, rim, bank.y1, rim + big)).area
    above = prof.intersection(sbox(-big, rim, big, rim + big))
    clearance = above.bounds[0] - bank.y1 if not above.is_empty else math.inf
    report.check(over <= AREA_TOL and clearance >= -EPS,
                 f"{bank.what} in the bank bay: clear of the lid at {a:g} deg",
                 f"bank footprint Y {_f(bank.y0)}..{_f(bank.y1)} (centred in the bay); the lid "
                 f"above the rim starts at Y {_f(above.bounds[0])}: clearance {_f(clearance)} mm, "
                 f"overlap {over:.3g} mm^2")

    things = dict(lay.board_keepouts)
    things.update({p.what: Box(p.cx - p.r, p.cy - p.r, p.z0, p.cx + p.r, p.cy + p.r, p.z1, p.what)
                   for p in lay.pins.values()})
    things.update({"plinth": lay.plinth, "port room": lay.port_room})
    if not lay.boost_in_lid:
        things["boost pocket"] = lay.boost_pocket
    hits = [n for n, b in things.items() if b.z1 > rim + EPS and _xy_overlap(b, bank)]
    report.check(not hits, f"{bank.what} in the bank bay: nothing in the base over it",
                 "over it: " + ", ".join(hits) if hits else
                 f"{len(things)} parts checked; none over the bank above z {_f(rim)}")


def button_reachable(report: Report, lay: Layout) -> None:
    """The design bank's button is at the port room end, and the port room
    takes a fingertip on it."""
    b = BATTERIES[L.DESIGN_BANK]
    pr, bay = lay.port_room, lay.bank_bay
    if b.button is None:
        report.check(True, f"{b.key}: no button to reach", "the bank has no power button")
        return
    face, u, v = b.button
    if face == "top":
        report.check(True, f"{b.key}: top-face button reachable with the lid open",
                     "nothing over the bay above the rim (bank_lifts_out)")
        return
    if face != "end":
        report.check(False, f"{b.key}: button reachable",
                     f"a {face}-face button faces the bay wall")
        return
    r = FINGERTIP_D / 2
    y, z = bay.y0 + SLACK + u, bay.z0 + v
    at_end = abs(pr.x1 - bay.x0) <= EPS and pr.y0 <= y - r + EPS and y + r <= pr.y1 + EPS \
        and pr.z0 <= z - r + EPS and z + r <= pr.z1 + EPS
    report.check(at_end, f"{b.key}: end button faces the port room",
                 f"button (y {_f(y)}, z {_f(z)}) on the bank end at x {_f(bay.x0)}; port room "
                 f"x {_f(pr.x0)}..{_f(pr.x1)}, y {_f(pr.y0)}..{_f(pr.y1)}, z {_f(pr.z0)}.."
                 f"{_f(pr.z1)} round a {FINGERTIP_D:g} mm fingertip")
    report.check(pr.size[0] >= FINGERTIP_D - EPS, f"{b.key}: port room takes a fingertip",
                 f"port room {_f(pr.size[0])} mm long >= FINGERTIP_D {FINGERTIP_D:g}")


def _panel_base_xy(lay: Layout) -> Box:
    """The closed monitor panel's footprint, base frame."""
    ms, hy = lay.monitor_space, lay.hinge_axis[0]
    return Box(ms.x0 + SLACK, ms.y0 + SLACK + hy, 0.0, ms.x1 - SLACK, ms.y1 - SLACK + hy, 0.0,
               "monitor panel")


def lid_closed_clears(report: Report, lay: Layout) -> None:
    """Closed, the monitor face is CLOSED_CLEARANCE above everything in the
    base; and the board can't lift off its pins, since its tallest part lies
    under the monitor panel, which stops it.  The face is worked from the lid
    depth and the monitor's own depth, not from ``monitor_space``; the
    tallest component is read live from the board data."""
    if not board_mod.TALLEST_COMPONENT_CONFIRMED:
        report.unconfirmed("TALLEST_COMPONENT", f"{board_mod.TALLEST_COMPONENT} mm: "
                           f"{board_mod.TALLEST_COMPONENT_SOURCE.note}")
    m = MONITORS[L.DESIGN_MONITOR]
    hz = lay.hinge_axis[1]
    face = hz + lay.lid_outer.z1 - lay.wall - L.TAPE_T - m.panel[2]
    need = L.CLOSED_CLEARANCE
    tops: dict[str, float] = {}
    for k in BOARD_KEYS:
        for key, b in lay.board_keepouts.items():
            if key.startswith(f"{k}/"):
                tops[f"{k} {key.split('/', 1)[1]}"] = b.z1
        tops[f"{k} tallest component"] = lay.board_origin[2] + board_mod.TALLEST_COMPONENT
    for p in lay.pins.values():
        tops[p.what] = p.z1
    b = BATTERIES[L.DESIGN_BANK]
    tops[f"bank {b.key}"] = lay.bank_bay.z0 + b.size[2]
    if not lay.boost_in_lid:
        tops["boost module"] = lay.boost_pocket.z0 + BOOST.plug[2]
    for n, t in tops.items():
        report.check(face - t >= need - EPS and t <= lay.rim_z + EPS,
                     f"monitor face clears the {n}",
                     f"face z {_f(face)} (seam {_f(hz)} + lid {_f(lay.lid_outer.z1)} - wall "
                     f"{lay.wall} - tape {L.TAPE_T} - monitor {m.panel[2]}), top {_f(t)}: "
                     f"{_f(face - t)} >= {need}; under the rim {_f(lay.rim_z)}")
    if lay.boost_in_lid:
        low = hz + lay.boost_pocket.z0
        top = max(tops.values())
        report.check(low - top >= need - EPS, "boost module in the lid clears the base",
                     f"underside z {_f(low)}, tallest in the base {_f(top)}")

    panel = _panel_base_xy(lay)
    for k in BOARD_KEYS:
        parts = [b for key, b in lay.board_keepouts.items() if key.startswith(f"{k}/")]
        tall = max(parts, key=lambda x: x.z1)
        lift = face - tall.z1
        pcb_top = _pcb_base(lay, k).z1
        pin = min(lay.pins["MT2"].z1, lay.pins[f"{k}/MT1"].z1) - pcb_top
        under = _xy_overlap(tall, panel)
        report.check(under and lift <= pin - PIN_ENGAGE + EPS,
                     f"{k}: board can't lift off its pins (tallest part under the monitor)",
                     f"{tall.what} (top {_f(tall.z1)}) "
                     + ("under" if under else "NOT under")
                     + f" the panel X {_f(panel.x0)}..{_f(panel.x1)}, Y {_f(panel.y0)}.."
                     f"{_f(panel.y1)}: lift {_f(lift)} <= pins {_f(pin)} proud - "
                     f"{PIN_ENGAGE} engaged")


def sweep_angles() -> list[float]:
    """Every whole degree from 0 to LID_OPEN_DEG, and the stop itself (the
    angles ``layout`` sizes ``hinge_relief_r`` over)."""
    return L.sweep_angles()


def _x_overlaps(b: Box, ranges) -> bool:
    return any(min(b.x1, x1) - max(b.x0, x0) > EPS for x0, x1 in ranges)


def _open_x(lay: Layout) -> list[tuple[float, float]]:
    """X 0..width less ``knuckle_x``: the open segments."""
    out, x = [], lay.outer.x0
    for a, b in sorted(lay.knuckle_x):
        if a > x + EPS:
            out.append((x, a))
        x = max(x, b)
    if x < lay.outer.x1 - EPS:
        out.append((x, lay.outer.x1))
    return out


def hinge_sweep(report: Report, lay: Layout) -> None:
    """R15: along X the hinge has knuckle segments (only inside
    ``knuckle_x``) and open segments (everywhere else).

    * ``knuckle_x`` holds no base content within ``hinge_relief_r`` of the
      axis in YZ (a lid knuckle's whole lid, or a base knuckle, sweeps
      there), and at least two ranges of ``KNUCKLE_LEN``.
    * At every angle from closed to LID_OPEN_DEG, inside ``knuckle_x`` the
      whole lid misses every base content there.
    * In open segments, the lid cut back to ``hinge_relief_r`` misses every
      base content there, and the base's walls cut back the same.

    Closed, the lid rests on the base: contact (below AREA_TOL), not a
    collision.  The profile turns about the hinge axis (checked against an
    independent rotation) and the sweep ends at LID_OPEN_DEG.  The physical
    stop is the hinge's (Task 4's tests and the solid sweep)."""
    lid, o = lay.lid_outer, lay.outer
    hy, hz = lay.hinge_axis
    rr = lay.hinge_relief_r
    relief = Point(hy, hz).buffer(rr, quad_segs=64)
    walls = sbox(o.y0, o.z0, o.y1, o.z1).difference(relief)
    knuckles, opens = list(lay.knuckle_x), _open_x(lay)
    contents = L.base_contents(lay)

    near = {n: b for n, b in contents.items()
            if math.hypot(max(b.y0 - hy, 0.0, hy - b.y1), max(b.z0 - hz, 0.0, hz - b.z1)) <= rr}
    under = sorted(n for n, b in near.items() if _x_overlaps(b, knuckles))
    report.check(not under, "knuckle_x: no base content within the hinge relief of the axis",
                 (f"within r {_f(rr)} of the axis and under a knuckle: {', '.join(under)}"
                  if under else f"within r {_f(rr)} of the axis: "
                  + (", ".join(f"{n} (X {_f(b.x0)}..{_f(b.x1)})" for n, b in sorted(near.items()))
                     or "nothing") + "; all in open segments"))
    long_ = [(a, b) for a, b in knuckles if b - a >= L.KNUCKLE_LEN - EPS]
    report.check(len(long_) >= 2, f"knuckle_x: at least 2 ranges of KNUCKLE_LEN {L.KNUCKLE_LEN:g}",
                 f"{len(long_)} long enough of " + ", ".join(f"{_f(a)}..{_f(b)}" for a, b in knuckles))

    corners = ((lid.y0, lid.z0), (lid.y1, lid.z0), (lid.y1, lid.z1), (lid.y0, lid.z1))
    in_k = {n: sbox(b.y0, b.z0, b.y1, b.z1) for n, b in contents.items() if _x_overlaps(b, knuckles)}
    in_o = {n: sbox(b.y0, b.z0, b.y1, b.z1) for n, b in contents.items() if _x_overlaps(b, opens)}
    angles = sweep_angles()
    drift = 0.0
    worst = {"knuckle": (0.0, 0.0, ""), "open": (0.0, 0.0, "")}
    for a in angles:
        prof = lay.lid_profile_yz(a)
        drift = max(drift, max(prof.exterior.distance(Point(lid_point_open(lay, y, z, a)))
                               for y, z in corners))
        cut = prof.difference(relief)
        for kind, shape, things in (("knuckle", prof, in_k),
                                    ("open", cut, {**in_o, "base walls": walls})):
            for n, t in things.items():
                area = shape.intersection(t).area
                if area > worst[kind][0]:
                    worst[kind] = (area, a, n)
    report.check(drift <= EPS, "lid profile turns about the hinge axis",
                 f"lid_profile_yz agrees with an independent rotation to {drift:.2g} mm "
                 f"over {len(angles)} angles")
    report.check(angles[-1] == L.LID_OPEN_DEG and max(angles) == L.LID_OPEN_DEG
                 and angles[0] == 0.0,
                 f"lid sweep runs 0..{L.LID_OPEN_DEG:g} deg (LID_OPEN_DEG)",
                 f"{len(angles)} angles, {angles[0]:g} to {angles[-1]:g}")
    for kind, what, n_things in (
            ("knuckle", "knuckle segments: whole lid misses every base content in knuckle_x",
             len(in_k)),
            ("open", "open segments: lid cut back to the hinge relief misses every base "
                     "content and the cut base walls", len(in_o) + 1)):
        area, a, n = worst[kind]
        report.check(area <= AREA_TOL, what,
                     f"{n_things} parts, {len(angles)} angles; largest YZ overlap {area:.3g} mm^2"
                     + (f" ({n} at {a:g} deg)" if area > 0 else "")
                     + f"; hinge relief r {_f(rr)} (contact below {AREA_TOL:g} mm^2 is not a "
                     "collision)")


def cables_route(report: Report, lay: Layout) -> None:
    """The monitor's pigtail from its exit, along the lid strip, through the
    hinge notch, down and into the VGA plug's stiff run in the bank row's +X
    back corner: within its length, clear of everything in the base, and
    every bend after the stiff run at least its bend radius, closed and at
    every sweep angle.  The bank-to-board USB cable: within USB_MAX_LEN,
    every bend at least its radius.  (Routes and the bend rule:
    ``pigtail_path``, ``usb_path``, ``max_bend_r``.)"""
    for c in CABLES.values():
        if not c.confirmed:
            report.unconfirmed(f"cable {c.key}", _placeholders(c.sources))
    m = MONITORS[L.DESIGN_MONITOR]
    r = PIGTAIL.dia / 2
    ms, n, strip = lay.monitor_space, lay.hinge_notch, lay.lid_strip
    ex = pigtail_exit(lay)
    hy, hz = lay.hinge_axis
    o, w = lay.outer, lay.wall
    on_edge = ms.x0 + SLACK <= ex[0] <= ms.x1 - SLACK and abs(ex[1] - (ms.y1 - SLACK)) <= EPS
    report.check(on_edge and strip.x0 + r <= ex[0] <= strip.x1 - r,
                 f"{m.key} pigtail: exit on the panel's cable edge, over the lid strip",
                 f"exit x {_f(ex[0])} on the {exit_edge(m)} edge (u {m.pigtail_exit_u}); lid strip "
                 f"x {_f(strip.x0)}..{_f(strip.x1)}")

    contents = L.base_contents(lay)
    for k in BOARD_KEYS:
        x, yd = _drop_xy(lay, k)
        end, back, face = _plug_ends(lay, k)
        through = n.x0 <= x - r + EPS and x + r <= n.x1 + EPS
        report.check(through, f"{m.key} pigtail ({k}): drops through the hinge notch",
                     f"over the plug's run axis x {_f(x)}: notch x {_f(n.x0)}..{_f(n.x1)} round "
                     f"the {PIGTAIL.dia} cable")
        clear = [(rod_distance(lay, pigtail_path(lay, a, k)), a) for a in sweep_angles()]
        least_d, at_d = min(clear)
        report.check(least_d >= ROD_CLEAR - EPS,
                     f"{m.key} pigtail ({k}): clear of the hinge rod",
                     f"drop at y {_f(yd)}, {_f(hy - yd)} in front of the axis; the path keeps "
                     f"{_f(least_d)} from it at worst ({at_d:g} deg) >= cable r {r:g} + rod r "
                     f"{L.PIN_ROD_D / 2:g} + FIT {L.FIT} = {_f(ROD_CLEAR)}")
        # the drop and the run in to the stiff run's end, as boxes round the cable
        legs = {"drop": Box(x - r, yd - r, end[2] - r, x + r, yd + r, hz),
                "run in": Box(x - r, end[1], end[2] - r, x + r, yd + r, end[2] + r)}
        hits = sorted({f"{leg} / {nm}" for leg, b in legs.items()
                       for nm, c in contents.items() if overlaps(b, c, EPS)})
        inside = all(b.x0 >= w - EPS and b.x1 <= o.x1 - w + EPS and b.y1 <= o.y1 - w + EPS
                     and b.z0 >= w - EPS for b in legs.values())
        report.check(inside and not hits,
                     f"{m.key} pigtail ({k}): its drop to the plug is in free room",
                     f"drop at ({_f(x)}, {_f(yd)}) from the seam to z {_f(end[2])}, then to the "
                     f"stiff run's end at y {_f(end[1])}: inside the walls"
                     + (f"; hits {', '.join(hits)}" if hits else
                        f", clear of all {len(contents)} base contents"))
        lengths = [(pigtail_length_bound(lay, a, k), a) for a in sweep_angles()]
        longest, at = max(lengths)
        report.check(longest <= m.pigtail_len + EPS, f"{m.key} pigtail ({k}): length",
                     f"exit to plug face, |dx|+|dy|+|dz| per leg: at most {_f(longest)} "
                     f"({at:g} deg) <= pigtail_len {_f(m.pigtail_len)} mm")
        bends = [(max_bend_r(pigtail_path(lay, a, k)[:-1], stiff_last=True), a)
                 for a in sweep_angles()]
        least, at = min(bends)
        closed_r = bends[0][0]
        lid_top = lay.rim_z + strip.z1 - r
        report.check(least >= PIGTAIL.min_bend_r - EPS,
                     f"{m.key} pigtail ({k}): every bend after the stiff run",
                     f"rounds to r {_f(least)} at worst ({at:g} deg) over {len(bends)} angles >= "
                     f"{PIGTAIL.key} min bend r {PIGTAIL.min_bend_r}; closed r {_f(closed_r)}, "
                     f"the U-turn from the lid's inside face (z {_f(lid_top)}) to the run "
                     f"(z {_f(end[2])}) allows {_f((lid_top - end[2]) / 2)}, the room behind the "
                     f"run's end (y {_f(end[1])} to {_f(yd)}) {_f(yd - end[1])}")

        c = usb_cable()
        path = usb_path(lay, k)
        length = manhattan_length(path)
        bend = max_bend_r(path[:-1])
        report.check(length <= USB_MAX_LEN + EPS and bend >= c.min_bend_r - EPS,
                     f"{c.key} ({k}): bank port to J1 through the port room",
                     f"length {_f(length)} <= {USB_MAX_LEN:g} mm; bends round to r {_f(bend)} "
                     f">= {c.min_bend_r}")


def lid_catch(report: Report, lay: Layout) -> None:
    """R22: the shut lid is held by pairs of disc magnets.  Each base magnet has
    its lid partner straight over it, the two faces at most CATCH_MAX_GAP apart
    (not touching through the rim); each base block is inside the walls and
    clear of every board keep-out in XY, each lid block clear of the monitor."""
    hz = lay.hinge_axis[1]
    o, w = lay.outer, lay.wall
    for i, c in enumerate(lay.lid_catch, 1):
        mg = lay.catch_lid_magnet(c)
        my, mz = lid_point_open(lay, mg.cy, mg.z0, 0.0)
        off = math.hypot(mg.cx - c.cx, my - c.cy)
        gap = mz - c.z1
        report.check(off <= EPS and 0 <= gap <= CATCH_MAX_GAP + EPS,
                     f"lid catch {i}: magnets face each other when shut",
                     f"lid magnet {_f(off)} mm off the base's, faces {_f(gap)} <= "
                     f"{CATCH_MAX_GAP:g} mm apart (seam z {_f(hz)})")
        blk = lay.catch_base_block(c)
        inside = blk.x0 >= o.x0 + w - EPS and blk.x1 <= o.x1 - w + EPS
        hits = [k.what for k in lay.board_keepouts.values() if _xy_overlap(blk, k)]
        report.check(inside and not hits, f"lid catch {i}: block clear of walls and board",
                     f"block X {_f(blk.x0)}..{_f(blk.x1)} Y {_f(blk.y0)}..{_f(blk.y1)} inside "
                     "the side walls" + (f"; over {', '.join(hits)}" if hits else
                                         ", clear of every board keep-out"))
        lb = lay.catch_lid_block(c)
        report.check(not overlaps(lb, lay.monitor_space, EPS),
                     f"lid catch {i}: lid block clear of the monitor",
                     f"block X {_f(lb.x0)}..{_f(lb.x1)}, monitor space X "
                     f"{_f(lay.monitor_space.x0)}..{_f(lay.monitor_space.x1)}")


def _budget(lay: Layout) -> dict[str, float]:
    """The box's dimensions from the part data by the spec's formula (layout
    docstring, "Base rows" and "Lid"), recomputed here: the board row (its
    keep-outs, not the VGA plug), port room + bay, the VGA plug's keep-out
    in the bank row's corner (from the part data) + SLACK, the monitor."""
    w, s = lay.wall, SLACK
    b = BATTERIES[L.DESIGN_BANK]
    mw, mh, md = MONITORS[L.DESIGN_MONITOR].panel
    ks = [v for key, v in lay.board_keepouts.items() if not key.endswith("/vga_plug")]
    u = ks[0]
    for k in ks[1:]:
        u = u.union(k)
    board_x, board_y, stack = u.size[0] + 2 * s, u.size[1], u.size[2]
    port = max(max(CABLES[k].plug[0] for k in L.BANK_SIDE_PLUGS) + s, FINGERTIP_D)
    bay_x, bay_y = b.size[0] + 2 * s, b.size[1] + 2 * s
    plug_x = max(vga_plug_box(lay, k).x1 for k in BOARD_KEYS) - w + s
    width = max(board_x, port + bay_x, plug_x, mw + 2 * s) + 2 * w
    # R18b: the catch blocks push the monitor back only if they reach over it
    ms_x0 = (width - (mw + 2 * s)) / 2
    over = any(lay.catch_base_block(c).x0 < ms_x0 + mw + 2 * s
               and ms_x0 < lay.catch_base_block(c).x1 for c in lay.lid_catch)
    # R18: the pigtail's turn behind the stiff run's end, in front of the rod
    run_end = max(_plug_ends(lay, k)[0][1] for k in BOARD_KEYS)
    terms = {"rows": w + s + board_y + s + bay_y + s + w,
             "monitor": mh + 2 * s + 2 * w + (L.CATCH_BLOCK if over else 0.0),
             "pigtail": run_end + PIGTAIL.min_bend_r + ROD_CLEAR + L.KNUCKLE_R}
    depth = max(terms.values())
    return {"width": width, "depth": depth, "height": w + max(b.size[2], stack) + s,
            "depth terms": terms,
            "lid width": width, "lid depth": depth,
            "lid height": w + L.TAPE_T + md + L.CLOSED_CLEARANCE}


def size_budget(report: Report, lay: Layout) -> None:
    """The base and lid are no bigger than contents + SLACK + walls: each
    dimension within SIZE_TOL of the formula recomputed from the part data.
    Reports the sizes and the closed volume."""
    f = _budget(lay)
    terms = f.pop("depth terms")
    o, lid = lay.outer, lay.lid_outer
    real = {"width": o.size[0], "depth": o.size[1], "height": o.size[2],
            "lid width": lid.size[0], "lid depth": lid.size[1], "lid height": lid.size[2]}
    litres = o.size[0] * o.size[1] * (o.size[2] + lid.size[2]) / 1e6
    sizes = (f"base {_f(o.size[0])} x {_f(o.size[1])} x {_f(o.size[2])}, lid {_f(lid.size[0])} "
             f"x {_f(lid.size[1])} x {_f(lid.size[2])}; closed {_f(o.size[2] + lid.size[2])} "
             f"high, {litres:.3f} L; depth terms "
             + ", ".join(f"{n} {_f(v)}" for n, v in terms.items()))
    for n, v in real.items():
        report.check(v <= f[n] + SIZE_TOL, f"size budget: {n}",
                     f"{_f(v)} <= formula {_f(f[n])} + {SIZE_TOL}; {sizes}")


#: Every proof, in the order verify.py prints them.
PROOFS = (kit_fits, boards_seat, bank_lifts_out, button_reachable, lid_closed_clears,
          hinge_sweep, cables_route, lid_catch, size_budget)
