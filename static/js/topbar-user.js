/* Enlightenment Compass — shared topbar user cluster (Profile link, display
   name). Hidden until /api/me confirms a session, so anonymous visitors on
   pages that don't require login (e.g. the landing page) see nothing broken. */
(function () {
  "use strict";
  var container = document.getElementById("topbar-user");
  var nameEl = document.getElementById("user-display-name");
  var profileImage = document.getElementById("user-profile-image");
  var fallbackIcon = document.getElementById("user-avatar-fallback");
  if (!container) return;

  fetch("/api/me", { credentials: "same-origin" })
    .then(function (res) { return res.ok ? res.json() : null; })
    .then(function (body) {
      if (!body || !body.ok) return;
      if (nameEl) nameEl.textContent = body.data.displayName || body.data.email || "";
      if (profileImage && body.data.profileImage && body.data.profileImageGenerated) {
        // Serve the portrait from its own cacheable endpoint instead of the
        // base64 data URL, so the browser reuses it across page loads.
        profileImage.src = "/api/profile/avatar";
        profileImage.hidden = false;
        if (fallbackIcon) fallbackIcon.hidden = true;
      }
      container.hidden = false;
    })
    .catch(function () {});
})();
