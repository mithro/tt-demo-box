"""Camera bearing and camera-view coordinates to image pixels, for the
dimension sidecar.

Pure Python (no ``bpy``), so it is testable outside Blender:
``render_scene._direction`` is ``direction`` (the camera and lights), and
``render_scene.project_dimensions`` uses ``to_px`` on
``world_to_camera_view``'s output, and ``render_scene._arc`` is
``arc_points``.  ``tests/test_scene.py`` checks with
``direction`` that every dimension stands out towards its view's camera.
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
