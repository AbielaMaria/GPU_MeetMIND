/* ============================================================
   MeetMind — shared theme toggle
   ------------------------------------------------------------
   Behaviour + storage key ("meetmind-theme") are identical to
   the inline module in index.html, so a theme chosen on the
   landing/auth/admin pages carries into the app and back.

   Every new page also needs the tiny pre-paint snippet inline
   in <head> (see any of the new .html files) to avoid a flash.
============================================================ */

(function () {
    var STORAGE_KEY = "meetmind-theme";
    var root = document.documentElement;

    function stored() {
        try {
            var v = localStorage.getItem(STORAGE_KEY);
            return (v === "light" || v === "dark") ? v : null;
        } catch (e) {
            return null;
        }
    }

    function current() {
        return root.getAttribute("data-theme") || stored() || "light";
    }

    function apply(theme) {
        root.setAttribute("data-theme", theme);
        document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
            btn.setAttribute("aria-pressed", String(theme === "dark"));
        });
    }

    apply(current());

    document.addEventListener("click", function (event) {
        var btn = event.target.closest("[data-theme-toggle]");
        if (!btn) return;

        var next = current() === "dark" ? "light" : "dark";
        try {
            localStorage.setItem(STORAGE_KEY, next);
        } catch (e) {}
        apply(next);
    });
})();
