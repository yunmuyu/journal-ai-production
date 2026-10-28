"""Optional vector clip algebra for EMF application and meta regions.

The region is represented as either a finite geometry or its complement, so
an unbounded clip never has to be approximated by the source page rectangle.
"""
from __future__ import annotations
from dataclasses import dataclass
import struct
from .errors import AuditInputError

try:
    from shapely.affinity import translate
    from shapely.geometry import GeometryCollection, LineString, Polygon, box, mapping
    from shapely.geometry.base import BaseGeometry
    from shapely.ops import unary_union
except ImportError as exc:
    raise AuditInputError('vector clipping requires optional shapely dependency; see requirements-clip.txt') from exc


@dataclass(frozen=True, slots=True)
class Region:
    geometry: BaseGeometry
    complement: bool = False


def universe():
    return Region(GeometryCollection(), True)


def combine(a, b, mode):
    """Combine finite or complemented sets without inventing finite bounds."""
    if mode == 5:
        return b
    if mode == 4:
        return combine(a, Region(b.geometry, not b.complement), 1)
    if mode == 3:
        left = combine(a, b, 4)
        right = combine(b, a, 4)
        return combine(left, right, 2)
    if mode == 2:
        result = combine(Region(a.geometry, not a.complement), Region(b.geometry, not b.complement), 1)
        return Region(result.geometry, not result.complement)
    if mode != 1:
        raise AuditInputError('invalid EMF clip region combine mode')
    if not a.complement and not b.complement:
        return Region(a.geometry.intersection(b.geometry))
    if a.complement and b.complement:
        return Region(a.geometry.union(b.geometry), True)
    if a.complement:
        return Region(b.geometry.difference(a.geometry))
    return Region(a.geometry.difference(b.geometry))


def region_from_record(data):
    if len(data) < 16:
        raise AuditInputError('truncated EMF clip region record')
    length, mode = struct.unpack_from('<II', data, 8)
    if mode not in (1, 2, 3, 4, 5) or length > len(data)-16:
        raise AuditInputError('invalid EMF clip region mode or length')
    if length == 0:
        if mode != 5:
            raise AuditInputError('null EMF clip region requires RGN_COPY')
        return mode, universe()
    if length < 32:
        raise AuditInputError('truncated EMF region data header')
    header_size, region_type, count, region_size = struct.unpack_from('<IIII', data, 16)
    if header_size != 32 or region_type != 1 or count > 4096 or region_size != count*16 or length != 32+region_size:
        raise AuditInputError('invalid EMF rectangle region data')
    rectangles=[]
    for index in range(count):
        left, top, right, bottom = struct.unpack_from('<iiii', data, 48+index*16)
        if left >= right or top >= bottom:
            raise AuditInputError('invalid EMF clip rectangle')
        rectangles.append(box(left, top, right, bottom))
    return mode, Region(unary_union(rectangles) if rectangles else GeometryCollection())


@dataclass(frozen=True, slots=True)
class ClipModel:
    application: Region
    meta: Region
    surface: Region
    application_known: bool = True
    meta_known: bool = True

    @property
    def known(self):
        return self.application_known and self.meta_known

    @property
    def effective(self):
        return combine(combine(self.application, self.meta, 1),self.surface,1)


def initial(bounds):
    if len(bounds)!=4 or bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:
        raise AuditInputError('clip device bounds must be a nonempty rectangle')
    surface=Region(box(*bounds))
    return ClipModel(surface, universe(), surface)


def polygon_region(points):
    polygon=Polygon(points)
    if not polygon.is_valid:
        raise AuditInputError('invalid EMF clip polygon')
    return Region(polygon)


def apply_event(model, kind, payload, state):
    app,meta=model.application,model.meta
    app_known,meta_known=model.application_known,model.meta_known
    if kind in (29,30):
        if state['coordinate_status']=='unknown':
            app_known=False
        else:
            points=state['clip_exclusions' if kind==29 else 'clip_regions'][-1]
            app=combine(app,polygon_region(points),4 if kind==29 else 1)
    elif kind==26:
        if state['coordinate_status']=='unknown':
            app_known=False
        else:
            from .emf_geometry import _device_point
            offset=struct.unpack_from('<ii',payload,8)
            origin=_device_point((0,0),state);target=_device_point(offset,state)
            app=Region(translate(app.geometry,xoff=target[0]-origin[0],yoff=target[1]-origin[1]),app.complement)
    elif kind==28:
        meta=combine(meta,app,1);meta_known=meta_known and app_known
        app=model.surface;app_known=True
    elif kind==67:
        app_known=False
    elif kind==115:
        app_known=False;meta_known=False
    elif kind==75:
        mode,region=region_from_record(payload)
        if mode==5 and region.complement:
            region=model.surface
        app=combine(app,region,mode)
        app_known=True if mode==5 else app_known
    return ClipModel(app,meta,model.surface,app_known,meta_known)


def clipped_geometry(points, closed, filled, kind, clip):
    if not clip.known:
        return {'status':'unknown'}
    if kind=='ellipse':
        return {'status':'unsupported-ellipse'}
    coords=list(points)
    if closed and coords[0]!=coords[-1]:coords.append(coords[0])
    stroke=LineString(coords)
    region=clip.effective
    clip_one=lambda shape:shape.difference(region.geometry) if region.complement else shape.intersection(region.geometry)
    result={'status':'clipped','stroke_centerline':mapping(clip_one(stroke))}
    if filled and closed:
        polygon=Polygon(coords)
        if not polygon.is_valid:
            return {'status':'unsupported-invalid-polygon'}
        result['fill']=mapping(clip_one(polygon))
    return result


def map_geometry_mm(data, point_to_mm):
    """Convert a GeoJSON geometry's device coordinates to reference mm."""
    if 'geometries' in data:
        return {'type':data['type'],'geometries':[map_geometry_mm(g,point_to_mm) for g in data['geometries']]}
    def map_coords(coords):
        if not coords:return []
        if isinstance(coords[0],(int,float)):
            return list(point_to_mm(coords))
        return [map_coords(c) for c in coords]
    return {'type':data['type'],'coordinates':map_coords(data['coordinates'])}
