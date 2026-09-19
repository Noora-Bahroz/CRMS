(function () {
  "use strict";

  // Keep the return date after the pickup date on search/filter forms.
  document.querySelectorAll("form[data-range-form]").forEach(function (form) {
    var pickup = form.querySelector('input[name="pickup_datetime"]');
    var ret = form.querySelector('input[name="return_datetime"]');
    if (!pickup || !ret) {
      return;
    }

    function syncMin() {
      if (pickup.value) {
        ret.min = pickup.value;
        if (ret.value && ret.value <= pickup.value) {
          ret.value = "";
        }
      } else {
        ret.removeAttribute("min");
      }
    }

    pickup.addEventListener("change", syncMin);
    syncMin();
  });

  // Horizontal fleet carousel controls.
  document.querySelectorAll("[data-carousel]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var track = document.getElementById(btn.getAttribute("data-target"));
      if (!track) {
        return;
      }
      var slide = track.querySelector(".fleet-slide");
      var amount = slide ? slide.offsetWidth + 24 : track.clientWidth * 0.8;
      var direction = btn.getAttribute("data-carousel") === "prev" ? -1 : 1;
      track.scrollBy({ left: amount * direction, behavior: "smooth" });
    });
  });
})();