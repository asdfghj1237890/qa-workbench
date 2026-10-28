// Display geometry only: the persisted UMAP coordinates are never recomputed.
export const initialView = () => ({ scale: 1, x: 0, y: 0 });

export function boundedView(view, width, height) {
  const scale = Math.max(1, Math.min(12, view.scale));
  const limit = (size) => (scale - 1) * size / 2 + size * .3;
  return { scale, x: Math.max(-limit(width), Math.min(limit(width), view.x)), y: Math.max(-limit(height), Math.min(limit(height), view.y)) };
}

export function zoomView(view, factor, anchor, width, height) {
  const scale = Math.max(1, Math.min(12, view.scale * factor));
  const ratio = scale / view.scale;
  return boundedView({ scale,
    x: anchor.x - width / 2 - (anchor.x - width / 2 - view.x) * ratio,
    y: anchor.y - height / 2 - (anchor.y - height / 2 - view.y) * ratio,
  }, width, height);
}

export function screenPoint(point, view, width, height) {
  const fit = Math.max(.01, Math.min((width - 48) / 928, (height - 64) / 428));
  return { ...point,
    sx: width / 2 + (point.cx - 500) * fit * view.scale + view.x,
    sy: height / 2 + (point.cy - 250) * fit * view.scale + view.y,
  };
}

// Fit the rendered distribution, including native 3D perspective, without changing
// UMAP coordinates. A few outliers may stay outside; zooming out reveals them.
export function fittedInitialView(points, width, height, project = screenPoint) {
  const base = initialView();
  const screen = points.map((point) => project(point, base, width, height))
    .filter((point) => Number.isFinite(point.sx) && Number.isFinite(point.sy));
  // Tiny samples and coincident points do not provide a useful density estimate.
  if (screen.length < 20) return base;
  const bounds = (axis) => {
    const values = screen.map((point) => point[axis]).sort((a, b) => a - b);
    return [values[Math.floor((values.length - 1) * .025)], values[Math.ceil((values.length - 1) * .975)]];
  };
  const [left, right] = bounds("sx"), [top, bottom] = bounds("sy");
  if (Math.max(right - left, bottom - top) < 1) return base;
  for (const scale of [2.25, 1.5]) {
    if ((right - left) * scale > width - 48 || (bottom - top) * scale > height - 48) continue;
    const view = boundedView({ scale, x: (width / 2 - (left + right) / 2) * scale, y: (height / 2 - (top + bottom) / 2) * scale }, width, height);
    const visible = screen.filter((point) => inViewport({ sx: width / 2 + (point.sx - width / 2) * scale + view.x, sy: height / 2 + (point.sy - height / 2) * scale + view.y }, width, height, 24)).length;
    if (visible >= screen.length * .95) return view;
  }
  return base;
}

export function inViewport(point, width, height, margin = 8) {
  return point.sx >= margin && point.sx <= width - margin && point.sy >= margin && point.sy <= height - margin;
}

export function nearestPoint(points, x, y, radius = 16) {
  let nearest = null, distance = radius * radius;
  for (const point of points) {
    const next = (point.sx - x) ** 2 + (point.sy - y) ** 2;
    if (next <= distance) { nearest = point; distance = next; }
  }
  return nearest;
}

const textWidth = (text) => [...text].reduce((sum, char) => sum + (/[^\u0000-\u00ff]/.test(char) ? 12 : 7), 0);
function fitText(text, width) {
  if (textWidth(text) <= width) return text;
  const chars = [...text];
  while (chars.length && textWidth(chars.join("")) > width - 12) chars.pop();
  return chars.join("") + "…";
}
const overlaps = (a, b) => a.x < b.x + b.width + 6 && a.x + a.width + 6 > b.x && a.y < b.y + b.height + 6 && a.y + a.height + 6 > b.y;

// Fixed projection-space bins keep regions independent of zoom, viewport and metadata.
// A grid watershed avoids pairwise point comparisons, including coincident 20k points.
// A shallow density valley joins one region; a sparse bridge between peaks does not.
const CELL = 18, VALLEY_RATIO = .45;
const cellKey = (x, y) => `${x},${y}`;
const neighbors = (cell, cells) => {
  const result = [];
  for (let x = cell.x - 1; x <= cell.x + 1; x++) for (let y = cell.y - 1; y <= cell.y + 1; y++) {
    const found = cells.get(cellKey(x, y));
    if (found) result.push(found);
  }
  return result;
};
const rankedCounts = (members, colorBy) => {
  const counts = new Map();
  for (const point of members) counts.set(point[colorBy], (counts.get(point[colorBy]) || 0) + 1);
  return [...counts].map(([name, count]) => ({ name, count, share: count / members.length })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
};
export function spatialRegions(points, colorBy) {
  const cells = new Map(), minimum = Math.max(12, Math.ceil(points.length * .002));
  const coreMinimum = Math.max(3, Math.ceil(points.length / 5000));
  for (const point of points) {
    if (!Number.isFinite(point.cx) || !Number.isFinite(point.cy)) continue;
    const x = Math.floor(point.cx / CELL), y = Math.floor(point.cy / CELL), key = cellKey(x, y);
    if (!cells.has(key)) cells.set(key, { key, x, y, members: [], density: 0 });
    cells.get(key).members.push(point);
  }
  const core = new Map([...cells].filter(([, cell]) => cell.members.length >= coreMinimum));
  for (const cell of core.values()) cell.density = neighbors(cell, cells).reduce((sum, item) => sum + item.members.length, 0);
  const uphill = (a, b) => b.density - a.density || a.x - b.x || a.y - b.y;
  const basins = new Map();
  for (const cell of [...core.values()].sort(uphill)) {
    const higher = neighbors(cell, core).sort(uphill)[0];
    cell.basin = higher !== cell && basins.has(higher.key) ? basins.get(higher.key) : cell;
    basins.set(cell.key, cell.basin);
  }
  const parent = new Map(), peak = new Map();
  for (const cell of core.values()) { parent.set(cell.basin.key, cell.basin.key); peak.set(cell.basin.key, cell.basin.density); }
  const root = (key) => { let at = key; while (parent.get(at) !== at) at = parent.get(at); while (key !== at) { const next = parent.get(key); parent.set(key, at); key = next; } return at; };
  const edges = [];
  for (const cell of core.values()) for (const other of neighbors(cell, core)) if (cell.key < other.key && cell.basin !== other.basin) edges.push({ a: cell.basin.key, b: other.basin.key, saddle: Math.min(cell.density, other.density) });
  edges.sort((a, b) => b.saddle - a.saddle || a.a.localeCompare(b.a) || a.b.localeCompare(b.b));
  for (const edge of edges) {
    let a = root(edge.a), b = root(edge.b);
    if (a === b || edge.saddle < Math.min(peak.get(a), peak.get(b)) * VALLEY_RATIO) continue;
    if (peak.get(a) < peak.get(b) || (peak.get(a) === peak.get(b) && a > b)) [a, b] = [b, a];
    parent.set(b, a); peak.set(a, Math.max(peak.get(a), peak.get(b)));
  }
  const groups = new Map();
  for (const cell of cells.values()) {
    const owner = core.has(cell.key) ? cell : neighbors(cell, core).sort(uphill)[0];
    if (!owner) continue; // Isolated points and sparse outliers have no region.
    const key = root(owner.basin.key);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(cell);
  }
  const regions = [];
  for (const [key, area] of groups) {
    const members = area.flatMap((cell) => cell.members);
    if (members.length < minimum) continue;
    const center = core.get(key);
    // A density-peak neighborhood centroid is an aggregate, never a selected article.
    const central = area.filter((cell) => Math.abs(cell.x - center.x) <= 1 && Math.abs(cell.y - center.y) <= 1).flatMap((cell) => cell.members);
    if (central.length < minimum) continue;
    const components = rankedCounts(members, colorBy), local = rankedCounts(central, colorBy);
    const first = components[0], second = components[1]?.share || 0;
    const dominant = first.share >= .65 && first.share - second >= .2 && local[0].name === first.name && local[0].share >= .65;
    regions.push({ key: `region:${key}`, name: dominant ? first.name : null, mixed: !dominant, count: members.length, components,
      cx: central.reduce((sum, point) => sum + point.cx, 0) / central.length,
      cy: central.reduce((sum, point) => sum + point.cy, 0) / central.length,
      members, minimum,
    });
  }
  return regions.sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
}

// Region memberships and metadata are cached by the Vue caller. Navigation only
// transforms aggregate anchors and checks the original region's visible support.
export function groupLabels(regions, view, width, height, labelFor = (name) => name, mixedFor = (parts) => `Mixed: ${parts}`, project = screenPoint) {
  const labels = [];
  const limit = width < 600 ? 8 : 20;
  const offsets = [[0, -25], [0, 25], [0, -55], [0, 55], [60, 0], [-60, 0], [60, -45], [-60, 45]];
  for (const region of regions) {
    if (labels.length >= limit) break;
    const anchor = project(region, view, width, height);
    if (!inViewport(anchor, width, height, 12)) continue;
    let visible = 0;
    for (const point of region.members) if (inViewport(project(point, view, width, height), width, height, 12)) visible++;
    if (visible < Math.max(region.minimum, Math.ceil(region.count * .2))) continue;
    const parts = region.components.slice(0, 2).map((part) => `${labelFor(part.name)} ${Math.round(part.share * 100)}%`).join(" / ");
    const title = region.mixed ? mixedFor(parts) : `${labelFor(region.name)} ${Math.round(region.components[0].share * 100)}%`;
    const fullText = `${title} · ${region.count}`, text = fitText(fullText, Math.min(260, width - 40));
    const boxWidth = Math.min(width - 24, textWidth(text) + 18);
    for (const [dx, dy] of offsets) {
      const box = { x: Math.max(12, Math.min(width - boxWidth - 12, anchor.sx - boxWidth / 2 + dx)), y: Math.max(12, Math.min(height - 36, anchor.sy - 12 + dy)), width: boxWidth, height: 24 };
      if (labels.some((other) => overlaps(box, other))) continue;
      labels.push({ ...box, key: region.key, name: region.name, mixed: region.mixed, text, fullText, count: region.count, anchorX: anchor.sx, anchorY: anchor.sy });
      break;
    }
  }
  return labels;
}
