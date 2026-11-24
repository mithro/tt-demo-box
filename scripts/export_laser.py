#!/usr/bin/env python3
"""Write the laser route: one DXF per panel, its printed parts, the assembly.

* ``output/laser/<panel>.dxf`` -- one sheet per panel (``demobox.laser.panels``),
  millimetres, kerf compensated: layer ``CUT`` (the outline, mortises, T-slots
  and clearance holes) and layer ``ENGRAVE`` (the panel's name and the
  outlines printed parts are glued on).  Laid landscape with its corner at the
  origin, within the 300 x 200 mm laser bed (``BedOverflow`` otherwise,
  before anything is written).  Normalised with the submodule's
  ``tools.reproducible``, so a rebuild is byte for byte the same.
* ``output/laser/printed/<part>.step`` / ``.stl`` -- the route's printed parts
  (its glued fittings and the shared parts at this wall), posed for printing.
* ``output/laser/assembly.step`` -- the box with the lid at the stop and the
  drawer shut, one named solid per part, no colours (see
  ``export_printed.write_assembly``).
* ``output/laser/hardware.txt`` -- the bought hardware list.

``--thickness`` and ``--kerf`` regenerate everything for plywood that is not
3 mm or a laser with another kerf (the layout is redrawn for the thickness);
``--out`` writes elsewhere; ``--no-printed`` writes only the DXFs and the
hardware list (the assembly is the nominal route's, so it is written only for
the default thickness).

Run: make outputs
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import ezdxf  # noqa: E402

import demobox  # noqa: E402,F401  (puts the submodule on sys.path)
from demobox.layout import LASER_BED, LID_OPEN_DEG, ROUTES, layout  # noqa: E402
from demobox.laser import fittings, panels  # noqa: E402
from demobox.printed import body  # noqa: E402
from tools import reproducible  # noqa: E402

OUT = ROOT / "output" / "laser"
LAYERS = {"CUT": 1, "ENGRAVE": 5}
#: Coordinates are written rounded to this many decimals (well under a micron).
DECIMALS = 6


def _r(v: float) -> float:
    v = round(v, DECIMALS)
    return 0.0 if v == 0 else v


def sheet_transform(p: panels.Panel):
    """(u, v) -> sheet (x, y): turned landscape, its cut corner at the origin."""
    u0, v0, u1, v1 = p.cut_shape().bounds
    turn = (v1 - v0) > (u1 - u0) + 1e-9
    if turn:
        return (lambda u, v: (_r(v - v0), _r(u1 - u))), (v1 - v0, u1 - u0)
    return (lambda u, v: (_r(u - u0), _r(v - v0))), (u1 - u0, v1 - v0)


def write_dxf(p: panels.Panel, path: Path) -> tuple[float, float]:
    tf, size = sheet_transform(p)
    if size[0] > LASER_BED[0] + 1e-6 or size[1] > LASER_BED[1] + 1e-6:
        raise panels.BedOverflow(f"{p.name} {size[0]:.2f} x {size[1]:.2f} mm does not fit the "
                                 f"{LASER_BED[0]:g} x {LASER_BED[1]:g} mm laser bed")
    reproducible.configure_dxf()
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4                       # millimetres
    for name, colour in LAYERS.items():
        doc.layers.add(name, color=colour)
    msp = doc.modelspace()
    cut = p.cut_shape()
    for ring in (cut.exterior, *cut.interiors):
        msp.add_lwpolyline([tf(u, v) for u, v in list(ring.coords)[:-1]], close=True,
                           dxfattribs={"layer": "CUT"})
    for u, v, d in p.cut_holes():
        msp.add_circle(tf(u, v), _r(d / 2), dxfattribs={"layer": "CUT"})
    for mark in p.marks:
        msp.add_lwpolyline([tf(u, v) for u, v in mark[:-1]], close=True,
                           dxfattribs={"layer": "ENGRAVE"})
    inner = p.shape.buffer(-2 * panels.LABEL_H)
    at = (inner if not inner.is_empty else p.shape).representative_point()
    x, y = tf(at.x, at.y)
    msp.add_text(p.name, height=panels.LABEL_H,
                 dxfattribs={"layer": "ENGRAVE", "insert": (x, y)})
    reproducible.normalise_dxf(doc)
    doc.saveas(str(path))
    return size


def write_printed(lay, t, out: Path) -> None:
    import export_printed as ep
    parts = fittings.printed_parts(lay, t)
    out.mkdir(parents=True, exist_ok=True)
    keep = {f"{n}.{ext}" for n in parts for ext in ("step", "stl")}
    for old in sorted(out.iterdir()):
        if old.is_file() and old.name not in keep:
            old.unlink()
    for name, p in parts.items():
        shape = body.posed(p)
        ep.write_step(shape, out / f"{name}.step")
        ep.write_stl(shape, out / f"{name}.stl")
        bb = shape.BoundingBox()
        print(f"  printed {name:26s} {bb.xlen:7.2f} x {bb.ylen:7.2f} x {bb.zlen:6.2f} mm")


def write_assembly(path: Path) -> None:
    import cadquery as cq
    assy = cq.Assembly(name="tt-demo-box-laser")
    for name, shape, _colour in body.assembly("laser", LID_OPEN_DEG, 0.0):
        assy.add(shape, name=name)
    assy.export(str(path), "STEP")
    reproducible.normalise_step(path, name=path.stem)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--thickness", type=float, default=ROUTES["laser"],
                    help="plywood thickness, mm (default %(default)s)")
    ap.add_argument("--kerf", type=float, default=panels.KERF,
                    help="laser kerf, mm (default %(default)s)")
    ap.add_argument("--out", type=Path, default=OUT, help="output directory")
    ap.add_argument("--no-printed", action="store_true",
                    help="only the DXFs and the hardware list")
    a = ap.parse_args(argv)
    t, kerf = a.thickness, a.kerf
    if not (t > 0 and kerf >= 0 and math.isfinite(t) and math.isfinite(kerf)):
        ap.error("thickness must be > 0 and kerf >= 0")
    lay = layout(t)
    built = panels.build(lay, t, kerf)            # raises BedOverflow before writing
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    o = lay.outer
    print(f"laser route: {t:g} mm plywood, kerf {kerf:g} mm; base {o.size[0]:.2f} x "
          f"{o.size[1]:.2f} x {o.size[2]:.2f} mm")
    keep = {f"{n}.dxf" for n in built.panels} | {"hardware.txt", "assembly.step"}
    for old in sorted(out.iterdir()):
        if old.is_file() and old.name not in keep:
            old.unlink()
    for name, p in built.panels.items():
        w, h = write_dxf(p, out / f"{name}.dxf")
        print(f"  {name:24s} {w:7.2f} x {h:6.2f} mm  {p.note}")
    for s in built.seams:
        print(f"  seam: {s.name} split at {s.axis} = {s.at:.2f} into {', '.join(s.pieces)}")
    hw = fittings.hardware(lay, t)
    (out / "hardware.txt").write_text(
        f"Laser route hardware ({t:g} mm plywood)\n\n"
        + "".join(f"{n:4d}  {k}\n" for k, n in hw.items()))
    print("hardware:\n" + "".join(f"  {n:4d}  {k}\n" for k, n in hw.items()), end="")
    if not a.no_printed:
        write_printed(lay, t, out / "printed")
        if abs(t - ROUTES["laser"]) < 1e-9:
            write_assembly(out / "assembly.step")
            print(f"assembly: lid at {LID_OPEN_DEG:g} deg, drawer shut")
    return 0


if __name__ == "__main__":
    sys.exit(main())
