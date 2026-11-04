"""Collision geometry in the measured text's own coordinate system."""
import math
from .common import segment_hits, contains


def local_point(point,text):
    x=point[0]-text['position']['offset'][0];y=point[1]-text['position']['offset'][1]
    angle=math.radians(text['position']['rotation'])
    return [x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle)]


def segment_hits_text(a,b,text,pad=0):
    return segment_hits(local_point(a,text),local_point(b,text),text['measurement']['ink'],pad)


def polygon_hits_text(points,text,pad=0):
    polygon=[local_point(p,text) for p in points];r=text['measurement']['ink']
    r=[r[0]-pad,r[1]-pad,r[2]+pad,r[3]+pad]
    if any(contains(r,[p[0],p[1],p[0],p[1]]) for p in polygon):return True
    if any(segment_hits(a,b,r) for a,b in zip(polygon,polygon[1:]+polygon[:1])):return True
    for x,y in [(r[0],r[1]),(r[0],r[3]),(r[2],r[1]),(r[2],r[3])]:
        values=[(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]) for a,b in zip(polygon,polygon[1:]+polygon[:1])]
        if all(v>=0 for v in values) or all(v<=0 for v in values):return True
    return False
