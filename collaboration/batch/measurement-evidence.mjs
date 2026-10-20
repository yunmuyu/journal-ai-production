import {VERSION, digest, nonempty, requireHash, uniqueMap} from './contracts.mjs';

/** Coordinate normalization only. No segmentation, collision solving or text recognition. */
export function normalizeMeasurements(input, expectedSourceHash) {
  requireHash(expectedSourceHash, 'expectedSourceHash');
  if (input.sourceHash !== expectedSourceHash) throw Error('Stale measurement source');
  nonempty(input.engineVersion, 'engineVersion');
  if (!['native', 'vector', 'raster'].includes(input.kind)) throw Error('Unknown measurement kind');
  if (!['pt', 'px'].includes(input.unit)) throw Error('Explicit pt or px units required');
  if (!['top-left', 'bottom-left'].includes(input.origin)) throw Error('Explicit coordinate origin required');
  if (input.unit === 'px' && (!Number.isFinite(input.dpi) || input.dpi <= 0)) throw Error('Pixel evidence requires explicit DPI');
  const scale = input.unit === 'px' ? 72 / input.dpi : 1;
  const {width, height} = input.page || {};
  if (![width, height].every(x => Number.isFinite(x) && x > 0)) throw Error('Positive page dimensions required');
  if (!Number.isInteger(input.pageIndex) || input.pageIndex < 0) throw Error('pageIndex required');
  if (!Number.isFinite(input.uncertainty) || input.uncertainty < 0) throw Error('Measurement uncertainty required');
  if (input.unit === 'px' && input.uncertainty < 0.5) throw Error('Pixel measurements cannot claim subpixel certainty');
  const objects = [...uniqueMap(input.objects, 'measurement').values()].map(object => {
    const {x, y, width: w, height: h} = object.bounds || {};
    if (![x, y, w, h].every(Number.isFinite) || w < 0 || h < 0) throw Error(`Invalid bounds: ${object.id}`);
    const top = input.origin === 'top-left' ? y : height - y - h;
    const role = object.role || 'unknown';
    if (role !== 'unknown') requireHash(object.roleEvidenceHash, 'roleEvidenceHash');
    return {id: object.id, role, roleEvidenceHash: object.roleEvidenceHash || null,
      boundsPt: {x: x * scale, y: top * scale, width: w * scale, height: h * scale},
      editableText: input.kind === 'native' && object.editableText === true,
      clipped: x < 0 || top < 0 || x + w > width || top + h > height};
  });
  const result = {version: VERSION, sourceHash: expectedSourceHash, engineVersion: input.engineVersion,
    kind: input.kind, pageIndex: input.pageIndex, pagePt: {width: width * scale, height: height * scale},
    unit: 'pt', origin: 'top-left', uncertaintyPt: input.uncertainty * scale,
    approximate: input.kind !== 'native', objects, semanticCompleteness: 'unverified'};
  return {...result, fingerprint: digest(result)};
}
