// Contract: qa/snapshot.py build_snapshot emits persisted x/y/category/site points.
// Deliberately synthetic independent spatial lobes; this does not run UMAP or
// reproduce the production density algorithm. One lobe has two equal categories.
const GROUPS = ["科技", "國際", "兩岸", "財經", "政治", "社會", "生活", "娛樂", "體育"];
function regionPoints(count) {
  let seed = 20261019;
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return (seed + .5) / 4294967296; };
  const gaussian = () => Math.sqrt(-2 * Math.log(random())) * Math.cos(2 * Math.PI * random());
  return Array.from({ length: count }, (_, i) => {
    const region = i % 9;
    return { x: region % 3 * 5 + gaussian() * .36, y: Math.floor(region / 3) * 4 + gaussian() * .36,
      category: region === 0 && Math.floor(i / 9) % 2 ? "國際" : GROUPS[region], site: "synthetic-source-" + (region % 3 + 1) };
  });
}
module.exports = { GROUPS, regionPoints };
