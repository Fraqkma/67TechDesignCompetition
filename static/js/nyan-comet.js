/* Enlightenment Compass — randomizes the Nyan Cat comet's flight height
   once at load and again at the start of every flight cycle, so each
   pass crosses at a different altitude but stays level during the pass
   itself. Purely decorative, no page data. */
(function () {
  "use strict";
  document.querySelectorAll(".nyan-comet").forEach(function (comet) {
    function randomizeHeight() {
      var top = 10 + Math.random() * 60;
      comet.style.setProperty("--fly-top", top.toFixed(1) + "%");
    }
    randomizeHeight();
    comet.addEventListener("animationiteration", randomizeHeight);
  });
})();
