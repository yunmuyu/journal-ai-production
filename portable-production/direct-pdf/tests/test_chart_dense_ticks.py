import pytest

from journal_pdf.charts import choose_tick_rotation
from journal_pdf.common import FigureError


def test_dense_ticks_rotate_before_reducing_size():
    measurements=[{'ink':[0,0,10,5]},{'ink':[0,0,10,5]}]
    assert choose_tick_rotation([0,9],measurements,2)==90
    assert choose_tick_rotation([0,15],measurements,2)==0


def test_dense_ticks_reject_when_even_rotated_labels_cannot_fit():
    with pytest.raises(FigureError,match='刻度'):
        choose_tick_rotation([0,6],[{'ink':[0,0,10,5]}]*2,2)
