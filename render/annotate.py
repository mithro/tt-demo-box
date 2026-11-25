"""Draw the dimension overlay onto a render, in place.

``make renders`` runs this after each Blender render::

    python render/annotate.py output/renders/<name>.png

It reads the sidecar ``<name>.png.dims.json`` that ``render_scene.py``
writes (``{"resolution": [w, h], "dimensions": [...]}``, every point in
top-left pixels; see ``render_scene.project_dimensions``) and draws, in
``C_DIM``:

* linear: extension lines from the anchors ``a``, ``b`` to the dimension
  line ``line_a`` .. ``line_b`` (a little past it), the line with filled
  arrowheads, and the label centred on it;
* angle: the arms from ``centre`` to ``a`` and ``b``, the ``arc`` polyline
  with arrowheads, and the label at its middle.

Labels are DejaVu Sans at ``max(18, h // 50)`` px on a white backing (3 px
padding).  Each is centred on its own line, at the middle if it can be,
otherwise nudged along the line; it must lie wholly between the arrowheads,
inside the image, and clear of every other label and every other
dimension's lines.
A label with no such place is a ``PlacementError``: never a silent overlap.

Fallback (rulings P2, P2b): entries with ``"fallback": true`` (the
flat-pack's overall X and Y extents) are drawn only when the others'
labels cannot all be placed, and then they replace them all.

Fails loudly: a missing sidecar, a resolution that is not the image's, or
a point off the image raises.  No ``bpy``: plain Pillow.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demobox import _paths  # noqa: E402,F401  (puts the vendored tools on sys.path)
from tools.drafting.style import C_DIM  # noqa: E402

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
PAD = 3                      # px of white backing round a label
GAP = 2                      # px kept clear between labels, and to the image edge
EXT_PAST = 8                 # px an extension line runs past the dimension line
STEPS = 40                   # positions tried along a line, each side of the middle


class PlacementError(ValueError):
    """A label that cannot be placed without clipping or overlapping."""


@dataclass(frozen=True)
class Placed:
    label: str
    box: tuple[float, float, float, float]      # x0, y0, x1, y1 of the white backing
    centre: tuple[float, float]


@dataclass(frozen=True)
class Plan:
    dims: list[dict]          # the dimensions drawn
    placed: list[Placed]      # their labels, in the same order
    fallback: bool            # True if the fallback entries replaced the others
    font_px: int


def sidecar_for(png: Path) -> Path:
    return png.with_name(png.name + ".dims.json")


def font_px(h: int) -> int:
    return max(18, h // 50)


def head_px(h: int) -> int:
    """Arrowhead length."""
    return max(10, h // 70)


def _font(px: int):
    return ImageFont.truetype(FONT, px)


# --- geometry -----------------------------------------------------------------------

def _points(d: dict) -> list[tuple[str, list[float]]]:
    keys = ("a", "b", "line_a", "line_b") if d["kind"] == "linear" else ("centre", "a", "b")
    pts = [(k, d[k]) for k in keys]
    if d["kind"] == "angle":
        pts += [(f"arc[{i}]", p) for i, p in enumerate(d["arc"])]
    return pts


def _path(d: dict) -> list[tuple[float, float]]:
    """The polyline the label sits on."""
    if d["kind"] == "linear":
        return [tuple(d["line_a"]), tuple(d["line_b"])]
    if d["kind"] == "angle":
        return [tuple(p) for p in d["arc"]]
    raise ValueError(f"dimension {d['label']!r}: unknown kind {d['kind']!r}")


def _ext_end(anchor, line_pt) -> tuple[float, float]:
    """The extension line's far end: ``line_pt``, EXT_PAST further on."""
    dx, dy = line_pt[0] - anchor[0], line_pt[1] - anchor[1]
    n = math.hypot(dx, dy)
    if n == 0:
        return tuple(line_pt)
    return (line_pt[0] + dx / n * EXT_PAST, line_pt[1] + dy / n * EXT_PAST)


def _segments(d: dict, w: int, h: int) -> list[tuple[tuple, tuple]]:
    """Every line segment drawn for ``d`` (path, extension lines or arms)."""
    path = _path(d)
    segs = list(zip(path, path[1:]))
    if d["kind"] == "linear":
        for a, la in ((d["a"], d["line_a"]), (d["b"], d["line_b"])):
            e = _ext_end(a, la)
            segs.append((tuple(a), (min(max(e[0], 0), w), min(max(e[1], 0), h))))
    else:
        segs += [(tuple(d["centre"]), tuple(d["a"])), (tuple(d["centre"]), tuple(d["b"]))]
    return segs


def _seg_hits_box(p, q, box) -> bool:
    """Liang-Barsky: does segment ``p``-``q`` touch the box's interior?"""
    x0, y0, x1, y1 = box
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if pk == 0:
            if qk <= 0:
                return False
        else:
            t = qk / pk
            if pk < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 >= t1:
                return False
    return True


def _overlap(p, q) -> bool:
    return (p[0] < q[2] + GAP and q[0] < p[2] + GAP
            and p[1] < q[3] + GAP and q[1] < p[3] + GAP)


def _along(path, s: float):
    """Point and unit tangent at fraction ``s`` of ``path``'s length."""
    lens = [math.dist(p, q) for p, q in zip(path, path[1:])]
    total = sum(lens)
    if total == 0:
        return path[0], (1.0, 0.0)
    want = s * total
    for (p, q), n in zip(zip(path, path[1:]), lens):
        if want <= n or (p, q) == (path[-2], path[-1]):
            f = 0.0 if n == 0 else min(want / n, 1.0)
            t = (1.0, 0.0) if n == 0 else ((q[0] - p[0]) / n, (q[1] - p[1]) / n)
            return (p[0] + f * (q[0] - p[0]), p[1] + f * (q[1] - p[1])), t
        want -= n
    raise AssertionError("unreachable")


# --- placement ----------------------------------------------------------------------

def _candidates(path, bw: float, bh: float, head: float):
    """Label centres to try, on the line from the middle outwards, keeping
    the whole label between the arrowheads.  None if it does not fit there:
    a label off its own line, beside a short one, is ambiguous (that is when
    the flat-pack falls back to its overall extent)."""
    total = sum(math.dist(p, q) for p, q in zip(path, path[1:]))
    out = []
    for s in [0.5] + [0.5 + sgn * 0.5 * k / STEPS for k in range(1, STEPS + 1) for sgn in (-1, 1)]:
        c, (tx, ty) = _along(path, s)
        half = (abs(tx) * bw + abs(ty) * bh) / 2          # the box's reach along the line
        if head <= s * total - half and s * total + half <= total - head:
            out.append(c)
    return out


def _place(dims: list[dict], w: int, h: int, draw, font) -> list[Placed]:
    head = head_px(h)
    segs = [_segments(d, w, h) for d in dims]
    placed: list[Placed] = []
    for i, d in enumerate(dims):
        l, t, r, b = draw.textbbox((0, 0), d["label"], font=font, anchor="mm")
        bw, bh = (r - l) + 2 * PAD, (b - t) + 2 * PAD
        others = [s for j, ss in enumerate(segs) if j != i for s in ss]
        for cx, cy in _candidates(_path(d), bw, bh, head):
            box = (cx + l - PAD, cy + t - PAD, cx + r + PAD, cy + b + PAD)
            if not (GAP <= box[0] and box[2] <= w - GAP and GAP <= box[1] and box[3] <= h - GAP):
                continue
            if any(_overlap(box, p.box) for p in placed):
                continue
            if any(_seg_hits_box(p, q, box) for p, q in others):
                continue
            placed.append(Placed(d["label"], box, (cx, cy)))
            break
        else:
            raise PlacementError(
                f"label {d['label']!r} ({d['kind']}, line {_path(d)[0]}..{_path(d)[-1]}) has "
                f"no place on its line, between the arrowheads, inside the {w}x{h} image and "
                f"clear of the other labels and lines")
    return placed


def _check(side: dict, size: tuple[int, int] | None = None) -> tuple[int, int]:
    w, h = side["resolution"]
    if size is not None and tuple(size) != (w, h):
        raise ValueError(f"sidecar resolution {w}x{h} is not the image's {size[0]}x{size[1]}")
    for d in side["dimensions"]:
        for key, (x, y) in _points(d):
            if not (0 <= x <= w and 0 <= y <= h):
                raise ValueError(f"dimension {d['label']!r} {key} ({x}, {y}) is outside "
                                 f"the {w}x{h} image")
    return w, h


def plan(side: dict, size: tuple[int, int] | None = None) -> Plan:
    """Which dimensions to draw and where their labels go."""
    w, h = _check(side, size)
    px = font_px(h)
    font = _font(px)
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    main = [d for d in side["dimensions"] if not d["fallback"]]
    fall = [d for d in side["dimensions"] if d["fallback"]]
    try:
        return Plan(main, _place(main, w, h, draw, font), False, px)
    except PlacementError as e:
        if not fall:
            raise
        try:
            return Plan(fall, _place(fall, w, h, draw, font), True, px)
        except PlacementError as e2:
            raise PlacementError(f"{e2} (falling back, because {e})") from e2


# --- drawing ------------------------------------------------------------------------

def _arrow(draw, tip, frm, size: float) -> None:
    """A filled arrowhead at ``tip``, pointing away from ``frm``."""
    dx, dy = tip[0] - frm[0], tip[1] - frm[1]
    n = math.hypot(dx, dy)
    if n == 0:
        return
    ux, uy = dx / n, dy / n
    bx, by = tip[0] - ux * size, tip[1] - uy * size
    hw = size / 3
    draw.polygon([tip, (bx - uy * hw, by + ux * hw), (bx + uy * hw, by - ux * hw)], fill=C_DIM)


def annotate(png: Path, sidecar: Path) -> Plan:
    """Draw ``sidecar``'s dimensions onto ``png``, in place."""
    png, sidecar = Path(png), Path(sidecar)
    if not sidecar.is_file():
        raise FileNotFoundError(f"no dimension sidecar {sidecar} for {png}")
    side = json.loads(sidecar.read_text())
    img = Image.open(png)
    img.load()
    p = plan(side, img.size)
    w, h = img.size
    lw = max(2, h // 400)
    head = head_px(h)
    draw = ImageDraw.Draw(img)
    for d in p.dims:
        path = _path(d)
        for a, q in _segments(d, w, h)[len(path) - 1:]:     # extension lines / arms
            draw.line([a, q], fill=C_DIM, width=max(1, lw - 1))
        draw.line(path, fill=C_DIM, width=lw, joint="curve")
        _arrow(draw, path[0], path[1], head)
        _arrow(draw, path[-1], path[-2], head)
    font = _font(p.font_px)
    for d, pl in zip(p.dims, p.placed):
        x0, y0, x1, y1 = pl.box
        draw.rectangle([round(x0), round(y0), round(x1), round(y1)], fill="white")
        draw.text(pl.centre, pl.label, fill=C_DIM, font=font, anchor="mm")
    img.save(png)
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("png", type=Path, nargs="+", help="render(s); sidecar is <png>.dims.json")
    a = ap.parse_args(argv)
    for png in a.png:
        p = annotate(png, sidecar_for(png))
        print(f"annotate: {png}: {len(p.dims)} dimensions drawn"
              f"{' (fallback: overall extent)' if p.fallback else ''}: "
              + ", ".join(pl.label for pl in p.placed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
