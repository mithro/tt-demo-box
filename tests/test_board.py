import pytest

from demobox.parts import board


def test_envelope_covers_pcb_pmod_and_usb():
    for key in board.BOARD_KEYS:
        spec = board.board_spec(key)
        env = board.board_envelope(key)
        assert env.x0 <= 0 and env.x1 >= spec.outline.width
        assert env.y0 == min(p.body_y0 for p in spec.pmods) < 0     # Pmod overhang
        usb = next(f for f in spec.features if f.kind == "usb_power")
        assert env.y1 == max(spec.outline.height, usb.y1)           # USB-C shell
        assert (env.z0, env.z1) == (0.0, board.TALLEST_COMPONENT)


def test_only_two_boards_and_dims():
    assert board.BOARD_KEYS == ("v3.2", "v3.3")
    assert board.board_spec("v3.2").outline.height == 80.0
    assert board.board_spec("v3.3").outline.height == 85.0
    assert board.TALLEST_COMPONENT == 12.0 and board.TALLEST_COMPONENT_CONFIRMED is False
    with pytest.raises(KeyError):
        board.board_spec("v1.2.1")
