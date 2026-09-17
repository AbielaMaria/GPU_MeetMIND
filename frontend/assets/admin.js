/* ============================================================
   MeetMind — admin: list / add / edit / remove users
   ============================================================
   All data is the mock store in assets/auth-store.js
   (localStorage). Changes here affect who can sign in.
   TODO(backend): swap MeetMindAuth.listUsers/addUser/updateUser/
   deleteUser for /api/admin/users calls.
============================================================ */

(function () {
    "use strict";

    var A = window.MeetMindAuth;
    var session = A && A.getSession();
    if (!session) return; // guard already redirected

    /* ---- header ---------------------------------------- */

    document.getElementById("whoEmail").textContent = session.email || "";

    document.getElementById("logoutBtn").addEventListener("click", function () {
        A.signOut();                 // TODO(backend): POST /api/auth/logout
        location.assign("/sign-in");
    });

    /* ---- refs ----------------------------------------- */

    var tbody = document.getElementById("userRows");
    var searchEl = document.getElementById("userSearch");
    var roleEl = document.getElementById("roleFilter");
    var statusEl = document.getElementById("statusFilter");
    var rowCount = document.getElementById("rowCount");

    var dialog = document.getElementById("userDialog");
    var form = document.getElementById("userForm");
    var dialogTitle = document.getElementById("dialogTitle");
    var pwLabelText = document.getElementById("pwLabelText");
    var alertEl = form.querySelector(".form-alert.js-error");

    var f = {
        username: form.querySelector('[name="username"]'),
        email: form.querySelector('[name="email"]'),
        password: form.querySelector('[name="password"]'),
        role: form.querySelector('[name="role"]'),
        status: form.querySelector('[name="status"]')
    };

    // null = adding; string = editing this (original) email
    var editingEmail = null;

    /* ---- helpers ------------------------------------- */

    function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c];
        });
    }

    function fmtDate(iso) {
        var d = new Date(iso);
        if (isNaN(d)) return "—";
        return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
    }

    function showAlert(msg) {
        alertEl.textContent = msg;
        alertEl.classList.add("is-shown");
    }
    function hideAlert() {
        alertEl.classList.remove("is-shown");
    }

    /* ---- render table ------------------------------- */

    function render() {
        var all = A.listUsers();
        var q = searchEl.value.trim().toLowerCase();
        var role = roleEl.value;
        var status = statusEl.value;

        var rows = all.filter(function (u) {
            if (role && u.role !== role) return false;
            if (status && (u.status || "active") !== status) return false;
            if (q && ((u.username || "") + " " + u.email).toLowerCase().indexOf(q) === -1) return false;
            return true;
        });

        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="6"><div class="table-empty">' +
                (all.length ? "No users match your filters." : "No users yet. Click “Add user”.") +
                "</div></td></tr>";
        } else {
            tbody.innerHTML = rows.map(function (u) {
                var isSelf = u.email === session.email;
                return "<tr>" +
                    "<td>" + esc(u.username) + (isSelf ? ' <span class="hint">(you)</span>' : "") + "</td>" +
                    "<td>" + esc(u.email) + "</td>" +
                    '<td><span class="pill role-' + esc(u.role) + '">' + esc(u.role) + "</span></td>" +
                    "<td>" + fmtDate(u.createdAt) + "</td>" +
                    '<td><span class="pill st-' + esc(u.status || "active") + '">' + esc(u.status || "active") + "</span></td>" +
                    '<td class="cell-actions">' +
                        '<button class="row-btn" data-edit="' + esc(u.email) + '">Edit</button>' +
                        (isSelf ? "" : '<button class="row-btn danger" data-del="' + esc(u.email) + '">Delete</button>') +
                    "</td>" +
                "</tr>";
            }).join("");
        }

        rowCount.textContent = rows.length + " of " + all.length + " user" + (all.length === 1 ? "" : "s");
    }

    /* ---- dialog: open / close ---------------------- */

    function openAdd() {
        editingEmail = null;
        dialogTitle.textContent = "Add user";
        pwLabelText.textContent = "Password";
        form.reset();
        f.role.value = "user";
        f.status.value = "active";
        hideAlert();
        clearFieldErrors();
        dialog.showModal();
        f.username.focus();
    }

    function openEdit(email) {
        var u = A.listUsers().find(function (x) { return x.email === email; });
        if (!u) return;
        editingEmail = u.email;
        dialogTitle.textContent = "Edit user";
        pwLabelText.textContent = "Password (leave blank to keep)";
        f.username.value = u.username || "";
        f.email.value = u.email;
        f.password.value = "";
        f.role.value = u.role === "admin" ? "admin" : "user";
        f.status.value = (u.status === "inactive") ? "inactive" : "active";
        hideAlert();
        clearFieldErrors();
        dialog.showModal();
        f.username.focus();
    }

    function clearFieldErrors() {
        form.querySelectorAll(".field.has-error").forEach(function (el) { el.classList.remove("has-error"); });
        form.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
    }

    function fieldError(name, msg) {
        var field = form.querySelector('.field[data-field="' + name + '"]');
        var out = form.querySelector('[data-error-for="' + name + '"]');
        if (out) out.textContent = msg || "";
        if (field) field.classList.toggle("has-error", !!msg);
    }

    document.getElementById("addUserBtn").addEventListener("click", openAdd);
    document.getElementById("dialogCancel").addEventListener("click", function () { dialog.close(); });

    // row actions (delegated)
    tbody.addEventListener("click", function (e) {
        var editBtn = e.target.closest("[data-edit]");
        if (editBtn) { openEdit(editBtn.getAttribute("data-edit")); return; }

        var delBtn = e.target.closest("[data-del]");
        if (delBtn) {
            var email = delBtn.getAttribute("data-del");
            if (confirm("Remove user " + email + "? This cannot be undone.")) {
                A.deleteUser(email);
                render();
            }
        }
    });

    /* ---- dialog: submit --------------------------- */

    form.addEventListener("submit", function (e) {
        e.preventDefault();            // we control close()
        hideAlert();
        clearFieldErrors();

        var data = {
            username: f.username.value.trim(),
            email: f.email.value.trim(),
            password: f.password.value,
            role: f.role.value,
            status: f.status.value
        };

        var bad = false;
        if (!data.username) { fieldError("username", "Username is required."); bad = true; }
        if (!data.email) { fieldError("email", "Email is required."); bad = true; }
        else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) { fieldError("email", "Enter a valid email address."); bad = true; }
        if (!editingEmail && !data.password) { fieldError("password", "Password is required."); bad = true; }
        if (bad) return;

        try {
            if (editingEmail) {
                A.updateUser(editingEmail, data);
            } else {
                A.addUser(data);
            }
        } catch (err) {
            showAlert(err.message || "Could not save the user.");
            return;
        }

        dialog.close();
        render();
    });

    // close on backdrop click
    dialog.addEventListener("click", function (e) {
        if (e.target === dialog) dialog.close();
    });

    /* ---- filters ---------------------------------- */

    searchEl.addEventListener("input", render);
    roleEl.addEventListener("change", render);
    statusEl.addEventListener("change", render);

    render();

})();
