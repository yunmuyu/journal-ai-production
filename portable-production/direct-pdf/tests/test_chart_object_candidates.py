import importlib.util
from pathlib import Path

import fitz


def load_module():
    root=Path(__file__).resolve().parents[3]
    spec=importlib.util.spec_from_file_location('chart_object_candidates',root/'workbench'/'chart_object_candidates.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_detects_real_frame_and_groups_source_curve_without_claiming_approval():
    module=load_module()
    with fitz.open() as doc:
        page=doc.new_page(width=300,height=200)
        page.draw_rect((40,30,260,150),color=(0,0,0))
        page.draw_polyline([(50,130),(110,100),(170,80),(240,40)],color=(1,0,0))
        page.insert_text((45,166),'1',fontsize=8)
        page.insert_text((20,95),'2',fontsize=8)
        spans=[s for b in page.get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
        result=module.propose_objects(page.rect,page.get_drawings(),spans)
    assert len(result['panels'])==1
    panel=result['panels'][0]
    assert panel['frameDrawingIndices']==[0]
    assert panel['xTicks'] and panel['yTicks']
    assert [axis['orientation'] for axis in panel['axisCandidates']]==['x','y']
    assert all(axis['verified'] is False for axis in panel['axisCandidates'])
    assert panel['curveGroups'][0]['drawingIndices']==[1]
    assert result['status']=='needs_semantic_binding'


def test_unrelated_colored_objects_are_not_automatically_approved():
    module=load_module()
    with fitz.open() as doc:
        page=doc.new_page(width=300,height=200)
        page.draw_rect((40,30,260,150),color=(0,0,0))
        page.draw_line((5,10),(20,10),color=(1,0,0))
        result=module.propose_objects(page.rect,page.get_drawings(),[])
    assert result['panels'][0]['curveGroups']==[]
    assert result['status']=='needs_semantic_binding'


def test_legend_swatch_links_matching_color_as_candidate_only():
    module=load_module()
    with fitz.open() as doc:
        page=doc.new_page(width=300,height=200)
        page.draw_rect((40,30,260,150),color=(0,0,0))
        page.draw_line((50,130),(240,40),color=(1,0,0))
        page.draw_line((80,18),(105,18),color=(1,0,0))
        page.insert_text((110,20),'Series A',fontsize=8)
        spans=[s for b in page.get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
        result=module.propose_objects(page.rect,page.get_drawings(),spans,[{'text':'Series A','bbox':spans[0]['bbox']}])
    legend=result['legendCandidates'][0]
    assert legend['swatchDrawingIndices']==[2]
    assert legend['matchingPanelIds']==['panel-1']
    assert legend['verified'] is False


def test_grayscale_curve_is_proposed_without_copying_other_figures():
    module=load_module()
    with fitz.open() as doc:
        page=doc.new_page(width=300,height=200)
        page.draw_rect((40,30,260,150),color=(0,0,0))
        page.draw_polyline([(50,130),(110,100),(170,80),(240,40)],color=(0,0,0))
        result=module.propose_objects(page.rect,page.get_drawings(),[])
    curves=result['panels'][0]['curveGroups']
    assert len(curves)==1 and curves[0]['drawingIndices']==[1]
    assert curves[0]['verified'] is False


def test_nested_legend_frame_is_not_claimed_as_a_plot():
    module=load_module()
    with fitz.open() as doc:
        page=doc.new_page(width=300,height=200)
        page.draw_rect((40,30,260,150),color=(0,0,0))
        page.draw_rect((180,90,250,140),color=(0,0,0))
        result=module.propose_objects(page.rect,page.get_drawings(),[])
    assert len(result['panels'])==1
    assert len(result['nestedUnclassified'])==1
    assert result['nestedUnclassified'][0]['verified'] is False
