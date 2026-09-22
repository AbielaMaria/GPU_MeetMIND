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

    /* An already-signed-in visitor never reaches this page: /sign-in and
       /sign-up redirect them server-side before the HTML is served (see
       backend/app.py). Doing it here as well used to race with that check
       and, against a stale cached app-guard.js, looped the browser between
       /sign-in and /app indefinitely. The server is the only authority. */

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

    // Matches the fixed string auth.py's login endpoint sends for a
    // not-yet-verified account (see UNVERIFIED_LOGIN_MSG), so sign-in can
    // route the user into the verify panel instead of just showing an alert.
    var UNVERIFIED_LOGIN_MSG = "Please verify your email before signing in.";

    function goToVerify(email) {
        var emailField = document.getElementById("vf_email");
        if (emailField) emailField.value = email || "";
        setMode("verify", true);
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

    var TITLES = {
        signin: "Sign In — MeetMind",
        signup: "Create your account — MeetMind",
        verify: "Verify your email — MeetMind"
    };
    var PATHS = { signin: "/sign-in", signup: "/sign-up", verify: "/verify-otp" };

    function currentMode() {
        var mode = document.body.getAttribute("data-auth-mode");
        return (mode === "signup" || mode === "verify") ? mode : "signin";
    }

    function setMode(mode, userInitiated) {
        if (mode !== "signin" && mode !== "signup" && mode !== "verify") mode = "signin";
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

        ["identifier", "password"].forEach(function (n) {
            signInForm.querySelector('[name="' + n + '"]').addEventListener("input", function () {
                clearError(signInForm, n);
                hideAlerts(siPanel);
            });
        });

        signInForm.addEventListener("submit", function (e) {
            e.preventDefault();
            hideAlerts(siPanel);

            var identifier = signInForm.querySelector('[name="identifier"]').value.trim();
            var password = signInForm.querySelector('[name="password"]').value;

            var ok = true;
            if (!identifier) ok = setError(signInForm, "identifier", "Username or email is required.") && ok;
            if (!password) ok = setError(signInForm, "password", "Password is required.") && ok;
            if (!ok) return;

            setLoading(siBtn, true);

            A.signIn(identifier, password).then(function (res) {
                redirectAfterAuth(res.session.role);
            }).catch(function (err) {
                setLoading(siBtn, false);
                if (err.message === UNVERIFIED_LOGIN_MSG) {
                    goToVerify(identifier.indexOf("@") !== -1 ? identifier : "");
                    return;
                }
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

        signUpForm.addEventListener("submit", function (e) {
            e.preventDefault();
            hideAlerts(suPanel);

            var username = signUpForm.querySelector('[name="username"]').value.trim();
            var email = signUpForm.querySelector('[name="email"]').value.trim();
            var password = pwInput.value;
            var confirm = cfInput.value;

            var ok = true;
            if (!username) ok = setError(signUpForm, "username", "A username is required.") && ok;

            if (!email) ok = setError(signUpForm, "email", "Email is required.") && ok;
            else if (!EMAIL_RE.test(email)) ok = setError(signUpForm, "email", "Enter a valid email address.") && ok;

            // Minimal password rule: just not empty.
            if (!password) ok = setError(signUpForm, "password", "Password is required.") && ok;

            if (!confirm) ok = setError(signUpForm, "confirm", "Please confirm your password.") && ok;
            else if (confirm !== password) ok = setError(signUpForm, "confirm", "Passwords don't match.") && ok;

            if (!ok) return;

            setLoading(suBtn, true);

            A.signUp({ username: username, email: email, password: password, role: "user" })
                .then(function () {
                    goToVerify(email);
                })
                .catch(function (err) {
                    setLoading(suBtn, false);
                    showAlert(suPanel, "error", err.message || "Could not create your account.");
                });
        });
    }

    /* ============================================================
       VERIFY EMAIL (OTP)
    ============================================================ */

    var verifyForm = document.getElementById("verifyForm");

    if (verifyForm) {
        var vfPanel = verifyForm.closest("[data-panel]");
        var vfBtn = verifyForm.querySelector('[type="submit"]');
        var vfEmail = verifyForm.querySelector('[name="email"]');
        var vfCode = verifyForm.querySelector('[name="code"]');
        var resendLink = document.getElementById("resendOtpLink");

        // Prefill from ?email= (e.g. arriving here after sign-up or a
        // blocked sign-in), so the person doesn't retype it.
        var qEmail = new URLSearchParams(location.search).get("email");
        if (qEmail && !vfEmail.value) vfEmail.value = qEmail;

        ["email", "code"].forEach(function (n) {
            verifyForm.querySelector('[name="' + n + '"]').addEventListener("input", function () {
                clearError(verifyForm, n);
                hideAlerts(vfPanel);
            });
        });

        verifyForm.addEventListener("submit", function (e) {
            e.preventDefault();
            hideAlerts(vfPanel);

            var email = vfEmail.value.trim();
            var code = vfCode.value.trim();

            var ok = true;
            if (!email) ok = setError(verifyForm, "email", "Email is required.") && ok;
            else if (!EMAIL_RE.test(email)) ok = setError(verifyForm, "email", "Enter a valid email address.") && ok;
            if (!code) ok = setError(verifyForm, "code", "Enter the code we emailed you.") && ok;
            if (!ok) return;

            setLoading(vfBtn, true);

            A.verifyOtp(email, code).then(function (res) {
                if (res.session) {
                    showAlert(vfPanel, "success", "Verified — taking you to the app…");
                    setTimeout(function () { redirectAfterAuth(res.session.role); }, 500);
                } else {
                    setLoading(vfBtn, false);
                    showAlert(vfPanel, "success", "Verified. Your administrator still needs to activate your account before you can sign in.");
                }
            }).catch(function (err) {
                setLoading(vfBtn, false);
                showAlert(vfPanel, "error", err.message || "Could not verify that code.");
            });
        });

        if (resendLink) {
            resendLink.addEventListener("click", function (e) {
                e.preventDefault();
                hideAlerts(vfPanel);
                var email = vfEmail.value.trim();
                if (!email || !EMAIL_RE.test(email)) {
                    setError(verifyForm, "email", "Enter a valid email address first.");
                    return;
                }
                A.resendOtp(email).then(function () {
                    showAlert(vfPanel, "success", "A new code is on its way.");
                }).catch(function (err) {
                    showAlert(vfPanel, "error", err.message || "Could not resend the code.");
                });
            });
        }
    }

})();