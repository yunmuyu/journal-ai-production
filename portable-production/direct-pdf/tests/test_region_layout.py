import pytest
from journal_pdf.region_layout import horizontal_band,content_region,align_region_bottoms
from journal_pdf.editorial import ARROW_LENGTH
from journal_pdf.common import FigureError


def test_measured_width_changes_reflow_all_following_columns():
    first=horizontal_band([20,30,40],origin=5)
    next=horizontal_band([35,30,40],origin=5)
    assert next[0]==first[0]
    assert next[1]-first[1]==next[2]-first[2]==15
    assert first[1]-first[0]-20==6.5


def test_arrow_channel_reserves_length_and_strokes_at_generation():
    x=horizontal_band([20,30],origin=0,arrow_channels=True)
    assert x[1]-20-.5==pytest.approx(ARROW_LENGTH)


def test_region_tracks_members_title_and_shared_bottom():
    a=content_region([[10,20,30,40]],title_height=12)
    b=content_region([[50,25,70,60]],title_height=12)
    assert a==[3.75,1.75,36.25,46.25]
    align_region_bottoms([a,b]);assert a[3]==b[3]==66.25


def test_invalid_members_and_gaps_cannot_silently_generate():
    with pytest.raises(FigureError):horizontal_band([20],origin=0,minimum_gap=2)
    with pytest.raises(FigureError):content_region([[20,0,10,20]])
