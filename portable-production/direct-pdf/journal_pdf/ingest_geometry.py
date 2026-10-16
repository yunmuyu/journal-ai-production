"""Geometry-only raster evidence. No OCR, data digitization or curve painting.
All detected objects are candidates, not semantic truth. Original pixels stay read-only.
"""
from __future__ import annotations
import math
from pathlib import Path
from PIL import Image, ImageDraw
from .common import FigureError, contains


def _cv():
    try:
        import cv2, numpy as np
    except ImportError as e:
        raise FigureError('geometry_dependency_missing','位图候选提取需要numpy和opencv-python-headless；不自动安装') from e
    return cv2,np


def ranges(values):
    """Contiguous true index runs, with a half-open stop."""
    out=[];start=None
    for i,v in enumerate(values):
        if bool(v) and start is None:start=i
        if start is not None and (not v or i==len(values)-1):
            out.append((start,i if not v else i+1));start=None
    return out


def union_rect(rows):
    return [min(r[0] for r in rows),min(r[1] for r in rows),max(r[2] for r in rows),max(r[3] for r in rows)]


def _components(mask, min_area=3):
    cv,np=_cv(); n,labels,stats,centers=cv.connectedComponentsWithStats(mask,8)
    return [[int(x),int(y),int(x+w),int(y+h),int(area)] for x,y,w,h,area in stats[1:] if area>=min_area]


def extend_label_left(seed, blocks, position, median_h):
    """Join neighbouring pieces of one tick label, including slightly overlapping boxes.
    Component bounding boxes can overlap by a pixel without their ink being connected.
    This only enlarges review crops; it does not alter pixels, tick locations or values.
    """
    box=list(seed)
    for obj in sorted(blocks,key=lambda item:-item['rect'][2]):
        r=obj['rect'];gap=box[0]-r[2]
        if r[0]<box[0] and -median_h*.2<=gap<median_h*.8 and abs((r[1]+r[3])/2-position)<max(6,median_h*.4):
            box=union_rect([box,r])
    return box


def raster_candidates(path:Path, *, max_pixels=25_000_000):
    cv,np=_cv()
    with Image.open(path) as src:
        if getattr(src,'n_frames',1)>1:raise FigureError('raster_multiframe','多帧图片需明确页/帧范围，不静默只取首帧')
        if src.width*src.height>max_pixels:raise FigureError('raster_pixel_limit','位图像素量超过本候选资源上限')
        if src.getexif().get(274,1)!=1:raise FigureError('raster_orientation','带EXIF方向的图需先明确方向，不默默变换坐标')
        # Black / white analysis only; original output uses original decoded pixels.
        gray=np.asarray(src.convert('L'));h,w=gray.shape
    ink=(gray<185).astype('uint8')*255
    hs=cv.morphologyEx(ink,cv.MORPH_OPEN,cv.getStructuringElement(cv.MORPH_RECT,(max(18,w//7),1)))
    vs=cv.morphologyEx(ink,cv.MORPH_OPEN,cv.getStructuringElement(cv.MORPH_RECT,(1,max(18,h//7))))
    hr=_components(hs);vr=_components(vs)
    horiz=sorted([r for r in hr if r[2]-r[0]>w*.23],key=lambda r:(-(r[2]-r[0]),-r[1]))
    vert=sorted([r for r in vr if r[3]-r[1]>h*.23],key=lambda r:(-(r[3]-r[1]),r[0]))
    axes=[]
    # At most a small candidate set. Open and boxed axes are both supported.
    for hl in horiz[:12]:
        for vl in vert[:12]:
            x=(vl[0]+vl[2]-1)/2;y=(hl[1]+hl[3]-1)/2
            if abs(hl[0]-x)>max(5,w*.008) or abs(vl[3]-1-y)>max(5,h*.008):continue
            r=[x,float(vl[1]),float(hl[2]-1),y]
            if r[2]-r[0]<w*.3 or r[3]-r[1]<h*.3:continue
            if any(max(abs(a-b) for a,b in zip(r,q['frame']))<4 for q in axes):continue
            axes.append({'id':f'axis-{len(axes)+1}','kind':'axis-frame','frame':r,
                'confidence':'geometry-candidate','evidence':'intersecting long horizontal and vertical pixel runs',
                'stroke_px':[vl[2]-vl[0],hl[3]-hl[1]],'x_ticks':[],'y_ticks':[]})
    axes.sort(key=lambda a:-(a['frame'][2]-a['frame'][0])*(a['frame'][3]-a['frame'][1]))
    axes=axes[:4]
    for k,a in enumerate(axes):
        a['id']=f'axis-{k+1}'
        l,t,r,b=a['frame'];margin=max(2,math.ceil(max(a['stroke_px'])/2));depth=max(10,round(min(w,h)*.016))
        x0,x1=max(0,round(l)-2),min(w,round(r)+3)
        y0,y1=max(0,round(t)-2),min(h,round(b)+3)
        bands=[ink[max(0,round(b)-depth):max(0,round(b)-margin),x0:x1],
               ink[min(h,round(b)+margin):min(h,round(b)+depth),x0:x1]]
        xv=np.maximum.reduce([np.cumprod((q[::-1] if i==0 else q)>0,axis=0).sum(axis=0) if q.size else np.zeros(x1-x0) for i,q in enumerate(bands)])
        xr=ranges(xv>=max(3,depth*.18))
        for q0,q1 in xr:
            if q1-q0>max(12,w*.009):continue
            x=x0+(q0+q1-1)/2
            if x<l-3 or x>r+3:continue
            # A visible label candidate below the source tick distinguishes major ticks.
            win=max(8,round(w*.035));yy0=min(h,round(b)+depth);yy1=min(h,round(b)+depth*3)
            xx0=max(0,round(x)-win);xx1=min(w,round(x)+win)
            sub=ink[yy0:yy1,xx0:xx1];nz=np.argwhere(sub)
            labeled=bool(len(nz)>10)
            box=[xx0,yy0,xx1,yy1]
            a['x_ticks'].append({'id':a['id']+f'-x{len(a["x_ticks"])+1}','position':round(x,4),
                'label_region':box,'label_candidate':labeled,'length_not_value':True})
        bands=[ink[y0:y1,max(0,round(l)-depth):max(0,round(l)-margin)],
               ink[y0:y1,min(w,round(l)+margin):min(w,round(l)+depth)]]
        yv=np.maximum.reduce([np.cumprod((q[:,::-1] if i==0 else q)>0,axis=1).sum(axis=1) if q.size else np.zeros(y1-y0) for i,q in enumerate(bands)])
        yr=ranges(yv>=max(3,depth*.18))
        for q0,q1 in yr:
            if q1-q0>max(12,h*.009):continue
            y=y0+(q0+q1-1)/2
            if y<t-3 or y>b+3:continue
            win=max(7,round(h*.016));xx0=max(0,round(l)-round(w*.12));xx1=max(0,round(l)-margin-2)
            yy0=max(0,round(y)-win);yy1=min(h,round(y)+win)
            sub=ink[yy0:yy1,xx0:xx1]
            a['y_ticks'].append({'id':a['id']+f'-y{len(a["y_ticks"])+1}','position':round(y,4),
                'label_region':[xx0,yy0,xx1,yy1],'label_candidate':bool(np.count_nonzero(sub)>10),'length_not_value':True})
        pad=max(2,math.ceil(max(a['stroke_px'])/2)+1)
        a['plot_clip']=[max(0,math.floor(l)-pad),max(0,math.floor(t)-pad),min(w,math.ceil(r)+pad+1),min(h,math.ceil(b)+pad+1)]
    # Local text-like connected components, with long ruling removed.
    long=cv.bitwise_or(hs,vs);clean=cv.bitwise_and(ink,cv.bitwise_not(long))
    comps=_components(clean,4)
    chars=[r for r in comps if 2<=r[2]-r[0]<=w*.06 and 3<=r[3]-r[1]<=h*.07]
    median_h=float(np.median([r[3]-r[1] for r in chars])) if chars else 8.
    kernel=(max(3,round(median_h*.6)),max(1,round(median_h*.10)))
    joined=cv.dilate(clean,cv.getStructuringElement(cv.MORPH_RECT,kernel))
    blocks=[]
    for r in _components(joined,12):
        x,y,rr,b,_=r
        if b-y>max(40,median_h*2.8) or rr-x<w*.005:continue
        # Tight bbox in original analysis pixels.
        nz=np.argwhere(clean[y:b,x:rr])
        if not len(nz):continue
        rect=[int(x+nz[:,1].min()),int(y+nz[:,0].min()),int(x+nz[:,1].max()+1),int(y+nz[:,0].max()+1)]
        blocks.append({'id':'','rect':rect,'kind':'text-or-symbol-region','confidence':'candidate'})
    blocks.sort(key=lambda q:(q['rect'][1],q['rect'][0]));blocks=blocks[:300]
    for i,q in enumerate(blocks):q['id']=f'region-{i+1}'
    # Bind labelled ticks to nearby text-region centers, not a wide window that
    # might contain the neighboring major label at an unlabeled minor tick.
    for a in axes:
        f=a['frame']
        for q in a['x_ticks']:
            nearby=[b for b in blocks if b['rect'][1]>f[3]+2 and b['rect'][1]<f[3]+h*.055 and abs((b['rect'][0]+b['rect'][2])/2-q['position'])<max(6,median_h*.65)]
            q['label_candidate']=bool(nearby)
            if nearby:
                bb=min(nearby,key=lambda b:b['rect'][1])['rect'];q['label_region']=[max(0,bb[0]-3),max(0,bb[1]-3),min(w,bb[2]+3),min(h,bb[3]+3)]
        for q in a['y_ticks']:
            nearby=[b for b in blocks if b['rect'][2]<f[0]-2 and b['rect'][2]>f[0]-w*.04 and abs((b['rect'][1]+b['rect'][3])/2-q['position'])<max(6,median_h*.65)]
            q['label_candidate']=bool(nearby)
            if nearby:
                bb=extend_label_left(max(nearby,key=lambda b:b['rect'][2])['rect'],blocks,q['position'],median_h)
                q['label_region']=[max(0,bb[0]-3),max(0,bb[1]-3),min(w,bb[2]+3),min(h,bb[3]+3)]
    # Short horizontal swatches with a separated text region to their right.
    short=cv.morphologyEx(ink,cv.MORPH_OPEN,cv.getStructuringElement(cv.MORPH_RECT,(max(12,round(median_h*1.4)),1)))
    legends=[]
    if axes:
        f=axes[0]['frame']
        for rr in _components(short,8):
            x,y,r,b,_=rr;length=r-x;cy=(y+b)/2
            if not (median_h*1.4<=length<=w*.18 and b-y<=max(8,median_h*.4)):continue
            if not contains([f[0]+8,f[1]+8,f[2]-8,f[3]-8],[x,y,r,b]):continue
            # Inspect original pixels to the RIGHT of the swatch. A text-region
            # dilation can merge a swatch with "nf"/"OP1" across a small gap;
            # never use that merged box as the label boundary.
            yy0=max(0,math.floor(cy-median_h*1.05));yy1=min(h,math.ceil(cy+median_h*1.15))
            xx0=r+2;xx1=min(w,math.floor(f[2]-6))
            if xx1<=xx0:continue
            strip=ink[yy0:yy1,xx0:xx1];col=np.count_nonzero(strip,axis=0);occupied=np.flatnonzero(col)
            if not len(occupied) or occupied[0]>median_h*2.7:continue
            stop=len(col)
            for i in range(len(occupied)-1):
                if occupied[i+1]-occupied[i]>median_h*2.4:stop=int(occupied[i]+1);break
            nz=np.argwhere(strip[:,:stop])
            if not len(nz):continue
            labelrect=[int(xx0+nz[:,1].min()),int(yy0+nz[:,0].min()),int(xx0+nz[:,1].max()+1),int(yy0+nz[:,0].max()+1)]
            if labelrect[3]-labelrect[1]<median_h*.55 or labelrect[2]-labelrect[0]<median_h*.65:continue
            # Tight swatch ink bounds (including a square marker); no fictitious
            # tall rectangle extending across an open axis's top endpoint.
            sy0=max(0,math.floor(cy-median_h*.75));sy1=min(h,math.ceil(cy+median_h*.75))
            sx0=max(0,x-2);sx1=min(w,r+2)
            sym=np.argwhere(ink[sy0:sy1,sx0:sx1])
            if not len(sym):continue
            sw=[sx0,max(0,int(sy0+sym[:,0].min())-2),sx1,min(h,int(sy0+sym[:,0].max())+3)]
            legends.append({'id':f'legend-row-{len(legends)+1}','kind':'legend-row','swatch_clip':sw,
                'label_region_id':f'legend-label-{len(legends)+1}','label_region':labelrect,'rect':union_rect([sw,labelrect]),
                'confidence':'candidate-needs-series-and-mask-review'})
    # Aligned legend rows share a swatch slot; preserve left half of a line split
    # by a square marker instead of cropping only its right-hand dash.
    for row in legends:
        peers=[q for q in legends if abs(q['label_region'][0]-row['label_region'][0])<median_h*.6 and abs(q['rect'][1]-row['rect'][1])<median_h*5]
        if peers:
            row['swatch_clip'][0]=min(q['swatch_clip'][0] for q in peers)
            row['swatch_clip'][2]=max(q['swatch_clip'][2] for q in peers)
            sw=row['swatch_clip'];cy=(sw[1]+sw[3])/2;dy=max(median_h,(row['label_region'][3]-row['label_region'][1])*.7)
            yy0=max(0,math.floor(cy-dy));yy1=min(h,math.ceil(cy+dy));sx0=int(sw[0]);sx1=int(sw[2])
            pix=np.argwhere(ink[yy0:yy1,sx0:sx1])
            if len(pix):
                sw[1]=max(0,int(yy0+pix[:,0].min())-2);sw[3]=min(h,int(yy0+pix[:,0].max())+3)
            row['rect']=union_rect([sw,row['label_region']])
    # Closed box/diamond candidates for raster diagrams: only contours, not text OCR.
    contours,_=cv.findContours(ink,cv.RETR_LIST,cv.CHAIN_APPROX_SIMPLE);shapes=[]
    for cnt in contours:
        area=cv.contourArea(cnt)
        if area<max(100,w*h*.0008) or area>w*h*.9:continue
        approx=cv.approxPolyDP(cnt,.018*cv.arcLength(cnt,True),True)
        if len(approx)!=4 or not cv.isContourConvex(approx):continue
        x,y,ww,hh=cv.boundingRect(approx);rect=[x,y,x+ww,y+hh]
        if any(max(abs(a-b) for a,b in zip(rect,q['rect']))<5 for q in shapes):continue
        if ww<12 or hh<12:continue
        pts=approx[:,0,:].tolist();axis_aligned=all(abs(a[0]-b[0])<4 or abs(a[1]-b[1])<4 for a,b in zip(pts,pts[1:]+pts[:1]))
        shapes.append({'id':f'shape-{len(shapes)+1}','rect':rect,'vertices':pts,'kind':'rectangle' if axis_aligned else 'diamond-or-quadrilateral','confidence':'contour-candidate'})
    shapes.sort(key=lambda q:(q['rect'][1],q['rect'][0]));shapes=shapes[:100]
    return {'size':[w,h],'coordinate_unit':'px','axes':axes,'regions':blocks,'legend_rows':legends,'shapes':shapes,
            'warnings':[] if axes else [{'code':'no_confident_axis_frame','message':'未检出可靠坐标轴候选；按框图或局部语义路径处理，不猜轴'}],
            'analysis':{'ocr_calls':0,'curve_digitization':False,'model_calls':0,'median_component_height':median_h}}


def overlay_candidates(image:Image.Image,evidence:dict,dest:Path):
    """An annotated evidence image, never used as output artwork."""
    im=image.convert('RGB').copy();d=ImageDraw.Draw(im)
    for a in evidence.get('axes',[]):
        d.rectangle(a['frame'],outline=(210,35,35),width=2);d.text((a['frame'][0]+3,a['frame'][1]+3),a['id'],fill=(210,35,35))
        for key in ('x_ticks','y_ticks'):
            for q in a[key]:
                x,y=(q['position'],a['frame'][3]) if key=='x_ticks' else (a['frame'][0],q['position'])
                d.ellipse([x-3,y-3,x+3,y+3],outline=(0,100,220),width=2)
                if q['label_candidate']:d.text((x+4,y-12),q['id'].replace(a['id']+'-',''),fill=(0,100,220))
    if not evidence.get('axes'):
        for q in evidence.get('shapes',[]):
            d.rectangle(q['rect'],outline=(20,110,160),width=2)
            d.text((q['rect'][0]+2,q['rect'][1]+2),q['id'],fill=(20,110,160))
    for q in evidence.get('legend_rows',[]):
        d.rectangle(q['rect'],outline=(170,60,180),width=2);d.text((q['rect'][0],q['rect'][1]-12),q['id'],fill=(170,60,180))
    im.thumbnail((1800,1800));im.save(dest)
