"""Measure declared label clearance against actual source PDF tick strokes."""
from __future__ import annotations

import math
import fitz
from .assets import Assets
from .common import FigureError


def audit_source_tick_gaps(page,scene,checks):
    if not isinstance(checks,list):raise FigureError('source_tick_gap_invalid','源刻度检查须为数组')
    if not checks:return {'checks':[],'ok':True}
    assets={a['id']:a for a in scene.assets};texts={t['id']:t for t in scene.texts};offset=page.cropbox_position
    cache={};results=[]
    with fitz.open() as ref:
        reference=ref.new_page(width=page.mediabox.width,height=page.mediabox.height);placer=Assets()
        try:
            for check in checks:
                if (not isinstance(check,dict) or set(check)-{'asset_id','text_id','gap_pt'}
                        or any(not isinstance(check.get(k),str) or not check[k] for k in ('asset_id','text_id'))):
                    raise FigureError('source_tick_gap_invalid','源刻度检查须指定资产和文字')
                asset_id=check['asset_id'];text_id=check['text_id'];gap=check.get('gap_pt',2.5)
                if asset_id not in assets or text_id not in texts or isinstance(gap,bool) or not isinstance(gap,(int,float)) or not math.isfinite(gap) or gap<0:
                    raise FigureError('source_tick_gap_invalid','源刻度检查字段无效')
                if asset_id not in cache:
                    reference.clean_contents();ref.delete_page(0);reference=ref.new_page(width=page.mediabox.width,height=page.mediabox.height)
                    item=assets[asset_id]
                    if item['asset'].kind!='pdf':raise FigureError('source_tick_gap_invalid','仅支持矢量 PDF 来源刻度')
                    placer.place(reference,item['asset'],item['rect']);reference.set_cropbox(page.cropbox)
                    cache[asset_id]=reference.get_drawings()
                bbox=texts[text_id]['position']['bbox'];x=(bbox[0]+bbox[2])/2-offset.x;top=bbox[1]-offset.y
                possible=[]
                for row in cache[asset_id]:
                    r=row['rect'];width=row['width']
                    if (row['type'] in ('s','fs') and width is not None and abs(r.x0-x)<.06 and r.width<.01
                            and .2<r.height<5 and r.y1<top and top-r.y1<12):
                        possible.append(row)
                if len(possible)!=1:
                    raise FigureError('source_tick_gap_unproven','无法唯一确认标签对应的原始刻度',id=text_id,count=len(possible))
                tick=possible[0];actual=top-(tick['rect'].y1+tick['width']/2)
                from .source_icons import path_record,consume_paths
                consume_paths([path_record(tick)],[path_record(row) for row in page.get_drawings()])
                results.append({'asset_id':asset_id,'text_id':text_id,'gap_pt':actual,'expected_pt':gap,
                                'source_sha256':assets[asset_id]['asset'].source_hash,'ok':abs(actual-gap)<=.15})
        finally:placer.close()
    return {'checks':results,'ok':all(r['ok'] for r in results)}
