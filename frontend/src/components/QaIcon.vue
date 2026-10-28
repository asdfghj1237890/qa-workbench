<template>
  <QIcon :name="icon" tag="span" class="qa-icon" />
</template>

<script setup>
import { computed } from "vue";
import { QIcon } from "quasar";
import { matCheckCircle, matError, matInfo, matPlayArrow, matRemoveCircle } from "@quasar/extras/material-icons";
import {
  symOutlinedAdsClick, symOutlinedArrowForward, symOutlinedCheckBox,
  symOutlinedCheckBoxOutlineBlank, symOutlinedCheckCircle, symOutlinedClose,
  symOutlinedCloudOff, symOutlinedContrast, symOutlinedDatabase,
  symOutlinedDescription, symOutlinedError, symOutlinedFactCheck,
  symOutlinedHome, symOutlinedKeyboardArrowDown, symOutlinedMenu,
  symOutlinedNorthEast, symOutlinedOpenInNew, symOutlinedPending,
  symOutlinedProgressActivity, symOutlinedRefresh, symOutlinedScatterPlot,
  symOutlinedSmartToy, symOutlinedCheck, symOutlinedLink,
  symOutlinedHistory, symOutlinedChevronRight, symOutlinedChatBubble,
  symOutlinedAccountTree, symOutlinedBarChart,
  symOutlinedDownload, symOutlinedTune, symOutlinedLock, symOutlinedCalendarMonth,
  symOutlinedFormatListBulleted, symOutlinedKeyboardArrowUp, symOutlinedAccountCircle,
  symOutlinedContentCopy, symOutlinedPriorityHigh,
  symOutlinedLanguage, symOutlinedFindInPage, symOutlinedArrowBack, symOutlinedMonitorHeart,
} from "@quasar/extras/material-symbols-outlined";

const props = defineProps({ name: { type: String, required: true } });
// Official SVG paths keep QA icons independent of browser font loading.
const icons = Object.freeze({
  ads_click: symOutlinedAdsClick,
  arrow_forward: symOutlinedArrowForward,
  check: symOutlinedCheck,
  link: symOutlinedLink,
  info: matInfo,
  monitor_heart: symOutlinedMonitorHeart,
  history: symOutlinedHistory,
  chevron_right: symOutlinedChevronRight,
  chat_bubble_outline: symOutlinedChatBubble,
  account_tree: symOutlinedAccountTree,
  bar_chart: symOutlinedBarChart,
  play_arrow: matPlayArrow,
  download: symOutlinedDownload,
  tune: symOutlinedTune,
  lock: symOutlinedLock,
  calendar: symOutlinedCalendarMonth,
  calendar_today: symOutlinedCalendarMonth,
  list: symOutlinedFormatListBulleted,
  format_list_bulleted: symOutlinedFormatListBulleted,
  expand_less: symOutlinedKeyboardArrowUp,
  account_circle: symOutlinedAccountCircle,
  content_copy: symOutlinedContentCopy,
  priority_high: symOutlinedPriorityHigh,
  remove_circle: matRemoveCircle,
  language: symOutlinedLanguage,
  manage_search: symOutlinedFindInPage,
  arrow_back: symOutlinedArrowBack,
  check_box: symOutlinedCheckBox,
  check_box_outline_blank: symOutlinedCheckBoxOutlineBlank,
  check_circle: symOutlinedCheckCircle,
  check_circle_filled: matCheckCircle,
  close: symOutlinedClose,
  cloud_off: symOutlinedCloudOff,
  contrast: symOutlinedContrast,
  database: symOutlinedDatabase,
  description: symOutlinedDescription,
  error: symOutlinedError,
  error_filled: matError,
  expand_more: symOutlinedKeyboardArrowDown,
  fact_check: symOutlinedFactCheck,
  home: symOutlinedHome,
  menu: symOutlinedMenu,
  north_east: symOutlinedNorthEast,
  open_in_new: symOutlinedOpenInNew,
  pending: symOutlinedPending,
  progress_activity: symOutlinedProgressActivity,
  refresh: symOutlinedRefresh,
  scatter_plot: symOutlinedScatterPlot,
  smart_toy: symOutlinedSmartToy,
});
const icon = computed(() => Object.hasOwn(icons, props.name) ? icons[props.name] : symOutlinedError);
</script>
