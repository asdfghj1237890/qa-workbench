// Physical layer. observatory-snapshot.json is anchored to qa/snapshot.py (build_snapshot)
// and agent-service/app/qa.py (read_snapshot). It is test data, never a UI fallback.
const SNAPSHOT = require("./observatory-snapshot.json");
const { DENSE_GROUPS, densePoints } = require("./observatory-dense-fixture.cjs");
const { CATEGORY_COUNTS, categoryPoints } = require("./observatory-category-fixture.cjs");
const { GROUPS: REGION_GROUPS, regionPoints } = require("./observatory-region-fixture.cjs");
const { GROUPS: GROUPS3D, points3d } = require("./observatory-3d-fixture.cjs");
const validation = require("./observatory-validation-physical.cjs");
const live = require("./observatory-live-evaluation-physical.cjs");
const BASE = process.env.OBSERVATORY_BASE_PATH || "";
const FIREBASE = { apiKey: "offline-observatory-key", authDomain: "qa-workbench-example.firebaseapp.com", projectId: "qa-workbench-example", appId: "1:123:web:offline-observatory" };
const UID = "offline-observatory-alice", EMAIL = "observatory@example.test";
const NEWS_ARTICLE = { title: SNAPSHOT.projection.points[0].title, url: SNAPSHOT.projection.points[0].url };
const UNSAFE_NEWS_TITLE = '<img src=x onerror="alert(1)">合成新聞';

// Contract: firebaseClient.js creates app "newscout-qa", selects browserLocalPersistence,
// then qaSession.accept independently authorizes the SDK identity with /auth/me.
// This is a real Firebase SDK restoration of an offline local persistence fixture. It does
// not claim to exercise a Google popup, a real Firebase token, or production auth.
async function authenticate(page, { signedIn = true } = {}) {
  const authRequests = [];
  const issued = Math.floor(Date.now() / 1000);
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const token = [encode({ alg: "RS256", typ: "JWT" }), encode({ aud: FIREBASE.projectId, iss: "https://securetoken.google.com/" + FIREBASE.projectId, sub: UID, user_id: UID, email: EMAIL, auth_time: issued, iat: issued, exp: issued + 3600, firebase: { sign_in_provider: "google.com", identities: {} } }), "offline-fixture-signature"].join(".");
  await page.route((url) => ["/config.js", "/qa/config.js"].includes(url.pathname), (route) => route.fulfill({ contentType: "application/javascript", body: "window.NS_CONFIG=" + JSON.stringify({ ENVIRONMENT: "qa", FIREBASE_API_KEY: FIREBASE.apiKey, FIREBASE_AUTH_DOMAIN: FIREBASE.authDomain, FIREBASE_PROJECT_ID: FIREBASE.projectId, FIREBASE_APP_ID: FIREBASE.appId }) }));
  await page.route("https://identitytoolkit.googleapis.com/**", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ users: [{ localId: UID, email: EMAIL, emailVerified: true, displayName: "Offline observatory", providerUserInfo: [{ providerId: "google.com", rawId: UID, email: EMAIL }], createdAt: String(issued * 1000), lastLoginAt: String(issued * 1000) }] }) }));
  await page.route("**/qa/api/auth/me", (route) => {
    authRequests.push({ path: new URL(route.request().url()).pathname, token: route.request().headers().authorization });
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ user_id: "firebase:" + UID, email: EMAIL }) });
  });
  if (signedIn) {
    const seedPath = BASE + "/?observatory-auth-fixture";
    await page.route("**/*observatory-auth-fixture", (route) => route.fulfill({ contentType: "text/html", body: "<!DOCTYPE html><title>Offline Firebase persistence setup</title>" }), { times: 1 });
    await page.goto(seedPath);
    await page.evaluate(({ config, uid, email, idToken, issuedAt }) => {
      localStorage.setItem("firebase:authUser:" + config.apiKey + ":newscout-qa", JSON.stringify({ uid, email, emailVerified: true, displayName: "Offline observatory", isAnonymous: false, providerData: [{ providerId: "google.com", uid, displayName: "Offline observatory", email, phoneNumber: null, photoURL: null }], stsTokenManager: { refreshToken: "offline-refresh-fixture", accessToken: idToken, expirationTime: (issuedAt + 3600) * 1000 }, createdAt: String(issuedAt * 1000), lastLoginAt: String(issuedAt * 1000), apiKey: config.apiKey, appName: "newscout-qa" }));
    }, { config: FIREBASE, uid: UID, email: EMAIL, idToken: token, issuedAt: issued });
  }
  return { authRequests, token };
}

function snapshotBody(state = "ok") {
  const value = JSON.parse(JSON.stringify(SNAPSHOT));
  if (state === "3d" || state === "3d-maximum") {
    const count = state === "3d-maximum" ? 20000 : 900, population = count * 2;
    value.index = "TEST FIXTURE - synthetic 3D coordinates; not real UMAP";
    value.total = population;
    value.embedding = { ...value.embedding, count: population, missing: 0, coverage: 1 };
    value.distributions = { categories: GROUPS3D.map((name, i) => ({ name, count: Math.floor(population / 9) + (i < population % 9 ? 1 : 0) })), sources: [1, 2, 3].map((i) => ({ name: "synthetic-3d-source-" + i, count: Math.floor(population / 3) + (i <= population % 3 ? 1 : 0) })) };
    value.projection = { ...value.projection, dimensions: 3, sample_size: count, population, sampled: true, points: points3d(count) };
  }
  if (state.startsWith("3d-news")) {
    value.index = "TEST FIXTURE - isolated native 3D news hit, not real UMAP";
    value.total = 6; value.embedding = { ...value.embedding, count: 6, missing: 0, coverage: 1 };
    value.distributions = { categories: ["科技", "國際", "兩岸"].map((name) => ({ name, count: 2 })), sources: [{ name: "synthetic-cna", count: 6 }] };
    value.projection = { ...value.projection, dimensions: 3, sample_size: 3, population: 6, sampled: true, points: [
      { x: 0, y: 0, z: 0, category: "科技", site: "synthetic-cna", ...NEWS_ARTICLE },
      { x: -2, y: -1, z: -1, category: "國際", site: "synthetic-cna" },
      { x: 2, y: 1, z: 1, category: "兩岸", site: "synthetic-cna" },
    ] };
    if (state === "3d-news-legacy") { delete value.projection.points[0].title; delete value.projection.points[0].url; }
    if (state === "3d-news-unsafe") Object.assign(value.projection.points[0], { title: UNSAFE_NEWS_TITLE, url: "javascript:alert(1)" });
  }
  if (state === "stale") { value.status = "stale"; value.stale_reasons = ["configuration", "age"]; }
  if (state === "half" || state === "maximum") {
    const count = state === "half" ? 8289 : 20000, population = state === "half" ? 16577 : 40000;
    value.index = "TEST FIXTURE - half embedding sample + synthetic regions";
    value.total = population;
    value.embedding = { ...value.embedding, count: population, missing: 0, coverage: 1 };
    value.distributions = { categories: REGION_GROUPS.map((name, index) => ({ name, count: Math.floor(population / 9) + (index < population % 9 ? 1 : 0) })), sources: [{ name: "synthetic-source-1", count: population }] };
    value.projection = { ...value.projection, sample_size: count, population, sampled: true, points: regionPoints(count) };
  }
  // Synthetic display stress fixture; not a real UMAP run or production data.
  if (state === "dense") {
    value.total = 3000;
    value.embedding = { ...value.embedding, count: 2800, missing: 200, coverage: 2800 / 3000 };
    value.distributions = { categories: DENSE_GROUPS.map((name, index) => ({ name, count: Math.floor(3000 / DENSE_GROUPS.length) + (index < 3000 % DENSE_GROUPS.length ? 1 : 0) })), sources: Array.from({ length: 7 }, (_, index) => ({ name: "synthetic-source-" + (index + 1), count: Math.floor(3000 / 7) + (index < 3000 % 7 ? 1 : 0) })) };
    value.projection = { ...value.projection, sample_size: 2500, population: 2800, points: densePoints() };
  }
  if (state === "categories") {
    value.index = "TEST FIXTURE - screenshot counts + synthetic coordinates";
    value.total = 10000;
    value.embedding = { ...value.embedding, count: 10000, missing: 0, coverage: 1 };
    value.distributions = { categories: [...CATEGORY_COUNTS.map(([name, count]) => ({ name, count: count * 4 })), { name: "__missing__", count: 0 }, { name: "__other__", count: 0 }], sources: [{ name: "synthetic-cna", count: 6000 }, { name: "synthetic-ettoday", count: 4000 }] };
    value.projection = { ...value.projection, sample_size: 2500, population: 10000, points: categoryPoints() };
  }
  // Historical schema-v1 category aliases at well-separated synthetic coordinates.
  // Exercises canonical point details and source-mode grouping without hit ambiguity.
  if (state === "cross-strait") {
    value.index = "TEST FIXTURE - Cross-strait aliases + synthetic coordinates";
    value.total = 4;
    value.embedding = { ...value.embedding, count: 4, missing: 0, coverage: 1 };
    value.distributions = { categories: ["大陸", "兩岸", "中國", "軍武"].map((name) => ({ name, count: 1 })), sources: [{ name: "cna", count: 2 }, { name: "ettoday", count: 2 }] };
    value.projection = { ...value.projection, sample_size: 4, population: 4, sampled: false, points: [
      { x: -3, y: 2, category: "大陸", site: "cna" }, { x: -2, y: 1, category: "兩岸", site: "ettoday" },
      { x: -1, y: 0, category: "中國", site: "cna" }, { x: 3, y: -2, category: "軍武", site: "ettoday" },
    ] };
  }
  if (state === "empty" || state === "insufficient") {
    const count = state === "empty" ? 0 : 2;
    value.total = count;
    value.embedding = { ...value.embedding, count, missing: 0, coverage: count ? 1 : 0 };
    value.distributions = { categories: count ? [{ name: "科技", count }] : [], sources: count ? [{ name: "cna", count }] : [] };
    value.projection = { ...value.projection, status: "insufficient_data", points: [], sample_size: count, population: count, sampled: false };
  }
  return value;
}

async function routeSnapshot(page, initial = "ok", validationMode = "unavailable", liveMode = "unavailable") {
  const validationFixture = await validation.routeValidation(page, validationMode);
  const liveFixture = await live.routeLiveEvaluation(page, liveMode);
  let state = initial;
  const requests = [];
  await page.route("**/api/qa/snapshot", async (route) => {
    requests.push({ method: route.request().method(), path: new URL(route.request().url()).pathname, token: route.request().headers().authorization });
    if (state === "error") return route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
    if (state === "unavailable") return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ status: "unavailable", message: "QA snapshot is not available yet.", generated_at: null, refresh_interval_hours: 24 }) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(snapshotBody(state)) });
  });
  return { recover() { state = "ok"; }, requests, validation: validationFixture, live: liveFixture };
}

// Contract: QaProjection.vue receives persisted x/y/category/site, transforms only
// display positions and exposes metadata selection. These gestures use Chromium's
// real mouse/touch/keyboard input; they do not call the component's methods.
const projection = (page) => page.locator(".qa-interactive-projection");
async function settleProjection(page) { await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))); }
// Contract: QaPage.vue exposes persistent global destinations, data sub-tabs,
// and task settings. Dedicated setting journeys use the supported public
// deep link; no hidden controls or component methods manufacture navigation.
async function openNavigation(page) {
  // Firebase restoration can mount the QA shell after page.load. Resolve the
  // actual shell before deciding whether the phone menu is visible.
  await page.locator(".qa-page").waitFor({ state: "visible" });
  const menu = page.locator('.qa-mobile-bar button[aria-controls="qa-navigation"]');
  if (await menu.isVisible() && await menu.getAttribute("aria-expanded") !== "true") await menu.click();
}
async function closeNavigation(page) {
  const menu = page.locator('.qa-mobile-bar button[aria-controls="qa-navigation"]');
  if (await menu.isVisible() && await menu.getAttribute("aria-expanded") === "true") { await page.keyboard.press("Escape"); await settleProjection(page); }
}
async function selectView(page, view) {
  if (["validation", "es-integration"].includes(view)) {
    const task = view === "validation" ? "offline_regression" : "es_integration";
    await page.goto(BASE + "/observatory?view=validation&task=" + task);
  } else if (["rag-chain", "live"].includes(view)) {
    await openNavigation(page); await page.getByTestId("qa-nav-verification").click(); await closeNavigation(page);
    await page.locator('[data-testid="qa-workbench"][aria-busy="false"]').waitFor();
    const mode = view === "live" ? "model_evaluation" : "real_es_llm_e2e";
    const picker = page.locator('.qt-mobile-select select');
    if (await picker.isVisible()) await picker.selectOption(mode);
    else await page.getByTestId('wb-task-' + mode).click();
    if (await page.locator('.qa-page').getAttribute('data-flow-view') === 'verification') {
      const configure = page.getByTestId('wb-configure');
      if (await configure.isEnabled()) await configure.click();
      // Busy task configuration remains readable through its public deep link.
      else await page.goto(BASE + "/observatory?view=" + (view === "live" ? "live" : "validation&task=real_es_llm_e2e"));
    }
  } else {
    await openNavigation(page);
    if (["overview", "vectors"].includes(view)) {
      await page.getByTestId("qa-nav-data").click(); await closeNavigation(page);
      await page.getByTestId("qa-nav-" + view).click();
    } else await page.getByTestId("qa-nav-" + view).click();
  }
  await closeNavigation(page); await settleProjection(page);
}
async function logout(page) {
  const toolbar = page.locator(".qa-toolbar").getByRole("button", { name: /登出|Sign out/ });
  if (await toolbar.isVisible()) { await toolbar.click(); return; }
  const context = page.locator(".qa-context-logout");
  if (await context.isVisible()) { await context.click(); return; }
  await openNavigation(page);
  const account = page.locator(".qa-account-menu");
  if (await account.getAttribute("open") === null) await account.locator("summary").click();
  await account.getByRole("button", { name: /登出|Sign out/ }).click();
}
async function returnToQaChat(page) {
  await openNavigation(page);
  const back = page.locator(".qa-sidebar .qa-back");
  if (await back.isVisible()) await back.click();
  else await page.locator(".qa-page .qa-brand:visible").first().click();
}
async function preference(page, kind) {
  await openNavigation(page);
  await (kind === "theme" ? page.getByRole("button", { name: /切換深淺色|Toggle dark mode/ }) : page.getByRole("button", { name: "EN", exact: true })).click();
  await closeNavigation(page); await settleProjection(page);
}
async function setTheme(page, dark) { if (await page.locator(".qa-page").getAttribute("data-mode") !== (dark ? "dark" : "light")) await preference(page, "theme"); }
async function workbenchState(page) {
  return page.locator(".qa-page").evaluate((root) => ({
    view: root.dataset.flowView,
    summary: root.querySelector('.qa-run-summary')?.textContent || "",
    menuOpen: root.querySelector('[aria-controls="qa-navigation"]').getAttribute("aria-expanded") === "true",
  }));
}
async function selectCanvasCentre(page) {
  const svg = projection(page).locator(".qa-scatter"); await svg.scrollIntoViewIfNeeded();
  const bounds = await svg.boundingBox(); await page.mouse.click(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2); await settleProjection(page);
}
async function releaseState(page) {
  return page.getByTestId("qa-workbench").evaluate((root) => ({
    title: root.querySelector("h1")?.textContent,
    statuses: ['offline_regression', 'es_integration'].map(mode => root.querySelector('[data-testid="wb-task-' + mode + '"] .qt-status')?.textContent.trim()),
    readiness: root.querySelector('[data-testid="wb-readiness-title"]')?.textContent,
    primaryDisabled: root.querySelector('[data-testid="wb-primary"]')?.disabled,
    paidTasksVisible: Boolean(root.querySelector('[data-testid="wb-task-model_evaluation"]')),
    preview: Boolean(root.querySelector(".qt-preview")),
  }));
}
async function runWorkbenchPrimary(page) { await page.getByTestId("wb-primary").click(); }
async function reopenValidationFromHistory(page) {
  await page.reload();
  await selectView(page, "history");
  await page.getByTestId("qa-execution-history").locator('[data-job-id^="offline-browser-"]').first().getByTestId("qa-history-details").click();
  await page.getByTestId("qa-validation-result").waitFor();
}
async function historyState(page) {
  return page.getByTestId("qa-execution-history").locator('[data-testid="qa-history-row"]').evaluateAll((rows) => rows.map((row) => ({ id: row.dataset.jobId, text: row.textContent })));
}
async function openHistoryLog(page, family) {
  const prefix = family === "evaluations" ? "live-browser-" : "offline-browser-";
  await page.getByTestId("qa-execution-history").locator('[data-job-id^="' + prefix + '"]').first().getByTestId("qa-history-logs").click();
}
async function articleState(page) {
  return projection(page).evaluate((root) => {
    const dialog = root.querySelector('[data-testid="qa-point-popover"]'), link = dialog?.querySelector('[data-testid="qa-article-link"]');
    return { open: Boolean(dialog), title: dialog?.querySelector('[data-testid="qa-article-title"]')?.textContent || null,
      text: dialog?.textContent || "", href: link?.getAttribute("href") || null, target: link?.getAttribute("target") || null, rel: link?.getAttribute("rel") || null,
      images: dialog?.querySelectorAll("img").length || 0, focused: document.activeElement === link ? "article" : document.activeElement === root.querySelector(".qa-scatter") ? "plot" : "other" };
  });
}
async function closeArticle(page) { await projection(page).getByTestId("qa-close-article").click(); await settleProjection(page); }
async function escapeArticle(page) { await projection(page).getByTestId("qa-article-link").focus(); await page.keyboard.press("Escape"); await settleProjection(page); }
async function projectionState(page) {
  return projection(page).evaluate((root) => {
    const svg = root.querySelector(".qa-scatter"), bounds = svg.getBoundingClientRect();
    return {
      zoom: root.querySelector('[data-testid="qa-zoom-level"]').textContent,
      points: [...svg.querySelectorAll("circle")].map((point) => ({ x: Number(point.getAttribute("cx")), y: Number(point.getAttribute("cy")), selected: point.classList.contains("is-selected") })),
      labels: [...svg.querySelectorAll(".qa-plot-label")].map((label) => {
        const rect = label.querySelector("rect").getBoundingClientRect();
        const leader = label.querySelector("line");
        return { name: label.getAttribute("data-group"), region: label.getAttribute("data-region"), count: Number(label.getAttribute("data-count")), mixed: label.getAttribute("data-mixed") === "true", stroke: leader.getAttribute("stroke"), anchorX: Number(leader.getAttribute("x1")), anchorY: Number(leader.getAttribute("y1")), fullText: label.querySelector("title").textContent, text: label.querySelector("text").textContent, fontSize: getComputedStyle(label.querySelector("text")).fontSize, left: rect.left - bounds.left, top: rect.top - bounds.top, right: rect.right - bounds.left, bottom: rect.bottom - bounds.top };
      }),
      detail: root.querySelector('[data-testid="qa-point-detail"]').textContent,
      visibleGroups: [...new Set([...svg.querySelectorAll("circle")].filter((point) => {
        const box = point.getBoundingClientRect(), x = box.x + box.width / 2, y = box.y + box.height / 2;
        return x >= bounds.left + 12 && x <= bounds.right - 12 && y >= bounds.top + 12 && y <= bounds.bottom - 12;
      }).map((point) => point.getAttribute("data-group")))],
      width: bounds.width, height: bounds.height,
      sample: root.closest(".qa-page").querySelector(".qa-vector-context").textContent,
      pageOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    };
  });
}
async function wheelProjection(page, modified = true) {
  await projection(page).locator(".qa-scatter").scrollIntoViewIfNeeded();
  const bounds = await projection(page).locator(".qa-scatter").boundingBox();
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  if (modified) await page.keyboard.down("Control");
  try { await page.mouse.wheel(0, -100); } finally { if (modified) await page.keyboard.up("Control"); }
  await settleProjection(page);
}
async function panProjection(page) {
  const bounds = await projection(page).locator(".qa-scatter").boundingBox();
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await page.mouse.down(); await page.mouse.move(bounds.x + bounds.width / 2 + 35, bounds.y + bounds.height / 2 + 18, { steps: 4 }); await page.mouse.up();
  await settleProjection(page);
}
async function projectionControl(page, name) { await projection(page).getByTestId("qa-" + name).click(); await settleProjection(page); }
async function selectProjectionPoint(page, touch = false) {
  const point = projection(page).locator(".qa-scatter circle").first();
  await point.scrollIntoViewIfNeeded();
  if (touch) { const bounds = await point.boundingBox(); await page.touchscreen.tap(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2); }
  else await point.click();
  await settleProjection(page);
}
async function projectionKey(page, key) { await projection(page).locator(".qa-scatter").focus(); await page.keyboard.press(key); await settleProjection(page); }
async function toggleProjectionGroup(page, name) { await page.locator(".qa-legend-item").filter({ has: page.getByText(name, { exact: true }) }).click(); await settleProjection(page); }
async function measureProjectionExploration(page) { const started = Date.now(); await wheelProjection(page); await panProjection(page); await projectionKey(page, "ArrowRight"); return Date.now() - started; }
async function captureProjection(page, name) { const { test } = require("@playwright/test"); await projection(page).screenshot({ path: test.info().outputPath("projection-" + name + ".png") }); }
async function projectionMetrics(page, metrics) {
  const { test } = require("@playwright/test");
  await test.info().attach("projection-performance", { body: JSON.stringify(metrics), contentType: "application/json" });
}
async function measureProjectionFilter(page, name) {
  const started = Date.now(); await toggleProjectionGroup(page, name); return Date.now() - started;
}

async function colorByCategory(page) { await page.getByRole("button", { name: "依分類", exact: true }).click(); await settleProjection(page); }
async function categoryState(page) {
  return page.locator(".qa-page").evaluate((root) => ({
    legend: [...root.querySelectorAll(".qa-legend-item")].map((item) => ({ name: item.querySelector("span:not([aria-hidden])").textContent, count: Number(item.querySelector("b").textContent.replaceAll(",", "")), color: item.querySelector("i").style.backgroundColor })),
    bars: [...root.querySelector('[data-testid="qa-overview"] [aria-labelledby="qa-categories"]').querySelectorAll("li")].map((item) => ({ name: item.querySelector(".qa-distribution-name").textContent, count: Number(item.querySelector("b").textContent.replaceAll(",", "")), color: item.querySelector(".qa-bar-track > div").style.backgroundColor })),
    theme: root.getAttribute("data-mode"),
  }));
}
async function captureCategoryViews(page, name) {
  const { test } = require("@playwright/test");
  // Screenshot-only annotation: keep synthetic evidence explicit without leaving
  // a fixed DOM overlay over the phone navigation between captures.
  const annotation = 'body::after { content:"TEST FIXTURE · Screenshot category counts + synthetic coordinates · Not real UMAP";position:fixed;z-index:9999;left:0;right:0;bottom:0;padding:7px 12px;background:#744808;color:#fff;font:11px sans-serif;text-align:center;pointer-events:none; }';
  for (const [section, selector] of [["plot", ".qa-vector-canvas"], ["legend", ".qa-legend"], ["categories", '[data-testid="qa-overview"] [aria-labelledby="qa-categories"]']]) {
    await selectView(page, section === "categories" ? "overview" : "vectors");
    await page.locator(selector).first().evaluate((element, section) => element.scrollIntoView({ block: section === "legend" ? "center" : "start" }), section);
    await settleProjection(page);
    await page.screenshot({ path: test.info().outputPath("categories-" + name + "-" + section + ".png"), style: annotation });
  }
  await selectView(page, "vectors");
  await projection(page).locator(".qa-scatter").scrollIntoViewIfNeeded();
}

module.exports = { SNAPSHOT, NEWS_ARTICLE, UNSAFE_NEWS_TITLE, snapshotBody, routeSnapshot, authenticate, BASE, selectView, logout, returnToQaChat, preference, setTheme, workbenchState, releaseState, runWorkbenchPrimary, reopenValidationFromHistory, historyState, openHistoryLog, selectCanvasCentre, articleState, closeArticle, escapeArticle, projectionState, wheelProjection, panProjection, projectionControl, selectProjectionPoint, projectionKey, captureProjection, toggleProjectionGroup, measureProjectionExploration, projectionMetrics, measureProjectionFilter, validation, live, colorByCategory, categoryState, captureCategoryViews };
