import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from "vitest";
import fixtures from "../../../e2e/observatory-physical.cjs";
import { projectedPoints, validQaSnapshot } from "../qa.js";

// Contract and projection actions keep mutation and coordinate details out of scripts.
function snapshotWith(change) { const value = fixtures.snapshotBody(); change(value); return value; }
function legacySnapshot() { return snapshotWith((value) => { for (const point of value.projection.points) { delete point.title; delete point.url; } }); }
function plotOfTriangle() { return projectedPoints([{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 0, y: 1 }]); }
const distance = (a, b) => Math.hypot(a.cx - b.cx, a.cy - b.cy);
const NEWS_FIELDS = { title: "合成新聞", url: "https://news.example.test/article" };

describe("authenticated QA snapshot contract", () => {
  it("接受正常、空索引與有效向量不足的快照契約", () => {
    expect(validQaSnapshot(legacySnapshot())).toBe(true);
    expect(validQaSnapshot(fixtures.snapshotBody("empty"))).toBe(true);
    expect(validQaSnapshot(fixtures.snapshotBody("insufficient"))).toBe(true);
  });
  it("拒絕向量母體與文章數不一致，防止覆蓋率誤導", () => {
    expect(validQaSnapshot(snapshotWith((value) => { value.embedding.missing = 1; }))).toBe(false);
  });
  it("拒絕投影樣本數與實際點數不一致", () => {
    expect(validQaSnapshot(snapshotWith((value) => { value.projection.sample_size = 3; }))).toBe(false);
  });
  it("拒絕非有限投影座標，避免產生無效 SVG", () => {
    expect(validQaSnapshot(snapshotWith((value) => { value.projection.points[0].x = Infinity; }))).toBe(false);
  });
  it("接受舊快照省略新聞欄位或新版字串資訊，拒絕損壞的新聞欄位型別", () => {
    expect(validQaSnapshot(fixtures.snapshotBody())).toBe(true);
    expect(validQaSnapshot(snapshotWith((value) => { Object.assign(value.projection.points[0], NEWS_FIELDS); }))).toBe(true);
    for (const field of ["title", "url"]) for (const invalid of [null, 42, {}, []]) {
      expect(validQaSnapshot(snapshotWith((value) => { value.projection.points[0][field] = invalid; }))).toBe(false);
    }
  });
  it("接受真三維與明示二維契約，省略維度仍視為舊二維", () => {
    expect(validQaSnapshot(fixtures.snapshotBody("3d"))).toBe(true);
    expect(validQaSnapshot(snapshotWith((value) => { value.projection.dimensions = 2; }))).toBe(true);
    expect(validQaSnapshot(snapshotWith((value) => { value.projection.dimensions = 3; value.projection.points = value.projection.points.map((point) => ({ ...point, z: 0 })); }))).toBe(true);
  });
  it("拒絕混維、不匹配維度與缺漏或非有限z，不以xy補z", () => {
    for (const z of [undefined, null, Infinity, NaN, "1"]) {
      const value = fixtures.snapshotBody("3d"); value.projection.points[0].z = z;
      expect(validQaSnapshot(value)).toBe(false);
    }
    expect(validQaSnapshot(snapshotWith((value) => { value.projection.points[0].z = 0; }))).toBe(false);
    expect(validQaSnapshot(snapshotWith((value) => { value.projection.dimensions = 3; }))).toBe(false);
    expect(validQaSnapshot(snapshotWith((value) => { value.projection.dimensions = 4; }))).toBe(false);
    expect(validQaSnapshot(snapshotWith((value) => { value.projection.dimensions = null; }))).toBe(false);
  });
  it("接受最多20000個點且拒絕超量回應", () => {
    const capped = snapshotWith((value) => {
      value.total = 40000; value.embedding.count = 40000; value.embedding.missing = 0;
      value.projection.population = 40000; value.projection.sample_size = 20000;
      value.projection.points = Array.from({ length: 20000 }, () => ({ ...value.projection.points[0] }));
    });
    expect(validQaSnapshot(capped)).toBe(true);
    capped.projection.sample_size++; capped.projection.points.push({ ...capped.projection.points[0] });
    expect(validQaSnapshot(capped)).toBe(false);
  });
  it("以同一縮放比例保留兩軸相對幾何", () => {
    const [origin, right, up] = plotOfTriangle();
    expect(distance(origin, right)).toBeCloseTo(distance(origin, up));
  });
  it("空投影維持空值，不捏造座標", () => {
    expect(projectedPoints([])).toEqual([]);
  });
});
