import fitz
from journal_pdf.render import draw_path
from types import SimpleNamespace


def test_standard_arrow_retains_both_arrowheads():
    with fitz.open() as document:
        page=document.new_page(width=100,height=100)
        draw_path(page,{'points':[[20,50],[80,50]],'width':.5,'arrow':True,'both':True,'dash':[]})
        drawings=page.get_drawings()
        assert sum(item.get('fill') == (0.0,0.0,0.0) for item in drawings) == 2


def test_block_outline_arrow_has_white_interior_over_background_line():
    with fitz.open() as document:
        page=document.new_page(width=100,height=100)
        page.draw_line((50,20),(50,80),color=(0,0,0),width=1)
        draw_path(page,{'points':[[20,50],[80,50]],'width':.5,'arrow_style':'block-outline','arrow':True,'both':True})
        pix=page.get_pixmap(matrix=fitz.Matrix(4,4),colorspace=fitz.csGRAY,alpha=False)
        assert pix.pixel(200,200)[0]>245
        assert pix.pixel(200,160)[0]<100


def test_arrow_is_drawn_above_node_boundary_even_when_node_is_drawn_later():
    from journal_pdf.render import draw_scene_elements
    with fitz.open() as document:
        page=document.new_page(width=100,height=100)
        from journal_pdf.scene import Scene
        scene=Scene(None)
        scene.nodes=[{'id':'frame','kind':'rectangle','rect':[50,20,80,80],'width':1}]
        scene.paths=[{'id':'arrow','points':[[20,50],[80,50]],'width':.5,'arrow_style':'block-outline','arrow':True,'both':True}]
        draw_scene_elements(page,scene,None,None)
        pix=page.get_pixmap(matrix=fitz.Matrix(4,4),colorspace=fitz.csGRAY,alpha=False)
        assert pix.pixel(200,200)[0]>245
        assert pix.pixel(200,160)[0]<100
