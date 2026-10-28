"""Partial EMF inspection CLI; not a renderer or source of truth."""
import os, json
from .errors import AuditInputError
from .emf_parser import Emf

def dump(path, isotropic_dpi=None, clip_geometry=False, clip_device_bounds=None):
    e = Emf(path, isotropic_dpi=isotropic_dpi, clip_geometry=clip_geometry, clip_device_bounds=clip_device_bounds)
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


def _poly_json(e, pl):
    result=dict(pts=[[round(v, 2) for v in e.pt_of(p)] for p in pl['pts']],
                closed=pl['closed'], kind=pl['kind'], width=round(pl['width'] * e.kx, 3),
                fill=pl['fill'], stroke=pl['stroke'], clip_status=pl['clip_status'], coordinate_status=pl['coordinate_status'],
                clip_regions_mm=[[list(e.pt_of(point)) for point in region] for region in pl['clip_regions']],
                clip_exclusions_mm=[[list(e.pt_of(point)) for point in region] for region in pl['clip_exclusions']])
    if e.clip_geometry:
        from .emf_clip_geometry import clipped_geometry, map_geometry_mm
        visible={'status':'unknown-coordinate-mapping'} if pl['coordinate_status']=='unknown' else clipped_geometry(
            pl['pts'],pl['closed'],pl['fill'] is not None,pl['kind'],pl['clip_model'])
        for key in ('stroke_centerline','fill'):
            if key in visible:visible[key]=map_geometry_mm(visible[key],e.pt_of)
        result['visible_geometry_mm']=visible
    return result


def to_json(path, out, isotropic_dpi=None, clip_geometry=False, clip_device_bounds=None):
    e = Emf(path, isotropic_dpi=isotropic_dpi, clip_geometry=clip_geometry, clip_device_bounds=clip_device_bounds)
    from pathlib import Path
    if Path(path).resolve() == Path(out).resolve():
        raise AuditInputError('output must not overwrite input')
    d = dict(file=os.path.basename(path), complete=False, isotropic_dpi=isotropic_dpi, clip_device_bounds=clip_device_bounds, unsupported_records=e.unsupported_records,
             warning="Partial extraction only; coordinates, transforms, clipping and text require independent review", nat_mm=e.nat_mm, frame_mm=e.frame_mm,
             bounds=e.bounds, texts=e.text_list(),
             polys=[_poly_json(e, pl) for pl in e.polys])
    Path(out).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
    print('->', out, len(d['texts']), 'texts', len(d['polys']), 'polys')



if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Partial EMF extraction; results require source review')
    parser.add_argument('command', choices=['dump', 'json'])
    parser.add_argument('source')
    parser.add_argument('output', nargs='?')
    parser.add_argument('--dpi-x', type=int, help='verified playback device horizontal DPI')
    parser.add_argument('--dpi-y', type=int, help='verified playback device vertical DPI')
    parser.add_argument('--clip-geometry', action='store_true', help='compute supported vector geometry clipping (optional Shapely dependency)')
    parser.add_argument('--clip-bounds', nargs=4, type=int, metavar=('LEFT','TOP','RIGHT','BOTTOM'), help='verified playback device surface bounds in device units')
    args = parser.parse_args()
    if (args.dpi_x is None) != (args.dpi_y is None):
        parser.error('--dpi-x and --dpi-y must be specified together')
    dpi = (args.dpi_x, args.dpi_y) if args.dpi_x is not None else None
    if args.command == 'dump':
        dump(args.source, dpi, args.clip_geometry, tuple(args.clip_bounds) if args.clip_bounds else None)
    elif not args.output:
        parser.error('json requires an output path')
    else:
        to_json(args.source, args.output, dpi, args.clip_geometry, tuple(args.clip_bounds) if args.clip_bounds else None)
