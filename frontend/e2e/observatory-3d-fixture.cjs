// Contract: qa/snapshot.py build_snapshot persists true UMAP x/y/z. This fixture
// supplies synthetic geometry to exercise camera rendering, not to claim UMAP fit.
const GROUPS = ["科技", "國際", "兩岸", "財經", "政治", "社會", "生活", "娛樂", "體育"];
const CENTERS = [[-3, -2, -2], [-3, -2, 2], [3, -2, -2], [0, 0, 0], [3, 0, 2], [-3, 0, -2], [-3, 2, 2], [0, 2, -2], [3, 2, 2]];
function points3d(count = 900) {
  return Array.from({ length: count }, (_, i) => {
    const group = i % 9, member = Math.floor(i / 9), center = CENTERS[group];
    return { x: center[0] + Math.sin(member * 2.399) * (.08 + member % 5 * .02), y: center[1] + Math.cos(member * 2.399) * (.08 + member % 7 * .02), z: center[2] + Math.sin(member * 1.731) * (.08 + member % 4 * .02), category: GROUPS[group], site: "synthetic-3d-source-" + (group % 3 + 1) };
  });
}
module.exports = { GROUPS, points3d };
