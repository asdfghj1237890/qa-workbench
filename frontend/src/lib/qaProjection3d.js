// Camera geometry only. UMAP x/y/z are persisted by the native producer.
// One isotropic normalization preserves distances; no axis is synthesized.
export function normalize3d(points) {
  if (!points.length) return [];
  const bounds = ["x", "y", "z"].map((axis) => {
    let min = Infinity, max = -Infinity;
    for (const point of points) { min = Math.min(min, point[axis]); max = Math.max(max, point[axis]); }
    return { center: (min + max) / 2, span: max - min };
  });
  const scale = Math.max(...bounds.map((bound) => bound.span)) / 2 || 1;
  return points.map((point) => ({ ...point, nx: (point.x - bounds[0].center) / scale, ny: (point.y - bounds[1].center) / scale, nz: (point.z - bounds[2].center) / scale }));
}

export const initialOrbit = () => ({ yaw: -.45, pitch: .25 });
export function orbitCamera(camera, dx, dy) {
  return { yaw: ((camera.yaw + dx * .008) % (Math.PI * 2)), pitch: Math.max(-Math.PI / 2 + .03, Math.min(Math.PI / 2 - .03, camera.pitch + dy * .008)) };
}
export function screenPoint3d(point, view, width, height, camera = initialOrbit()) {
  const cosY = Math.cos(camera.yaw), sinY = Math.sin(camera.yaw), cosP = Math.cos(camera.pitch), sinP = Math.sin(camera.pitch);
  const x = point.nx * cosY + point.nz * sinY, z = -point.nx * sinY + point.nz * cosY;
  const y = point.ny * cosP - z * sinP, depth = point.ny * sinP + z * cosP;
  const perspective = 4 / (4 - depth), fit = Math.max(20, Math.min(width - 48, height - 64)) * .32;
  return { ...point, sx: width / 2 + x * fit * perspective * view.scale + view.x, sy: height / 2 - y * fit * perspective * view.scale + view.y, depth, radius: Math.max(1.6, Math.min(5, 2.8 * perspective)) };
}

// Fixed normalized 3D voxels and watershed: screen overlap cannot merge distinct
// depths. Memberships and aggregate peak anchors do not change during rotation.
const CELL = .12, VALLEY = .45;
const keyOf = (x, y, z) => `${x},${y},${z}`;
function neighbors(cell, cells) {
  const result = [];
  for (let x = cell.x - 1; x <= cell.x + 1; x++) for (let y = cell.y - 1; y <= cell.y + 1; y++) for (let z = cell.z - 1; z <= cell.z + 1; z++) {
    const found = cells.get(keyOf(x, y, z));
    if (found) result.push(found);
  }
  return result;
}
const countsFor = (points, colorBy) => {
  const counts = new Map();
  for (const point of points) counts.set(point[colorBy], (counts.get(point[colorBy]) || 0) + 1);
  return [...counts].map(([name, count]) => ({ name, count, share: count / points.length })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
};
export function spatialRegions3d(points, colorBy) {
  const cells = new Map(), minimum = Math.max(12, Math.ceil(points.length * .002)), coreMinimum = Math.max(3, Math.ceil(points.length / 5000));
  for (const point of points) {
    if (![point.nx, point.ny, point.nz].every(Number.isFinite)) continue;
    const x = Math.floor(point.nx / CELL), y = Math.floor(point.ny / CELL), z = Math.floor(point.nz / CELL), key = keyOf(x, y, z);
    if (!cells.has(key)) cells.set(key, { key, x, y, z, members: [] });
    cells.get(key).members.push(point);
  }
  const core = new Map([...cells].filter(([, cell]) => cell.members.length >= coreMinimum));
  for (const cell of core.values()) cell.density = neighbors(cell, cells).reduce((sum, item) => sum + item.members.length, 0);
  const uphill = (a, b) => b.density - a.density || a.x - b.x || a.y - b.y || a.z - b.z;
  for (const cell of [...core.values()].sort(uphill)) {
    const higher = neighbors(cell, core).sort(uphill)[0];
    cell.basin = higher !== cell && higher.basin ? higher.basin : cell;
  }
  const parent = new Map(), peak = new Map();
  for (const cell of core.values()) { parent.set(cell.basin.key, cell.basin.key); peak.set(cell.basin.key, cell.basin.density); }
  const root = (key) => { let at = key; while (parent.get(at) !== at) at = parent.get(at); while (key !== at) { const next = parent.get(key); parent.set(key, at); key = next; } return at; };
  const edges = [];
  for (const cell of core.values()) for (const other of neighbors(cell, core)) if (cell.key < other.key && cell.basin !== other.basin) edges.push({ a: cell.basin.key, b: other.basin.key, saddle: Math.min(cell.density, other.density) });
  edges.sort((a, b) => b.saddle - a.saddle || a.a.localeCompare(b.a) || a.b.localeCompare(b.b));
  for (const edge of edges) {
    let a = root(edge.a), b = root(edge.b);
    if (a === b || edge.saddle < Math.min(peak.get(a), peak.get(b)) * VALLEY) continue;
    if (peak.get(a) < peak.get(b) || (peak.get(a) === peak.get(b) && a > b)) [a, b] = [b, a];
    parent.set(b, a); peak.set(a, Math.max(peak.get(a), peak.get(b)));
  }
  const groups = new Map();
  for (const cell of cells.values()) {
    const owner = core.has(cell.key) ? cell : neighbors(cell, core).sort(uphill)[0];
    if (!owner) continue;
    const key = root(owner.basin.key);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(cell);
  }
  const regions = [];
  for (const [key, area] of groups) {
    const members = area.flatMap((cell) => cell.members), center = core.get(key);
    if (members.length < minimum) continue;
    const central = area.filter((cell) => Math.abs(cell.x - center.x) <= 1 && Math.abs(cell.y - center.y) <= 1 && Math.abs(cell.z - center.z) <= 1).flatMap((cell) => cell.members);
    if (central.length < minimum) continue;
    const components = countsFor(members, colorBy), local = countsFor(central, colorBy), first = components[0];
    const dominant = first.share >= .65 && first.share - (components[1]?.share || 0) >= .2 && local[0].name === first.name && local[0].share >= .65;
    const anchor = {};
    for (const axis of ["nx", "ny", "nz", "cx", "cy"]) anchor[axis] = central.reduce((sum, point) => sum + point[axis], 0) / central.length;
    regions.push({ ...anchor, key: `region3d:${key}`, name: dominant ? first.name : null, mixed: !dominant, count: members.length, components, members, minimum, support: central.length });
  }
  return regions.sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
}
