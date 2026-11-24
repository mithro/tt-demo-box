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


def test_readme_size_and_rods_are_generated():
    """R34: the size table and the hinge rod lengths were typed by hand and
    could go stale; they are generated sections now, from the layout and the
    routes' hardware, rounded as the sheets round (``geom.mm``)."""
    import demobox  # noqa: F401
    from demobox.geom import mm
    from demobox.layout import ROUTES, layout
    from demobox.shared import hinge as H
    u = _mod()
    assert {"size", "rods"} <= set(u.SECTIONS)
    size = "\n".join(u.SECTIONS["size"]())
    rods = "\n".join(u.SECTIONS["rods"]())
    for route, wall in ROUTES.items():
        lay = layout(wall)
        o, lid = lay.outer, lay.lid_outer
        assert f"{mm(o.size[0])} x {mm(o.size[1])} x {mm(o.size[2] + lid.size[2])} mm" in size
        litres = o.size[0] * o.size[1] * (o.size[2] + lid.size[2]) / 1e6
        assert f"{litres:.2f} L" in size
        assert f"{H.pin_length(lay):.1f} mm" in rods and route in rods
    assert "steel" in rods
    text = (ROOT / "README.md").read_text()
    for name in ("size", "rods"):
        assert u.rewrite(text, {name: u.SECTIONS[name]()}) == text, f"{name} stale: make readme"


def test_readme_drops_what_the_box_no_longer_uses():
    """R34, R35: no slim VGA cable (the monitor's own pigtail plugs in), no
    filament hinge rod, and the board's orientation as laid out (J1 at -X)."""
    text = (ROOT / "README.md").read_text()
    assert "vga-slim" not in text and "slim VGA" not in text
    assert "filament" not in text
    assert "turns 180 degrees" not in text
    for field in ("pigtail_len", "pigtail_exit_u", 'cable_edge="bottom"'):
        assert field in text, field
    assert "## Assembly" in text and "opposite poles" in text
