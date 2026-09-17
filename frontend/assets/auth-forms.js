/* ============================================================
   MeetMind — auth form validation + submit (single auth.html)
   ============================================================
   One page, two panels (sign in / sign up) toggled in place.
   All DOM lookups are SCOPED to each <form> so the two forms
   can coexist without id collisions.

   Client-side validation only. Account/session work is delegated
   to window.MeetMindAuth (assets/auth-store.js) — the MOCK you
   replace with real API calls.

   Password rules are intentionally minimal for now: required,
   and sign-up's "confirm" must match. No length/strength gate.

   TODO(backend):
     - Swap MeetMindAuth.signIn/signUp implementations in
       auth-store.js; the call-sites here should not change.
     - After real auth, the SERVER decides role + redirect.
============================================================ */

(function () {
    "use strict";

    var A = window.MeetMindAuth;

    /* ---- already signed in? skip the forms entirely ---- */
    if (A && A.isAuthed()) {
        var s = A.getSession();
        location.replace(A.landingPathForRole(s.role));
        return;
    }

    var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    /* ---- scoped helpers -------------------------------- */

    function setError(root, name, msg) {
        var field = root.querySelector('.field[data-field="' + name + '"]');
        var out = root.querySelector('[data-error-for="' + name + '"]');
        if (out) out.textContent = msg || "";
        if (field) field.classList.toggle("has-error", !!msg);
        return !msg;
    }

    function clearError(root, name) { setError(root, name, ""); }

    function showAlert(panel, kind, msg) {
        var el = panel.querySelector(".form-alert.js-" + kind);
        if (!el) return;
        el.textContent = msg;
        el.classList.add("is-shown");
    }

    function hideAlerts(panel) {
        panel.querySelectorAll(".form-alert.js-error, .form-alert.js-success")
            .forEach(function (el) { el.classList.remove("is-shown"); });
    }

    function setLoading(btn, on) {
        if (!btn) return;
        btn.classList.toggle("is-loading", on);
        btn.disabled = on;
    }

    function redirectAfterAuth(role) {
        // Honour ?next= only if it is a same-origin absolute path.
        var next = new URLSearchParams(location.search).get("next");
        if (next) { try { next = decodeURIComponent(next); } catch (e) { next = null; } }
        if (next && /^\/(?!\/)/.test(next)) { location.assign(next); return; }
        location.assign(A ? A.landingPathForRole(role) : "/app");
    }

    /* ---- password show / hide ------------------------- */

    document.querySelectorAll("[data-toggle-pw]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var input = document.getElementById(btn.getAttribute("data-toggle-pw"));
            if (!input) return;
            var toText = input.type === "password";
            input.type = toText ? "text" : "password";
            btn.classList.toggle("is-visible", toText);
            btn.setAttribute("aria-label", toText ? "Hide password" : "Show password");
        });
    });

    /* ============================================================
       MODE SWITCHING  (sign in  <->  sign up)
    ============================================================ */

    var TITLES = { signin: "Sign In — MeetMind", signup: "Create your account — MeetMind" };
    var PATHS = { signin: "/sign-in", signup: "/sign-up" };

    function currentMode() {
        return document.body.getAttribute("data-auth-mode") === "signup" ? "signup" : "signin";
    }

    function setMode(mode, userInitiated) {
        if (mode !== "signin" && mode !== "signup") mode = "signin";
        document.body.setAttribute("data-auth-mode", mode);   // CSS shows the right panel
        document.title = TITLES[mode];

        if (userInitiated) {
            try {
                history.replaceState(null, "", PATHS[mode] + (location.search || ""));
            } catch (e) {}
            var panel = document.querySelector('[data-panel="' + mode + '"]');
            var first = panel && panel.querySelector("input:not([type=hidden])");
            if (first) first.focus();
        }
    }

    document.querySelectorAll("[data-auth-switch]").forEach(function (a) {
        a.addEventListener("click", function (e) {
            e.preventDefault();
            setMode(a.getAttribute("data-auth-switch"), true);
        });
    });

    // Initial mode was already applied inline (no flash); re-affirm title.
    setMode(currentMode(), false);

    /* ============================================================
       SIGN IN
    ============================================================ */

    var signInForm = document.getElementById("signInForm");

    if (signInForm) {
        var siPanel = signInForm.closest("[data-panel]");
        var siBtn = signInForm.querySelector('[type="submit"]');
        var forgot = siPanel.querySelector("[data-forgot]");

        if (forgot) {
            forgot.addEventListener("click", function (e) {
                e.preventDefault();
                // PLACEHOLDER: no password-reset flow yet.
                showAlert(siPanel, "error", "Password reset isn't available in this preview yet.");
            });
        }

        ["email", "password"].forEach(function (n) {
            signInForm.querySelector('[name="' + n + '"]').addEventListener("input", function () {
                clearError(signInForm, n);
                hideAlerts(siPanel);
            });
        });

        signInForm.addEventListener("submit", function (e) {
            e.preventDefault();
            hideAlerts(siPanel);

            var email = signInForm.querySelector('[name="email"]').value.trim();
            var password = signInForm.querySelector('[name="password"]').value;
            var remember = signInForm.querySelector('[name="remember"]').checked;

            var ok = true;
            if (!email) ok = setError(signInForm, "email", "Email is required.") && ok;
            else if (!EMAIL_RE.test(email)) ok = setError(signInForm, "email", "Enter a valid email address.") && ok;
            if (!password) ok = setError(signInForm, "password", "Password is required.") && ok;
            if (!ok) return;

            setLoading(siBtn, true);

            // TODO(backend): real POST /api/auth/login
            A.signIn(email, password, remember).then(function (res) {
                redirectAfterAuth(res.session.role);
            }).catch(function (err) {
                setLoading(siBtn, false);
                showAlert(siPanel, "error", err.message || "Sign in failed. Try again.");
            });
        });
    }

    /* ============================================================
       SIGN UP
    ============================================================ */

    var signUpForm = document.getElementById("signUpForm");

    if (signUpForm) {
        var suPanel = signUpForm.closest("[data-panel]");
        var suBtn = signUpForm.querySelector('[type="submit"]');
        var pwInput = signUpForm.querySelector('[name="password"]');
        var cfInput = signUpForm.querySelector('[name="confirm"]');

        pwInput.addEventListener("input", function () {
            clearError(signUpForm, "password");
            hideAlerts(suPanel);
            // keep the confirm error in sync as the password changes
            if (cfInput.value) {
                setError(signUpForm, "confirm", cfInput.value === pwInput.value ? "" : "Passwords don't match.");
            }
        });

        ["username", "email", "confirm"].forEach(function (n) {
            signUpForm.querySelector('[name="' + n + '"]').addEventListener("input", function () {
                clearError(signUpForm, n);
                hideAlerts(suPanel);
            });
        });

        signUpForm.querySelector('[name="terms"]').addEventListener("change", function () {
            clearError(signUpForm, "terms");
        });

        signUpForm.addEventListener("submit", function (e) {
            e.preventDefault();
            hideAlerts(suPanel);

            var username = signUpForm.querySelector('[name="username"]').value.trim();
            var email = signUpForm.querySelector('[name="email"]').value.trim();
            var password = pwInput.value;
            var confirm = cfInput.value;
            var terms = signUpForm.querySelector('[name="terms"]').checked;

            var ok = true;
            if (!username) ok = setError(signUpForm, "username", "A username is required.") && ok;

            if (!email) ok = setError(signUpForm, "email", "Email is required.") && ok;
            else if (!EMAIL_RE.test(email)) ok = setError(signUpForm, "email", "Enter a valid email address.") && ok;

            // Minimal password rule: just not empty.
            if (!password) ok = setError(signUpForm, "password", "Password is required.") && ok;

            if (!confirm) ok = setError(signUpForm, "confirm", "Please confirm your password.") && ok;
            else if (confirm !== password) ok = setError(signUpForm, "confirm", "Passwords don't match.") && ok;

            if (!terms) ok = setError(signUpForm, "terms", "You must accept the terms to continue.") && ok;

            if (!ok) return;

            setLoading(suBtn, true);

            // TODO(backend): real POST /api/auth/register, then auto-login
            // or send them to sign in. Mock auto-logs-in.
            A.signUp({ username: username, email: email, password: password, role: "user" })
                .then(function () { return A.signIn(email, password, true); })
                .then(function (res) {
                    showAlert(suPanel, "success", "Account created — taking you to the app…");
                    setTimeout(function () { redirectAfterAuth(res.session.role); }, 500);
                })
                .catch(function (err) {
                    setLoading(suBtn, false);
                    showAlert(suPanel, "error", err.message || "Could not create your account.");
                });
        });
    }

})();
