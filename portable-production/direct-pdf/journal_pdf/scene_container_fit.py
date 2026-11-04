"""Fit the bottoms of free-standing scene regions to their visible contents."""
from __future__ import annotations
from copy import deepcopy
from .common import contains
from .scene import audit_scene


def _segment_bottom(a, b, rect):
    """Return the largest y on an axis-aligned segment inside a region."""
    x0,y0,x1,y1=rect
    if abs(a[1]-b[1])<1e-5:
        return a[1] if y0 <= a[1] <= y1 and max(min(a[0],b[0]),x0) <= min(max(a[0],b[0]),x1) else None
    if abs(a[0]-b[0])<1e-5 and x0 <= a[0] <= x1:
        low=max(min(a[1],b[1]),y0);high=min(max(a[1],b[1]),y1)
        return high if low<=high else None
    return None


def compact_container_bottoms(scene):
    """Trim unused region bottoms without moving any object or connection."""
    baseline={(x.get('code'),x.get('id'),x.get('path')) for x in audit_scene(scene)}
    regions=[n for n in scene.nodes if n['container']]
    parallel={}
    for n in regions:
        parallel.setdefault((round(n['rect'][1],2),round(n['rect'][3],2)),[]).append(n)
    for region in regions:
        r=region['rect']; old=r[3]
        if any(any((e.get('node') if isinstance(e,dict) else e)==region['id'] for e in (p.get('endpoint_nodes') or [])) for p in scene.paths):
            continue
        if any(abs(a[0]-b[0])>1e-5 and abs(a[1]-b[1])>1e-5 for p in scene.paths for a,b in zip(p['points'],p['points'][1:])):
            continue
        bottoms=[n['rect'][3]+n['width']/2 for n in scene.nodes if n is not region and contains(r,n['rect'])]
        bottoms.extend(t['position']['bbox'][3] for t in scene.texts if contains(r,t['position']['bbox']))
        bottoms.extend(y for p in scene.paths for a,b in zip(p['points'],p['points'][1:]) if (y:=_segment_bottom(a,b,r)) is not None)
        if not bottoms:continue
        candidate=max(bottoms)+6*scene.size/8+region['width']/2
        if candidate >= old-2 or candidate <= r[1]:continue
        region['rect'][3]=candidate
        issues={(x.get('code'),x.get('id'),x.get('path')) for x in audit_scene(scene)}
        if issues-baseline:region['rect'][3]=old
        else:scene.layout_evidence.setdefault('compact_container_bottoms',[]).append({'id':region['id'],'old_bottom_pt':old,'bottom_pt':candidate})

    for group in parallel.values():
        if len(group)<2 or any(a['rect'][0]<b['rect'][2] and b['rect'][0]<a['rect'][2] for i,a in enumerate(group) for b in group[i+1:]):
            continue
        original=[n['rect'][3] for n in group]; shared=max(original)
        for n in group:n['rect'][3]=shared
        issues={(x.get('code'),x.get('id'),x.get('path')) for x in audit_scene(scene)}
        if issues-baseline:
            for n,bottom in zip(group,original):n['rect'][3]=bottom
        else:
            scene.layout_evidence.setdefault('aligned_container_bottoms',[]).append({'ids':[n['id'] for n in group],'bottom_pt':shared})
