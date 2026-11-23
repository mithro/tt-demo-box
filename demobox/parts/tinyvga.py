"""The TinyVGA Pmod (mole99/tiny-vga) and its DE-15 plug keep-out.

Frame: the TinyVGA *plug frame*, the same orientation as a host board's frame.
X runs along the Pmod edge; Y = 0 is the TinyVGA PCB's host-side edge; the PCB
and the DE-15 lie at NEGATIVE Y, i.e. away from the host (as a host's Pmod
sockets overhang to its negative Y); the Pmod pins stick out to positive Y into
the host socket.  Z = 0 is the PCB underside.

The downstream fact is the distance from the host board's Pmod edge to the
DE-15 face when plugged in: ``reach_from_host_edge``.  Fully inserted, the PCB
edge sits at the host socket's mouth (host Y = ``body_y0`` of the host Pmod,
-8.55 mm), so the DE-15 face is at host Y = body_y0 + de15.y0.

Heights and plug dimensions are NOT in the KiCad file (no 3D model is
extracted), so they are typical-part placeholders and ``confirmed`` is False.
"""

from __future__ import annotations

from tools.schema import Source

from demobox.geom import Box
from demobox.parts import tinyvga_data as _d
from demobox.parts.board import PmodBoard, board_spec

_E = _d.EXTRACTED
_T = _E["thickness"]

#: Typical HD DE-15 shell height above the PCB top (not in the repo).
DE15_HEIGHT = 12.5
#: Moulded VGA plug body length past the socket face; hood height.  Typical.
PLUG_BODY_LEN = 17.0
PLUG_HEIGHT = 20.0
STRAIGHT_RUN = 40.0   # spec: stiff cable run behind a straight plug
ANGLED_RUN = 20.0     # spec: with a 90 degree adapter
HEADER_HEIGHT = 2.5   # right-angle 2x6 header body above the PCB top


def _box(xyxy, z0, z1, what):
    x0, y0, x1, y1 = xyxy
    return Box(x0, y0, z0, x1, y1, z1, what)


_pcb = _box(_E["pcb"], 0.0, _T, "TinyVGA PCB")
_de15 = _box(_E["de15"], _T, _T + DE15_HEIGHT, "TinyVGA DE-15 socket")

TINYVGA = PmodBoard(
    key="tinyvga",
    pcb=_pcb,
    de15=_de15,
    header=_box(_E["header"], _T, _T + HEADER_HEIGHT, "TinyVGA Pmod header"),
    sources=_d.SOURCES + (Source(
        label="Typical-part heights (placeholder)",
        ref="generic HD DE-15 shell and moulded VGA plug",
        note="DE-15 height, plug body/height are not in the KiCad file."),),
    confirmed=False,
    plug_body_len=PLUG_BODY_LEN,
    straight_run=STRAIGHT_RUN,
    angled_run=ANGLED_RUN,
    plug_width=_de15.size[0],
    # plug axis ~ mid shell height; hood PLUG_HEIGHT tall centred on it
    plug_z0=_T + DE15_HEIGHT / 2 - PLUG_HEIGHT / 2,
    plug_z1=_T + DE15_HEIGHT / 2 + PLUG_HEIGHT / 2,
)


def reach_from_host_edge(host_key: str, pmod_key: str = "pmod3") -> float:
    """Distance from the host board's Pmod edge (host Y = 0) to the DE-15 face
    with the TinyVGA fully plugged into ``pmod_key`` (the TinyVGA is a Pmod
    OUTPUT peripheral, so pmod3 by default)."""
    pmod = next(p for p in board_spec(host_key).pmods if p.key == pmod_key)
    return -(pmod.body_y0 + TINYVGA.de15.y0)
