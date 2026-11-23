import demobox  # noqa: F401
from tinytapeout.boards import BOARDS


def test_submodule_boards_importable():
    assert BOARDS["v3.2"].outline.width == 85.0 and BOARDS["v3.2"].outline.height == 80.0
    assert BOARDS["v3.3"].outline.height == 85.0
