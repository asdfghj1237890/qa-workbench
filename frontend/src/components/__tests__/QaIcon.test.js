// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
// Regression: 2026-10-19 deployed QA showed literal home/check_box text when the
// Material Symbols font did not load. Inline official geometry must remain real
// SVG through QIcon; do not replace it with an icon component stub.
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { Quasar } from "quasar";
import { symOutlinedHome, symOutlinedKeyboardArrowDown, symOutlinedError } from "@quasar/extras/material-symbols-outlined";
import QaIcon from "../QaIcon.vue";

// Expected public asset contracts, not copies of QaIcon's name mapping.
const HOME_PATH = symOutlinedHome.split("|")[0];
const DISCLOSURE_PATH = symOutlinedKeyboardArrowDown.split("|")[0];
const ERROR_PATH = symOutlinedError.split("|")[0];
const SYMBOL_VIEWBOX = "0 -960 960 960";
const mounted = [];
function openIcon(name) {
  const wrapper = mount(QaIcon, { props: { name }, global: { plugins: [Quasar] } });
  mounted.push(wrapper);
  return {
    geometry: () => ({ paths: wrapper.get("svg").findAll("path").map((path) => path.attributes("d")), viewBox: wrapper.get("svg").attributes("viewBox") }),
    accessibility: () => ({ tag: wrapper.element.tagName, hidden: wrapper.attributes("aria-hidden"), tabIndex: wrapper.attributes("tabindex") }),
    text: () => wrapper.text(),
    ligatures: () => wrapper.findAll(".material-symbols-outlined, .material-icons, .q-icon__font-ligature").length,
    async showDisclosure() { await wrapper.setProps({ name: "expand_more" }); },
  };
}
afterEach(() => { mounted.splice(0).forEach((wrapper) => wrapper.unmount()); });

describe("QA icons without font loading", () => {
  it("renders navigation as the official SVG path and viewBox without font ligature text", () => {
    const icon = openIcon("home");
    expect(icon.geometry()).toEqual({ paths: [HOME_PATH], viewBox: SYMBOL_VIEWBOX });
    expect(icon.text()).toBe("");
    expect(icon.ligatures()).toBe(0);
  });
  it("keeps decorative icons out of assistive navigation while changing to the official disclosure asset", async () => {
    const icon = openIcon("home");
    await icon.showDisclosure();
    expect(icon.geometry()).toEqual({ paths: [DISCLOSURE_PATH], viewBox: SYMBOL_VIEWBOX });
    expect(icon.accessibility()).toEqual({ tag: "SPAN", hidden: "true", tabIndex: undefined });
    expect(icon.text()).toBe("");
  });
  it("uses a safe visible SVG fallback for an unavailable icon instead of exposing arbitrary text", () => {
    const icon = openIcon("missing-news-symbol");
    expect(icon.geometry()).toEqual({ paths: [ERROR_PATH], viewBox: SYMBOL_VIEWBOX });
    expect(icon.text()).toBe("");
    expect(icon.ligatures()).toBe(0);
  });
});
