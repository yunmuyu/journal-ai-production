from pathlib import Path
import argparse,json,sys
from .probe import scan
from .routing import apply_review,bridge_legacy

def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    # Outputs are append-only candidate files; explicit overwrite not supported.
    with p.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)

def main():
    ap=argparse.ArgumentParser(description='Evidence-first preflight; does not render or publish production PDFs.')
    sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('probe');p.add_argument('manifest');p.add_argument('--out',required=True)
    p=sub.add_parser('route');p.add_argument('probe');p.add_argument('review');p.add_argument('--manifest',required=True);p.add_argument('--out',required=True)
    p=sub.add_parser('bridge');p.add_argument('legacy');p.add_argument('report');p.add_argument('--out',required=True)
    a=ap.parse_args()
    if a.command=='probe':
        root=Path(a.out)
        if (root/'probe.json').exists():ap.error('Choose a new candidate output directory, not existing evidence.')
        r=scan(load(a.manifest),root);print(json.dumps({'assets':r['asset_count'],'seconds':r['program_seconds'],'output':str(root/'probe.json')}))
    elif a.command=='route':
        r=apply_review(load(a.probe),load(a.review),load(a.manifest));save(a.out,r);print(json.dumps({'figures':len(r['figures']),'output':a.out,'published':False}))
    else:save(a.out,bridge_legacy(load(a.legacy),load(a.report)))
if __name__=='__main__':main()
