/* Enlightenment Compass — shared back-to-previous-page button. */
(function () {
  "use strict";
  document.querySelectorAll(".back-button").forEach(function (btn) {
    btn.addEventListener("click", function () {
      window.history.back();
    });
  });
})();
