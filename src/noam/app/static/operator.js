// קונסולה: פוקוס על שורת הפקודה במסך נועם, וגלילה לסוף הפלט.
(function () {
  function settle() {
    const t = document.getElementById("term-out");
    if (t) t.scrollTop = t.scrollHeight;
  }
  document.addEventListener("htmx:oobAfterSwap", settle);
  document.addEventListener("DOMContentLoaded", settle);
  document.addEventListener("htmx:afterRequest", (e) => {
    const f = e.detail.elt;
    if (f && f.id === "shell-form") { f.reset(); const i = f.querySelector("input"); if (i) i.focus(); }
  });
})();
