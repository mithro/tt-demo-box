"""20,000 mAh class USB-C power banks (docs/superpowers/specs/battery-survey.md).

``size`` is (L, W, H) from the manufacturer spec pages in the survey.
``button`` is (face, u, v): the face the button is on and its position along
that face's two axes (u along L, v along W, or along H for end faces); the
positions are placeholders, so ``confirmed`` is False for every entry -- measure
each bank's button and port face.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tools.schema import Source

_SURVEY = "docs/superpowers/specs/battery-survey.md"


@dataclass(frozen=True)
class Battery:
    key: str
    title: str
    size: tuple[float, float, float]
    port_face: Literal["end", "top", "side"]
    button: tuple[str, float, float] | None
    sources: tuple[Source, ...]
    confirmed: bool


def _bank(key, title, size, port_face, button, line, note=""):
    return Battery(
        key=key, title=title, size=size, port_face=port_face, button=button,
        sources=(
            Source(f"Survey candidate: {title}", _SURVEY, line),
            Source("Placeholder: button position, port face", _SURVEY,
                   "Not in the survey; measure the button and the port face." + note),
        ),
        confirmed=False)


BATTERIES: dict[str, Battery] = {b.key: b for b in (
    _bank("iniu-p512", "INIU P512 20000 mAh", (104, 70, 29), "end", ("end", 35.0, 14.5),
          "#2: 20000 / 74 Wh, 104 x 70 x 29 mm, 314 g, 2C + A, 12 V PDO, "
          "5V 3A 15W multi-port; AU$49.73; iniushop.com"),
    _bank("ugreen-pb505", "UGREEN PB505 (built-in cable)", (116.22, 70.55, 30.03), "end",
          ("end", 35.275, 15.015),
          "#3: 20000 / 74 Wh, 116.22 x 70.55 x 30.03 mm, 338 g, built-in C + C + A all "
          "on the top face; chargerlab.com teardown",
          " The survey says 'all on top face'; read as the short top end -- ports on a "
          "broad face could not be used in any slim bay; confirm on the real unit."),
    _bank("xiaomi-pb2020", "Xiaomi 20000 integrated cable PB2020", (128, 73, 32), "end",
          ("end", 36.5, 16.0),
          "#4: 20000 / 74 Wh, 128 x 73 x 32 mm, 342 g, built-in C + C + A; mi.com"),
    _bank("anker-zolo-20k", "Anker Zolo 20K A1689", (119.9, 73.4, 31.5), "end",
          ("end", 36.7, 15.75),
          "#5: 20000 mAh, 119.9 x 73.4 x 31.5 mm, 318 g, built-in C + C + A; "
          "anker.com (some batches on the 2025 recall list)"),
)}
