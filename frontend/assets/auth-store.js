/* ============================================================
   MeetMind — real auth / user store (server-backed)
   ============================================================
   Talks to the FastAPI backend's /api/auth/* and /api/users
   endpoints (see backend/auth.py + backend/database.py). Accounts
   and sessions live in a SQLite database on the server, not in
   this browser's localStorage — so an account registered on one
   machine can sign in from any other machine hitting the same
   backend, and the admin dashboard's changes persist for everyone.

   The session itself is an HttpOnly cookie the server sets on
   /api/auth/login — JS never reads or writes it directly. Closing
   the tab/browser without "remember me" checked drops the cookie
   (the server issues it with no Max-Age in that case), so the next
   visit requires signing in again.

   Every function below returns a Promise, since every call now
   round-trips to the server. `auth-forms.js` and `admin.js` already
   consume signIn()/signUp() as promises; the CRUD helpers changed
   from synchronous to async here too, and their call sites were
   updated to match.
============================================================ */

(function (global) {
    "use strict";

    var API_BASE = "/api";

    function request(method, path, body) {
        var opts = {
            method: method,
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin"
        };
        if (body !== undefined) opts.body = JSON.stringify(body);

        return fetch(API_BASE + path, opts).then(function (res) {
            if (res.status === 204) return null;
            return res.json().catch(function () { return null; }).then(function (data) {
                if (!res.ok) {
                    throw new Error((data && data.detail) || "Request failed.");
                }
                return data;
            });
        });
    }

    var MeetMindAuth = {

        /* ---- session ------------------------------------------- */

        // Resolves with the session {username,email,role,...} or null.
        getSession: function () {
            return request("GET", "/auth/session").catch(function () { return null; });
        },

        isAuthed: function () {
            return this.getSession().then(function (s) { return !!(s && s.email); });
        },

        signOut: function () {
            return request("POST", "/auth/logout").catch(function () {});
        },

        /* ---- sign up (self-service = always role "user") ------ */

        signUp: function (payload) {
            return request("POST", "/auth/register", {
                username: payload.username,
                email: payload.email,
                password: payload.password
            }).then(function (user) { return { user: user }; });
        },

        /* ---- sign in ----------------------------------------- */

        signIn: function (email, password, remember) {
            return request("POST", "/auth/login", {
                email: email,
                password: password,
                remember: !!remember
            }).then(function (session) { return { session: session }; });
        },

        /* ---- role routing / guard --------------------------- */

        landingPathForRole: function (role) {
            return role === "admin" ? "/admin" : "/app";
        },

        /* ============================================================
           ADMIN — user CRUD (server-backed, admin-only endpoints)
        ============================================================ */

        listUsers: function () {
            return request("GET", "/users");
        },

        addUser: function (data) {
            return request("POST", "/users", data);
        },

        // `originalEmail` identifies the row; patch may include a new email.
        updateUser: function (originalEmail, patch) {
            return request("PATCH", "/users/" + encodeURIComponent(originalEmail), patch);
        },

        deleteUser: function (email) {
            return request("DELETE", "/users/" + encodeURIComponent(email))
                .then(function () { return true; })
                .catch(function () { return false; });
        }
    };

    global.MeetMindAuth = MeetMindAuth;

})(window);
