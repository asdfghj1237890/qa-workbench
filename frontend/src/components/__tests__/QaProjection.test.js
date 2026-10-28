// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createI18n } from "vue-i18n";
import { markRaw } from "vue";
import { Quasar } from "quasar";
import QaProjection from "../QaProjection.vue";
import en from "../../i18n/en.json";
import zhTW from "../../i18n/zh-TW.json";

const mounted = [];
const ARTICLE = { title: "半導體研發新聞", url: "https://news.example.test/articles/semiconductor?edition=tw" };
const SECOND_ARTICLE = { title: "國會政策新聞", url: "http://news.example.test/articles/policy" };
const UNSAFE_ARTICLE_URLS = ["javascript:alert(1)", "data:text/html,unsafe", "//news.example.test/article", "/articles/local", "https://alice:password@news.example.test/article", "https://@news.example.test/article", "https:\\news.example.test/article", "https://news.example.test/\narticle", "https://", "https://[invalid/article"];
const UNTRUSTED_TITLE = '<img src=x onerror="alert(1)">新聞';
function openProjection(dense = false, { article, threeD = false, workbench = false, viewport, resizable = false, offCenter = false } = {}) {
  // QaPage's projectedPoints computed returns plain objects. Keep that identity
  // boundary here so selected metadata and the visual marker cannot diverge.
  const points = markRaw([{ x: -1.2345, y: 2.3456, cx: 350, cy: 250, category: "科技", site: "cna" }, { x: 3, y: 4, cx: 550, cy: 260, category: "政治", site: "rthk" }, { x: 5, y: 6, cx: 650, cy: 280, category: "科技", site: "rthk" }]);
  // Contract: QaPage.vue's normalized projection retains producer title/url. The
  // first native 3D point is at the camera origin, hence the visible canvas centre.
  if (article) { Object.assign(points[0], article); Object.assign(points[1], SECOND_ARTICLE); }
  if (threeD) points.forEach((point, index) => Object.assign(point, { z: index / 2, nx: index === 0 ? 0 : index === 1 ? -1 : 1, ny: index === 0 ? 0 : .6, nz: index === 0 ? 0 : index === 1 ? -.8 : .8 }));
  if (dense) for (let i = 0; i < 80; i++) points.push({ x: i, y: i, cx: (i < 40 ? 350 : 550) + i % 5, cy: 250 + Math.floor(i % 40 / 5), category: i < 40 ? "科技" : "政治", site: "cna" });
  if (offCenter) points.forEach((point, index) => { point.cx = 900 + index % 5; });
  // jsdom substitutes only physical layout/Canvas APIs, never selection/hit-test
  // methods. Real pointer events still enter QaProjection's SVG interaction layer.
  if (threeD) vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ scale() {}, clearRect() {}, beginPath() {}, arc() {}, fill() {} });
  let currentViewport = viewport, notifyResize;
  if (viewport) vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function () { return this.classList?.contains("qa-plot-surface") ? { ...currentViewport, x: 0, y: 0, left: 0, top: 0, right: currentViewport.width, bottom: currentViewport.height } : { width: 0, height: 0, left: 0, top: 0, right: 0, bottom: 0 }; });
  if (resizable) vi.stubGlobal("ResizeObserver", class {
    constructor(callback) { this.callback = callback; }
    observe(element) { if (element.classList.contains("qa-plot-surface")) notifyResize = this.callback; }
    disconnect() {}
  });
  const i18n = createI18n({ legacy: false, locale: "zh-TW", messages: { en, "zh-TW": zhTW } });
  const wrapper = mount(QaProjection, { attachTo: document.body, props: { points, dimensions: threeD ? 3 : 2, workbench, colorBy: "category", colorFor: () => "#168478", groupLabel: (name) => name, resetKey: {}, description: "sample" }, global: { plugins: [i18n, Quasar] } });
  mounted.push(wrapper);
  const plot = () => wrapper.find(".qa-scatter");
  const button = (name) => wrapper.find(`[data-testid="qa-${name}"]`);
  const first = () => { const point = wrapper.find(".qa-scatter circle"); return { x: Number(point.attributes("cx")), y: Number(point.attributes("cy")) }; };
  const sendPointer = async (type, clientX, clientY, pointerType = "mouse", target = plot().element) => {
    const event = new MouseEvent(type, { clientX, clientY, button: 0, bubbles: true, cancelable: true });
    Object.defineProperties(event, { pointerId: { value: 1 }, pointerType: { value: pointerType } });
    target.dispatchEvent(event); await wrapper.vm.$nextTick();
  };
  return {
    zoom: () => button("zoom-level").text(),
    async ready() { await wrapper.vm.$nextTick(); },
    async resize(width, height) { currentViewport = { width, height }; notifyResize(); await wrapper.vm.$nextTick(); },
    labels: () => wrapper.findAll(".qa-plot-label").map((item) => item.attributes("data-group")),
    detail: () => button("point-detail").text(),
    selectedCount: () => wrapper.findAll(".qa-scatter circle.is-selected").length,
    articleTitle: () => button("article-title").text(),
    articleLink: () => button("article-link").exists() ? button("article-link").attributes() : null,
    unavailable: () => button("article-unavailable").text(),
    articleOpen: () => button("point-popover").exists(),
    articleDialog: () => button("point-popover").attributes(),
    articleBounds: () => { const style = button("point-popover").element.style; return { x: parseFloat(style.left), y: parseFloat(style.top), width: parseFloat(style.width), maxHeight: parseFloat(style.maxHeight) }; },
    injectedImages: () => button("point-popover").findAll("img").length,
    selectedArticleEvents: () => (wrapper.emitted("selection-change") || []).map(([point]) => point?.title || null),
    focus: () => document.activeElement === plot().element ? "plot" : document.activeElement === button("article-link").element ? "article" : "other",
    position: first,
    async zoomIn() { await button("zoom-in").trigger("click"); },
    async reset() { await button("reset-view").trigger("click"); },
    async toggleLabels() { await button("label-toggle").trigger("click"); },
    async key(key, shiftKey = false) { await plot().trigger("keydown", { key, shiftKey }); },
    async wheel(ctrlKey) { plot().element.dispatchEvent(new WheelEvent("wheel", { ctrlKey, deltaY: -100, clientX: 500, clientY: 220, bubbles: true, cancelable: true })); await wrapper.vm.$nextTick(); },
    async tapFirst() { await wrapper.vm.$nextTick(); const at = first(); for (const type of ["pointerdown", "pointerup"]) await sendPointer(type, at.x, at.y, "touch"); },
    async clickCentre3d() { const [width, height] = plot().attributes("viewBox").split(" ").slice(2).map(Number); for (const type of ["pointerdown", "pointerup"]) await sendPointer(type, width / 2, height / 2); },
    async clickSecond() { const point = wrapper.findAll(".qa-scatter circle")[1]; const at = { x: Number(point.attributes("cx")), y: Number(point.attributes("cy")) }; for (const type of ["pointerdown", "pointerup"]) await sendPointer(type, at.x, at.y); },
    async leavePoint() { await sendPointer("pointermove", 20, 20); await plot().trigger("pointerleave"); },
    async closeArticle() { await button("close-article").trigger("click"); },
    async escapeArticle() { await button("article-link").trigger("keydown", { key: "Escape" }); },
    async interactWithArticle() { for (const [type, x, y] of [["pointerdown", 300, 200], ["pointermove", 360, 220], ["pointerup", 360, 220]]) await sendPointer(type, x, y, "mouse", button("article-link").element); },
    async pan() { await sendPointer("pointerdown", 300, 200); await sendPointer("pointermove", 360, 220); await sendPointer("pointerup", 360, 220); },
    async hideTechnology() { await wrapper.setProps({ points: points.filter((point) => point.category !== "科技") }); },
    async widenDistribution() { await wrapper.setProps({ points: markRaw(Array.from({ length: 200 }, (_, i) => ({ ...points[0], cx: i < 100 ? 45 + i % 6 : 950 + i % 6, cy: i < 100 ? 45 + i % 6 : 450 + i % 6 }))) }); },
    async sourceMode() { await wrapper.setProps({ colorBy: "site" }); },
    async newSnapshot() { await wrapper.setProps({ resetKey: {} }); },
    async english() { i18n.global.locale.value = "en"; await wrapper.vm.$nextTick(); },
  };
}
afterEach(() => { for (const wrapper of mounted.splice(0)) wrapper.unmount(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("interactive metadata projection", () => {
  it.each([false, true])("keeps a pinned article open when an adaptive initial view is resized (off-center: %s)", async (offCenter) => {
    const plot = openProjection(true, { article: ARTICLE, viewport: { width: 1000, height: 440 }, resizable: true, offCenter });
    await plot.ready(); await plot.key("ArrowRight");
    expect(plot.articleOpen()).toBe(true);
    await plot.resize(390, 420);
    expect(plot.articleOpen()).toBe(true);
    expect(plot.articleTitle()).toBe(ARTICLE.title);
  });
  it("starts a compact distribution two levels closer and restores that framing on reset and snapshot changes", async () => {
    const plot = openProjection(true);
    await plot.ready();
    expect(plot.zoom()).toBe("225%");
    const initial = plot.position();
    await plot.zoomIn();
    expect(plot.zoom()).toBe("338%");
    await plot.reset();
    expect(plot.zoom()).toBe("225%");
    expect(plot.position()).toEqual(initial);
    await plot.zoomIn(); await plot.newSnapshot();
    expect(plot.zoom()).toBe("225%");
    await plot.zoomIn(); await plot.sourceMode();
    expect(plot.zoom()).toBe("225%");
  });
  it("adapts untouched framing when points arrive or spread out, and preserves manual navigation", async () => {
    const automatic = openProjection(true);
    await automatic.ready();
    expect(automatic.zoom()).toBe("225%");
    await automatic.widenDistribution();
    expect(automatic.zoom()).toBe("100%");
    const manual = openProjection(true);
    await manual.ready(); await manual.zoomIn();
    await manual.widenDistribution();
    expect(manual.zoom()).toBe("338%");
  });
  it("starts with aggregate region labels, allows hiding them, and translates controls", async () => {
    const plot = openProjection(true);
    expect(plot.labels()).toEqual(["科技", "政治"]);
    await plot.toggleLabels();
    expect(plot.labels()).toEqual([]);
    await plot.toggleLabels();
    await plot.english();
    expect(plot.detail()).toContain(en.observatory.plot.selectHint);
    expect(plot.labels()).toHaveLength(2);
  });
  it("ignores ordinary page scrolling and supports modified wheel zoom, pan and reset", async () => {
    const plot = openProjection(), original = plot.position();
    await plot.wheel(false);
    expect(plot.zoom()).toBe("100%");
    await plot.wheel(true);
    expect(plot.zoom()).toBe("149%");
    const zoomed = plot.position();
    await plot.pan();
    expect(plot.position().x).toBeCloseTo(zoomed.x + 60);
    expect(plot.selectedCount()).toBe(0);
    await plot.reset();
    expect(plot.zoom()).toBe("100%");
    expect(plot.position()).toEqual(original);
  });
  it("a touch tap exposes only real metadata and coordinates, and a filter clears selection", async () => {
    const plot = openProjection();
    await plot.tapFirst();
    expect(plot.selectedCount()).toBe(1);
    expect(plot.detail()).toContain("科技");
    expect(plot.detail()).toContain("cna");
    expect(plot.detail()).toContain("-1.2345");
    expect(plot.detail()).toContain("2.3456");
    await plot.hideTechnology();
    expect(plot.selectedCount()).toBe(0);
    expect(plot.labels()).toEqual([]);
  });
  it("offers keyboard point navigation, pan, zoom and reset without 2500 tab stops", async () => {
    const plot = openProjection();
    await plot.key("ArrowRight");
    expect(plot.detail()).toContain("cna");
    await plot.key("ArrowRight");
    expect(plot.detail()).toContain("政治");
    await plot.key("Escape");
    expect(plot.selectedCount()).toBe(0);
    await plot.key("+");
    expect(plot.zoom()).toBe("150%");
    const previous = plot.position();
    await plot.key("ArrowRight", true);
    expect(plot.position().x).toBeCloseTo(previous.x - 40);
    await plot.key("Home");
    expect(plot.zoom()).toBe("100%");
  });
  it("resets navigation and selection consistently when metadata mode or snapshot changes", async () => {
    const plot = openProjection();
    await plot.zoomIn(); await plot.key("ArrowRight"); await plot.sourceMode();
    expect(plot.zoom()).toBe("100%");
    expect(plot.selectedCount()).toBe(0);
    expect(plot.labels()).toEqual([]);
    await plot.zoomIn(); await plot.tapFirst(); await plot.newSnapshot();
    expect(plot.zoom()).toBe("100%");
    expect(plot.selectedCount()).toBe(0);
  });
  it("selects a real 3D canvas hit and pins a dialog with the producer's news link", async () => {
    const plot = openProjection(false, { article: ARTICLE, threeD: true });
    expect(plot.articleOpen()).toBe(false);
    await plot.clickCentre3d();
    expect(plot.selectedCount()).toBe(1);
    expect(plot.articleTitle()).toBe(ARTICLE.title);
    expect(plot.detail()).toContain("科技");
    expect(plot.detail()).toContain("cna");
    expect(plot.articleLink()).toMatchObject({ href: ARTICLE.url, target: "_blank", rel: "noopener noreferrer" });
    expect(plot.articleDialog()).toMatchObject({ role: "dialog", "aria-modal": "false" });
    await plot.leavePoint();
    expect(plot.articleOpen()).toBe(true);
  });
  it("renders untrusted titles as text and never turns unsafe URLs into news links", async () => {
    for (const url of UNSAFE_ARTICLE_URLS) {
      const plot = openProjection(false, { article: { title: UNTRUSTED_TITLE, url } });
      await plot.tapFirst();
      expect(plot.articleTitle()).toBe(UNTRUSTED_TITLE);
      expect(plot.injectedImages()).toBe(0);
      expect(plot.articleLink()).toBeNull();
      expect(plot.unavailable()).toBe(zhTW.observatory.plot.articleLinkUnavailable);
    }
  });
  it("keeps legacy points inspectable without inventing an article title or link", async () => {
    const plot = openProjection();
    await plot.tapFirst();
    expect(plot.articleTitle()).toBe(zhTW.observatory.plot.articleTitleUnavailable);
    expect(plot.articleLink()).toBeNull();
    expect(plot.unavailable()).toBe(zhTW.observatory.plot.articleLinkUnavailable);
  });
  it("updates the pinned article on another hit and clears it on filtering or snapshot reset", async () => {
    const plot = openProjection(false, { article: ARTICLE, workbench: true });
    await plot.tapFirst();
    expect(plot.selectedArticleEvents()).toEqual([ARTICLE.title]);
    await plot.clickSecond();
    expect(plot.articleTitle()).toBe(SECOND_ARTICLE.title);
    expect(plot.articleLink().href).toBe(SECOND_ARTICLE.url);
    await plot.newSnapshot();
    expect(plot.articleOpen()).toBe(false);
    expect(plot.selectedArticleEvents().at(-1)).toBeNull();
    await plot.tapFirst(); await plot.hideTechnology();
    expect(plot.articleOpen()).toBe(false);
    expect(plot.selectedArticleEvents().at(-1)).toBeNull();
  });
  it("dismisses the pinned article during camera navigation and reset", async () => {
    const plot = openProjection(false, { article: ARTICLE, threeD: true });
    await plot.clickCentre3d(); await plot.pan();
    expect(plot.articleOpen()).toBe(false);
    await plot.reset(); await plot.clickCentre3d(); await plot.zoomIn();
    expect(plot.articleOpen()).toBe(false);
    await plot.reset(); await plot.clickCentre3d(); await plot.reset();
    expect(plot.articleOpen()).toBe(false);
  });
  it("supports keyboard entry into a news link and restores plot focus after closing", async () => {
    const plot = openProjection(false, { article: ARTICLE });
    await plot.key("ArrowRight"); await plot.key("Enter");
    expect(plot.focus()).toBe("article");
    await plot.escapeArticle();
    expect(plot.articleOpen()).toBe(false);
    expect(plot.focus()).toBe("plot");
    await plot.tapFirst(); await plot.closeArticle();
    expect(plot.articleOpen()).toBe(false);
    expect(plot.focus()).toBe("plot");
  });
  it("keeps the popup inside a phone canvas and isolates its pointer interactions", async () => {
    const plot = openProjection(false, { article: ARTICLE, viewport: { width: 280, height: 200 } });
    await plot.tapFirst();
    const bounds = plot.articleBounds();
    expect(bounds.x).toBeGreaterThanOrEqual(8);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(272);
    expect(bounds.y).toBeGreaterThanOrEqual(8);
    expect(bounds.y + bounds.maxHeight).toBeLessThanOrEqual(192);
    const before = plot.position();
    await plot.interactWithArticle();
    expect(plot.articleOpen()).toBe(true);
    expect(plot.position()).toEqual(before);
  });
});
