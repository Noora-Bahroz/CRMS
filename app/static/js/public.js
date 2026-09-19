(function () {
  "use strict";

  // Flag for scroll-reveal gating (content stays visible if JS is missing).
  document.documentElement.classList.add("js");

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

  // Scroll-reveal for the "Why choose", "Featured fleet" and promo sections:
  // once a block scrolls near the viewport it fades/rises in (CSS staggers).
  var revealEls = document.querySelectorAll(
    ".why .reveal-el, .fleet .reveal-el, .promo .reveal-el, .categories .reveal-el, .cta-scene .reveal-el"
  );
  if (revealEls.length) {
    if ("IntersectionObserver" in window) {
      var revealObserver = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-revealed");
              revealObserver.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.15, rootMargin: "0px 0px -10% 0px" }
      );
      revealEls.forEach(function (el) {
        revealObserver.observe(el);
      });
    } else {
      revealEls.forEach(function (el) {
        el.classList.add("is-revealed");
      });
    }
  }
})();