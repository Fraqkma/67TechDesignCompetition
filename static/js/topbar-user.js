/* Enlightenment Compass — shared topbar user cluster (Profile link, display
   name). Hidden until /api/me confirms a session, so anonymous visitors on
   pages that don't require login (e.g. the landing page) see nothing broken. */
(function () {
  "use strict";
  var container = document.getElementById("topbar-user");
  var nameEl = document.getElementById("user-display-name");
  if (!container) return;

  fetch("/api/me", { credentials: "same-origin" })
    .then(function (res) { return res.ok ? res.json() : null; })
    .then(function (body) {
      if (!body || !body.ok) return;
      if (nameEl) nameEl.textContent = body.data.displayName || body.data.email || "";
      container.hidden = false;
    })
    .catch(function () {});
})();
