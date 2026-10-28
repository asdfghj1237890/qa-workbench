// Contract: qa/snapshot.py build_snapshot emits raw category counts and x/y/category/site.
// Counts reproduce the user's 25-category screenshot; coordinates are synthetic,
// never a real UMAP result or actual article metadata. Full-index counts deliberately
// differ from sample counts to catch denominator/filter coupling in the UI.
const CATEGORY_COUNTS = [["社會", 322], ["體育", 307], ["政治", 289], ["國際", 279], ["娛樂", 266], ["生活", 256], ["財經", 135], ["地方", 127], ["大陸", 124], ["時尚", 73], ["旅遊", 56], ["兩岸", 45], ["科技", 43], ["房產", 38], ["健康", 37], ["遊戲", 26], ["消費", 22], ["評論", 17], ["汽車", 16], ["寵物與動物", 14], ["軍武", 4], ["公益", 1], ["新奇", 1], ["運勢", 1], ["ESG", 1]];
const MACRO_COUNTS = { "生活": 458, "兩岸": 169, "國際": 283, "社會": 451, "體育": 307, "政治": 306, "娛樂": 293, "財經": 174, "科技": 59 };
// Spatial placement is independent of production taxonomy; tests inspect grouping,
// count preservation and label geometry without reimplementing display aggregation.
const CENTERS = [[0, 0], [5, 0], [10, 0], [15, 0], [0, 5], [5, 5], [10, 5], [15, 5]];
function categoryPoints() {
  let index = 0;
  return CATEGORY_COUNTS.flatMap(([category, count], group) => Array.from({ length: count }, (_, member) => {
    const [x, y] = CENTERS[group % CENTERS.length];
    index++;
    return { x: x + Math.sin(index * 2.39996) * (.2 + member % 29 / 24), y: y + Math.cos(index * 2.39996) * (.2 + member % 23 / 21), category, site: group % 2 ? "synthetic-cna" : "synthetic-ettoday" };
  }));
}
module.exports = { CATEGORY_COUNTS, MACRO_COUNTS, categoryPoints };
