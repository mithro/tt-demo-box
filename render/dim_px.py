"""The dimension sidecar's geometry: camera bearing, the camera fit, the
dimensions' world points and their projection to image pixels.

Pure Python (no ``bpy``), so it is testable outside Blender:
``render_scene._direction`` is ``direction`` (the camera and lights);
``render_scene`` places its camera with ``fit_camera`` and projects
``dim_points`` (the arc by ``arc_points``) with ``world_to_camera_view``
and ``to_px``, checking on every render that ``camera_view`` gives the same
pixels.  ``tests/test_scene.py`` checks with ``direction`` that every
dimension stands out towards its view's camera; ``tests/test_renders.py``
reprojects the committed sidecars with ``camera_view``.
"""

from __future__ import annotations

import math


def direction(az_deg: float, el_deg: float) -> tuple[float, float, float]:
    """Unit vector from the scene towards the camera: bearing ``az_deg``
    about Z, 0 in front (-Y), +90 at the right (+X); ``el_deg`` above the
    horizon."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    return (math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))


def to_px(v, w: int, h: int, what: str = "point") -> list[float]:
    """``v`` = (x, y, depth) from ``world_to_camera_view`` (x, y in 0..1 from
    the bottom-left, depth along the view) -> ``[px, py]`` in a ``w`` x ``h``
    image, origin top-left.  Raises ``ValueError`` if the point is behind the
    camera (depth <= 0) or outside ``[0, w] x [0, h]``."""
    x, y, z = v
    px, py = x * w, (1.0 - y) * h
    if z <= 0 or not (0.0 <= px <= w and 0.0 <= py <= h):
        raise ValueError(f"{what} projects to ({px:.1f}, {py:.1f}, depth {z:.3f}), "
                         f"outside the {w}x{h} image")
    return [round(px, 3), round(py, 3)]


#: How far inside (0, 180) degrees an arc's angle must be: at 0 or 180 the
#: plane of the arc is undefined (the arms are collinear), and close to them
#: it is numerically unstable.
ARC_MARGIN_DEG = 1.0


def arc_points(centre, a, b, steps: int) -> list[tuple[float, float, float]]:
    """Points on the circular arc about ``centre`` from ``a`` to ``b`` (3D,
    equal radii), the short way round, sampled at ``steps + 1`` points.

    Raises ``ValueError`` if the arms' lengths differ, an arm is zero, or the
    angle between them is not inside (0, 180) degrees by ARC_MARGIN_DEG."""
    c = [float(v) for v in centre]
    va = [float(p) - q for p, q in zip(a, c)]
    vb = [float(p) - q for p, q in zip(b, c)]
    r, rb = math.hypot(*va), math.hypot(*vb)
    if r <= 0 or abs(rb - r) > 1e-6 * max(r, 1.0):
        raise ValueError(f"angle arms differ: {r} and {rb}")
    u = [v / r for v in va]
    cos = max(-1.0, min(1.0, sum(p * q for p, q in zip(u, vb)) / rb))
    theta = math.acos(cos)
    lo, hi = math.radians(ARC_MARGIN_DEG), math.pi - math.radians(ARC_MARGIN_DEG)
    if not lo < theta < hi:
        raise ValueError(f"angle {math.degrees(theta):.3f} deg is not inside (0, 180) by "
                         f"{ARC_MARGIN_DEG:g} deg: the arc's plane is undefined")
    along = sum(p * q for p, q in zip(vb, u))
    wv = [q - p * along for p, q in zip(u, vb)]
    n = math.hypot(*wv)
    w = [v / n for v in wv]
    out = []
    for i in range(steps + 1):
        t = theta * i / steps
        ct, st = math.cos(t), math.sin(t)
        out.append(tuple(c[k] + (u[k] * ct + w[k] * st) * r for k in range(3)))
    return out


#: Segments the angle arc is sampled in (``dim_points``).
ARC_STEPS = 32


def dim_points(d) -> dict:
    """A manifest dimension's named points (world, mm, as tuples): linear
    ``a``, ``b``, ``line_a``, ``line_b`` (the anchors + ``offset``); angle
    ``centre``, ``a``, ``b`` and ``arc`` (``arc_points``, ARC_STEPS + 1
    points, a list); outline ``points`` (a list).  These are the points
    ``render_scene.project_dimensions`` projects, and the sidecar records."""
    def pt(p):
        return tuple(float(v) for v in p)

    if d["kind"] == "linear":
        a, b, off = pt(d["a"]), pt(d["b"]), pt(d["offset"])
        return {"a": a, "b": b, "line_a": tuple(p + q for p, q in zip(a, off)),
                "line_b": tuple(p + q for p, q in zip(b, off))}
    if d["kind"] == "angle":
        c, a, b = pt(d["centre"]), pt(d["a"]), pt(d["b"])
        return {"centre": c, "a": a, "b": b, "arc": arc_points(c, a, b, ARC_STEPS)}
    if d["kind"] == "outline":
        return {"points": [pt(p) for p in d["points"]]}
    raise ValueError(f"unknown dimension kind {d['kind']!r}")


def flat_points(dims) -> list[tuple[float, float, float]]:
    """Every point of ``dims`` (``dim_points``), in order, in mm."""
    out = []
    for d in dims:
        for v in dim_points(d).values():
            out += v if isinstance(v, list) else [v]
    return out


# --- the camera -------------------------------------------------------------------------
#
# ``render_scene`` places Blender's camera with ``fit_camera`` and records
# the result in the sidecar; ``camera_view`` is ``world_to_camera_view``
# for that camera, so tests can reproduce the sidecar's pixels without
# Blender.  ``render_scene`` checks the two agree on every render.

#: Margin round the fitted framing (the camera backs off by this factor).
FRAME_MARGIN = 1.10
#: The camera's sensor width (mm; Blender's default), fitted horizontally.
SENSOR_WIDTH_MM = 36.0


def _dot(p, q) -> float:
    return sum(a * b for a, b in zip(p, q))


def _cross(p, q) -> tuple[float, float, float]:
    return (p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0])


def _unit(p) -> tuple[float, ...]:
    n = math.hypot(*p)
    return tuple(v / n for v in p)


def camera_axes(az_deg: float, el_deg: float):
    """The camera's (right, up, back) world axes looking at the scene from
    bearing ``az_deg``, elevation ``el_deg`` (``direction``): back is
    ``direction``, up is world +Z made square to it (Blender's
    ``(-back).to_track_quat("-Z", "Y")``).  Raises looking straight down or up."""
    back = direction(az_deg, el_deg)
    if abs(back[2]) > 1 - 1e-9:
        raise ValueError(f"elevation {el_deg} deg: the camera's up is undefined")
    right = _unit(_cross((0.0, 0.0, 1.0), back))
    up = _cross(back, right)
    return right, up, back


def fit_camera(az_deg: float, el_deg: float, lens_mm: float, res, corners, extra=(),
               margin: float = FRAME_MARGIN, sensor_width_mm: float = SENSOR_WIDTH_MM
               ) -> list[float]:
    """The camera's 4 x 4 ``matrix_world`` (row major, metres) at bearing
    ``az_deg``, elevation ``el_deg``, as close as it can be while every
    point of ``corners`` (the parts' bounding-box corners) and ``extra``
    (the dimensions' points) is inside the ``res`` frame shrunk by
    ``margin``, centred by shifting the camera square to its view.  The
    view is aimed along the corners' bounding-box centre."""
    lo = [min(p[k] for p in corners) for k in range(3)]
    hi = [max(p[k] for p in corners) for k in range(3)]
    centre = [(p + q) / 2 for p, q in zip(lo, hi)]
    right, up, back = camera_axes(az_deg, el_deg)
    pts = [tuple(p) for p in corners] + [tuple(p) for p in extra]
    tan_x = sensor_width_mm / 2 / lens_mm / margin
    tan_y = tan_x * res[1] / res[0]

    def at(dist, sx, sy):
        return [centre[k] + back[k] * dist + right[k] * sx + up[k] * sy for k in range(3)]

    def extents(dist, sx, sy):
        c = at(dist, sx, sy)
        xs, ys = [], []
        for p in pts:
            v = [p[k] - c[k] for k in range(3)]
            z = -_dot(v, back)
            if z <= 1e-6:
                return None
            xs.append(_dot(v, right) / z)
            ys.append(_dot(v, up) / z)
        return min(xs), max(xs), min(ys), max(ys)

    def fit(dist):
        sx = sy = 0.0
        for _ in range(8):
            e = extents(dist, sx, sy)
            if e is None:
                return False, sx, sy
            sx += (e[0] + e[1]) / 2 * dist
            sy += (e[2] + e[3]) / 2 * dist
        e = extents(dist, sx, sy)
        ok = e is not None and e[1] - e[0] <= 2 * tan_x and e[3] - e[2] <= 2 * tan_y
        return ok, sx, sy

    lo_d, hi_d = 0.0, 100.0 * math.dist(lo, hi)
    for _ in range(50):
        mid = (lo_d + hi_d) / 2
        if fit(mid)[0]:
            hi_d = mid
        else:
            lo_d = mid
    _ok, sx, sy = fit(hi_d)
    loc = at(hi_d, sx, sy)
    return [right[0], up[0], back[0], loc[0],
            right[1], up[1], back[1], loc[1],
            right[2], up[2], back[2], loc[2],
            0.0, 0.0, 0.0, 1.0]


def _inverse3(m):
    """Inverse of the 3 x 3 ``m`` (rows)."""
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        raise ValueError("the camera's matrix_world is singular")
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def camera_view(cam: dict, p) -> tuple[float, float, float]:
    """``bpy_extras.object_utils.world_to_camera_view`` for the sidecar's
    ``cam`` (``"matrix_world_m"``, row major in metres, ``"lens_mm"``,
    ``"sensor_width_mm"``, ``"sensor_fit"`` HORIZONTAL, ``"shift"`` [0, 0],
    ``"resolution"``) and world point ``p`` (metres): (x, y) in 0..1 from
    the frame's bottom-left, and the depth along the view."""
    if cam["sensor_fit"] != "HORIZONTAL":
        raise ValueError(f"sensor_fit {cam['sensor_fit']!r}: only HORIZONTAL is modelled")
    if list(cam["shift"]) != [0.0, 0.0]:
        raise ValueError(f"shift {cam['shift']}: only an unshifted lens is modelled")
    m = cam["matrix_world_m"]
    cols = [_unit((m[k], m[4 + k], m[8 + k])) for k in range(3)]   # .normalized()
    inv = _inverse3([[cols[c][r] for c in range(3)] for r in range(3)])
    v = [p[k] - m[4 * k + 3] for k in range(3)]
    x, y, z = (_dot(row, v) for row in inv)
    depth = -z
    if depth == 0.0:
        return 0.5, 0.5, 0.0
    w, h = cam["resolution"]
    half_x = cam["sensor_width_mm"] / 2 / cam["lens_mm"]
    half_y = half_x * h / w
    return 0.5 + x / depth / (2 * half_x), 0.5 + y / depth / (2 * half_y), depth


def project_px(cam: dict, p, what: str = "point") -> list[float]:
    """World point ``p`` (metres) to ``[px, py]`` in the ``cam`` render
    (``camera_view`` then ``to_px``)."""
    w, h = cam["resolution"]
    return to_px(camera_view(cam, p), w, h, what)
