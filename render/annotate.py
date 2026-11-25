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
  with arrowheads, and the label at its middle;
* outline: the ``points`` polyline with no label: ``style`` "line" thin
  (a projection line, P6), "area" at the dimension line's width with a
  light translucent ``C_DIM`` fill (the bank bay, P4, P8).

Every extension line starts EXT_GAP px off its anchor (a drafting gap, P8),
so corners read as corners.

Labels are DejaVu Sans at ``max(18, h // 50)`` px on a white backing (3 px
padding).  Each is centred on its own line, at the middle if it can be,
otherwise nudged along the line; it must lie wholly between the arrowheads,
inside the image, and clear of every other label and every other
dimension's lines (outlines included).  A label with no such place is a
``PlacementError`` naming what blocked it: never a silent overlap.

Fallback (rulings P2, P2b): entries with ``"fallback": true`` (the
flat-pack's overall X and Y extents) are drawn only when the others'
labels cannot all be placed, and then they replace them all.

Fails loudly: a missing sidecar, a resolution that is not the image's, an
entry missing a key, or a point off the image raises.  No ``bpy``: plain Pillow.
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
EXT_GAP = 5                  # px gap between an anchor and its extension line (P8)
AREA_ALPHA = 0.18            # opacity of an "area" outline's C_DIM fill (P8)
STYLES = ("line", "area")    # outline styles
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
    dims: list[dict]          # the dimensions drawn, outlines included
    placed: list[Placed]      # the labelled ones' labels, in the same order
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

#: Each kind's keys (``render_scene.project_dimensions``).
KEYS = {"linear": {"label", "kind", "fallback", "a", "b", "line_a", "line_b"},
        "angle": {"label", "kind", "fallback", "centre", "a", "b", "arc"},
        "outline": {"kind", "fallback", "points", "style"}}


def _name(d: dict, i: int) -> str:
    return repr(d["label"]) if "label" in d else f"#{i} ({d.get('kind')})"


def _points(d: dict) -> list[tuple[str, list[float]]]:
    if d["kind"] == "outline":
        return [(f"points[{i}]", p) for i, p in enumerate(d["points"])]
    keys = ("a", "b", "line_a", "line_b") if d["kind"] == "linear" else ("centre", "a", "b")
    pts = [(k, d[k]) for k in keys]
    if d["kind"] == "angle":
        pts += [(f"arc[{i}]", p) for i, p in enumerate(d["arc"])]
    return pts


def _path(d: dict) -> list[tuple[float, float]]:
    """The polyline drawn heavy (and the label sits on)."""
    if d["kind"] == "linear":
        return [tuple(d["line_a"]), tuple(d["line_b"])]
    if d["kind"] == "angle":
        return [tuple(p) for p in d["arc"]]
    if d["kind"] == "outline":
        return [tuple(p) for p in d["points"]]
    raise ValueError(f"dimension {_name(d, -1)}: unknown kind {d['kind']!r}")


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
    if d["kind"] == "outline":
        return segs
    if d["kind"] == "linear":
        for a, la in ((d["a"], d["line_a"]), (d["b"], d["line_b"])):
            e = _ext_end(a, la)
            dx, dy = la[0] - a[0], la[1] - a[1]
            n = math.hypot(dx, dy)
            g = min(EXT_GAP, n)
            start = (a[0], a[1]) if n == 0 else (a[0] + dx / n * g, a[1] + dy / n * g)
            segs.append((start, (min(max(e[0], 0), w), min(max(e[1], 0), h))))
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
    """Place the labelled ``dims``' labels, in order; outlines are only
    obstacles.  Raises ``PlacementError`` naming what blocked a label."""
    head = head_px(h)
    segs = [_segments(d, w, h) for d in dims]
    placed: list[Placed] = []
    for i, d in enumerate(dims):
        if d["kind"] == "outline":
            continue
        l, t, r, b = draw.textbbox((0, 0), d["label"], font=font, anchor="mm")
        bw, bh = (r - l) + 2 * PAD, (b - t) + 2 * PAD
        others = [(j, s) for j, ss in enumerate(segs) if j != i for s in ss]
        cands = _candidates(_path(d), bw, bh, head)
        blocked: dict[str, int] = {}
        for cx, cy in cands:
            box = (cx + l - PAD, cy + t - PAD, cx + r + PAD, cy + b + PAD)
            why = None
            if not (GAP <= box[0] and box[2] <= w - GAP and GAP <= box[1] and box[3] <= h - GAP):
                why = "outside the frame"
            if why is None:
                hit = next((p for p in placed if _overlap(box, p.box)), None)
                if hit is not None:
                    why = f"overlaps label {hit.label!r}"
            if why is None:
                hit = next((j for j, (p, q) in others if _seg_hits_box(p, q, box)), None)
                if hit is not None:
                    why = f"covers a line of {_name(dims[hit], hit)}"
            if why is None:
                placed.append(Placed(d["label"], box, (cx, cy)))
                break
            blocked[why] = blocked.get(why, 0) + 1
        else:
            where = f"({d['kind']}, line {_path(d)[0]}..{_path(d)[-1]}, {w}x{h} image)"
            if not cands:
                raise PlacementError(f"label {d['label']!r} {where} does not fit between "
                                     f"its arrowheads")
            reasons = "; ".join(f"{k} ({n} of {len(cands)})" for k, n in blocked.items())
            raise PlacementError(f"label {d['label']!r} {where} has no place on its line: "
                                 f"{reasons}")
    return placed


def _check(side: dict, size: tuple[int, int] | None = None) -> tuple[int, int]:
    w, h = side["resolution"]
    if size is not None and tuple(size) != (w, h):
        raise ValueError(f"sidecar resolution {w}x{h} is not the image's {size[0]}x{size[1]}")
    for i, d in enumerate(side["dimensions"]):
        want = KEYS.get(d.get("kind"))
        if want is None:
            raise ValueError(f"dimension {_name(d, i)}: unknown kind {d.get('kind')!r}")
        if set(d) != want:
            raise ValueError(f"dimension {_name(d, i)} ({d['kind']}): keys {sorted(set(d))}, "
                             f"want {sorted(want)} (missing {sorted(want - set(d))})")
        if d["kind"] == "outline" and d["style"] not in STYLES:
            raise ValueError(f"dimension {_name(d, i)}: outline style {d['style']!r}, "
                             f"want one of {STYLES}")
        for key, (x, y) in _points(d):
            if not (0 <= x <= w and 0 <= y <= h):
                raise ValueError(f"dimension {_name(d, i)} {key} ({x}, {y}) is outside "
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
    areas = [d for d in p.dims if d["kind"] == "outline" and d["style"] == "area"]
    if areas:                                # translucent fills first, under everything
        mode = img.mode
        base = img.convert("RGBA")
        tint = Image.new("RGBA", base.size, (0, 0, 0, 0))
        r, g, b = (int(C_DIM[i:i + 2], 16) for i in (1, 3, 5))
        td = ImageDraw.Draw(tint)
        for d in areas:
            td.polygon([tuple(q) for q in d["points"]], fill=(r, g, b, round(255 * AREA_ALPHA)))
        img = Image.alpha_composite(base, tint).convert(mode)
    draw = ImageDraw.Draw(img)
    for d in p.dims:
        path = _path(d)
        if d["kind"] == "outline":
            width = lw if d["style"] == "area" else max(1, lw - 1)
            draw.line(path, fill=C_DIM, width=width, joint="curve")
            continue
        for a, q in _segments(d, w, h)[len(path) - 1:]:     # extension lines / arms
            draw.line([a, q], fill=C_DIM, width=max(1, lw - 1))
        draw.line(path, fill=C_DIM, width=lw, joint="curve")
        _arrow(draw, path[0], path[1], head)
        _arrow(draw, path[-1], path[-2], head)
    font = _font(p.font_px)
    for pl in p.placed:
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
        n_out = sum(d["kind"] == "outline" for d in p.dims)
        print(f"annotate: {png}: {len(p.placed)} dimensions and {n_out} outlines drawn"
              f"{' (fallback: overall extent)' if p.fallback else ''}: "
              + ", ".join(pl.label for pl in p.placed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
