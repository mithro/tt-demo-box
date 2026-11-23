"""Off-the-shelf cables and adapters (spec "Cable sourcing").

``dia`` is the cable outside diameter, ``min_bend_r`` its minimum bend radius
(typically 6-8 x diameter for the thin ones), ``plug`` the moulded plug body
(L, W, H).  No product is named in the spec, so every figure is a typical-part
placeholder and ``confirmed`` is False: replace with the bought cable's own
stated numbers (calipers on the plug, vendor spec for the bend radius).
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.schema import Source

_SPEC = "docs/superpowers/specs/2026-11-23-tt-demo-box-design.md"


@dataclass(frozen=True)
class Cable:
    key: str
    title: str
    dia: float
    min_bend_r: float
    plug: tuple[float, float, float]
    sources: tuple[Source, ...]
    confirmed: bool


def _cable(key, title, dia, bend, plug, quote):
    return Cable(key, title, dia, bend, plug, (
        Source(f"Spec: {title}", _SPEC, quote),
        Source("Placeholder: typical-part figures", _SPEC,
               "Diameter, bend radius and plug body are typical values; measure the "
               "bought cable."),
    ), confirmed=False)


CABLES: dict[str, Cable] = {c.key: c for c in (
    _cable("vga-slim", "Slim VGA cable, <= 0.5 m", 5.0, 30.0, (45.0, 17.0, 20.0),
           "Cable sourcing: slim, short (<= 0.5 m) VGA cable."),
    _cable("vga-90-adapter", "VGA 90 degree adapter", 5.0, 30.0, (35.0, 17.0, 20.0),
           "Cable sourcing: 90 degree adapter where a socket faces backwards; "
           "shortens the plug run to ~20 mm."),
    _cable("usb-c-right-angle", "USB-C right-angle cable", 3.5, 20.0, (20.0, 9.0, 8.5),
           "Cable sourcing: short right-angle USB cables, right-angle at the board end."),
    _cable("usb-a-c", "USB-A to USB-C cable", 3.5, 20.0, (22.0, 13.0, 7.0),
           "Bank to dev board: USB-A or USB-C to USB-C."),
    _cable("usb-12v-boost", "USB to 12 V DC (5.5 x 2.1) boost cable (Tim's adapter)", 4.0,
           25.0, (60.0, 20.0, 15.0),
           "Tim's Shenzhen adapter: cable with a boost converter in line; the module "
           "body size is a placeholder (measure it); the boost module needs a place to sit."),
)}
