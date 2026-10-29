"""Conservative line-segment intersection for explicitly bound legend data."""
import math


def segment_intersects_box(a: list[float], b: list[float], box: list[float]) -> bool:
    """Return whether a segment touches a closed, axis-aligned box."""
    dx,dy=b[0]-a[0],b[1]-a[1]
    lower,upper=0.,1.
    for p,q in ((-dx,a[0]-box[0]),(dx,box[2]-a[0]),(-dy,a[1]-box[1]),(dy,box[3]-a[1])):
        if p==0:
            if q<0:return False
        elif p<0:lower=max(lower,q/p)
        else:upper=min(upper,q/p)
        if lower>upper:return False
    return True


def segment_box_distance(a: list[float], b: list[float], box: list[float]) -> float:
    """Euclidean distance from a line segment to a closed rectangle."""
    if segment_intersects_box(a,b,box):return 0.
    def point_box(p):
        return math.hypot(max(box[0]-p[0],0,p[0]-box[2]),max(box[1]-p[1],0,p[1]-box[3]))
    def point_segment(p):
        dx=b[0]-a[0];dy=b[1]-a[1];length=dx*dx+dy*dy
        t=max(0.,min(1.,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0.
        return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)
    return min(point_box(a),point_box(b),*(point_segment(p) for p in
        ([box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]])))


def visible_dash_ink(start: float, end: float, dash: list[float], covered: list[tuple[float,float]]) -> float | None:
    """Measure painted dash fragments after rectangular marker occlusion."""
    if len(dash)%2:dash=dash*2
    direction=1 if end>=start else -1;length=abs(end-start);position=0.;index=0;paint=0.
    while position<length-1e-9:
        next_position=min(length,position+dash[index%len(dash)])
        if index%2==0:
            a,b=sorted((start+direction*position,start+direction*next_position));hidden=0.;last=None
            for left,right in sorted((max(a,l),min(b,r)) for l,r in covered if r>a and l<b):
                if right<=left:continue
                if last is None or left>last:hidden+=right-left;last=right
                elif right>last:hidden+=right-last;last=right
            paint+=max(0.,b-a-hidden)
        position=next_position;index+=1
        if index>10000:return None
    return paint
