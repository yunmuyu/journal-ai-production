"""Measure and place semantic row/column panels using the public font rules."""
from copy import deepcopy
from .common import FigureError
from .label_layout import layout_label
from .region_layout import horizontal_band


def _move(block,dx,dy):
    for n in block['nodes']:
        n['rect']=[v+(dx if i%2==0 else dy) for i,v in enumerate(n['rect'])]
    for t in block['texts']:t['x']+=dx;t['y']+=dy


def _width(block,width):
    extra=width-block['width']
    if extra<0:raise FigureError('panel_width','容纳内容的宽度不足')
    if block.get('stretch_part'):
        part=block['stretch_part'];frame=next(n for n in part['nodes'] if n['id']==part['frame']);old=frame['rect'][:]
        _move(part,extra/2,0);frame['rect']=[old[0],old[1],old[2]+extra,old[3]]
        block['width']=width
        return
    _move(block,extra/2,0)
    if block.get('frame'):
        frame=next(n for n in block['nodes'] if n['id']==block['frame'])
        frame['rect'][0]=0;frame['rect'][2]=width
    block['width']=width


def measure_panel(data,reg,size=8):
    """Return measured geometry from content, hierarchy and publication gaps."""
    result={'width':0.,'height':0.,'nodes':[],'texts':[],'evidence':[]}
    if 'block' in data:return deepcopy(data['block'])
    if 'space_pt' in data:
        result.update(width=1,height=data['space_pt']);return result
    if 'text' in data:
        text=layout_label(reg,data['text'],size,wrap_width_pt=data.get('wrap_width_pt'))
        m=reg.measure_vertical(text,size) if data.get('vertical') else reg.measure(text,size)
        boxed=data.get('box',False);w=m['width']+(9*size/8 if boxed else 0);h=m['height']+(5.4*size/8 if boxed else 0)
        result.update(width=w,height=h)
        if boxed:
            result['nodes']=[{'id':data['id'],'text':data['text'],'rect':[0,0,w,h],
                              'wrap_width_pt':data.get('wrap_width_pt'),'vertical_text':data.get('vertical',False)}]
            if data.get('source_lock'):
                result['frame']=data['id'];result['nodes'][0].update(role='source-locked-viewport',
                 fixed_size={'purpose':'source-locked-viewport','evidence':data['source_lock']})
        else:result['texts']=[{'id':data['id'],'text':text,'x':w/2,'y':h/2,'vertical_text':data.get('vertical',False)}]
        return result
    axis=data.get('axis');children=[measure_panel(c,reg,size) for c in data.get('children',[])]
    if axis not in ('row','column') or not children:raise FigureError('panel_tree','排版块须明确行列及内容')
    gap=data.get('gap_pt',3)*size/8
    primary='width' if axis=='row' else 'height';secondary='height' if axis=='row' else 'width'
    offsets=horizontal_band([c[primary] for c in children],origin=0,minimum_gap=gap)
    main=offsets[-1]+children[-1][primary];cross=max(c[secondary] for c in children)
    for child in children:
        if axis=='column' and data.get('equal_width'):_width(child,cross)
    pad=data.get('padding_pt',6 if data.get('frame') else 0)*size/8
    title=data.get('title');title_h=0
    if title:
        m=reg.measure(title,size);title_h=m['height']+6*size/8
        if axis=='column':cross=max(cross,m['width'])
        else:main=max(main,m['width'])
    w,h=(main,cross) if axis=='row' else (cross,main)
    w+=2*pad;h+=2*pad+title_h
    for child,offset in zip(children,offsets):
        cross_offset=(cross-child[secondary])/2 if data.get('align','center')=='center' else 0
        dx,dy=(offset,cross_offset) if axis=='row' else (cross_offset,offset)
        _move(child,pad+dx,pad+title_h+dy)
        result['nodes']+=child['nodes'];result['texts']+=child['texts'];result['evidence']+=child['evidence']
    if data.get('frame'):
        result['frame']=data['frame'];frame={'id':data['frame'],'rect':[0,0,w,h],'container':True}
        if data.get('dash'):frame['dash']=data['dash']
        result['nodes'].insert(0,frame)
    if title:result['texts'].append({'id':data['frame']+'-title','text':title,'x':w/2,'y':pad+(title_h-6*size/8)/2})
    if data.get('stretch_last') and children[-1].get('frame'):result['stretch_part']=children[-1]
    result.update(width=w,height=h)
    result['evidence'].append({'id':data.get('frame'),'axis':axis,'gap_pt':gap,'width_pt':w,'height_pt':h})
    return result


def place_panel(data,reg,origin=(4,4),size=8):
    block=measure_panel(data,reg,size);_move(block,*origin)
    return block
