/* ============================================================
   MeetMind — admin: list / add / edit / remove users
   ============================================================
   Server-backed via assets/auth-store.js, which calls the
   admin-only /api/users endpoints (backend/auth.py). Changes here
   persist in the shared SQLite database, so they're visible to
   every machine hitting this backend — not just this browser.
============================================================ */

(function () {
    "use strict";

    var A = window.MeetMindAuth;

    /* ---- refs ------------------------------------------ */

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

    // Cache of the last fetched list, so opening the edit dialog
    // doesn't need a second round-trip.
    var allUsers = [];
    var session = null;

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
        return A.listUsers().then(function (all) {
            allUsers = all;

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
        }).catch(function () {
            tbody.innerHTML = '<tr><td colspan="6"><div class="table-empty">Could not load users.</div></td></tr>';
        });
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
        var u = allUsers.find(function (x) { return x.email === email; });
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
                A.deleteUser(email).then(render);
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

        // Editing without a new password: don't send an empty one.
        var payload = data;
        if (editingEmail && !data.password) {
            payload = { username: data.username, email: data.email, role: data.role, status: data.status };
        }

        var op = editingEmail ? A.updateUser(editingEmail, payload) : A.addUser(payload);
        op.then(function () {
            dialog.close();
            return render();
        }).catch(function (err) {
            showAlert(err.message || "Could not save the user.");
        });
    });

    // close on backdrop click
    dialog.addEventListener("click", function (e) {
        if (e.target === dialog) dialog.close();
    });

    /* ---- filters ---------------------------------- */

    searchEl.addEventListener("input", render);
    roleEl.addEventListener("change", render);
    statusEl.addEventListener("change", render);

    /* ============================================================
       MEETINGS — every user's transcripts + summaries
       ------------------------------------------------------------
       Read-only. Uses the same /api/meetings endpoints as the user's
       own history drawer; the server widens the scope to all users
       because this session's role is "admin".
    ============================================================ */

    var mtBody = document.getElementById("meetingRows");
    var mtSearch = document.getElementById("meetingSearch");
    var mtCount = document.getElementById("meetingCount");

    var mtDialog = document.getElementById("meetingDialog");
    var mtTitle = document.getElementById("meetingDialogTitle");
    var mtMeta = document.getElementById("meetingDialogMeta");
    var mtSummaryPane = document.getElementById("meetingSummaryPane");
    var mtTranscriptPane = document.getElementById("meetingTranscriptPane");

    var allMeetings = [];

    function fmtDateTime(iso) {
        var d = new Date(iso);
        if (isNaN(d)) return "—";
        return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) +
            ", " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    }

    function api(path) {
        return fetch(path, { credentials: "same-origin" }).then(function (res) {
            if (!res.ok) throw new Error("Request failed.");
            return res.json();
        });
    }

    function renderMeetings() {
        var q = mtSearch.value.trim().toLowerCase();

        var rows = allMeetings.filter(function (m) {
            if (!q) return true;
            return ((m.title || "") + " " + (m.username || "") + " " + (m.email || ""))
                .toLowerCase().indexOf(q) !== -1;
        });

        if (!rows.length) {
            mtBody.innerHTML = '<tr><td colspan="5"><div class="table-empty">' +
                (allMeetings.length
                    ? "No meetings match your search."
                    : "No meetings have been recorded yet.") +
                "</div></td></tr>";
        } else {
            mtBody.innerHTML = rows.map(function (m) {
                return "<tr>" +
                    "<td>" + esc(m.title || "Untitled meeting") + "</td>" +
                    "<td>" + esc(m.username || "") +
                        ' <span class="hint">' + esc(m.email || "") + "</span></td>" +
                    "<td>" + fmtDateTime(m.createdAt) + "</td>" +
                    '<td><span class="pill ' + (m.hasSummary ? "st-active" : "role-user") + '">' +
                        (m.hasSummary ? "Summary" : "Transcript only") + "</span></td>" +
                    '<td class="cell-actions">' +
                        '<button class="row-btn" data-view="' + esc(m.id) + '">View</button>' +
                    "</td>" +
                "</tr>";
            }).join("");
        }

        mtCount.textContent = rows.length + " of " + allMeetings.length +
            " meeting" + (allMeetings.length === 1 ? "" : "s");
    }

    function loadMeetings() {
        return api("/api/meetings?scope=all").then(function (meetings) {
            allMeetings = meetings;
            renderMeetings();
        }).catch(function () {
            mtBody.innerHTML = '<tr><td colspan="5"><div class="table-empty">' +
                "Could not load meetings.</div></td></tr>";
        });
    }

    /* ---- viewer dialog ----------------------------- */

    function section(heading, buildBody) {
        var wrap = document.createElement("div");
        wrap.className = "meeting-section";
        var h = document.createElement("h4");
        h.textContent = heading;
        wrap.appendChild(h);
        buildBody(wrap);
        return wrap;
    }

    function textSection(heading, text) {
        return section(heading, function (wrap) {
            var p = document.createElement("p");
            p.textContent = text;
            wrap.appendChild(p);
        });
    }

    function listSection(heading, items) {
        return section(heading, function (wrap) {
            var ul = document.createElement("ul");
            items.forEach(function (item) {
                var li = document.createElement("li");
                // Items may be plain strings or {task, owner, ...} objects.
                if (item && typeof item === "object") {
                    li.textContent = Object.keys(item).map(function (k) {
                        return item[k];
                    }).filter(Boolean).join(" — ");
                } else {
                    li.textContent = String(item);
                }
                ul.appendChild(li);
            });
            wrap.appendChild(ul);
        });
    }

    function renderSummaryPane(summary) {
        mtSummaryPane.innerHTML = "";

        if (!summary) {
            var none = document.createElement("div");
            none.className = "meeting-none";
            none.textContent = "No summary was generated for this meeting.";
            mtSummaryPane.appendChild(none);
            return;
        }

        if (summary.objective) {
            mtSummaryPane.appendChild(textSection("Objective", summary.objective));
        }
        if (summary.meeting_summary) {
            mtSummaryPane.appendChild(textSection("Summary", summary.meeting_summary));
        }

        [
            ["Tasks assigned", summary.tasks_assigned],
            ["Decision points", summary.decision_points],
            ["Objections", summary.objections],
            ["Action items", summary.action_items]
        ].forEach(function (pair) {
            if (Array.isArray(pair[1]) && pair[1].length) {
                mtSummaryPane.appendChild(listSection(pair[0], pair[1]));
            }
        });

        if (!mtSummaryPane.children.length) {
            mtSummaryPane.appendChild(textSection("Summary", "This summary is empty."));
        }
    }

    function showTab(which) {
        var isSummary = which === "summary";
        mtSummaryPane.hidden = !isSummary;
        mtTranscriptPane.hidden = isSummary;
        mtDialog.querySelectorAll(".meeting-tab").forEach(function (t) {
            t.classList.toggle("is-active", t.getAttribute("data-tab") === which);
        });
    }

    mtDialog.querySelectorAll(".meeting-tab").forEach(function (tab) {
        tab.addEventListener("click", function () {
            showTab(tab.getAttribute("data-tab"));
        });
    });

    function openMeeting(id) {
        api("/api/meetings/" + encodeURIComponent(id)).then(function (m) {
            mtTitle.textContent = m.title || "Untitled meeting";
            mtMeta.textContent = (m.username || "") + " · " + (m.email || "") +
                " · " + fmtDateTime(m.createdAt);

            renderSummaryPane(m.summary);

            mtTranscriptPane.innerHTML = "";
            var pre = document.createElement("pre");
            pre.className = "meeting-transcript";
            pre.textContent = m.transcript || "No transcript was stored.";
            mtTranscriptPane.appendChild(pre);

            showTab("summary");
            mtDialog.showModal();

        }).catch(function () {
            alert("Could not open that meeting.");
        });
    }

    mtBody.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-view]");
        if (btn) openMeeting(btn.getAttribute("data-view"));
    });

    document.getElementById("meetingDialogClose")
        .addEventListener("click", function () { mtDialog.close(); });

    mtDialog.addEventListener("click", function (e) {
        if (e.target === mtDialog) mtDialog.close();
    });

    mtSearch.addEventListener("input", renderMeetings);

    /* ---- boot -------------------------------------- */

    if (A) {
        A.getSession().then(function (s) {
            if (!s) return; // guard already redirected
            session = s;
            document.getElementById("whoEmail").textContent = session.email || "";
            document.getElementById("logoutBtn").addEventListener("click", function () {
                A.signOut().then(function () { location.assign("/sign-in"); });
            });
            render();
            loadMeetings();
        });
    }

})();
