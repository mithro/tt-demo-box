"""The design rulings the code cites (R1, R16a, ...) are defined in a
committed document, so the comments resolve after the working ledger is
gone (final review I5, ruling R36)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "superpowers" / "specs" / "2026-11-24-compact-box-rulings.md"
SPEC = ROOT / "docs" / "superpowers" / "specs" / "2026-11-24-compact-box-design.md"
#: A ruling ID: R, a number under 100, an optional letter ("R2010" is a DXF
#: version, "R4.00" a radius).
CITED = re.compile(r"\bR(\d{1,2}[a-z]?)\b(?!\.\d)")


def _cited() -> set[str]:
    files = [ROOT / "verify.py", *(ROOT / "demobox").rglob("*.py"),
             *(ROOT / "scripts").rglob("*.py"),
             *(f for f in (ROOT / "tests").rglob("*.py") if f.name != "test_rulings.py")]
    return {m for f in files for m in CITED.findall(f.read_text())}


def _defined() -> list[str]:
    return re.findall(r"^### R(\d{1,2}[a-z]?)\b", DOC.read_text(), re.MULTILINE)


def test_every_cited_ruling_is_defined():
    missing = sorted(_cited() - set(_defined()), key=lambda r: (int(re.match(r"\d+", r)[0]), r))
    assert not missing, f"cited but not in {DOC.name}: {missing}"


def test_rulings_r1_to_r36_each_say_what_why_and_cost():
    text = DOC.read_text()
    ids = _defined()
    assert len(ids) == len(set(ids))
    numbers = {int(re.match(r"\d+", r)[0]) for r in ids}
    # R20 was never issued (the ledger went from R19 to R21); the doc says so
    assert numbers | {20} == set(range(1, 37))
    assert "R20" in text
    for block in re.split(r"^### ", text, flags=re.MULTILINE)[1:]:
        head = block.splitlines()[0]
        for field in ("**What:**", "**Why:**", "**Cost if wrong:**"):
            assert field in block, (head, field)


def test_the_spec_points_at_the_rulings():
    head = "\n".join(SPEC.read_text().splitlines()[:15])
    assert DOC.name in head


def test_fittings_cites_the_rulings_doc():
    text = (ROOT / "demobox" / "laser" / "fittings.py").read_text()
    assert DOC.name in text
