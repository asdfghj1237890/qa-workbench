// Cloudflare Turnstile token 就緒等待器。
//
// widget 以非互動模式渲染，token 由 callback「非同步」在載入後約 1–2 秒才送達。
// 首頁建議 chips／ask 輸入一載入即可點，若送出時同步抓當下 token 會抓到空字串 → 後端 403。
// 故送出前一律 await get()：已就緒立即回；未就緒則等到 set()（callback 送達）或逾時回空字串
// （逾時讓使用者收到「請完成驗證」而非永久卡住）。未啟用（無 sitekey）時 get() 回 undefined。
export function createCfToken({ enabled = true, timeoutMs = 8000 } = {}) {
  let token = "";
  let waiters = [];

  function set(tk) {
    token = tk || "";
    const ws = waiters;
    waiters = [];
    ws.forEach((finish) => finish(token));
  }

  function clear() {
    token = "";
  }

  function get() {
    if (!enabled) return Promise.resolve(undefined);
    if (token) return Promise.resolve(token);
    return new Promise((resolve) => {
      let done = false;
      const finish = (val) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve(val);
      };
      const timer = setTimeout(() => finish(token || ""), timeoutMs);
      waiters.push(finish);
    });
  }

  return { set, clear, get, current: () => token };
}
