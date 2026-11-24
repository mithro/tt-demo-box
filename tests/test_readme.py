"""README.md's generated sections (scripts/update_readme.py, finding 5)."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location("update_readme",
                                                  ROOT / "scripts" / "update_readme.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rewrite_replaces_only_between_the_markers():
    u = _mod()
    text = ("intro\n<!-- hardware-laser:begin -->\n| 1 | old |\n<!-- hardware-laser:end -->\n"
            "outro\n")
    new = u.rewrite(text, {"hardware-laser": u.table({"M3 square nut": 40, "magnet": 2})})
    assert new == ("intro\n<!-- hardware-laser:begin -->\n| Qty | Part |\n|---:|---|\n"
                   "| 40 | M3 square nut |\n| 2 | magnet |\n<!-- hardware-laser:end -->\noutro\n")
    with pytest.raises(SystemExit):
        u.rewrite("no markers\n", {"hardware-laser": []})


def test_readme_has_every_generated_section():
    u = _mod()
    text = (ROOT / "README.md").read_text()
    for name in u.SECTIONS:
        begin, end = u._markers(name)
        assert text.count(begin) == 1 and text.count(end) == 1, name
        assert text.index(begin) < text.index(end), name


def test_readme_hardware_tables_are_the_routes_lists():
    """The hand-copied tables went stale silently; now they are the routes'
    hardware() lists, and check-readme guards them."""
    u = _mod()
    text = (ROOT / "README.md").read_text()
    for name in ("hardware-printed", "hardware-laser"):
        made = u.SECTIONS[name]()
        assert u.rewrite(text, {name: made}) == text, f"{name} stale: run make readme"
