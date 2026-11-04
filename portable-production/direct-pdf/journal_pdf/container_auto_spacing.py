"""Review likely direct framed children; geometry does not prove semantics."""
from __future__ import annotations
import math
from .common import FigureError

def parse_container_spacing_exceptions(value):
    if not isinstance(value,list):raise FigureError('container_spacing_exception_invalid','容器间距例外须为数组')
    result=[];seen=set()
    for item in value:
        if (not isinstance(item,dict) or set(item)!={'container','child','side','gap_pt','reason'}
                or not isinstance(item['container'],str) or not item['container']
                or not isinstance(item['child'],str) or not item['child']
                or item['side'] not in ('top','bottom') or isinstance(item['gap_pt'],bool)
                or not isinstance(item['gap_pt'],(int,float)) or not math.isfinite(item['gap_pt']) or item['gap_pt']<0
                or not isinstance(item['reason'],str) or not item['reason'].strip()):
            raise FigureError('container_spacing_exception_invalid','例外须指定容器、方向、实测值与原因')
        key=(item['container'],item['side'])
        if key in seen:raise FigureError('container_spacing_exception_invalid','容器例外重复')
        seen.add(key);result.append(dict(item))
    return result

def _inside(inner,outer):
    a=inner['rect'];b=outer['rect']
    return (a[0]>b[0]+.01 and a[1]>b[1]+.01 and a[2]<b[2]-.01 and a[3]<b[3]-.01)

def audit_automatic_container_spacing(scene):
    nodes=[n for n in scene.nodes if n.get('kind')=='rectangle' and not n.get('invisible')
           and isinstance(n.get('width'),(int,float)) and n['width']>0]
    result=[];notes=[];reference=3.*scene.size/8;matched=set()
    exceptions={(item['container'],item['side']):item for item in scene.container_spacing_exceptions}
    for container in nodes:
        if not container.get('container'):continue
        inside=[n for n in nodes if n is not container and _inside(n,container)]
        direct=[n for n in inside if not any(other is not n and _inside(n,other) for other in inside)]
        if not direct:continue
        outer=container['rect'];outer_half=container['width']/2
        for side in ('top','bottom'):
            # A container-owned title occupies this space; the title-to-frame
            # relationship is governed by its own rule, not an empty margin.
            if side=='top' and any(t.get('owner')==container['id'] for t in scene.texts):continue
            def gap(n):
                box=n['rect'];half=n['width']/2
                return box[1]-half-(outer[1]+outer_half) if side=='top' else outer[3]-outer_half-(box[3]+half)
            child=min(direct,key=gap);actual=gap(child)
            row={'container':container['id'],'child':child['id'],'side':side,'gap_pt':actual,'reference_pt':reference,
                 'scope':'geometry-inferred immediate rectangles; verify semantic relation and exceptions'}
            exception=exceptions.get((container['id'],side))
            if exception:
                matched.add((container['id'],side))
                if child['id']==exception['child'] and abs(actual-exception['gap_pt']*scene.size/8)<=.15*scene.size/8:
                    row['exception_reason']=exception['reason']
            result.append(row)
            if abs(actual-reference)>.15*scene.size/8 and 'exception_reason' not in row:
                notes.append({'code':'container_spacing_review','id':container['id'],'child':child['id'],
                              'side':side,'gap_pt':actual,'reference_pt':reference,
                              'message':'可能的容器与内部框上下净距偏离参考；先核对层级和布局需求。'})
    for key,exception in exceptions.items():
        if key not in matched:
            notes.append({'code':'container_exception_unverified','id':exception['container'],'side':exception['side'],
                          'message':'容器例外未匹配到实际直接内部框，须重新核对。'})
    return {'checks':result,'notes':notes}
