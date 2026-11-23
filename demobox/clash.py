"""The assembly clash test, shared by both build routes.

``clashes(items)`` intersects every pair of an assembly's named solids (the
``(name, shape, colour)`` triples ``printed.body.assembly`` returns) and lists
the pairs whose common volume is more than ``tol``.  Pairs named in
``declared`` (frozensets of two names) are allowed to interpenetrate; each
route declares its own, precisely, rather than exempting whole parts.  Bought
hardware is in the assembly as ``hw:*`` keep-outs, so a screw head or a nut
clashes like any other part.
"""

from __future__ import annotations

import itertools

#: Pairwise common volume (mm^3) below which two solids only touch.
VOL_TOL = 1.0


def clashes(items, declared=frozenset(), tol: float = VOL_TOL) -> list[tuple[str, str, float]]:
    """``(name_a, name_b, volume)`` for every undeclared pair of ``items``
    sharing more than ``tol`` mm^3."""
    bad = []
    for (na, a, _), (nb, b, _) in itertools.combinations(items, 2):
        if frozenset((na, nb)) in declared:
            continue
        ba, bb = a.BoundingBox(), b.BoundingBox()
        if (ba.xmax < bb.xmin or bb.xmax < ba.xmin or ba.ymax < bb.ymin or bb.ymax < ba.ymin
                or ba.zmax < bb.zmin or bb.zmax < ba.zmin):
            continue
        v = a.intersect(b).Volume()
        if v > tol:
            bad.append((na, nb, round(v, 3)))
    return bad
