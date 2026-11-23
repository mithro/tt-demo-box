"""Hidden-line projection of a solid onto the three views a sheet draws.

``project(shape, view)`` runs OpenCascade's exact hidden-line removal
(``HLRBRep_Algo`` + ``HLRBRep_HLRToShape``) and hands back the visible and the
hidden edges as polylines in model millimetres, each edge discretised to a
CHORD (0.1 mm) deflection.

The views, first-angle (ISO 128-30), in the base frame of ``demobox.layout``:

* ``front``: seen from the visitor (from -Y): across = X, up = Z;
* ``side``: seen from the left (from -X), drawn to the RIGHT of the front:
  across = -Y (the visitor's side is on the right), up = Z;
* ``plan``: seen from above (from +Z), drawn BELOW the front: across = X,
  up = Y (the hinge at the top, the visitor's side towards the bottom).

Edges are what OpenCascade calls sharp edges and outlines (silhouettes of
curved faces); smooth seams between tangent faces are left out, as a drawing
leaves them out.  Hidden detail that lies on a visible line (a box's back
edges, behind its front ones) is dropped, as a drawing drops it: a dashed
line printed over a solid one is noise.

Projections are cached on disk under ``tmp/hlr`` by a hash of the shape's
BREP and the view, because the bodies take seconds each and every sheet run
asks for the same ones.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBndLib import BRepBndLib
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.GeomAbs import GeomAbs_Line
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from demobox._paths import ROOT

View = Literal["front", "side", "plan"]

#: Chord deflection for discretising curved edges, mm.
CHORD = 0.1

#: For each view: the direction OpenCascade's projector looks back along
#: (towards the viewer) and its X direction, the sheet's "across".
_AXES: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "front": ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0)),
    "side": ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0)),
    "plan": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
}

CACHE = ROOT / "tmp" / "hlr"
#: Bump when the projection's output changes for the same input.
_CACHE_VERSION = 2

Polyline = list[tuple[float, float]]


@dataclass
class Projection:
    visible: list[Polyline] = field(default_factory=list)
    hidden: list[Polyline] = field(default_factory=list)

    def bbox(self) -> tuple[float, float, float, float]:
        """(x0, y0, x1, y1) of the visible edges."""
        xs = [x for pl in self.visible for x, _ in pl]
        ys = [y for pl in self.visible for _, y in pl]
        return min(xs), min(ys), max(xs), max(ys)


def exact_bbox(shape: cq.Shape) -> tuple[float, float, float, float, float, float]:
    """(xmin, ymin, zmin, xmax, ymax, zmax) from the geometry itself, with no
    triangulation and no tolerance gap (``BRepBndLib.AddOptimal``):
    ``Shape.BoundingBox`` pads by the shape's tolerance."""
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, box, False, False)
    return box.Get()


def view_bbox(shape: cq.Shape, view: View) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) of the solid's exact bounding box in ``view``'s axes.

    The overall sizes are dimensioned from this, not from the projected
    polylines: those are discretised, and a circle's chords fall inside it
    (a 16.00 hinge profile measured 15.98 off its knuckle's polygon)."""
    x0, y0, z0, x1, y1, z1 = exact_bbox(shape)
    corners = [to_view(view, (x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    return (round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4))


def to_view(view: View, p: tuple[float, float, float]) -> tuple[float, float]:
    """A model point's (across, up) in ``view``, the same mapping as ``project``."""
    x, y, z = p
    return {"front": (x, z), "side": (-y, z), "plan": (x, y)}[view]


def _polylines(compound, chord: float = CHORD) -> list[Polyline]:
    out: list[Polyline] = []
    if compound is None or compound.IsNull():
        return out
    exp = TopExp_Explorer(compound, TopAbs_EDGE)
    while exp.More():
        edge = TopoDS.Edge_s(exp.Current())
        exp.Next()
        curve = BRepAdaptor_Curve(edge)
        a, b = curve.FirstParameter(), curve.LastParameter()
        if curve.GetType() == GeomAbs_Line:
            pts = [curve.Value(a), curve.Value(b)]
        else:
            d = GCPnts_QuasiUniformDeflection(curve, chord, a, b)
            if not d.IsDone() or d.NbPoints() < 2:
                pts = [curve.Value(a), curve.Value(b)]
            else:
                pts = [d.Value(i) for i in range(1, d.NbPoints() + 1)]
        pl = [(round(p.X(), 4), round(p.Y(), 4)) for p in pts]
        if len(pl) >= 2 and any(q != pl[0] for q in pl[1:]):
            out.append(pl)
    return out


def _hlr(shape: cq.Shape, view: View, chord: float = CHORD) -> Projection:
    toward, across = _AXES[view]
    algo = HLRBRep_Algo()
    algo.Add(shape.wrapped)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*toward), gp_Dir(*across))))
    algo.Update()
    algo.Hide()
    h = HLRBRep_HLRToShape(algo)
    visible = _polylines(h.VCompound(), chord) + _polylines(h.OutLineVCompound(), chord)
    hidden = _polylines(h.HCompound(), chord) + _polylines(h.OutLineHCompound(), chord)
    return Projection(visible, _off_visible(hidden, visible))


#: Hidden detail within this of a visible line is on it, mm; and a hidden
#: piece left shorter than SCRAP is dropped.
ON_LINE = 0.05
SCRAP = 0.3


def _off_visible(hidden: list[Polyline], visible: list[Polyline]) -> list[Polyline]:
    """The parts of the hidden polylines not lying on a visible one."""
    if not hidden:
        return []
    from shapely.geometry import LineString, MultiLineString
    from shapely.ops import unary_union
    cover = unary_union([LineString(pl) for pl in visible]).buffer(ON_LINE, cap_style=2)
    out: list[Polyline] = []
    for pl in hidden:
        rest = LineString(pl).difference(cover)
        parts = rest.geoms if isinstance(rest, MultiLineString) else [rest]
        for g in parts:
            if g.geom_type == "LineString" and g.length >= SCRAP:
                out.append([(round(x, 4), round(y, 4)) for x, y in g.coords])
    return out


def _key(shape: cq.Shape, view: View, chord: float) -> str:
    buf = io.BytesIO()
    shape.exportBrep(buf)
    h = hashlib.sha256(buf.getvalue())
    h.update(f"{view}/{chord}/{_CACHE_VERSION}".encode())
    return h.hexdigest()[:32]


def project(shape: cq.Shape, view: View, cache: Path | None = CACHE,
            chord: float = CHORD) -> Projection:
    """Visible and hidden edges of ``shape`` in ``view``, as polylines in
    model mm (see the module docstring for the axes).  ``chord`` is the
    discretising deflection: CHORD by default, finer for a part drawn
    enlarged, where 0.1 mm of model is half a millimetre of paper."""
    if view not in _AXES:
        raise ValueError(f"unknown view {view!r}; views are {sorted(_AXES)}")
    path = None
    if cache is not None:
        path = cache / f"{_key(shape, view, chord)}.json"
        if path.exists():
            d = json.loads(path.read_text())
            return Projection([[tuple(p) for p in pl] for pl in d["visible"]],
                              [[tuple(p) for p in pl] for pl in d["hidden"]])
    p = _hlr(shape, view, chord)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"visible": p.visible, "hidden": p.hidden}))
    return p
