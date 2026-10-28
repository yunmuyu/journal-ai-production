"""Review explicit reductions while preserving legitimate mathematical scripts."""
from __future__ import annotations


def font_size_notices(scene):
    notices=[]
    if scene.size < 8-1e-6:
        notices.append({'code':'base_font_below_8_requires_review','actual_base_font_size_pt':scene.size,
                        'message':'最终基础字号低于8 pt，须核对是否有该图的明确例外；数学上下标单独处理。'})
    for text in scene.texts:
        content=text.get('content')
        if not isinstance(content,list):
            continue
        parts=[part for part in content if isinstance(part,dict) and part.get('text','').strip()
               and float(part.get('scale',1))<1 and float(part.get('baseline_shift_pt',0))==0]
        if parts:
            notices.append({'code':'reduced_nonscript_text_requires_review','id':text['id'],
                            'parts':[{'text':part['text'],'scale':part['scale']} for part in parts],
                            'message':'检测到未标明上、下标的局部缩字，请核对该图是否有明确例外。'})
    return notices
