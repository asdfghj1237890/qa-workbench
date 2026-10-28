// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { createI18n } from "vue-i18n";
import { Quasar } from "quasar";
import QaSemanticReviewPanel from "../QaSemanticReviewPanel.vue";
import { observeReviewedJob } from "../../lib/__tests__/qa/semantic-review-physical.js";
import zhTW from "../../i18n/zh-TW.json";
import en from "../../i18n/en.json";

const mounted = [];
// Action/physical boundary: actual component with contract-anchored public rows.
function openReview({ caseView = false, invalid = false, busy = false, archived = false, incomplete = false } = {}) {
  const job = observeReviewedJob({ incomplete, archived });
  if (invalid) job.semantic_review.cases[0].row_sha = "f".repeat(64);
  const entry = caseView ? job.cases[0] : null;
  const i18n = createI18n({ legacy: false, globalInjection: true, locale: "zh-TW", messages: { "zh-TW": zhTW, en } });
  const wrapper = mount(QaSemanticReviewPanel, { props: { job, entry, busy }, global: { plugins: [i18n, Quasar] } });
  mounted.push(wrapper);
  return {
    text: () => wrapper.text(),
    pending: () => wrapper.find('[data-testid="qa-semantic-pending"]').exists(),
    failedDimensions: () => wrapper.findAll('[data-score="failed"]').map((item) => [item.get("dt").text(), item.get("dd").text()].join(" ")),
    async selectFile() {
      const input = wrapper.get('input[type="file"]');
      const file = new File(['{"reviews":[]}'], "review.json", { type: "application/json" });
      Object.defineProperty(input.element, "files", { configurable: true, value: [file] });
      await input.trigger("change");
      return wrapper.emitted("import")?.at(-1)?.[0];
    },
    importDisabled: () => wrapper.get('[data-testid="qa-semantic-import"]').attributes("disabled") !== undefined,
  };
}
afterEach(() => mounted.splice(0).forEach((wrapper) => wrapper.unmount()));

describe("semantic review evidence display", () => {
  it("shows the AI reviewer, measured outcome and the incomplete run coverage", () => {
    const panel = openReview({ incomplete: true });
    expect(panel.text()).toContain("AI 語意審核已完成");
    expect(panel.text()).toContain("Codex (AI)");
    expect(panel.text()).toContain("7 通過 · 1 未通過");
    expect(panel.text()).toContain("已審核 8／8 個已產生案例");
    expect(panel.text()).toContain("原定 49 題；41 題尚未執行");
    expect(panel.text()).not.toContain("人工語意審核待完成");
  });
  it("keeps a stale row hash pending instead of inventing completed review", () => {
    const panel = openReview({ invalid: true });
    expect(panel.pending()).toBe(true);
    expect(panel.text()).not.toContain("AI 語意審核已完成");
  });
  it("exposes per-case failed dimensions and the source-based reason", () => {
    const panel = openReview({ caseView: true });
    expect(panel.failedDimensions()).toEqual(["來源支持 FAIL"]);
    expect(panel.text()).toContain("The source does not support the numeric claim.");
  });
  it("selecting a review file only requests an import and respects a busy state", async () => {
    const panel = openReview();
    expect((await panel.selectFile()).name).toBe("review.json");
    expect(openReview({ busy: true }).importDisabled()).toBe(true);
  });
  it("identifies restored evidence without presenting it as a fresh run", () => {
    const panel = openReview({ archived: true });
    expect(panel.text()).toContain("匯入的歷史執行紀錄");
  });
});
