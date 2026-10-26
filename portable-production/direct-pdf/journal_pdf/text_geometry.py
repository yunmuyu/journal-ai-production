"""Rotated glyph ink quadrilaterals; no font substitution or raster OCR."""
from __future__ import annotations
import math


def rotate_point(x,y,angle):
    angle=angle%360
    if angle in (0,90,180,270):return {0:(x,y),90:(y,-x),180:(-x,-y),270:(-y,x)}[angle]
    radians=math.radians(angle);c,s=math.cos(radians),math.sin(radians)
    return x*c+y*s,-x*s+y*c


def ink_polygons(measurement,angle,offset=(0,0)):
    boxes=[g['ink'] for g in measurement.get('glyphs',[]) if not g['ch'].isspace()] or [measurement['ink']]
    result=[]
    for x0,y0,x1,y1 in boxes:
        if x1<=x0 or y1<=y0:continue
        points=[rotate_point(x,y,angle) for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))]
        result.append([(x+offset[0],y+offset[1]) for x,y in points])
    return result


def oblique(item):
    return abs(item['position'].get('rotation',0)%90)>1e-8


def polygons(item):
    return ink_polygons(item['measurement'],item['position']['rotation'],item['position']['offset'])


def convex_intersects(a,b,gap=0):
    for points in (a,b):
        for p,q in zip(points,points[1:]+points[:1]):
            dx,dy=q[0]-p[0],q[1]-p[1];length=math.hypot(dx,dy)
            if length<1e-12:continue
            nx,ny=-dy/length,dx/length
            first=[x*nx+y*ny for x,y in a];second=[x*nx+y*ny for x,y in b]
            if max(first)+gap<=min(second)+1e-9 or max(second)+gap<=min(first)+1e-9:return False
    return True


def texts_intersect(a,b,gap=.05):
    return any(convex_intersects(x,y,gap) for x in polygons(a) for y in polygons(b))


def segment_intersects_text(a,b,text,pad):
    dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
    if length<1e-10:dx,dy,length=1,0,1
    ux,uy=dx/length,dy/length;nx,ny=-uy*pad,ux*pad
    p=(a[0]-ux*pad,a[1]-uy*pad);q=(b[0]+ux*pad,b[1]+uy*pad)
    box=[(p[0]+nx,p[1]+ny),(q[0]+nx,q[1]+ny),(q[0]-nx,q[1]-ny),(p[0]-nx,p[1]-ny)]
    return any(convex_intersects(box,g) for g in polygons(text))


def arrow_intersects_text(vertices,text):
    return any(convex_intersects([vertices[0],vertices[i],vertices[i+1]],g)
               for i in range(1,len(vertices)-1) for g in polygons(text))


def audit_pdf_rotations(texts,traces):
    remaining={}
    for trace in traces:
        angle=math.degrees(math.atan2(-trace['dir'][1],trace['dir'][0]))%360
        for char in trace['chars']:
            if not chr(char[0]).isspace():remaining.setdefault(char[0],[]).append(angle)
    issues=[];checked=0
    for item in texts:
        for glyph in item['measurement']['glyphs']:
            if glyph['ch'].isspace():continue
            checked+=1;expected=(item['position']['rotation']+glyph.get('rotation',0))%360
            angles=remaining.get(ord(glyph['ch']),[])
            index=next((i for i,actual in enumerate(angles) if abs((actual-expected+180)%360-180)<.01),None)
            if index is None:issues.append({'text_id':item['id'],'character':glyph['ch'],'expected_degrees':expected})
            else:angles.pop(index)
    return {'ok':not issues,'checked_scene_characters':checked,'tolerance_degrees':.01,'issues':issues,
            'scope':'Editable scene glyph rotations; imported native text is audited separately by content.'}
