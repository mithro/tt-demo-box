#!/usr/bin/env python3
"""Write the printed route's parts as STEP and STL, and the assembly as STEP.

Every part from ``demobox.printed.body.printed_parts(layout(2.4))`` is written
lying as it prints (``posed``: turned onto the bed, its bounding box's corner
at the origin), so a slicer takes it as it comes:

* ``output/printed/<part>.step`` -- written by CadQuery, then its header
  pinned by the submodule's ``tools.reproducible.normalise_step``;
* ``output/printed/<part>.stl`` -- meshed to STL_TOLERANCE.

``output/printed/assembly.step`` is the box with the lid at the stop and the
drawer shut (``body.assembly``), one named solid per part (no colours: see
``write_assembly``).

A part bigger than the bed fails the export with ``BedOverflow`` naming it and
its size (a base or lid is first split, see ``body``); nothing is written.
Files in ``output/printed`` that are no longer produced are removed.

Run: make outputs
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cadquery as cq  # noqa: E402

import demobox  # noqa: E402,F401  (puts the submodule on sys.path)
from demobox.layout import LID_OPEN_DEG, ROUTES, layout  # noqa: E402
from demobox.printed import body  # noqa: E402
from tools import reproducible  # noqa: E402

OUT = ROOT / "output" / "printed"
#: STL chord tolerance (mm) and angular tolerance (radians).
STL_TOLERANCE = 0.05
STL_ANGULAR = 0.1


def write_step(shape: cq.Shape, path: Path) -> None:
    cq.exporters.export(cq.Workplane("XY").add(shape), str(path), "STEP")
    reproducible.normalise_step(path, name=path.stem)


def write_stl(shape: cq.Shape, path: Path) -> None:
    cq.exporters.export(cq.Workplane("XY").add(shape), str(path), "STL",
                        tolerance=STL_TOLERANCE, angularTolerance=STL_ANGULAR)


def write_assembly(path: Path) -> None:
    """One named solid per part.  Without colours: OpenCascade writes the
    colour entities in an order that changes from run to run, so a coloured
    file would never rebuild byte for byte; the colours are in
    ``body.assembly`` for the renders."""
    assy = cq.Assembly(name="tt-demo-box")
    for name, shape, _colour in body.assembly("printed", LID_OPEN_DEG, 0.0):
        assy.add(shape, name=name)
    assy.export(str(path), "STEP")
    reproducible.normalise_step(path, name=path.stem)


def main() -> int:
    lay = layout(ROUTES["printed"])
    parts = body.printed_parts(lay)          # raises BedOverflow before writing
    OUT.mkdir(parents=True, exist_ok=True)
    keep = {f"{n}.{ext}" for n in parts for ext in ("step", "stl")} | {"assembly.step"}
    for old in sorted(OUT.iterdir()):
        if old.is_file() and old.name not in keep:
            old.unlink()
            print(f"removed {old.relative_to(ROOT)}")
    for name, p in parts.items():
        shape = body.posed(p)
        bb = shape.BoundingBox()
        write_step(shape, OUT / f"{name}.step")
        write_stl(shape, OUT / f"{name}.stl")
        print(f"{name:28s} {bb.xlen:7.2f} x {bb.ylen:7.2f} x {bb.zlen:6.2f} mm  {p.note}")
    write_assembly(OUT / "assembly.step")
    print(f"assembly: lid at {LID_OPEN_DEG:g} deg, drawer shut")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.stat().st_size:>10,d}  {f.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
