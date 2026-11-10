// טאבלט: חתימה באצבע. ה-hash מחושב בשרת; כאן רק ציור ושליחת PNG.
(function () {
  let pad = null;
  function init() {
    const c = document.getElementById("sig");
    if (!c || c.dataset.ready) return;
    c.dataset.ready = "1";
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    c.width = c.offsetWidth * ratio;
    c.height = c.offsetHeight * ratio;
    c.getContext("2d").scale(ratio, ratio);
    pad = new SignaturePad(c, { penColor: "#1c2430", minWidth: 1.2, maxWidth: 3 });
    const btn = document.getElementById("sig-submit");
    const sync = () => { if (btn) btn.disabled = pad.isEmpty(); };
    pad.addEventListener("endStroke", sync);
    sync();
    const clr = document.getElementById("sig-clear");
    if (clr) clr.addEventListener("click", () => { pad.clear(); sync(); });
  }
  document.addEventListener("htmx:configRequest", (e) => {
    if (e.detail.path === "/cl/consent") {
      if (!pad || pad.isEmpty()) { e.preventDefault(); return; }
      e.detail.parameters["signature"] = pad.toDataURL("image/png");
    }
  });
  document.addEventListener("DOMContentLoaded", init);
  document.addEventListener("htmx:oobAfterSwap", init);
  document.addEventListener("htmx:afterSettle", init);
  // מצב קיוסק: בלי תפריט לחיצה ארוכה, בלי זום בשתי אצבעות
  document.addEventListener("contextmenu", (e) => e.preventDefault());
})();
