/* Enlightenment Compass — tap-to-toggle fallback for the floating AI
   widget on touch devices (desktop already expands on CSS :hover). */
(function () {
  "use strict";
  var widget = document.getElementById("ai-widget");
  var toggle = widget && widget.querySelector(".ai-widget-avatar-button");
  if (!widget || !toggle) return;

  toggle.addEventListener("click", function () {
    var isOpen = widget.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
  });

  document.addEventListener("click", function (event) {
    if (widget.classList.contains("is-open") && !widget.contains(event.target)) {
      widget.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
    }
  });

  // Tuck the mascot away (small + blurred) while near the top of the
  // page, so it doesn't sit on top of the hero on load; scrolling down
  // a bit brings it back to full size.
  var MINIMIZE_SCROLL_THRESHOLD = 120;
  var ticking = false;

  function applyMinimizedState() {
    widget.classList.toggle("is-minimized", window.scrollY < MINIMIZE_SCROLL_THRESHOLD);
    ticking = false;
  }

  applyMinimizedState();
  window.addEventListener(
    "scroll",
    function () {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(applyMinimizedState);
    },
    { passive: true }
  );
})();
