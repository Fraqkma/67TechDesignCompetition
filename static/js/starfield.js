/* Enlightenment Compass — shared full-page starfield background.
   Draws twinkling stars into a fixed canvas behind all page content.
   Purely decorative, no page data — same visual on every page. */
(function () {
  "use strict";
  var canvas = document.getElementById("cosmic-starfield-bg");
  if (!canvas) return;
  var ctx = canvas.getContext("2d");
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var stars = [];

  function buildStars() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var width = window.innerWidth;
    var height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    var count = Math.min(260, Math.floor((width * height) / 3800));
    stars = [];
    for (var i = 0; i < count; i++) {
      stars.push({
        x: Math.random() * width,
        y: Math.random() * height,
        r: Math.random() * 1.3 + 0.35,
        base: Math.random() * 0.5 + 0.3,
        speed: Math.random() * 0.0016 + 0.0006,
        phase: Math.random() * Math.PI * 2,
        tint: Math.random() < 0.15 ? "82,214,232" : (Math.random() < 0.1 ? "255,180,84" : "244,239,228"),
      });
    }
  }

  function drawStars(t) {
    var width = window.innerWidth;
    var height = window.innerHeight;
    ctx.clearRect(0, 0, width, height);
    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      var alpha = reduceMotion ? s.base : s.base * (0.55 + 0.45 * Math.sin(t * s.speed + s.phase));
      ctx.beginPath();
      ctx.fillStyle = "rgba(" + s.tint + "," + alpha.toFixed(3) + ")";
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function starLoop(t) {
    drawStars(t || 0);
    if (!reduceMotion) requestAnimationFrame(starLoop);
  }

  function debounce(fn, ms) {
    var handle;
    return function () {
      clearTimeout(handle);
      handle = setTimeout(fn, ms);
    };
  }

  buildStars();
  starLoop(0);
  window.addEventListener("resize", debounce(buildStars, 200));
})();
