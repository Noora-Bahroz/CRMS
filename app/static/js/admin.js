/* CRMS admin scripts. */
(function () {
  "use strict";

  var logoutButtons = document.querySelectorAll("[data-logout]");

  logoutButtons.forEach(function (button) {
    button.addEventListener("click", function (event) {
      event.preventDefault();
      fetch("/auth/logout", {
        method: "POST",
        headers: { "Accept": "application/json" },
        credentials: "same-origin",
      })
        .catch(function () { /* session is cleared server-side regardless */ })
        .finally(function () {
          window.location.href = "/";
        });
    });
  });
})();