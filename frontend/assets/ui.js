/* ============================================================
   MeetMind — shared UI glue
   Scroll-reveal, mobile nav, and footer year.
   Used by landing / auth / admin pages. Purely presentational.
============================================================ */

(function () {

    /* ---- scroll reveal ------------------------------------- */

    var revealEls = document.querySelectorAll(".reveal");

    if (!("IntersectionObserver" in window) ||
        window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        revealEls.forEach(function (el) { el.classList.add("is-in"); });
    } else {
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-in");
                    io.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });

        revealEls.forEach(function (el) { io.observe(el); });
    }

    /* ---- mobile nav -------------------------------------- */

    var nav = document.querySelector(".site-nav");
    var navToggle = document.querySelector(".nav-toggle");

    if (nav && navToggle) {
        navToggle.addEventListener("click", function () {
            var open = nav.classList.toggle("is-open");
            navToggle.setAttribute("aria-expanded", String(open));
        });

        nav.querySelectorAll(".nav-links a").forEach(function (a) {
            a.addEventListener("click", function () {
                nav.classList.remove("is-open");
                navToggle.setAttribute("aria-expanded", "false");
            });
        });
    }

    /* ---- footer year ------------------------------------ */

    document.querySelectorAll("[data-year]").forEach(function (el) {
        el.textContent = new Date().getFullYear();
    });

})();
