import pytest

from journal_pdf.charts import place_bar_top_labels
from journal_pdf.common import FigureError


def measured(runs):
    text=''.join(run['text'] for run in runs)
    width=len(text)*3.1
    return {'text':text,'ink':[0,-5,width,2],'width':width,'height':7,'size':7,'glyphs':[]}


def test_nine_bar_labels_share_one_ink_gap_and_clear_horizontally():
    groups=[]
    values=['0.69','0.58','0.63','0.76','0.79','0.77','0.82','0.83','0.82']
    for group in range(3):
        bars=[]
        for item in range(3):
            cx=40+group*65+item*21
            bars.append({'rect':[cx-6,30+item,cx+6,105],
                         'runs':[{'text':values[group*3+item],'face':'latin'}]})
        groups.append(bars)
    labels,evidence=place_bar_top_labels(groups,measured,ink_gap_pt=2,
                                         min_horizontal_gap_pt=2,plot_rect=[0,0,230,110])
    assert len(labels)==9
    assert evidence['actual_ink_gaps_pt']==pytest.approx([2]*9)
    assert evidence['minimum_horizontal_gap_pt']>=2


def test_bar_label_collision_is_rejected():
    groups=[[{'rect':[10,20,20,80],'runs':[{'text':'0.79'}]},
             {'rect':[21,20,31,80],'runs':[{'text':'0.77'}]}]]
    with pytest.raises(FigureError) as error:
        place_bar_top_labels(groups,measured,ink_gap_pt=2,
                             min_horizontal_gap_pt=2,plot_rect=[0,0,100,100])
    assert error.value.code=='bar_label_collision'
