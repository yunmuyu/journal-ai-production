import fs from 'node:fs';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';

// Optional checks over a measured public Scene; never a substitute for PDF review.
export function inspectRelations(scene, recipe) {
  const index = (items) => {
    const result = new Map();
    for (const item of items) {
      if (!item.id || result.has(item.id)) throw Error('Missing or duplicate Scene id');
      result.set(item.id, item);
    }
    return result;
  };
  const nodes = index(scene.nodes), paths = index(scene.paths), texts = index(scene.texts);
  const get = (map, id) => {
    if (!map.has(id)) throw Error(`Unknown Scene object: ${id}`);
    return map.get(id);
  };
  const numeric = (values) => {
    if (!Array.isArray(values) || !values.every(Number.isFinite)) throw Error('Non-finite geometry');
    return values;
  };
  const rect = (value) => {
    const r = numeric(value);
    if (r.length !== 4 || r[0] >= r[2] || r[1] >= r[3]) throw Error('Invalid measured rectangle');
    return r;
  };
  const vertical = (id, ink = null) => {
    const p = get(paths, id).points;
    if (!Array.isArray(p) || p.length < 2) throw Error('Missing path points');
    p.forEach(point => { if (numeric(point).length !== 2) throw Error('Invalid point'); });
    if (ink) {
      const segments = p.slice(1).map((point,i)=>[p[i],point]).filter(([a,b])=>Math.abs(a[0]-b[0]) <= 0.00001 && Math.min(a[1],b[1]) <= ink[1] && Math.max(a[1],b[1]) >= ink[3]);
      if (segments.length !== 1) throw Error(`Label needs one unambiguous vertical segment: ${id}`);
      return segments[0][0][0];
    }
    if (p.some(point => Math.abs(point[0] - p[0][0]) > 0.00001)) throw Error(`Path is not vertical: ${id}`);
    return p[0][0];
  };
  if (!Array.isArray(recipe.rules) || !recipe.rules.length) throw Error('Empty relation recipe');
  const seen = new Set();
  return recipe.rules.map(rule => {
    if (!rule.id || seen.has(rule.id)) throw Error('Missing or duplicate rule id');
    seen.add(rule.id);
    if (rule.type === 'horizontal_gap') {
      const left = rect(get(nodes, rule.left).rect), right = rect(get(nodes, rule.right).rect);
      numeric([rule.minimum_pt]);
      const widths = [get(nodes, rule.left).width, get(nodes, rule.right).width];
      numeric(widths);
      if (widths.some(w=>w < 0)) throw Error('Invalid stroke width');
      const geometricGap = right[0] - left[2];
      const gap = geometricGap - (widths[0] + widths[1]) / 2;
      const yOverlap = Math.min(left[3], right[3]) - Math.max(left[1], right[1]);
      return {id:rule.id, passed:yOverlap > 0 && gap + 0.00001 >= rule.minimum_pt, gap_pt:gap, geometric_gap_pt:geometricGap, stroke_widths_pt:widths, y_overlap_pt:yOverlap, minimum_pt:rule.minimum_pt};
    }
    if (rule.type === 'vertical_path') {
      return {id:rule.id, passed:true, x_pt:vertical(rule.path)};
    }
    if (rule.type === 'label_left_corridor') {
      const ink = rect(get(texts, rule.label).ink_bounds), x = vertical(rule.path, ink);
      const upper = rect(get(nodes, rule.upper_node).rect)[3];
      const frame = get(paths, rule.lower_frame).points;
      frame.forEach(numeric);
      const lower = Math.min(...frame.map(p=>p[1]));
      numeric([upper, lower, rule.minimum_pt, rule.maximum_pt]);
      const gap = x - ink[2];
      return {id:rule.id, passed:ink[1] - upper >= rule.minimum_pt && lower - ink[3] >= rule.minimum_pt && gap >= rule.minimum_pt && gap <= rule.maximum_pt, ink_bounds:ink, path_x_pt:x, gap_pt:gap, corridor_y_pt:[upper,lower]};
    }
    throw Error(`Unsupported rule: ${rule.type}`);
  });
}

if (process.argv[1] && fileURLToPath(import.meta.url) === fs.realpathSync(process.argv[1])) {
  try {
    if (process.argv.length !== 4) throw Error('Usage: node diagram-relations.mjs measured-scene.json recipe.json');
    const [scenePath, recipePath] = process.argv.slice(2);
    const sceneBytes = fs.readFileSync(scenePath), recipeBytes = fs.readFileSync(recipePath);
    const data = JSON.parse(sceneBytes);
    const checks = inspectRelations(data.scene ?? data, JSON.parse(recipeBytes));
    const digest = b=>crypto.createHash('sha256').update(b).digest('hex');
    const ok = checks.every(c=>c.passed);
    console.log(JSON.stringify({ok,scene_sha256:digest(sceneBytes),recipe_sha256:digest(recipeBytes),checks,coverage:'Measured Scene relationships only; actual PDF and source semantics require independent review'},null,2));
    if (!ok) process.exitCode = 1;
  } catch (error) {
    console.log(JSON.stringify({ok:false,error:String(error.message)})); process.exitCode = 1;
  }
}
