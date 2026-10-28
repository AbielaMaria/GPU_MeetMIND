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

        getSession: function () {
            return request("GET", "/auth/session").catch(function () { return null; });
        },

        isAuthed: function () {
            return this.getSession().then(function (s) { return !!(s && s.email); });
        },

        signOut: function () {
            return request("POST", "/auth/logout").catch(function () {});
        },

        signUp: function (payload) {
            return request("POST", "/auth/register", {
                username: payload.username,
                email: payload.email,
                password: payload.password
            });
        },

        signIn: function (identifier, password) {
            return request("POST", "/auth/login", {
                identifier: identifier,
                password: password
            }).then(function (session) { return { session: session }; });
        },

        pendingStatus: function () {
            return request("GET", "/auth/pending-status");
        },

        continueAfterApproval: function () {
            return request("POST", "/auth/continue");
        },

        verifyOtp: function (email, code) {
            return request("POST", "/auth/verify-otp", { email: email, code: code });
        },

        resendOtp: function (email) {
            return request("POST", "/auth/resend-otp", { email: email });
        },

        landingPathForRole: function (role) {
            return role === "admin" ? "/admin" : "/app";
        },

        listUsers: function () {
            return request("GET", "/users");
        },

        addUser: function (data) {
            return request("POST", "/users", data);
        },

        updateUser: function (originalEmail, patch) {
            return request("PATCH", "/users/" + encodeURIComponent(originalEmail), patch);
        },

        setUserVerified: function (email, verified) {
            return this.updateUser(email, { emailVerified: !!verified });
        },

        deleteUser: function (email) {
            return request("DELETE", "/users/" + encodeURIComponent(email))
                .then(function () { return true; })
                .catch(function () { return false; });
        }
    };

    global.MeetMindAuth = MeetMindAuth;

})(window);