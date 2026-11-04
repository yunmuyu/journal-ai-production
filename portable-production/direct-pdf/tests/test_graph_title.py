import pytest
from journal_pdf.agent_spec import compile_reply_figure
from journal_pdf.render import compile_figure


def test_native_title_binds_without_becoming_box(reg):
    page={'id':'p','kind':'svg','objects':[{'id':'title','text':'示例标题'}, {'id':'a','text':'开始'}, {'id':'b','text':'结束'}]}
    reply={'id':'sample','author':'test','kind':'diagram','title_ref':'title','review':{'source_checked':True,'labels_checked':True,'topology_checked':True},'nodes':[{'id':'a','ref':'a'},{'id':'b','ref':'b'}],'edges':[{'from':'a','to':'b','arrow':False}]}
    spec=compile_reply_figure(reply,{'id':'s','snapshot':'source.svg','sha256':'a'*64},page)
    scene=compile_figure(spec,reg,None,None)
    title=next(t for t in scene.texts if t['id']=='graph-title')
    assert title['measurement']['text']=='示例标题'
    assert title['position']['bbox'][3]<min(n['rect'][1] for n in scene.nodes)
    assert len(scene.nodes)==2
