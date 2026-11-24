"""Off-the-shelf cables and adapters (spec "Cable sourcing").

``dia`` is the cable outside diameter, ``min_bend_r`` its minimum bend radius
(typically 6-8 x diameter for the thin ones), ``plug`` the moulded plug body
(L, W, H).  No product is named in the spec, so every figure is a typical-part
placeholder and ``confirmed`` is False: replace with the bought cable's own
stated numbers (calipers on the plug, vendor spec for the bend radius).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

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
           "Cable sourcing: \"a slim, short (<= 0.5 m) VGA cable\"."),
    _cable("vga-90-adapter", "VGA 90 degree adapter", 5.0, 30.0, (35.0, 17.0, 20.0),
           "Cable sourcing: \"with a 90 degree adapter where a monitor's socket faces "
           "backwards\"; the ~20 mm run behind it is the tinyvga.py ANGLED_RUN (paraphrase)."),
    _cable("usb-c-right-angle", "USB-C right-angle cable", 3.5, 20.0, (20.0, 9.0, 8.5),
           "Cable sourcing: \"USB: short right-angle cables.\""),
    _cable("usb-a-c", "USB-A to USB-C cable", 3.5, 20.0, (22.0, 13.0, 7.0),
           "Cables and adapters: \"Bank to dev board: USB-A or USB-C to USB-C, right-angle at the board end preferred.\""),
    _cable("usb-12v-boost", "USB to 12 V DC (5.5 x 2.1) boost cable (Tim's adapter)", 4.0,
           25.0, (60.0, 20.0, 15.0),
           "Cables and adapters: \"a USB to 12 V DC (5.5 x 2.1) boost cable. The boost "
           "module must have a place to sit.\" Module body size is a placeholder (measure it)."),
    _cable("bank-built-in", "Power bank built-in USB-C cable", 4.0, 20.0, (20.0, 9.0, 8.5),
           "Battery survey: UGREEN PB505, Xiaomi PB2020 and Anker Zolo list \"built-in C\"; "
           "cable and plug body are not stated, so the USB-C right-angle figures are used. "
           "Unconfirmed."),
    # Ruling R13: the monitor's own cable, not a bought one.  Its plug is the
    # slim VGA cable's typical body.
    # Rulings R13, R17: the monitor's own cable, not a bought one.  Its plug
    # is the slim VGA cable's typical body.
    Cable("monitor-pigtail", "Monitor's own hard-wired VGA cable (pigtail)", 5.0, 15.0,
          (45.0, 17.0, 20.0), (
              Source("Placeholder: Tim's monitor's own hard-wired cable",
                     "docs/measurements/2026-11-23-photo-measurements.md",
                     "Placeholder: 3 x dia for a static bend; this value decides the layout "
                     "(at 20 mm the VGA plug cannot sit in the bank-row corner and the box "
                     "grows to about 208 x 209 mm); measure Tim's cable."),
          ), confirmed=False),
)}

# Ruling R16a: the adapter's orientation is assumed, not read off a part.
CABLES["vga-90-adapter"] = replace(CABLES["vga-90-adapter"], sources=CABLES[
    "vga-90-adapter"].sources + (Source(
        "Placeholder: adapter orientation", _SPEC,
        "left/right-angle type assumed (socket on the D-sub's end, facing the back of the "
        "box); check the one bought; an up/down type changes the layout"),))
