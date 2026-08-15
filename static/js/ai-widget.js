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
})();
