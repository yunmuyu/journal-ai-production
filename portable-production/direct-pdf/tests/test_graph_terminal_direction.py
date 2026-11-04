from journal_pdf.graph_layout import _route


def test_target_stub_cannot_be_entered_backwards():
    # A left-side port extends from the destination stub toward the right.
    # Entering that stub from the right creates a U-turn and loses arrow length.
    points = _route([3, 0], [0, 0], [], [0, 3], [0, 10], forbidden_end_direction=(-1, 0))
    previous, endpoint = points[-2:]
    assert previous[1] != endpoint[1] or previous[0] <= endpoint[0]
    assert points[0] == [3, 0]
    assert endpoint == [0, 0]
