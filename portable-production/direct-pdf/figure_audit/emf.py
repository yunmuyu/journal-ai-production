"""Partial EMF inspection CLI; not a renderer or source of truth."""
import os, json
from .errors import AuditInputError
from .emf_parser import Emf

def dump(path):
    e = Emf(path)
    print('PARTIAL: verify transforms, clipping, text and geometry against the original')
    print('unsupported record counts', e.unsupported_records)
    print('file      ', os.path.basename(path))
    print('natural mm', tuple(round(v, 2) for v in e.nat_mm),
          ' frame(word) mm', tuple(round(v, 2) for v in e.frame_mm),
          ' stretch x%.3f y%.3f' % (e.frame_mm[0] / max(e.nat_mm[0], 1e-6), e.frame_mm[1] / max(e.nat_mm[1], 1e-6)))
    print('polys     ', len(e.polys), ' texts', len(e.texts))
    print('font sizes(pt, 按字数计)', e.font_stats())
    print('---- 文字 ----')
    for t in e.text_list():
        print('  %-28s x%7.2f y%7.2f w%7.2f h%6.2f %5.2fpt w%d%s %s' %
              (repr(t['text'])[:28], t['x'], t['y'], t['w'], t['h'], t['size'], t['weight'],
               ' i' if t['italic'] else '', t['face']))


def to_json(path, out):
    e = Emf(path)
    from pathlib import Path
    if Path(path).resolve() == Path(out).resolve():
        raise AuditInputError('output must not overwrite input')
    d = dict(file=os.path.basename(path), complete=False, unsupported_records=e.unsupported_records,
             warning="Partial extraction only; coordinates, transforms, clipping and text require independent review", nat_mm=e.nat_mm, frame_mm=e.frame_mm,
             bounds=e.bounds, texts=e.text_list(),
             polys=[dict(pts=[[round(v, 2) for v in e.pt_of(p)] for p in pl['pts']],
                         closed=pl['closed'], kind=pl['kind'],
                         width=round(pl['width'] * e.kx, 3),
                         fill=pl['fill'], stroke=pl['stroke'], clip_status=pl['clip_status'], coordinate_status=pl['coordinate_status'],
                         clip_regions_mm=[[list(e.pt_of(point)) for point in region] for region in pl['clip_regions']]) for pl in e.polys])
    Path(out).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
    print('->', out, len(d['texts']), 'texts', len(d['polys']), 'polys')



if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Partial EMF extraction; results require source review')
    parser.add_argument('command', choices=['dump', 'json'])
    parser.add_argument('source')
    parser.add_argument('output', nargs='?')
    args = parser.parse_args()
    if args.command == 'dump':
        dump(args.source)
    elif not args.output:
        parser.error('json requires an output path')
    else:
        to_json(args.source, args.output)