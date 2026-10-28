// Physical fixture for qa/snapshot.py build_snapshot's x/y/category/site contract.
// These 2500 coordinates are synthetic projected input with a fixed data seed.
// This neither runs UMAP nor reproduces QaProjection's screen/label layout.
const DENSE_GROUPS = ["科技", "國際", "兩岸", "財經", "政治", "社會", "生活", "娛樂", "體育"];
function densePoints() {
  let seed = 73023;
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return (seed + .5) / 4294967296; };
  const gaussian = () => Math.sqrt(-2 * Math.log(random())) * Math.cos(2 * Math.PI * random());
  return Array.from({ length: 2500 }, (_, index) => {
    const group = index % DENSE_GROUPS.length;
    return { x: (group % 3) * 3 + gaussian() * .58, y: Math.floor(group / 3) * 5 + gaussian() * .58, category: DENSE_GROUPS[group], site: "synthetic-source-" + (group % 7 + 1) };
  });
}
module.exports = { DENSE_GROUPS, densePoints };
