/* Must load before app.js — honor ?lang= into mfw.lang */
(function () {
  try {
    var q = new URLSearchParams(location.search).get("lang");
    if (q && /^(ja|en|zh)$/.test(q)) {
      localStorage.setItem("mfw.lang", q);
    }
  } catch (e) {}
})();
