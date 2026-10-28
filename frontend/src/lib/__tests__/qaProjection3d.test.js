import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from "vitest";
import { normalize3d, initialOrbit, orbitCamera, screenPoint3d, spatialRegions3d } from "../qaProjection3d.js";
import { groupLabels, initialView } from "../qaProjection.js";
import fixture from "../../../e2e/observatory-3d-fixture.cjs";
import { projectedPoints } from "../qa.js";

// Action: construct only persisted fixture geometry and observe real display logic.
function explore3d(count = 900) {
  const points = normalize3d(projectedPoints(fixture.points3d(count)));
  const start = performance.now(), regions = spatialRegions3d(points, "category"), clusterMs = performance.now() - start;
  const camera = initialOrbit(), rotated = orbitCamera(camera, 70, 20);
  const project = (orbit) => (point, view, width, height) => screenPoint3d(point, view, width, height, orbit);
  const first = screenPoint3d(points[0], initialView(), 1000, 440, camera), after = screenPoint3d(points[0], initialView(), 1000, 440, rotated);
  const navigate = performance.now();
  const labels = groupLabels(regions, initialView(), 1000, 440, undefined, undefined, project(camera));
  const rotatedLabels = groupLabels(regions, initialView(), 1000, 440, undefined, undefined, project(rotated));
  const navigationMs = performance.now() - navigate;
  return { points, regions, first, after, labels, rotatedLabels, clusterMs, navigationMs };
}
function overlappingDepths() {
  const points = [-1, 1].flatMap((z, group) => Array.from({ length: 60 }, (_, i) => ({ x: (i % 6 - 2.5) * .01, y: (Math.floor(i / 6) - 4.5) * .01, z: z + (i % 3 - 1) * .01, category: group ? "B" : "A", site: "source" })));
  const normalized = normalize3d(projectedPoints(points));
  return { points: normalized, regions: spatialRegions3d(normalized, "category") };
}
function mixedDepth() {
  const points = fixture.points3d(900).map((point, i) => i % 18 === 0 ? { ...point, category: "國際" } : point);
  return spatialRegions3d(normalize3d(projectedPoints(points)), "category");
}
describe("persisted 3D UMAP exploration", () => {
  it("preserves isotropic geometry and fits finite three-dimensional coordinates", () => {
    const result = explore3d();
    expect(result.points.every((point) => [point.nx, point.ny, point.nz].every(Number.isFinite))).toBe(true);
    expect(result.first.sx).not.toBeCloseTo(result.after.sx);
    expect(result.first.sy).not.toBeCloseTo(result.after.sy);
    expect(normalize3d([])).toEqual([]);
    expect(normalize3d([{ x: 2, y: 2, z: 2 }])[0]).toMatchObject({ nx: 0, ny: 0, nz: 0 });
  });
  it("keeps overlapping XY lobes separate by depth and anchors at aggregates", () => {
    const { points, regions } = overlappingDepths();
    expect(regions).toHaveLength(2);
    expect(regions.map((region) => region.name).sort()).toEqual(["A", "B"]);
    expect(regions.every((region) => region.support >= 12 && region.count === 60)).toBe(true);
    expect(regions.every((region) => !points.some((point) => point.nx === region.nx && point.ny === region.ny && point.nz === region.nz))).toBe(true);
    expect(Math.abs(regions[0].nz - regions[1].nz)).toBeGreaterThan(1.8);
  });
  it("keeps full region membership and metadata stable under orbit, and marks mixed regions", () => {
    const result = explore3d();
    expect(result.regions).toHaveLength(9);
    expect(result.labels.length).toBeGreaterThan(0);
    expect(result.rotatedLabels.length).toBeGreaterThan(0);
    expect(result.labels.every((label) => result.regions.some((region) => region.key === label.key && region.count === label.count && region.name === label.name))).toBe(true);
    expect(result.rotatedLabels.every((label) => result.regions.some((region) => region.key === label.key && region.count === label.count && region.name === label.name))).toBe(true);
    expect(mixedDepth().some((region) => region.mixed && region.count === 100)).toBe(true);
  });
  it("does not label singleton or small scattered groups", () => {
    const points = normalize3d(Array.from({ length: 9 }, (_, i) => ({ x: i, y: i * i, z: i * 2, category: "A" })));
    expect(spatialRegions3d(points, "category")).toEqual([]);
  });
  it.each([8000, 20000])("supports %i points without quadratic point comparisons", (count) => {
    const result = explore3d(count);
    expect(result.regions).toHaveLength(9);
    expect(result.regions.reduce((sum, region) => sum + region.count, 0)).toBe(count);
    expect(result.clusterMs).toBeLessThan(1500);
    expect(result.navigationMs).toBeLessThan(1500);
  });
});
