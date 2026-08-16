/* Enlightenment Compass — shared topbar user cluster (Profile link, display
   name). Hidden until /api/me confirms a session, so anonymous visitors on
   pages that don't require login (e.g. the landing page) see nothing broken. */
(function () {
  "use strict";
  var container = document.getElementById("topbar-user");
  var nameEl = document.getElementById("user-display-name");
  var profileImage = document.getElementById("user-profile-image");
  if (!container) return;

  fetch("/api/me", { credentials: "same-origin" })
    .then(function (res) { return res.ok ? res.json() : null; })
    .then(function (body) {
      if (!body || !body.ok) return;
      if (nameEl) nameEl.textContent = body.data.displayName || body.data.email || "";
      // Show any stored portrait (including legacy SVG fallbacks) so the
      // topbar chip always reflects the account's picture when one exists.
      if (profileImage && body.data.profileImage) {
        // Per-account cache key: the URL is shared by every account, so the
        // user id must bust the browser cache or another account's cached
        // portrait could be shown here.
        profileImage.src = "/api/profile/avatar?u=" + encodeURIComponent(body.data.id);
        profileImage.removeAttribute("hidden");
      }
      container.hidden = false;
    })
    .catch(function () {});
})();
