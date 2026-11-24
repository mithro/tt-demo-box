import pytest

from demobox.geom import BedOverflow, Box, Cyl, box_gap, overlaps


def b(x0, x1, y0=0, y1=10, z0=0, z1=10, what="b"):
    return Box(x0, y0, z0, x1, y1, z1, what)


def test_gap_one_mm_in_x():
    assert box_gap(b(0, 10), b(11, 20)) == 1.0


def test_overlap_two_mm_is_negative():
    assert box_gap(b(0, 10), b(8, 20)) == -2.0


def test_touching_is_zero():
    assert box_gap(b(0, 10), b(10, 20)) == 0.0


def test_gap_is_symmetric_and_diagonal_is_euclidean():
    a, c = b(0, 10), b(13, 20, y0=14, y1=20)
    assert box_gap(a, c) == box_gap(c, a) == pytest.approx(5.0)


def test_overlaps_tolerance():
    assert overlaps(b(0, 10), b(8, 20))
    assert not overlaps(b(0, 10), b(8, 20), tol=2.0)
    assert not overlaps(b(0, 10), b(10, 20))


def test_union_covers_both():
    u = b(0, 10, what="a").union(b(20, 30, y0=-5, y1=3, z1=40, what="c"))
    assert (u.x0, u.y0, u.z0, u.x1, u.y1, u.z1) == (0, -5, 0, 30, 10, 40)
    assert u.what == "a+c"


def test_size_and_moved():
    bx = Box(1, 2, 3, 4, 6, 9, "x")
    assert bx.size == (3, 4, 6)
    m = bx.moved(10, 0, -3)
    assert (m.x0, m.x1, m.z0, m.z1) == (11, 14, 0, 6) and m.what == "x"


def test_inverted_box_rejected():
    with pytest.raises(ValueError):
        Box(5, 0, 0, 1, 1, 1, "bad")


def test_cyl_and_bedoverflow():
    assert Cyl(0, 0, 0, 5, 2, "c").r == 2
    assert issubclass(BedOverflow, Exception)


def test_stadium_covers():
    from demobox.geom import Stadium
    s = Stadium(0.0, 0.0, 0.0, 5.0, 3.2, 0.0, 6.0, "slot")
    assert s.covers(0.0, 0.0) and s.covers(0.0, 5.0) and s.covers(3.2, 2.5)
    assert s.covers(0.0, 8.2) and not s.covers(0.0, 8.3)
    assert not s.covers(3.3, 2.5) and not s.covers(2.5, -2.5)


def test_stadium_along_x_covers_its_plane_and_sizes():
    from demobox.geom import Stadium
    s = Stadium(10.0, 5.0, 10.0, 6.5, 10.0, 0.0, 2.4, "finger slot", axis="x")
    assert s.covers(10.0, 15.0) and s.covers(19.9, 5.75) and not s.covers(10.0, 16.6)
    assert s.width == pytest.approx(20.0) and s.length == pytest.approx(21.5)
    with pytest.raises(ValueError):
        Stadium(0, 0, 0, 0, 1, 0, 1, "bad", axis="w")


def test_mm_rounds_once_whatever_the_float_noise():
    """One rounding source for every printed figure: 174.755 reached from a
    solid's bounding box (174.75499999) and from the layout (174.75500002)
    reads the same, half up, never "-0.00"."""
    from demobox.geom import mm
    assert mm(174.75499999999) == mm(174.75500000002) == "174.76"
    assert mm(0.125) == "0.13" and mm(-0.001) == "0.00" and mm(197.7) == "197.70"
