/* ============================================================
   MeetMind — account bar  (loaded by index.html)
   ============================================================
   The ONLY hook added to index.html — a single <script> tag. It
   does not touch the recorder / websocket / summary logic, ids,
   classes, or data-attributes. It only injects a plain-text
   "Log out" button (and, for admins, a "Dashboard" link) into
   the header.

   This file deliberately does NOT redirect. Access to /app is
   enforced server-side in backend/app.py before the page is ever
   served, so a second opinion here can only disagree with the
   server — and when it did (an old cached copy of this file still
   reading the long-gone localStorage session), the two bounced the
   browser back and forth in an endless redirect loop. The server
   is the single authority on who is signed in.

   Session is a server-side HttpOnly cookie (see backend/auth.py) —
   this file no longer reads or writes localStorage for auth.
============================================================ */

(function () {
    "use strict";

    var A = window.MeetMindAuth;

    function signOut() {
        (A ? A.signOut() : Promise.resolve()).then(function () {
            location.href = "/sign-in";
        });
    }

    function buildBar(session) {
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

    function init() {
        if (!A) return;
        A.getSession().then(function (session) {
            // No session here just means "don't draw the bar". The server
            // decides access; this never redirects. See the header note.
            if (session && session.email) buildBar(session);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
