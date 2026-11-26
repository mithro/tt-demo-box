"""Camera bearing and camera-view coordinates to image pixels, for the
dimension sidecar.

Pure Python (no ``bpy``), so it is testable outside Blender:
``render_scene._direction`` is ``direction`` (the camera and lights), and
``render_scene.project_dimensions`` uses ``to_px`` on
``world_to_camera_view``'s output.  ``tests/test_scene.py`` checks with
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
