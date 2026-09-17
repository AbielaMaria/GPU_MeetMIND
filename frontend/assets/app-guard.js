/* ============================================================
   MeetMind — app route guard + account bar  (loaded by index.html)
   ============================================================
   The ONLY hook added to index.html — a single <script> tag. It
   does not touch the recorder / websocket / summary logic, ids,
   classes, or data-attributes. It only:

     1. Redirects to /sign-in when there is no session.
     2. Injects a plain-text "Log out" button (and, for admins, a
        "Dashboard" link) into the header.

   ⚠️  TEMPORARY / PLACEHOLDER auth. Session is in this browser's
   localStorage ("meetmind:session", written by auth-store.js on
   the sign-in page). Nothing is sent to the backend yet.

   TODO(backend): replace the localStorage check with a real
   server-verified session; point "Log out" at POST /api/auth/logout.
============================================================ */

(function () {
    "use strict";

    var SESSION_KEY = "meetmind:session";
    var SEED_KEY = "meetmind:seed";
    var SEED_VERSION = "4"; // keep in sync with auth-store.js

    function read(key) {
        try {
            var raw = localStorage.getItem(key);
            return raw ? JSON.parse(raw) : null;
        } catch (e) { return null; }
    }

    /* If auth-store's seed version moved on, the old session is stale —
       drop it so the user re-authenticates against the fresh data. */
    try {
        if (localStorage.getItem(SEED_KEY) !== SEED_VERSION) {
            localStorage.removeItem(SESSION_KEY);
        }
    } catch (e) {}

    var session = read(SESSION_KEY);

    /* ---- 1. guard ------------------------------------- */

    if (!session || !session.email) {
        var next = encodeURIComponent(location.pathname + location.search);
        location.replace("/sign-in?next=" + next);
        return;
    }

    /* ---- 2. account bar ------------------------------ */

    function signOut() {
        try { localStorage.removeItem(SESSION_KEY); } catch (e) {}
        // TODO(backend): also POST /api/auth/logout
        location.href = "/sign-in";
    }

    function buildBar() {
        if (document.getElementById("mm-account-bar")) return;

        // Scoped styles. The `button::before` reset is important: index.html
        // gives every <button> an icon pseudo-element (a masked square) —
        // without this our text button shows a stray filled block.
        var style = document.createElement("style");
        style.textContent =
            "#mm-account-bar{display:inline-flex;align-items:center;gap:8px;" +
            "font:500 12px/1 var(--font-sans,system-ui)}" +
            "#mm-account-bar .mm-who{color:var(--text-muted);white-space:nowrap}" +
            "#mm-account-bar a,#mm-account-bar button{font:600 12px/1 var(--font-sans,system-ui);" +
            "cursor:pointer;text-decoration:none;white-space:nowrap;" +
            "padding:8px 13px;border-radius:var(--r-md,12px);" +
            "border:1px solid var(--border,#e7e3dd);color:var(--text-secondary,#56524c);" +
            "background:var(--bg-surface,#faf9f7);transition:color .15s,border-color .15s}" +
            "#mm-account-bar a::before,#mm-account-bar button::before{content:none;display:none}" +
            "#mm-account-bar a:hover{color:var(--text-primary,#1b1a18);border-color:var(--border-strong,#d7d2ca)}" +
            "#mm-account-bar button:hover{color:var(--danger,#dc2626);border-color:var(--danger,#dc2626)}" +
            "@media(max-width:640px){#mm-account-bar .mm-who{display:none}}";
        document.head.appendChild(style);

        var wrap = document.createElement("div");
        wrap.id = "mm-account-bar";

        var who = document.createElement("span");
        who.className = "mm-who";
        who.textContent = session.username ? (session.username + " · " + session.email) : session.email;
        wrap.appendChild(who);

        if (session.role === "admin") {
            var dash = document.createElement("a");
            dash.href = "/admin";
            dash.textContent = "Dashboard";
            wrap.appendChild(dash);
        }

        var btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = "Log out";
        btn.addEventListener("click", signOut);
        wrap.appendChild(btn);

        var host = document.querySelector(".header-actions");
        if (host) {
            host.appendChild(wrap);
        } else {
            wrap.style.cssText =
                "position:fixed;top:14px;right:14px;z-index:9999;padding:8px 10px;" +
                "background:var(--bg-elevated,#fff);border:1px solid var(--border,#e7e3dd);" +
                "border-radius:var(--r-md,12px);box-shadow:var(--shadow-md,0 6px 16px -4px rgba(0,0,0,.1))";
            document.body.appendChild(wrap);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", buildBar);
    } else {
        buildBar();
    }
})();
