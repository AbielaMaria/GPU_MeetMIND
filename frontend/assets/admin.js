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
    var D = window.MeetMindDialog;

    /* ---- refs ------------------------------------------ */

    var tbody = document.getElementById("userRows");
    var searchEl = document.getElementById("userSearch");
    var roleEl = document.getElementById("roleFilter");
    var verifiedEl = document.getElementById("verifiedFilter");
    var rowCount = document.getElementById("rowCount");

    var statTotalUsers = document.getElementById("statTotalUsers");
    var statVerifiedUsers = document.getElementById("statVerifiedUsers");
    var statUnverifiedUsers = document.getElementById("statUnverifiedUsers");
    var statSummarized = document.getElementById("statSummarized");
    var statMindmapped = document.getElementById("statMindmapped");
    var statSummarizedBy = document.getElementById("statSummarizedBy");
    var statMindmappedBy = document.getElementById("statMindmappedBy");

    var dialog = document.getElementById("userDialog");
    var form = document.getElementById("userForm");
    var dialogTitle = document.getElementById("dialogTitle");
    var pwLabelText = document.getElementById("pwLabelText");
    var alertEl = form.querySelector(".form-alert.js-error");

    var f = {
        username: form.querySelector('[name="username"]'),
        email: form.querySelector('[name="email"]'),
        password: form.querySelector('[name="password"]'),
        role: form.querySelector('[name="role"]')
    };
    var verifyNote = document.getElementById("dialogVerifyNote");

    // null = adding; string = editing this (original) email
    var editingEmail = null;
    // Role select value before the latest change, so Cancel on the
    // "grant admin" warning can put it back.
    var roleBefore = "user";

    var ADMIN_PRIVILEGES = [
        "Open this admin dashboard",
        "Add, edit and delete any account, including changing emails and passwords",
        "Verify or unverify other accounts (unverified accounts are signed out immediately)",
        "Give or remove the admin role on other accounts",
        "View every user's meetings: transcripts, summaries and mind maps"
    ];

    // Cache of the last fetched list, so opening the edit dialog
    // doesn't need a second round-trip.
    var allUsers = [];
    var session = null;

    var userPagination = document.getElementById("userPagination");
    var userPage = 1;
    var USERS_PER_PAGE = 5;

    /* ---- helpers ------------------------------------- */

    // Shared by the users and meetings tables: prev/next arrows plus
    // clickable page numbers (with an ellipsis once there are many pages).
    function renderPagination(container, page, totalPages, onChange) {
        container.innerHTML = "";
        if (totalPages <= 1) return;

        function makeBtn(label, targetPage, opts) {
            opts = opts || {};
            var b = document.createElement("button");
            b.type = "button";
            b.className = opts.arrow ? "page-arrow" : "page-btn";
            if (opts.active) b.className += " is-active";
            b.textContent = label;
            if (opts.disabled) {
                b.disabled = true;
            } else {
                b.addEventListener("click", function () { onChange(targetPage); });
            }
            return b;
        }

        container.appendChild(makeBtn("‹", page - 1, { arrow: true, disabled: page <= 1 }));

        var shown;
        if (totalPages <= 7) {
            shown = [];
            for (var i = 1; i <= totalPages; i++) shown.push(i);
        } else {
            shown = [1];
            var start = Math.max(2, page - 1);
            var end = Math.min(totalPages - 1, page + 1);
            if (start > 2) shown.push("…");
            for (var p = start; p <= end; p++) shown.push(p);
            if (end < totalPages - 1) shown.push("…");
            shown.push(totalPages);
        }

        shown.forEach(function (p) {
            if (p === "…") {
                var span = document.createElement("span");
                span.className = "page-ellipsis";
                span.textContent = "…";
                container.appendChild(span);
            } else {
                container.appendChild(makeBtn(String(p), p, { active: p === page }));
            }
        });

        container.appendChild(makeBtn("›", page + 1, { arrow: true, disabled: page >= totalPages }));
    }

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

    /* ---- filter dropdowns ------------------------------ */

    // Every toolbar <select> is shown as the same dropdown the recorder
    // page uses: a trigger button plus a menu of options with a check
    // mark on the current one. The <select> stays in the page (hidden)
    // as the source of truth, so the filters keep reading .value and
    // listening for "change", and option lists rebuilt in code (the
    // meetings' user and model filters) show up the next time the menu
    // opens. A trigger turns accent-coloured while it is filtering.
    var dropdowns = [];

    function enhanceSelect(select) {
        var label = select.getAttribute("aria-label") || "";

        var wrap = document.createElement("div");
        wrap.className = "dropdown";

        var trigger = document.createElement("button");
        trigger.type = "button";
        trigger.className = "btn-filter dropdown-trigger";
        trigger.setAttribute("aria-haspopup", "menu");
        trigger.setAttribute("aria-expanded", "false");

        var valueEl = document.createElement("span");
        valueEl.className = "dropdown-value";
        trigger.appendChild(valueEl);

        var menu = document.createElement("div");
        menu.className = "dropdown-menu";
        menu.setAttribute("role", "menu");
        if (label) menu.setAttribute("aria-label", label);
        menu.hidden = true;

        select.parentNode.insertBefore(wrap, select);
        wrap.appendChild(select);
        wrap.appendChild(trigger);
        wrap.appendChild(menu);
        select.hidden = true;
        select.tabIndex = -1;

        var dd = { wrap: wrap };

        dd.sync = function () {
            var opt = select.options[select.selectedIndex];
            valueEl.textContent = opt ? opt.textContent : "";
            trigger.setAttribute("aria-label", (label ? label + ": " : "") + valueEl.textContent);
            trigger.classList.toggle("is-filtered", select.selectedIndex > 0);
        };

        dd.isOpen = function () { return !menu.hidden; };

        dd.close = function (returnFocus) {
            if (menu.hidden) return;
            menu.hidden = true;
            trigger.setAttribute("aria-expanded", "false");
            if (returnFocus) trigger.focus();
        };

        dd.open = function () {
            dropdowns.forEach(function (other) { if (other !== dd) other.close(); });

            menu.innerHTML = "";
            Array.prototype.forEach.call(select.options, function (opt) {
                var item = document.createElement("button");
                item.type = "button";
                item.className = "dropdown-item";
                item.setAttribute("role", "menuitemradio");
                item.setAttribute("aria-checked", String(opt.value === select.value));

                var text = document.createElement("span");
                text.className = "dropdown-item-label";
                text.textContent = opt.textContent;
                item.appendChild(text);

                item.addEventListener("click", function () {
                    dd.close(true);
                    if (select.value === opt.value) return;
                    select.value = opt.value;
                    dd.sync();
                    select.dispatchEvent(new Event("change", { bubbles: true }));
                });
                menu.appendChild(item);
            });

            menu.hidden = false;
            trigger.setAttribute("aria-expanded", "true");
            var current = menu.querySelector('[aria-checked="true"]') || menu.firstChild;
            if (current) current.focus();
        };

        trigger.addEventListener("click", function () {
            if (dd.isOpen()) { dd.close(); } else { dd.open(); }
        });

        menu.addEventListener("keydown", function (e) {
            var items = Array.prototype.slice.call(menu.querySelectorAll(".dropdown-item"));
            var i = items.indexOf(document.activeElement);
            var next = null;
            if (e.key === "ArrowDown") next = items[(i + 1) % items.length];
            else if (e.key === "ArrowUp") next = items[(i - 1 + items.length) % items.length];
            else if (e.key === "Home") next = items[0];
            else if (e.key === "End") next = items[items.length - 1];
            else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); dd.close(true); }
            else if (e.key === "Tab") dd.close();
            if (next) { e.preventDefault(); next.focus(); }
        });

        // Option lists rebuilt in code, and values set by code.
        new MutationObserver(dd.sync).observe(select, { childList: true });
        select.addEventListener("change", dd.sync);

        dd.sync();
        dropdowns.push(dd);
        return dd;
    }

    function syncDropdowns() {
        dropdowns.forEach(function (dd) { dd.sync(); });
    }

    document.addEventListener("click", function (e) {
        dropdowns.forEach(function (dd) {
            if (dd.isOpen() && !dd.wrap.contains(e.target)) dd.close();
        });
    });

    /* ---- overview stats ------------------------------ */

    function renderStats() {
        var verified = allUsers.filter(function (u) { return u.emailVerified; }).length;
        statTotalUsers.textContent = allUsers.length;
        statVerifiedUsers.textContent = verified;
        statUnverifiedUsers.textContent = allUsers.length - verified;
        statSummarized.textContent = allMeetings.filter(function (m) {
            return m.hasSummary;
        }).length;
        statMindmapped.textContent = allMeetings.filter(function (m) {
            return m.hasMindmap;
        }).length;
        statSummarizedBy.textContent = modelBreakdown("hasSummary");
        statMindmappedBy.textContent = modelBreakdown("hasMindmap");
    }

    /* "Mistral 128B 17 · Qwen3 27B 3": meetings with that output, per model. */
    function modelBreakdown(field) {
        var counts = {};
        allMeetings.forEach(function (m) {
            (m.models || []).forEach(function (mm) {
                if (mm[field]) counts[mm.key] = (counts[mm.key] || 0) + 1;
            });
        });
        return knownModels().map(function (key) {
            return modelLabel(key) + " " + (counts[key] || 0);
        }).join(" · ");
    }

    /* ---- render table ------------------------------- */

    function renderUserRows() {
        renderStats();

        var q = searchEl.value.trim().toLowerCase();
        var role = roleEl.value;
        var verification = verifiedEl.value;

        var rows = allUsers.filter(function (u) {
            if (role && u.role !== role) return false;
            if (verification === "verified" && !u.emailVerified) return false;
            if (verification === "unverified" && u.emailVerified) return false;
            if (q && ((u.username || "") + " " + u.email).toLowerCase().indexOf(q) === -1) return false;
            return true;
        });

        var totalPages = Math.max(1, Math.ceil(rows.length / USERS_PER_PAGE));
        if (userPage > totalPages) userPage = totalPages;
        if (userPage < 1) userPage = 1;
        var pageRows = rows.slice((userPage - 1) * USERS_PER_PAGE, userPage * USERS_PER_PAGE);

        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="6"><div class="table-empty">' +
                (allUsers.length ? "No users match your filters." : "No users yet. Click “Add user”.") +
                "</div></td></tr>";
        } else {
            tbody.innerHTML = pageRows.map(function (u) {
                var isSelf = u.email === session.email;
                return "<tr>" +
                    "<td>" + esc(u.username) + (isSelf ? ' <span class="hint">(you)</span>' : "") + "</td>" +
                    "<td>" + esc(u.email) + "</td>" +
                    '<td><span class="pill role-' + esc(u.role) + '">' + esc(u.role) + "</span></td>" +
                    "<td>" + fmtDate(u.createdAt) + "</td>" +
                    '<td>' + (u.emailVerified
                        ? '<span class="pill st-verified">verified</span>'
                        : '<span class="pill st-unverified">unverified</span>') +
                    "</td>" +
                    '<td class="cell-actions">' +
                        (u.emailVerified
                            ? (isSelf ? "" : '<button class="row-btn" data-unverify="' + esc(u.email) + '">Unverify</button>')
                            : '<button class="row-btn" data-verify="' + esc(u.email) + '">Verify</button>') +
                        '<button class="row-btn" data-edit="' + esc(u.email) + '">Edit</button>' +
                        (isSelf ? "" : '<button class="row-btn danger" data-del="' + esc(u.email) + '">Delete</button>') +
                    "</td>" +
                "</tr>";
            }).join("");
        }

        rowCount.textContent = rows.length + " of " + allUsers.length + " user" + (allUsers.length === 1 ? "" : "s");

        renderPagination(userPagination, userPage, totalPages, function (p) {
            userPage = p;
            renderUserRows();
        });
    }

    function render() {
        return A.listUsers().then(function (all) {
            allUsers = all;
            renderUserRows();
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
        roleBefore = "user";
        f.role.disabled = false;
        verifyNote.hidden = false;
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
        roleBefore = f.role.value;
        // The server refuses self-demotion; don't offer it.
        f.role.disabled = u.email === session.email;
        verifyNote.hidden = true;
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

    f.role.addEventListener("change", function () {
        var editingUser = editingEmail && allUsers.find(function (x) { return x.email === editingEmail; });
        var alreadyAdmin = editingUser && editingUser.role === "admin";
        if (f.role.value !== "admin" || alreadyAdmin) {
            roleBefore = f.role.value;
            return;
        }
        D.confirm({
            title: "Grant admin privileges?",
            message: "Setting this role to Admin gives this account full control of MeetMind. " +
                "Admin accounts are always verified and skip email verification. An admin can:",
            items: ADMIN_PRIVILEGES,
            confirmText: "Proceed",
            danger: true
        }).then(function (ok) {
            if (ok) {
                roleBefore = "admin";
            } else {
                f.role.value = roleBefore;
            }
        });
    });

    document.getElementById("addUserBtn").addEventListener("click", openAdd);
    document.getElementById("dialogCancel").addEventListener("click", function () { dialog.close(); });

    // row actions (delegated)
    tbody.addEventListener("click", function (e) {
        var editBtn = e.target.closest("[data-edit]");
        if (editBtn) { openEdit(editBtn.getAttribute("data-edit")); return; }

        var verifyBtn = e.target.closest("[data-verify]");
        if (verifyBtn) {
            A.setUserVerified(verifyBtn.getAttribute("data-verify"), true)
                .then(render)
                .catch(function (err) {
                    D.alert({ title: "Couldn't verify user", message: err.message || "Could not verify that user." });
                });
            return;
        }

        var unverifyBtn = e.target.closest("[data-unverify]");
        if (unverifyBtn) {
            var target = unverifyBtn.getAttribute("data-unverify");
            var targetUser = allUsers.find(function (x) { return x.email === target; });
            var confirmOpts = (targetUser && targetUser.role === "admin") ? {
                title: "Unverify an admin?",
                message: target + " is an admin. If you proceed:",
                items: [
                    "They are signed out everywhere, immediately",
                    "They can't sign in at all, including to this dashboard, until another admin verifies them",
                    "They can't fix it themselves: emailed verification codes are disabled for their account",
                    "They keep the admin role, so verifying them again restores full admin access",
                    "To take away admin access for good, edit them and change their role to User instead"
                ],
                confirmText: "Unverify admin",
                danger: true
            } : {
                title: "Unverify this user?",
                message: target + " will be signed out and can't sign in again until an admin verifies them.",
                confirmText: "Unverify",
                danger: true
            };
            D.confirm(confirmOpts).then(function (ok) {
                if (!ok) return;
                A.setUserVerified(target, false)
                    .then(render)
                    .catch(function (err) {
                        D.alert({ title: "Couldn't unverify user", message: err.message || "Could not unverify that user." });
                    });
            });
            return;
        }

        var delBtn = e.target.closest("[data-del]");
        if (delBtn) {
            var email = delBtn.getAttribute("data-del");
            D.confirm({
                title: "Delete this user?",
                message: email + " and all of their meetings will be permanently removed. This cannot be undone.",
                confirmText: "Delete user",
                danger: true
            }).then(function (ok) {
                if (!ok) return;
                A.deleteUser(email).then(function (deleted) {
                    if (!deleted) D.alert({ title: "Couldn't delete user", message: "Could not delete " + email + ". Please try again." });
                    return render();
                });
            });
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
            role: f.role.value
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
            payload = { username: data.username, email: data.email, role: data.role };
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

    searchEl.addEventListener("input", function () { userPage = 1; renderUserRows(); });
    roleEl.addEventListener("change", function () { userPage = 1; renderUserRows(); });
    verifiedEl.addEventListener("change", function () { userPage = 1; renderUserRows(); });

    enhanceSelect(roleEl);
    enhanceSelect(verifiedEl);

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
    var mtUserFilter = document.getElementById("meetingUserFilter");
    var mtStatusFilter = document.getElementById("meetingStatusFilter");
    var mtModelFilter = document.getElementById("meetingModelFilter");
    var mtDateFrom = document.getElementById("meetingDateFrom");
    var mtDateTo = document.getElementById("meetingDateTo");
    var mtFilterReset = document.getElementById("meetingFilterReset");

    var mtDialog = document.getElementById("meetingDialog");
    var mtTitle = document.getElementById("meetingDialogTitle");
    var mtMeta = document.getElementById("meetingDialogMeta");
    var mtSummaryPane = document.getElementById("meetingSummaryPane");
    var mtMindmapPane = document.getElementById("meetingMindmapPane");
    var mtTranscriptPane = document.getElementById("meetingTranscriptPane");

    var meetingPagination = document.getElementById("meetingPagination");
    var meetingPage = 1;
    var MEETINGS_PER_PAGE = 10;

    var allMeetings = [];

    // [{key, label, modelId}] from GET /api/models (backend LLM_MODELS).
    var modelCatalog = [];

    // Model-filter value: meetings with results from every model.
    var EVERY_MODEL = "__every__";

    /* Model keys in display order: the catalog's, then any model that
       only appears in saved meetings (no longer offered). */
    function knownModels() {
        var keys = modelCatalog.map(function (mm) { return mm.key; });
        allMeetings.forEach(function (m) {
            (m.models || []).forEach(function (mm) {
                if (keys.indexOf(mm.key) === -1) keys.push(mm.key);
            });
        });
        return keys;
    }

    function modelLabel(key) {
        var found = modelCatalog.filter(function (mm) { return mm.key === key; })[0];
        if (found) return found.label || key;
        for (var i = 0; i < allMeetings.length; i++) {
            var tag = (allMeetings[i].models || []).filter(function (mm) { return mm.key === key; })[0];
            if (tag) return tag.label || key;
        }
        return key;
    }

    function populateMeetingModelFilter() {
        var current = mtModelFilter.value;
        var keys = knownModels();
        var options = [{ value: "", label: "Any model" }].concat(keys.map(function (key) {
            return { value: key, label: modelLabel(key) };
        }));
        if (keys.length > 1) {
            options.push({
                value: EVERY_MODEL,
                label: keys.length === 2 ? "Both models" : "All " + keys.length + " models"
            });
        }
        mtModelFilter.innerHTML = options.map(function (o) {
            return '<option value="' + esc(o.value) + '">' + esc(o.label) + "</option>";
        }).join("");
        if (options.some(function (o) { return o.value === current; })) mtModelFilter.value = current;
    }

    function loadModelCatalog() {
        return api("/api/models").then(function (list) {
            modelCatalog = Array.isArray(list) ? list : [];
        }).catch(function () {
            modelCatalog = [];
        }).then(function () {
            populateMeetingModelFilter();
            renderStats();
        });
    }

    function fmtDateTime(iso) {
        var d = new Date(iso);
        if (isNaN(d)) return "—";
        return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) +
            ", " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    }

    /* Recording length down to the second: "45 sec", "5 min 43 sec",
       "1 h 12 min 5 sec". A unit that is zero is left out ("38 min").
       Empty for meetings saved before durations were recorded. */
    function fmtDuration(seconds) {
        var total = Math.round(Number(seconds));
        if (!total || total < 0) return "";
        var h = Math.floor(total / 3600);
        var m = Math.floor((total % 3600) / 60);
        var s = total % 60;
        var parts = [];
        if (h) parts.push(h + " h");
        if (m) parts.push(m + " min");
        if (s) parts.push(s + " sec");
        return parts.join(" ");
    }

    function api(path) {
        return fetch(path, { credentials: "same-origin" }).then(function (res) {
            if (!res.ok) throw new Error("Request failed.");
            return res.json();
        });
    }

    function populateMeetingUserFilter() {
        var current = mtUserFilter.value;
        var seen = {};
        var options = [];

        allMeetings.forEach(function (m) {
            var key = m.email || m.username;
            if (key && !seen[key]) {
                seen[key] = true;
                options.push({ value: key, label: m.username || m.email });
            }
        });
        options.sort(function (a, b) { return a.label.localeCompare(b.label); });

        mtUserFilter.innerHTML = '<option value="">All users</option>' +
            options.map(function (o) {
                return '<option value="' + esc(o.value) + '">' + esc(o.label) + "</option>";
            }).join("");

        if (current && seen[current]) mtUserFilter.value = current;
    }

    /* One pill per model with results for the meeting (the `models`
       field of /api/meetings), saying which outputs it has when it
       only has one. Same tags as the history drawer on the app page. */
    function modelTagsHtml(models) {
        if (!models || !models.length) return '<span class="hint">—</span>';
        return models.map(function (mm) {
            var note = "";
            if (mm.hasSummary && !mm.hasMindmap) note = "summary only";
            if (mm.hasMindmap && !mm.hasSummary) note = "mind map only";
            return '<span class="pill model-pill" title="' +
                esc((mm.label || mm.key) + ": " + (note || "summary and mind map")) + '">' +
                esc(mm.label || mm.key) +
                (note ? ' <span class="pill-note">· ' + note + "</span>" : "") +
                "</span>";
        }).join("");
    }

    function renderMeetings() {
        var q = mtSearch.value.trim().toLowerCase();
        var userVal = mtUserFilter.value;
        var statusVal = mtStatusFilter.value;
        var modelVal = mtModelFilter.value;
        var everyKey = knownModels();
        var fromVal = mtDateFrom.value;
        var toVal = mtDateTo.value;

        var rows = allMeetings.filter(function (m) {
            if (q && ((m.title || "") + " " + (m.username || "") + " " + (m.email || ""))
                    .toLowerCase().indexOf(q) === -1) return false;

            if (userVal && (m.email || m.username) !== userVal) return false;

            if (statusVal === "summarized" && !m.hasSummary) return false;
            if (statusVal === "transcript" && m.hasSummary) return false;

            if (modelVal) {
                var has = (m.models || []).map(function (mm) { return mm.key; });
                if (modelVal === EVERY_MODEL) {
                    if (!everyKey.every(function (k) { return has.indexOf(k) !== -1; })) return false;
                } else if (has.indexOf(modelVal) === -1) {
                    return false;
                }
            }

            if (fromVal || toVal) {
                var d = new Date(m.createdAt);
                if (isNaN(d)) return false;
                if (fromVal && d < new Date(fromVal + "T00:00:00")) return false;
                if (toVal && d > new Date(toVal + "T23:59:59")) return false;
            }

            return true;
        });

        var totalPages = Math.max(1, Math.ceil(rows.length / MEETINGS_PER_PAGE));
        if (meetingPage > totalPages) meetingPage = totalPages;
        if (meetingPage < 1) meetingPage = 1;
        var pageRows = rows.slice((meetingPage - 1) * MEETINGS_PER_PAGE, meetingPage * MEETINGS_PER_PAGE);

        if (!rows.length) {
            mtBody.innerHTML = '<tr><td colspan="6"><div class="table-empty">' +
                (allMeetings.length
                    ? "No meetings match your filters."
                    : "No meetings have been recorded yet.") +
                "</div></td></tr>";
        } else {
            mtBody.innerHTML = pageRows.map(function (m) {
                return "<tr>" +
                    "<td>" + esc(m.title || "Untitled meeting") + "</td>" +
                    "<td>" + esc(m.username || "") +
                        ' <span class="hint">' + esc(m.email || "") + "</span></td>" +
                    "<td>" + fmtDateTime(m.createdAt) + "</td>" +
                    "<td>" + (fmtDuration(m.durationSeconds) || '<span class="hint">—</span>') + "</td>" +
                    '<td><div class="model-tags">' + modelTagsHtml(m.models) + "</div></td>" +
                    '<td class="cell-actions">' +
                        '<button class="row-btn" data-view="' + esc(m.id) + '">View</button>' +
                    "</td>" +
                "</tr>";
            }).join("");
        }

        mtCount.textContent = rows.length + " of " + allMeetings.length +
            " meeting" + (allMeetings.length === 1 ? "" : "s");

        renderPagination(meetingPagination, meetingPage, totalPages, function (p) {
            meetingPage = p;
            renderMeetings();
        });
    }

    function loadMeetings() {
        return api("/api/meetings?scope=all").then(function (meetings) {
            allMeetings = meetings;
            populateMeetingUserFilter();
            populateMeetingModelFilter();
            renderMeetings();
            renderStats();
        }).catch(function () {
            mtBody.innerHTML = '<tr><td colspan="6"><div class="table-empty">' +
                "Could not load meetings.</div></td></tr>";
        });
    }

    /* ---- viewer dialog -----------------------------
       Read-only view of one meeting, per model: a switch picks the
       model, and the Summary / Mind Map tabs show that model's results
       laid out like the recorder page (same sections, labels and icons;
       the same mind-map tree). The transcript is shared by every model.
    -------------------------------------------------- */

    var mtModelSwitch = document.getElementById("meetingModelSwitch");
    var mtExpandBtn = document.getElementById("meetingExpandBtn");
    var mtTranscriptText = document.getElementById("meetingTranscriptText");
    var mtTranscriptSearch = document.getElementById("meetingTranscriptSearch");
    var mtSearchPrev = document.getElementById("meetingSearchPrev");
    var mtSearchNext = document.getElementById("meetingSearchNext");
    var mtSearchCount = document.getElementById("meetingSearchCount");

    var viewedMeeting = null;
    var viewedModel = null;
    var viewedTab = "summary";

    function noneHtml(text) {
        return '<div class="meeting-none">' + esc(text) + "</div>";
    }

    function sectionHtml(icon, heading, body) {
        return '<div class="result-section">' +
            '<div class="label"><span class="section-icon section-icon--' + icon + '" aria-hidden="true"></span>' +
            esc(heading) + "</div>" + body + "</div>";
    }

    function textList(items) {
        return (Array.isArray(items) ? items : []).filter(function (x) {
            return x != null && String(x).trim();
        });
    }

    function renderSummaryPane(summary, label) {
        if (!summary) {
            mtSummaryPane.innerHTML = noneHtml(label + " didn't generate a summary for this meeting.");
            return;
        }

        var tasks = (Array.isArray(summary.tasks_assigned) ? summary.tasks_assigned : [])
            .filter(function (t) { return t && (t.task || typeof t === "string"); });
        var decisions = textList(summary.decision_points);
        var objections = textList(summary.objections);
        var actions = textList(summary.action_items);

        var html = "";

        html += sectionHtml("title", "Title",
            '<div class="title-result">' + esc(summary.title || "Untitled Meeting") + "</div>");

        html += sectionHtml("summary", "Meeting summary",
            '<p class="summary">' + esc(summary.meeting_summary || "No summary available.") + "</p>");

        html += sectionHtml("objective", "Objective",
            '<p class="summary">' + esc(summary.objective || "Objective could not be generated.") + "</p>");

        html += sectionHtml("tasks", "Tasks", tasks.length
            ? tasks.map(function (t) {
                if (typeof t === "string") return '<div class="item"><strong>' + esc(t) + "</strong></div>";
                return '<div class="item"><strong>' + esc(t.task) + "</strong>" +
                    (t.assignee && String(t.assignee).trim()
                        ? '<div class="meta">Assignee: ' + esc(t.assignee) + "</div>" : "") +
                    (t.deadline && String(t.deadline).trim()
                        ? '<div class="meta">Deadline: ' + esc(t.deadline) + "</div>" : "") +
                    "</div>";
            }).join("")
            : '<div class="meta">No tasks identified.</div>');

        html += sectionHtml("decisions", "Decisions", decisions.length
            ? decisions.map(function (d) { return '<div class="decision">' + esc(d) + "</div>"; }).join("")
            : '<div class="meta">No decisions identified.</div>');

        // Like the recorder page, these two only appear when present.
        if (objections.length) {
            html += sectionHtml("objections", "Objections", objections.map(function (o) {
                return '<div class="item objection">' + esc(o) + "</div>";
            }).join(""));
        }
        if (actions.length) {
            html += sectionHtml("actions", "Action items", actions.map(function (a) {
                return '<div class="item action">' + esc(a) + "</div>";
            }).join(""));
        }

        mtSummaryPane.innerHTML = '<div class="intelligence">' + html + "</div>";
    }

    /* Same tree markup as the recorder page's mind map, minus editing. */
    function buildMindmapNode(node, isRoot) {
        if (!node || !node.title) return null;

        var wrap = document.createElement("div");
        wrap.className = isRoot ? "mindmap-root" : "mindmap-branch";

        var label = document.createElement("div");
        label.className = isRoot ? "mindmap-root-title" : "mindmap-node";
        label.textContent = node.title;
        wrap.appendChild(label);

        var children = Array.isArray(node.children) ? node.children : [];
        if (children.length) {
            var box = document.createElement("div");
            box.className = isRoot ? "mindmap-children" : "mindmap-node-children";
            children.forEach(function (child) {
                var built = buildMindmapNode(child, false);
                if (built) box.appendChild(built);
            });
            wrap.appendChild(box);
        }
        return wrap;
    }

    function renderMindmapPane(mindmap, label) {
        mtMindmapPane.innerHTML = "";

        var root = mindmap && buildMindmapNode(mindmap, true);
        if (!root) {
            mtMindmapPane.innerHTML = noneHtml(label + " didn't generate a mind map for this meeting.");
            return;
        }

        var container = document.createElement("div");
        container.className = "mindmap-container";
        var top = Array.isArray(mindmap.children) ? mindmap.children.length : 0;
        container.style.setProperty("--mindmap-columns", Math.max(1, Math.min(top || 1, 5)));
        container.appendChild(root);
        mtMindmapPane.appendChild(container);
    }

    /* The tree is wider than the pane: open it scrolled to its centre
       (only possible once the pane is visible and laid out). */
    function centerMindmap() {
        var container = mtMindmapPane.querySelector(".mindmap-container");
        if (!container || mtMindmapPane.hidden) return;
        requestAnimationFrame(function () {
            container.scrollLeft = (container.scrollWidth - container.clientWidth) / 2;
        });
    }

    function renderModelSwitch() {
        var models = viewedMeeting.models || [];
        mtModelSwitch.innerHTML = "";
        mtModelSwitch.hidden = !models.length;

        models.forEach(function (mm) {
            var b = document.createElement("button");
            b.type = "button";
            b.className = "model-switch-btn";
            b.setAttribute("aria-pressed", String(mm.key === viewedModel));

            var note = "";
            if (mm.hasSummary && !mm.hasMindmap) note = "summary only";
            if (mm.hasMindmap && !mm.hasSummary) note = "mind map only";

            var name = document.createElement("span");
            name.textContent = mm.label || mm.key;
            b.appendChild(name);
            if (note) {
                var small = document.createElement("span");
                small.className = "model-switch-note";
                small.textContent = note;
                b.appendChild(small);
            }

            b.addEventListener("click", function () { selectModel(mm.key); });
            mtModelSwitch.appendChild(b);
        });
    }

    function selectModel(key) {
        viewedModel = key;
        var results = (viewedMeeting && viewedMeeting.results) || {};
        var result = results[key] || {};
        var info = (viewedMeeting.models || []).filter(function (mm) { return mm.key === key; })[0];
        var label = info ? (info.label || info.key) : "This model";

        renderModelSwitch();
        renderSummaryPane(result.summary || null, label);
        renderMindmapPane(result.mindmap || null, label);
        centerMindmap();
    }

    function showTab(which) {
        viewedTab = which;
        mtSummaryPane.hidden = which !== "summary";
        mtMindmapPane.hidden = which !== "mindmap";
        mtTranscriptPane.hidden = which !== "transcript";
        mtDialog.querySelectorAll(".meeting-tab").forEach(function (t) {
            var active = t.getAttribute("data-tab") === which;
            t.classList.toggle("is-active", active);
            t.setAttribute("aria-selected", String(active));
        });
        // The transcript belongs to the meeting, not to a model.
        mtModelSwitch.classList.toggle("is-muted", which === "transcript");
        if (which === "mindmap") centerMindmap();
    }

    mtDialog.querySelectorAll(".meeting-tab").forEach(function (tab) {
        tab.addEventListener("click", function () {
            showTab(tab.getAttribute("data-tab"));
        });
    });

    /* ---- full view ---- */

    function setExpanded(expanded) {
        mtDialog.classList.toggle("is-expanded", expanded);
        mtExpandBtn.setAttribute("aria-pressed", String(expanded));
        mtExpandBtn.setAttribute("aria-label", expanded ? "Exit full view" : "Expand the viewer");
        mtExpandBtn.title = expanded ? "Exit full view" : "Expand";
        centerMindmap();
    }

    mtExpandBtn.addEventListener("click", function () {
        setExpanded(!mtDialog.classList.contains("is-expanded"));
    });

    /* ---- transcript search (same behaviour as the recorder page) ---- */

    var tsMatches = [];
    var tsIndex = -1;

    function updateSearchCount() {
        var count = tsMatches.length;
        if (!mtTranscriptSearch.value.trim()) mtSearchCount.textContent = "0 matches";
        else if (!count) mtSearchCount.textContent = "No matches";
        else mtSearchCount.textContent = (tsIndex + 1) + " / " + count;
        mtSearchPrev.disabled = !count;
        mtSearchNext.disabled = !count;
    }

    function setSearchMatch(i) {
        if (!tsMatches.length) { tsIndex = -1; updateSearchCount(); return; }
        tsIndex = (i + tsMatches.length) % tsMatches.length;
        tsMatches.forEach(function (mark, n) { mark.classList.toggle("current", n === tsIndex); });
        tsMatches[tsIndex].scrollIntoView({ block: "center" });
        updateSearchCount();
    }

    function renderTranscript() {
        var text = (viewedMeeting && viewedMeeting.transcript) || "";
        var query = mtTranscriptSearch.value.trim();
        tsMatches = [];
        tsIndex = -1;
        mtTranscriptText.textContent = "";

        if (!text) {
            mtTranscriptText.textContent = "No transcript was stored.";
            updateSearchCount();
            return;
        }
        if (!query) {
            mtTranscriptText.textContent = text;
            updateSearchCount();
            return;
        }

        var re = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
        var last = 0;
        var m;
        while ((m = re.exec(text)) !== null) {
            if (m.index > last) mtTranscriptText.appendChild(document.createTextNode(text.slice(last, m.index)));
            var mark = document.createElement("mark");
            mark.className = "transcript-match";
            mark.textContent = m[0];
            mtTranscriptText.appendChild(mark);
            tsMatches.push(mark);
            last = m.index + m[0].length;
            if (!m[0].length) re.lastIndex++;
        }
        if (last < text.length) mtTranscriptText.appendChild(document.createTextNode(text.slice(last)));

        if (tsMatches.length) setSearchMatch(0); else updateSearchCount();
    }

    mtTranscriptSearch.addEventListener("input", renderTranscript);
    mtTranscriptSearch.addEventListener("keydown", function (e) {
        // Enter would otherwise submit (and close) the dialog's form.
        if (e.key === "Enter") {
            e.preventDefault();
            if (tsMatches.length) setSearchMatch(tsIndex + (e.shiftKey ? -1 : 1));
        }
    });
    mtSearchPrev.addEventListener("click", function () { setSearchMatch(tsIndex - 1); });
    mtSearchNext.addEventListener("click", function () { setSearchMatch(tsIndex + 1); });

    /* ---- open ---- */

    function openMeeting(id) {
        api("/api/meetings/" + encodeURIComponent(id)).then(function (m) {
            viewedMeeting = m;

            mtTitle.textContent = m.title || "Untitled meeting";
            var length = fmtDuration(m.durationSeconds);
            mtMeta.textContent = (m.username || "") + " · " + (m.email || "") +
                " · " + fmtDateTime(m.createdAt) + (length ? " · " + length : "");

            mtTranscriptSearch.value = "";
            renderTranscript();

            var first = (m.models || [])[0];
            if (first) {
                selectModel(first.key);
            } else {
                viewedModel = null;
                renderModelSwitch();
                mtSummaryPane.innerHTML = noneHtml("No summary was generated for this meeting.");
                mtMindmapPane.innerHTML = noneHtml("No mind map was generated for this meeting.");
            }

            setExpanded(false);
            showTab("summary");
            mtDialog.showModal();

        }).catch(function () {
            D.alert({ title: "Couldn't open meeting", message: "Could not open that meeting. Please try again." });
        });
    }

    mtDialog.addEventListener("close", function () {
        setExpanded(false);
    });

    mtBody.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-view]");
        if (btn) openMeeting(btn.getAttribute("data-view"));
    });

    document.getElementById("meetingDialogClose")
        .addEventListener("click", function () { mtDialog.close(); });

    mtDialog.addEventListener("click", function (e) {
        if (e.target === mtDialog) mtDialog.close();
    });

    function onMeetingFilterChange() { meetingPage = 1; renderMeetings(); }

    mtSearch.addEventListener("input", onMeetingFilterChange);
    mtUserFilter.addEventListener("change", onMeetingFilterChange);
    mtStatusFilter.addEventListener("change", onMeetingFilterChange);
    mtModelFilter.addEventListener("change", onMeetingFilterChange);
    mtDateFrom.addEventListener("change", onMeetingFilterChange);
    mtDateTo.addEventListener("change", onMeetingFilterChange);

    mtFilterReset.addEventListener("click", function () {
        mtSearch.value = "";
        mtUserFilter.value = "";
        mtStatusFilter.value = "";
        mtModelFilter.value = "";
        mtDateFrom.value = "";
        mtDateTo.value = "";
        meetingPage = 1;
        syncDropdowns();
        renderMeetings();
    });

    enhanceSelect(mtUserFilter);
    enhanceSelect(mtStatusFilter);
    enhanceSelect(mtModelFilter);

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
            loadMeetings().then(loadModelCatalog);
        });
    }

})();
