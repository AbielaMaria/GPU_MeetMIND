/* ============================================================
   MeetMind — MOCK auth / user store
   ============================================================
   ⚠️  TEMPORARY / PLACEHOLDER — NO REAL SECURITY HERE.
   Client-side stand-in so the product flow (landing → sign-up →
   sign-in → role routing → app / admin → logout) and basic user
   admin (list / add / edit / remove) work before a backend exists.

   Everything lives in the browser's localStorage:
     meetmind:session → JSON { username, email, role, ts }
     meetmind:users   → JSON array of user records
     meetmind:seed    → seed version marker (forces a reset when bumped)

   Nothing is sent to the server / a database yet.

   ADMIN IS NOT A SEPARATE LOGIN.
   -------------------------------------------------------------
   There is ONE sign-in form and ONE signIn() path for everyone.
   A user record just carries a `role` field ("user" | "admin");
   after login landingPathForRole() sends admins to /admin and
   everyone else to /app. The only thing admins can't do is
   self-register as admin (sign-up always creates role "user") —
   an admin account is seeded, or created by another admin from
   the dashboard.

   WHAT YOU (backend dev) SWAP IN LATER
   -------------------------------------------------------------
   signUp()      → POST /api/auth/register            (role: "user")
   signIn()      → POST /api/auth/login               (same endpoint
                   for admins and users; server returns the role)
   getSession()  → real server-verified session (httpOnly cookie)
   signOut()     → POST /api/auth/logout
   listUsers()/addUser()/updateUser()/deleteUser()
                 → the admin USER-MANAGEMENT screen (not auth) —
                   back it with admin-gated /api/users endpoints.
   Then delete SEED_USERS and the seed-reset block.
============================================================ */

(function (global) {

    var SESSION_KEY = "meetmind:session";
    var USERS_KEY = "meetmind:users";
    var SEED_KEY = "meetmind:seed";

    /* Bump this string to wipe every browser's user list + session
       and re-seed from scratch on next load. */
    var SEED_VERSION = "4";

    /* --- PLACEHOLDER seed: a single admin account. -------------- */
    var SEED_USERS = [
        {
            username: "admin",
            email: "admin@gmail.com",
            password: "admin123",       // PLACEHOLDER — plaintext, mock only
            role: "admin",
            createdAt: "2026-09-01T09:00:00Z",
            status: "active"
        }
    ];

    function readJSON(key, fallback) {
        try {
            var raw = localStorage.getItem(key);
            return raw ? JSON.parse(raw) : fallback;
        } catch (e) {
            return fallback;
        }
    }

    function writeJSON(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch (e) {}
    }

    /* ---- one-time reset when SEED_VERSION changes -------------- */
    (function seedReset() {
        try {
            if (localStorage.getItem(SEED_KEY) === SEED_VERSION) return;
            localStorage.removeItem(USERS_KEY);
            localStorage.removeItem(SESSION_KEY);
            writeJSON(USERS_KEY, SEED_USERS.slice());
            localStorage.setItem(SEED_KEY, SEED_VERSION);
        } catch (e) {}
    })();

    function getUsers() {
        var users = readJSON(USERS_KEY, null);
        if (!Array.isArray(users)) {
            users = SEED_USERS.slice();
            writeJSON(USERS_KEY, users);
        }
        return users;
    }

    function saveUsers(users) {
        writeJSON(USERS_KEY, users);
    }

    function normEmail(v) {
        return String(v || "").toLowerCase().trim();
    }

    function findByEmail(users, email) {
        var e = normEmail(email);
        return users.find(function (u) { return normEmail(u.email) === e; }) || null;
    }

    var MeetMindAuth = {

        /* ---- session ------------------------------------------- */

        getSession: function () {
            return readJSON(SESSION_KEY, null);
        },

        isAuthed: function () {
            var s = this.getSession();
            return !!(s && s.email);
        },

        _startSession: function (user, remember) {
            var session = {
                username: user.username || user.name || "",
                email: user.email,
                role: user.role || "user",
                ts: Date.now(),
                remember: !!remember
            };
            writeJSON(SESSION_KEY, session);
            return session;
        },

        signOut: function () {
            try { localStorage.removeItem(SESSION_KEY); } catch (e) {}
        },

        /* ---- sign up (self-service = always role "user") ------ */

        signUp: function (payload) {
            return new Promise(function (resolve, reject) {
                setTimeout(function () {
                    var users = getUsers();
                    var email = normEmail(payload.email);
                    var username = String(payload.username || "").trim();

                    if (!username) { reject(new Error("Username is required.")); return; }
                    if (findByEmail(users, email)) {
                        reject(new Error("An account with that email already exists."));
                        return;
                    }

                    var user = {
                        username: username,
                        email: email,
                        password: payload.password,   // PLACEHOLDER — plaintext
                        role: "user",
                        createdAt: new Date().toISOString(),
                        status: "active"
                    };
                    users.push(user);
                    saveUsers(users);
                    resolve({ user: user });
                }, 500);
            });
        },

        /* ---- sign in ----------------------------------------- */

        signIn: function (email, password, remember) {
            var self = this;
            return new Promise(function (resolve, reject) {
                setTimeout(function () {
                    var users = getUsers();
                    var match = users.find(function (u) {
                        return normEmail(u.email) === normEmail(email)
                            && u.password === password;
                    });

                    if (!match) {
                        reject(new Error("Incorrect email or password."));
                        return;
                    }
                    if (match.status && match.status !== "active") {
                        reject(new Error("This account is inactive. Contact your administrator."));
                        return;
                    }

                    resolve({ session: self._startSession(match, remember) });
                }, 500);
            });
        },

        /* ---- role routing / guard --------------------------- */

        landingPathForRole: function (role) {
            return role === "admin" ? "/admin" : "/app";
        },

        guard: function (requiredRole) {
            var s = this.getSession();
            if (!s || !s.email) {
                var next = encodeURIComponent(location.pathname + location.search);
                location.replace("/sign-in?next=" + next);
                return false;
            }
            if (requiredRole && s.role !== requiredRole) {
                location.replace(this.landingPathForRole(s.role));
                return false;
            }
            return true;
        },

        /* ============================================================
           ADMIN — user CRUD  (synchronous; localStorage-backed)
           TODO(backend): swap each for a /api/admin/users call.
        ============================================================ */

        listUsers: function () {
            // newest first
            return getUsers().slice().sort(function (a, b) {
                return new Date(b.createdAt || 0) - new Date(a.createdAt || 0);
            });
        },

        addUser: function (data) {
            var users = getUsers();
            var email = normEmail(data.email);
            var username = String(data.username || "").trim();

            if (!username) throw new Error("Username is required.");
            if (!email) throw new Error("Email is required.");
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error("Enter a valid email address.");
            if (!data.password) throw new Error("Password is required.");
            if (findByEmail(users, email)) throw new Error("A user with that email already exists.");

            var user = {
                username: username,
                email: email,
                password: String(data.password),
                role: data.role === "admin" ? "admin" : "user",
                status: data.status === "inactive" ? "inactive" : "active",
                createdAt: new Date().toISOString()
            };
            users.push(user);
            saveUsers(users);
            return user;
        },

        // `originalEmail` identifies the row; patch may include a new email.
        updateUser: function (originalEmail, patch) {
            var users = getUsers();
            var user = findByEmail(users, originalEmail);
            if (!user) throw new Error("User not found.");

            if (patch.email != null) {
                var newEmail = normEmail(patch.email);
                if (!newEmail) throw new Error("Email is required.");
                if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newEmail)) throw new Error("Enter a valid email address.");
                var clash = findByEmail(users, newEmail);
                if (clash && clash !== user) throw new Error("Another user already uses that email.");
                user.email = newEmail;
            }
            if (patch.username != null) {
                var un = String(patch.username).trim();
                if (!un) throw new Error("Username is required.");
                user.username = un;
            }
            if (patch.password != null && patch.password !== "") {
                user.password = String(patch.password);
            }
            if (patch.role != null) {
                user.role = patch.role === "admin" ? "admin" : "user";
            }
            if (patch.status != null) {
                user.status = patch.status === "inactive" ? "inactive" : "active";
            }
            saveUsers(users);
            return user;
        },

        deleteUser: function (email) {
            var users = getUsers();
            var e = normEmail(email);
            var next = users.filter(function (u) { return normEmail(u.email) !== e; });
            if (next.length === users.length) return false;
            saveUsers(next);
            return true;
        }
    };

    global.MeetMindAuth = MeetMindAuth;

})(window);
