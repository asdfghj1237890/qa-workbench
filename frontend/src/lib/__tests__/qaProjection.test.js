import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from "vitest";
import { boundedView, fittedInitialView, groupLabels, initialView, inViewport, nearestPoint, screenPoint, spatialRegions, zoomView } from "../qaProjection.js";
import { normalize3d, screenPoint3d } from "../qaProjection3d.js";

// Pure display actions: observations describe screen geometry, not UMAP fitting.
function exploreAtPointer() {
  const before = { scale: 2, x: 35, y: -20 }, pointer = { x: 230, y: 180 };
  const after = zoomView(before, 1.5, pointer, 800, 420);
  const worldAt = (view) => ({ x: (pointer.x - 400 - view.x) / view.scale, y: (pointer.y - 210 - view.y) / view.scale });
  return { before: worldAt(before), after: worldAt(after) };
}
// Physical: synthetic persisted display geometry, anchored to projectedPoints in
// src/lib/qa.js; categories never determine where these independent blobs appear.
const blob = (cx, cy, count = 40, category = "A", site = "source") => Array.from({ length: count }, (_, i) => ({ cx: cx + (i % 6) * 3 - 7.5, cy: cy + Math.floor(i % 30 / 6) * 3 - 6, category, site }));
function exploreRegions(points, { colorBy = "category", width = 1000, height = 500, view = initialView() } = {}) {
  const regions = spatialRegions(points, colorBy);
  return { regions, labels: groupLabels(regions, view, width, height) };
}
function crowdedLabels(width = 330) {
  const points = Array.from({ length: 2500 }, (_, i) => ({ cx: 120 + i % 20, cy: 150 + i % 15, category: "Group " + i % 50, site: "source" }));
  return exploreRegions(points, { width, height: 300 }).labels;
}
function bridgeBetweenLargeLobes() {
  const points = [...blob(200, 250, 4000), ...blob(700, 250, 4000, "B")];
  for (let x = 240; x < 680; x += 18) points.push(...blob(x, 250, 3, "bridge"));
  return exploreRegions(points);
}
function aggregateWithoutPointAnchor() {
  const points = blob(400, 250, 30);
  return { points, ...exploreRegions(points) };
}
function croppedRegion() {
  const points = [...blob(500, 250, 39), { cx: 503, cy: 250, category: "A", site: "source" }];
  const regions = spatialRegions(points, "category");
  return { regions, labels: groupLabels(regions, { scale: 12, x: -596, y: 0 }, 300, 400) };
}
function largeProjection(count) {
  const points = Array.from({ length: count }, (_, i) => {
    const group = i % 9, member = Math.floor(i / 9);
    return { cx: 140 + group % 3 * 300 + Math.sin(member * 2.399) * (10 + member % 30), cy: 100 + Math.floor(group / 3) * 150 + Math.cos(member * 2.399) * (10 + member % 30), category: `Group ${group}`, site: "source" };
  });
  const started = performance.now(), regions = spatialRegions(points, "category"), clusterMs = performance.now() - started;
  const navigation = performance.now();
  for (let i = 0; i < 10; i++) groupLabels(regions, { scale: 1.5, x: i * 2, y: 0 }, 1100, 500);
  const navigationMs = performance.now() - navigation;
  const filter = performance.now(), filtered = spatialRegions(points.filter((point) => point.category !== "Group 0"), "category"), filterMs = performance.now() - filter;
  return { regions, filtered, clusterMs, navigationMs, filterMs };
}
function boxesIntersect(a, b) { return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y; }

function frameDistribution(kind, width = 1000, height = 500) {
  // Contract: persisted display coordinates consumed by screenPoint/screenPoint3d.
  const points = kind === "wide" ? [...blob(45, 45, 100), ...blob(950, 450, 100, "B")]
    : kind === "medium" ? [...blob(270, 160, 100), ...blob(730, 340, 100, "B")]
    : [...blob(680, 290, 200), { cx: 40, cy: 40 }, { cx: 960, cy: 460 }];
  const original = structuredClone(points), view = fittedInitialView(points, width, height);
  const visible = points.filter((point) => inViewport(screenPoint(point, view, width, height), width, height, 24));
  const core = screenPoint(points[100], view, width, height);
  return { view, share: visible.length / points.length, core, original, points, width, height };
}
function frameNative3d() {
  const points = normalize3d(Array.from({ length: 200 }, (_, i) => ({ x: Math.sin(i) * 5, y: Math.cos(i) * 3, z: Math.sin(i * 2) * 2 })));
  const view = fittedInitialView(points, 390, 420, screenPoint3d);
  return { view, share: points.filter((point) => inViewport(screenPoint3d(point, view, 390, 420), 390, 420, 24)).length / points.length };
}

describe("distribution-aware initial framing", () => {
  it("enlarges a compact off-center distribution by at most two existing zoom levels", () => {
    const result = frameDistribution("compact");
    expect(result.view.scale).toBe(2.25);
    expect(result.share).toBeGreaterThanOrEqual(.95);
    expect(Math.abs(result.core.sx - result.width / 2)).toBeLessThan(30);
    expect(result.points).toEqual(result.original);
  });
  it("uses one level for a wider distribution and retains all broad separated groups", () => {
    expect(frameDistribution("medium").view.scale).toBe(1.5);
    const wide = frameDistribution("wide");
    expect(wide.view).toEqual(initialView());
    expect(wide.share).toBe(1);
  });
  it("frames a narrow viewport and native 3D using the rendered geometry", () => {
    expect(frameDistribution("compact", 320, 400).share).toBeGreaterThanOrEqual(.95);
    const result = frameNative3d();
    expect(result.view.scale).toBeGreaterThan(1);
    expect(result.view.scale).toBeLessThanOrEqual(2.25);
    expect(result.share).toBeGreaterThanOrEqual(.95);
  });
  it("keeps empty and coincident data finite without arbitrary zoom", () => {
    expect(fittedInitialView([], 1000, 500)).toEqual(initialView());
    expect(fittedInitialView(blob(500, 250).map((point) => ({ ...point, cx: 500, cy: 250 })), 1000, 500)).toEqual(initialView());
  });
});

describe("projection navigation geometry", () => {
  it("keeps the coordinate under the pointer stationary while zooming", () => {
    const result = exploreAtPointer();
    expect(result.after.x).toBeCloseTo(result.before.x);
    expect(result.after.y).toBeCloseTo(result.before.y);
  });
  it("bounds extreme zoom and pan so reset remains meaningful", () => {
    const result = boundedView({ scale: 100, x: Infinity, y: -Infinity }, 800, 400);
    expect(result.scale).toBe(12);
    expect(Number.isFinite(result.x) && Number.isFinite(result.y)).toBe(true);
    expect(zoomView(initialView(), .00001, { x: 400, y: 200 }, 800, 400)).toEqual(initialView());
  });
  it("preserves relative distances on a narrow viewport and keeps the center centered", () => {
    const project = (cx, cy) => screenPoint({ cx, cy }, initialView(), 300, 400);
    const center = project(500, 250), right = project(600, 250), down = project(500, 350);
    expect(center).toMatchObject({ sx: 150, sy: 200 });
    expect(right.sx - center.sx).toBeCloseTo(down.sy - center.sy);
  });
  it("selects the nearest actual point within a usable touch target", () => {
    const a = { sx: 10, sy: 10, category: "A" }, b = { sx: 20, sy: 10, category: "B" };
    expect(nearestPoint([a, b], 18, 13)).toBe(b);
    expect(nearestPoint([a, b], 90, 90)).toBe(null);
  });
});

describe("spatial density region labels", () => {
  it("rejects singleton, small group and scattered metadata even at a category median", () => {
    const points = [...blob(200, 200), ...blob(800, 200), { cx: 500, cy: 200, category: "A", site: "source" }, ...blob(500, 400, 5, "tiny")];
    const { regions } = exploreRegions(points);
    expect(regions).toHaveLength(2);
    expect(regions.map((region) => region.name)).toEqual(["A", "A"]);
    expect(regions.map((region) => region.key)[0]).not.toBe(regions[1].key);
    expect(regions.every((region) => region.cx < 250 || region.cx > 750)).toBe(true);
    expect(exploreRegions(Array.from({ length: 20 }, (_, i) => ({ cx: 100 + i * 40, cy: 200, category: "A" }))).regions).toEqual([]);
  });
  it("anchors to the density neighborhood aggregate rather than choosing an individual article", () => {
    const { points, regions } = aggregateWithoutPointAnchor();
    expect(regions).toHaveLength(1);
    expect(regions[0].cx).toBeCloseTo(400);
    expect(regions[0].cy).toBeCloseTo(250);
    expect(points.some((point) => point.cx === regions[0].cx && point.cy === regions[0].cy)).toBe(false);
  });
  it("keeps two 8k lobes distinct across a low density bridge", () => {
    const { regions } = bridgeBetweenLargeLobes();
    expect(regions).toHaveLength(2);
    expect(regions.map((region) => region.name).sort()).toEqual(["A", "B"]);
    expect(regions.every((region) => region.count >= 4000)).toBe(true);
  });
  it("names spatial neighbors by their local majority rather than the nearest foreign category point", () => {
    const { regions } = exploreRegions([...blob(300, 250, 60, "A"), ...blob(300, 250, 15, "B"), ...blob(750, 250, 40, "B")]);
    expect(regions.map((region) => region.name)).toEqual(["A", "B"]);
    expect(regions[0].components[0].share).toBe(.8);
    expect(regions[0].count).toBe(75);
  });
  it("honestly identifies a mixed region with components and retains source-mode aggregation", () => {
    const points = [...blob(500, 250, 30, "A", "a"), ...blob(500, 250, 25, "B", "a")];
    const { regions, labels } = exploreRegions(points);
    expect(regions).toHaveLength(1);
    expect(regions[0]).toMatchObject({ name: null, mixed: true, count: 55 });
    expect(labels[0].fullText).toContain("Mixed: A 55% / B 45% · 55");
    expect(exploreRegions(points, { colorBy: "site" }).regions[0]).toMatchObject({ name: "a", mixed: false, count: 55 });
  });
  it("does not put a region-wide majority label on a center neighborhood dominated by another category", () => {
    const majority = Array.from({ length: 300 }, (_, i) => ({ cx: 400 + i % 15 * 6, cy: 200 + Math.floor(i / 15) * 4, category: "A", site: "source" }));
    const { regions } = exploreRegions([...majority, ...blob(490, 235, 80, "B")]);
    expect(regions).toHaveLength(1);
    expect(regions[0].components[0].share).toBeGreaterThan(.65);
    expect(regions[0]).toMatchObject({ name: null, mixed: true });
  });
  it("never renames a viewport fragment or invents a label for its lone visible point", () => {
    const { regions, labels } = croppedRegion();
    expect(regions).toHaveLength(1);
    expect(regions[0].count).toBe(40);
    expect(labels).toEqual([]);
  });
  it("limits a crowded mobile plot to nonoverlapping region labels inside its bounds", () => {
    const labels = crowdedLabels();
    expect(labels.length).toBeGreaterThan(0);
    expect(labels.length).toBeLessThanOrEqual(8);
    expect(labels.every((label) => label.x >= 12 && label.y >= 12 && label.x + label.width <= 318 && label.y + label.height <= 288)).toBe(true);
    expect(labels.some((a, index) => labels.slice(index + 1).some((b) => boxesIntersect(a, b)))).toBe(false);
  });
  it("keeps full metadata available when a long label must be shortened", () => {
    const name = "很長的來源名稱".repeat(20);
    const [label] = exploreRegions(blob(500, 250, 40, name), { width: 280, height: 300 }).labels;
    expect(label.fullText).toContain(name);
    expect(label.text.endsWith("…")).toBe(true);
    expect(label.width).toBeLessThanOrEqual(256);
    expect(groupLabels([], initialView(), 280, 300)).toEqual([]);
  });
  it.each([8289, 20000])("clusters, filters and navigates %i points without pairwise point work", (count) => {
    const result = largeProjection(count);
    expect(result.regions.length).toBeGreaterThanOrEqual(9);
    expect(result.filtered.every((region) => region.name !== "Group 0")).toBe(true);
    expect(result.clusterMs).toBeLessThan(1000);
    expect(result.filterMs).toBeLessThan(1000);
    expect(result.navigationMs).toBeLessThan(1000);
  });
});
