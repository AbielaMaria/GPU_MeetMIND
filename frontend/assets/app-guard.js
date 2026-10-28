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
            if (session && session.email) buildBar(session);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
