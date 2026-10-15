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
    var statConsultations = document.getElementById("statConsultations");
    var statConsultationsBy = document.getElementById("statConsultationsBy");

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
        "View every user's meetings, consultations and interviews, with their recordings and reports"
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
        statConsultations.textContent = consultsLoaded ? allConsults.length : "—";
        var finals = allConsults.filter(function (c) { return c.prescriptionStatus === "final"; }).length;
        var drafts = allConsults.filter(function (c) { return c.prescriptionStatus === "draft"; }).length;
        statConsultationsBy.textContent = allConsults.length
            ? finals + " final · " + drafts + " draft prescription" + (drafts === 1 ? "" : "s")
            : "";
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
    var mtAudioFilter = document.getElementById("meetingAudioFilter");
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

    var AUDIO_PILL = '<span class="pill audio-pill" title="The recording is saved and can be played back">Recording</span>';

    /* One pill per model with results for the meeting (the `models`
       field of /api/meetings), saying which outputs it has when it
       only has one. Same tags as the history drawer on the app page. */
    function modelTagsHtml(models) {
        if (!models || !models.length) return "";
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
        var audioVal = mtAudioFilter.value;
        var everyKey = knownModels();
        var fromVal = mtDateFrom.value;
        var toVal = mtDateTo.value;

        var rows = allMeetings.filter(function (m) {
            if (q && ((m.title || "") + " " + (m.username || "") + " " + (m.email || ""))
                    .toLowerCase().indexOf(q) === -1) return false;

            if (userVal && (m.email || m.username) !== userVal) return false;

            if (statusVal === "summarized" && !m.hasSummary) return false;
            if (statusVal === "transcript" && m.hasSummary) return false;

            if (audioVal === "with" && !m.hasAudio) return false;
            if (audioVal === "without" && m.hasAudio) return false;

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
                    '<td><div class="model-tags">' + (m.hasAudio ? AUDIO_PILL : "") +
                        modelTagsHtml(m.models) + "</div></td>" +
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

    /* ---- recording players (meeting + consultation viewers) ---- */

    function makePlayer(slotId, teal) {
        var slot = document.getElementById(slotId);
        var player = window.MeetMindAudioPlayer
            ? window.MeetMindAudioPlayer.create({ teal: teal })
            : { el: document.createElement("div"), load: function () {}, clear: function () {} };
        slot.appendChild(player.el);
        return player;
    }

    function showPlayer(player, audio, title, downloadName) {
        if (!audio || !audio.url) {
            player.clear();
            return;
        }
        var meta = [
            audio.mimeType === "audio/mpeg" ? "MP3" : String(audio.mimeType || "").replace(/^audio\//, "").toUpperCase(),
            window.MeetMindAudioPlayer ? window.MeetMindAudioPlayer.formatBytes(audio.sizeBytes) : "",
            audio.source === "upload"
                ? "Uploaded" + (audio.originalFilename ? " · " + audio.originalFilename : "")
                : "Live recording"
        ].filter(Boolean).join(" · ");
        player.load(audio.url, { title: title, meta: meta, downloadName: downloadName });
    }

    var mtPlayer = makePlayer("meetingPlayerSlot", false);

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

    /* ---- transcript search (same behaviour as the recorder page) ----
       Shared by the meeting and consultation viewers. */

    function makeTranscriptSearch(o) {
        var matches = [];
        var index = -1;

        function updateCount() {
            var count = matches.length;
            if (!o.input.value.trim()) o.count.textContent = "0 matches";
            else if (!count) o.count.textContent = "No matches";
            else o.count.textContent = (index + 1) + " / " + count;
            o.prev.disabled = !count;
            o.next.disabled = !count;
        }

        function setMatch(i) {
            if (!matches.length) { index = -1; updateCount(); return; }
            index = (i + matches.length) % matches.length;
            matches.forEach(function (mark, n) { mark.classList.toggle("current", n === index); });
            matches[index].scrollIntoView({ block: "center" });
            updateCount();
        }

        function render() {
            var text = o.text();
            var query = o.input.value.trim();
            matches = [];
            index = -1;
            o.pre.textContent = "";

            if (!text) {
                o.pre.textContent = "No transcript was stored.";
                updateCount();
                return;
            }
            if (!query) {
                o.pre.textContent = text;
                updateCount();
                return;
            }

            var re = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
            var last = 0;
            var m;
            while ((m = re.exec(text)) !== null) {
                if (m.index > last) o.pre.appendChild(document.createTextNode(text.slice(last, m.index)));
                var mark = document.createElement("mark");
                mark.className = "transcript-match";
                mark.textContent = m[0];
                o.pre.appendChild(mark);
                matches.push(mark);
                last = m.index + m[0].length;
                if (!m[0].length) re.lastIndex++;
            }
            if (last < text.length) o.pre.appendChild(document.createTextNode(text.slice(last)));

            if (matches.length) setMatch(0); else updateCount();
        }

        o.input.addEventListener("input", render);
        o.input.addEventListener("keydown", function (e) {
            // Enter would otherwise submit (and close) the dialog's form.
            if (e.key === "Enter") {
                e.preventDefault();
                if (matches.length) setMatch(index + (e.shiftKey ? -1 : 1));
            }
        });
        o.prev.addEventListener("click", function () { setMatch(index - 1); });
        o.next.addEventListener("click", function () { setMatch(index + 1); });

        return {
            render: render,
            reset: function () { o.input.value = ""; render(); }
        };
    }

    var mtTranscript = makeTranscriptSearch({
        input: mtTranscriptSearch,
        prev: mtSearchPrev,
        next: mtSearchNext,
        count: mtSearchCount,
        pre: mtTranscriptText,
        text: function () { return (viewedMeeting && viewedMeeting.transcript) || ""; }
    });

    /* ---- open ---- */

    function openMeeting(id) {
        api("/api/meetings/" + encodeURIComponent(id)).then(function (m) {
            viewedMeeting = m;

            mtTitle.textContent = m.title || "Untitled meeting";
            var length = fmtDuration(m.durationSeconds);
            mtMeta.textContent = (m.username || "") + " · " + (m.email || "") +
                " · " + fmtDateTime(m.createdAt) + (length ? " · " + length : "");

            mtTranscript.reset();

            var first = (m.models || [])[0];
            showPlayer(mtPlayer, m.hasAudio && m.audio, "Meeting recording", "meeting_" + m.id);

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
        mtPlayer.clear();
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
    mtAudioFilter.addEventListener("change", onMeetingFilterChange);
    mtDateFrom.addEventListener("change", onMeetingFilterChange);
    mtDateTo.addEventListener("change", onMeetingFilterChange);

    mtFilterReset.addEventListener("click", function () {
        mtSearch.value = "";
        mtUserFilter.value = "";
        mtStatusFilter.value = "";
        mtModelFilter.value = "";
        mtAudioFilter.value = "";
        mtDateFrom.value = "";
        mtDateTo.value = "";
        meetingPage = 1;
        syncDropdowns();
        renderMeetings();
    });

    enhanceSelect(mtUserFilter);
    enhanceSelect(mtStatusFilter);
    enhanceSelect(mtModelFilter);
    enhanceSelect(mtAudioFilter);

    /* ============================================================
       DOCTOR CONSULTATIONS — every user's Doctor–Patient sessions
       ------------------------------------------------------------
       Read-only, like meetings. A consultation is shown with its
       recording, its prescription on that doctor's letterhead
       (assets/prescription.js — the same page the doctor downloads)
       and its transcript. /api/doctor/consultations?scope=all.
    ============================================================ */

    var csBody = document.getElementById("consultRows");
    var csSearch = document.getElementById("consultSearch");
    var csCount = document.getElementById("consultCount");
    var csUserFilter = document.getElementById("consultUserFilter");
    var csStatusFilter = document.getElementById("consultStatusFilter");
    var csAudioFilter = document.getElementById("consultAudioFilter");
    var csDateFrom = document.getElementById("consultDateFrom");
    var csDateTo = document.getElementById("consultDateTo");
    var csFilterReset = document.getElementById("consultFilterReset");
    var csPagination = document.getElementById("consultPagination");
    var consultPage = 1;
    var CONSULTS_PER_PAGE = 10;

    var allConsults = [];
    var consultsLoaded = false;

    function consultName(c) {
        return c.patientName || c.title || "Untitled consultation";
    }

    function rxPill(status) {
        if (status === "final") return '<span class="pill rx-pill rx-final" title="Prescription downloaded by the doctor">Prescription · final</span>';
        if (status === "draft") return '<span class="pill rx-pill rx-draft" title="AI draft, not downloaded yet">Prescription · draft</span>';
        return '<span class="pill rx-pill rx-none">No prescription</span>';
    }

    function populateConsultUserFilter() {
        var current = csUserFilter.value;
        var seen = {};
        var options = [];
        allConsults.forEach(function (c) {
            var key = c.email || c.username;
            if (key && !seen[key]) {
                seen[key] = true;
                options.push({ value: key, label: c.username || c.email });
            }
        });
        options.sort(function (a, b) { return a.label.localeCompare(b.label); });
        csUserFilter.innerHTML = '<option value="">All doctors</option>' +
            options.map(function (o) {
                return '<option value="' + esc(o.value) + '">' + esc(o.label) + "</option>";
            }).join("");
        if (current && seen[current]) csUserFilter.value = current;
    }

    function renderConsults() {
        var q = csSearch.value.trim().toLowerCase();
        var userVal = csUserFilter.value;
        var statusVal = csStatusFilter.value;
        var audioVal = csAudioFilter.value;
        var fromVal = csDateFrom.value;
        var toVal = csDateTo.value;

        var rows = allConsults.filter(function (c) {
            if (q && [consultName(c), c.diagnosis, c.username, c.email].join(" ")
                    .toLowerCase().indexOf(q) === -1) return false;
            if (userVal && (c.email || c.username) !== userVal) return false;
            if (statusVal === "none" ? c.prescriptionStatus : (statusVal && c.prescriptionStatus !== statusVal)) return false;
            if (audioVal === "with" && !c.hasAudio) return false;
            if (audioVal === "without" && c.hasAudio) return false;
            if (fromVal || toVal) {
                var d = new Date(c.createdAt);
                if (isNaN(d)) return false;
                if (fromVal && d < new Date(fromVal + "T00:00:00")) return false;
                if (toVal && d > new Date(toVal + "T23:59:59")) return false;
            }
            return true;
        });

        var totalPages = Math.max(1, Math.ceil(rows.length / CONSULTS_PER_PAGE));
        if (consultPage > totalPages) consultPage = totalPages;
        if (consultPage < 1) consultPage = 1;
        var pageRows = rows.slice((consultPage - 1) * CONSULTS_PER_PAGE, consultPage * CONSULTS_PER_PAGE);

        if (!rows.length) {
            csBody.innerHTML = '<tr><td colspan="6"><div class="table-empty">' +
                (allConsults.length
                    ? "No consultations match your filters."
                    : "No consultations have been recorded yet.") +
                "</div></td></tr>";
        } else {
            csBody.innerHTML = pageRows.map(function (c) {
                return "<tr>" +
                    "<td><strong>" + esc(consultName(c)) + "</strong>" +
                        (c.ageSex ? ' <span class="hint">' + esc(c.ageSex) + "</span>" : "") +
                        (c.diagnosis ? '<div class="cell-sub">' + esc(c.diagnosis) + "</div>" : "") + "</td>" +
                    "<td>" + esc(c.username || "") +
                        ' <span class="hint">' + esc(c.email || "") + "</span></td>" +
                    "<td>" + fmtDateTime(c.createdAt) + "</td>" +
                    "<td>" + (fmtDuration(c.durationSeconds) || '<span class="hint">—</span>') + "</td>" +
                    '<td><div class="model-tags">' + (c.hasAudio ? AUDIO_PILL : "") +
                        rxPill(c.prescriptionStatus) + "</div></td>" +
                    '<td class="cell-actions">' +
                        '<button class="row-btn" data-view-consult="' + esc(c.id) + '">View</button>' +
                    "</td>" +
                "</tr>";
            }).join("");
        }

        csCount.textContent = rows.length + " of " + allConsults.length +
            " consultation" + (allConsults.length === 1 ? "" : "s");

        renderPagination(csPagination, consultPage, totalPages, function (p) {
            consultPage = p;
            renderConsults();
        });
    }

    function loadConsults() {
        return api("/api/doctor/consultations?scope=all").then(function (consults) {
            allConsults = consults;
            consultsLoaded = true;
            populateConsultUserFilter();
            syncDropdowns();
            renderConsults();
            renderStats();
        }).catch(function () {
            csBody.innerHTML = '<tr><td colspan="6"><div class="table-empty">' +
                "Could not load consultations.</div></td></tr>";
        });
    }

    function onConsultFilterChange() { consultPage = 1; renderConsults(); }

    csSearch.addEventListener("input", onConsultFilterChange);
    csUserFilter.addEventListener("change", onConsultFilterChange);
    csStatusFilter.addEventListener("change", onConsultFilterChange);
    csAudioFilter.addEventListener("change", onConsultFilterChange);
    csDateFrom.addEventListener("change", onConsultFilterChange);
    csDateTo.addEventListener("change", onConsultFilterChange);

    csFilterReset.addEventListener("click", function () {
        csSearch.value = "";
        csUserFilter.value = "";
        csStatusFilter.value = "";
        csAudioFilter.value = "";
        csDateFrom.value = "";
        csDateTo.value = "";
        consultPage = 1;
        syncDropdowns();
        renderConsults();
    });

    enhanceSelect(csUserFilter);
    enhanceSelect(csStatusFilter);
    enhanceSelect(csAudioFilter);

    /* ---- consultation viewer ---- */

    var csDialog = document.getElementById("consultDialog");
    var csTitle = document.getElementById("consultDialogTitle");
    var csMeta = document.getElementById("consultDialogMeta");
    var csRxPane = document.getElementById("consultRxPane");
    var csTranscriptPane = document.getElementById("consultTranscriptPane");
    var csExpandBtn = document.getElementById("consultExpandBtn");
    var csDownloadBtn = document.getElementById("consultDownloadBtn");
    var csPlayer = makePlayer("consultPlayerSlot", true);
    var csSheet = null;
    var viewedConsult = null;

    var csTranscript = makeTranscriptSearch({
        input: document.getElementById("consultTranscriptSearch"),
        prev: document.getElementById("consultSearchPrev"),
        next: document.getElementById("consultSearchNext"),
        count: document.getElementById("consultSearchCount"),
        pre: document.getElementById("consultTranscriptText"),
        text: function () { return (viewedConsult && viewedConsult.transcript) || ""; }
    });

    /* The A4 sheet is laid out at full width and scaled to the pane. */
    function fitSheet() {
        if (!csSheet || csRxPane.hidden) return;
        var paper = csRxPane.querySelector(".consult-paper");
        var width = paper.clientWidth;
        if (!width) return;
        var scale = Math.min(1, width / 794);
        csSheet.el.style.transform = "scale(" + scale + ")";
        paper.style.height = Math.ceil(csSheet.el.offsetHeight * scale) + "px";
    }

    if (window.ResizeObserver) new ResizeObserver(fitSheet).observe(csRxPane);

    function renderRxPane(c) {
        csSheet = null;
        csRxPane.innerHTML = "";
        csDownloadBtn.hidden = true;
        var p = c.prescription;
        if (!p || !window.MeetMindRx) {
            csRxPane.innerHTML = '<div class="meeting-none">' +
                "No prescription was generated for this consultation.</div>";
            return;
        }
        var info = document.createElement("div");
        info.className = "consult-rx-info";
        info.innerHTML = rxPill(p.status) +
            '<span class="hint">' +
            (p.status === "final"
                ? "Downloaded by the doctor " + esc(fmtDateTime(p.finalizedAt)) + " — this is the copy they issued."
                : "AI draft from " + esc(fmtDateTime(p.updatedAt)) + " — not reviewed or downloaded yet.") +
            (p.modelLabel ? " Drafted by " + esc(p.modelLabel) + "." : "") +
            "</span>";
        csRxPane.appendChild(info);

        var desk = document.createElement("div");
        desk.className = "consult-desk";
        var paper = document.createElement("div");
        paper.className = "consult-paper";
        desk.appendChild(paper);
        csRxPane.appendChild(desk);

        csSheet = window.MeetMindRx.createSheet({ editable: false });
        csSheet.el.classList.add("consult-sheet");
        csSheet.setProfile(c.doctorProfile);
        csSheet.setData(p, { consultationId: c.id, createdAt: c.createdAt });
        paper.appendChild(csSheet.el);
        csDownloadBtn.hidden = false;
        requestAnimationFrame(fitSheet);
    }

    function showConsultTab(which) {
        csRxPane.hidden = which !== "prescription";
        csTranscriptPane.hidden = which !== "transcript";
        csDialog.querySelectorAll("[data-ctab]").forEach(function (t) {
            var active = t.getAttribute("data-ctab") === which;
            t.classList.toggle("is-active", active);
            t.setAttribute("aria-selected", String(active));
        });
        if (which === "prescription") requestAnimationFrame(fitSheet);
    }

    csDialog.querySelectorAll("[data-ctab]").forEach(function (tab) {
        tab.addEventListener("click", function () { showConsultTab(tab.getAttribute("data-ctab")); });
    });

    function setConsultExpanded(expanded) {
        csDialog.classList.toggle("is-expanded", expanded);
        csExpandBtn.setAttribute("aria-pressed", String(expanded));
        csExpandBtn.setAttribute("aria-label", expanded ? "Exit full view" : "Expand the viewer");
        csExpandBtn.title = expanded ? "Exit full view" : "Expand";
        requestAnimationFrame(fitSheet);
    }

    csExpandBtn.addEventListener("click", function () {
        setConsultExpanded(!csDialog.classList.contains("is-expanded"));
    });

    function openConsult(id) {
        api("/api/doctor/consultations/" + encodeURIComponent(id)).then(function (c) {
            viewedConsult = c;
            var p = c.prescription || {};
            csTitle.textContent = (p.patient_name || c.title || "Untitled consultation") +
                (p.age_sex ? " · " + p.age_sex : "");
            var length = fmtDuration(c.durationSeconds);
            csMeta.textContent = "Recorded by " + (c.username || "") + " · " + (c.email || "") +
                " · " + fmtDateTime(c.createdAt) + (length ? " · " + length : "");

            showPlayer(csPlayer, c.hasAudio && c.audio, "Consultation recording", "consultation_" + c.id);
            csTranscript.reset();
            renderRxPane(c);
            setConsultExpanded(false);
            showConsultTab("prescription");
            csDialog.showModal();
            requestAnimationFrame(fitSheet);
        }).catch(function () {
            D.alert({ title: "Couldn't open consultation", message: "Could not open that consultation. Please try again." });
        });
    }

    csBody.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-view-consult]");
        if (btn) openConsult(btn.getAttribute("data-view-consult"));
    });

    csDownloadBtn.addEventListener("click", function () {
        if (!csSheet) return;
        csDownloadBtn.disabled = true;
        csSheet.downloadPdf().catch(function (error) {
            D.alert({ title: "Couldn't create the PDF", message: error.message || "Please try again." });
        }).then(function () {
            csDownloadBtn.disabled = false;
        });
    });

    document.getElementById("consultDialogClose")
        .addEventListener("click", function () { csDialog.close(); });

    csDialog.addEventListener("click", function (e) {
        if (e.target === csDialog) csDialog.close();
    });

    csDialog.addEventListener("close", function () {
        setConsultExpanded(false);
        csPlayer.clear();
    });

    /* ============================================================
       INTERVIEWS — every user's Interview template sessions
       ------------------------------------------------------------
       Read-only, like consultations. An interview is shown with its
       recording, its evaluation report on that interviewer's
       letterhead (assets/interview-report.js — the same page the
       interviewer downloads) and its transcript.
       /api/interview/interviews?scope=all.
    ============================================================ */

    var ivBody = document.getElementById("interviewRows");
    var ivSearch = document.getElementById("interviewSearch");
    var ivCount = document.getElementById("interviewCount");
    var ivUserFilter = document.getElementById("interviewUserFilter");
    var ivStatusFilter = document.getElementById("interviewStatusFilter");
    var ivTypeFilter = document.getElementById("interviewTypeFilter");
    var ivDateFrom = document.getElementById("interviewDateFrom");
    var ivDateTo = document.getElementById("interviewDateTo");
    var ivFilterReset = document.getElementById("interviewFilterReset");
    var ivPagination = document.getElementById("interviewPagination");
    var statInterviews = document.getElementById("statInterviews");
    var statInterviewsBy = document.getElementById("statInterviewsBy");
    var interviewPage = 1;
    var INTERVIEWS_PER_PAGE = 10;

    var allInterviews = [];
    var interviewsLoaded = false;

    function interviewName(i) {
        return i.candidateName || i.title || "Untitled interview";
    }

    function evalPill(status) {
        if (status === "final") return '<span class="pill rx-pill rx-final" title="Report downloaded by the interviewer">Report · final</span>';
        if (status === "draft") return '<span class="pill rx-pill rx-draft" title="Evaluated, report not downloaded yet">Evaluation · draft</span>';
        return '<span class="pill rx-pill rx-none">Not evaluated</span>';
    }

    function renderInterviewStats() {
        statInterviews.textContent = interviewsLoaded ? allInterviews.length : "—";
        var evaluated = allInterviews.filter(function (i) { return i.evaluationStatus; });
        var scored = evaluated.filter(function (i) { return i.scorePercent != null; });
        var avg = scored.length
            ? Math.round(scored.reduce(function (sum, i) { return sum + i.scorePercent; }, 0) / scored.length)
            : null;
        statInterviewsBy.textContent = allInterviews.length
            ? evaluated.length + " evaluated" + (avg == null ? "" : " · avg score " + avg + "%")
            : "";
    }

    function populateInterviewUserFilter() {
        var current = ivUserFilter.value;
        var seen = {};
        var options = [];
        allInterviews.forEach(function (i) {
            var key = i.email || i.username;
            if (key && !seen[key]) {
                seen[key] = true;
                options.push({ value: key, label: i.username || i.email });
            }
        });
        options.sort(function (a, b) { return a.label.localeCompare(b.label); });
        ivUserFilter.innerHTML = '<option value="">All interviewers</option>' +
            options.map(function (o) {
                return '<option value="' + esc(o.value) + '">' + esc(o.label) + "</option>";
            }).join("");
        if (current && seen[current]) ivUserFilter.value = current;
    }

    function renderInterviews() {
        var q = ivSearch.value.trim().toLowerCase();
        var userVal = ivUserFilter.value;
        var statusVal = ivStatusFilter.value;
        var typeVal = ivTypeFilter.value;
        var fromVal = ivDateFrom.value;
        var toVal = ivDateTo.value;

        var rows = allInterviews.filter(function (i) {
            if (q && [interviewName(i), i.position, (i.requiredSkills || []).join(" "), i.username, i.email].join(" ")
                    .toLowerCase().indexOf(q) === -1) return false;
            if (userVal && (i.email || i.username) !== userVal) return false;
            if (statusVal === "none" ? i.evaluationStatus : (statusVal && i.evaluationStatus !== statusVal)) return false;
            if (typeVal && i.interviewType !== typeVal) return false;
            if (fromVal || toVal) {
                var d = new Date(i.createdAt);
                if (isNaN(d)) return false;
                if (fromVal && d < new Date(fromVal + "T00:00:00")) return false;
                if (toVal && d > new Date(toVal + "T23:59:59")) return false;
            }
            return true;
        });

        var totalPages = Math.max(1, Math.ceil(rows.length / INTERVIEWS_PER_PAGE));
        if (interviewPage > totalPages) interviewPage = totalPages;
        if (interviewPage < 1) interviewPage = 1;
        var pageRows = rows.slice((interviewPage - 1) * INTERVIEWS_PER_PAGE, interviewPage * INTERVIEWS_PER_PAGE);

        if (!rows.length) {
            ivBody.innerHTML = '<tr><td colspan="7"><div class="table-empty">' +
                (allInterviews.length
                    ? "No interviews match your filters."
                    : "No interviews have been recorded yet.") +
                "</div></td></tr>";
        } else {
            ivBody.innerHTML = pageRows.map(function (i) {
                var sub = [i.position, i.interviewType].filter(Boolean).join(" · ");
                return "<tr>" +
                    "<td><strong>" + esc(interviewName(i)) + "</strong>" +
                        (sub ? '<div class="cell-sub">' + esc(sub) + "</div>" : "") + "</td>" +
                    "<td>" + esc(i.username || "") +
                        ' <span class="hint">' + esc(i.email || "") + "</span></td>" +
                    "<td>" + fmtDateTime(i.createdAt) + "</td>" +
                    "<td>" + (fmtDuration(i.durationSeconds) || '<span class="hint">—</span>') + "</td>" +
                    "<td>" + (i.evaluationStatus && i.scorePercent != null
                        ? '<span class="pill iv-score" title="' + esc(i.totalQuestions) + ' questions">' + esc(i.scorePercent) + "%</span>"
                        : '<span class="hint">—</span>') + "</td>" +
                    '<td><div class="model-tags">' + (i.hasAudio ? AUDIO_PILL : "") +
                        evalPill(i.evaluationStatus) + "</div></td>" +
                    '<td class="cell-actions">' +
                        '<button class="row-btn" data-view-interview="' + esc(i.id) + '">View</button>' +
                    "</td>" +
                "</tr>";
            }).join("");
        }

        ivCount.textContent = rows.length + " of " + allInterviews.length +
            " interview" + (allInterviews.length === 1 ? "" : "s");

        renderPagination(ivPagination, interviewPage, totalPages, function (p) {
            interviewPage = p;
            renderInterviews();
        });
    }

    function loadInterviews() {
        return api("/api/interview/interviews?scope=all").then(function (interviews) {
            allInterviews = interviews;
            interviewsLoaded = true;
            populateInterviewUserFilter();
            syncDropdowns();
            renderInterviews();
            renderInterviewStats();
        }).catch(function () {
            ivBody.innerHTML = '<tr><td colspan="7"><div class="table-empty">' +
                "Could not load interviews.</div></td></tr>";
        });
    }

    function onInterviewFilterChange() { interviewPage = 1; renderInterviews(); }

    ivSearch.addEventListener("input", onInterviewFilterChange);
    ivUserFilter.addEventListener("change", onInterviewFilterChange);
    ivStatusFilter.addEventListener("change", onInterviewFilterChange);
    ivTypeFilter.addEventListener("change", onInterviewFilterChange);
    ivDateFrom.addEventListener("change", onInterviewFilterChange);
    ivDateTo.addEventListener("change", onInterviewFilterChange);

    ivFilterReset.addEventListener("click", function () {
        ivSearch.value = "";
        ivUserFilter.value = "";
        ivStatusFilter.value = "";
        ivTypeFilter.value = "";
        ivDateFrom.value = "";
        ivDateTo.value = "";
        interviewPage = 1;
        syncDropdowns();
        renderInterviews();
    });

    enhanceSelect(ivUserFilter);
    enhanceSelect(ivStatusFilter);
    enhanceSelect(ivTypeFilter);

    /* ---- interview viewer ---- */

    var ivDialog = document.getElementById("interviewDialog");
    var ivTitle = document.getElementById("interviewDialogTitle");
    var ivMeta = document.getElementById("interviewDialogMeta");
    var ivReportPane = document.getElementById("interviewReportPane");
    var ivTranscriptPane = document.getElementById("interviewTranscriptPane");
    var ivExpandBtn = document.getElementById("interviewExpandBtn");
    var ivDownloadBtn = document.getElementById("interviewDownloadBtn");
    var ivPlayer = makePlayer("interviewPlayerSlot", false);
    ivPlayer.el.classList.add("mm-player--indigo");
    var ivSheet = null;
    var viewedInterview = null;

    var ivTranscript = makeTranscriptSearch({
        input: document.getElementById("interviewTranscriptSearch"),
        prev: document.getElementById("interviewSearchPrev"),
        next: document.getElementById("interviewSearchNext"),
        count: document.getElementById("interviewSearchCount"),
        pre: document.getElementById("interviewTranscriptText"),
        text: function () { return (viewedInterview && viewedInterview.transcript) || ""; }
    });

    /* The A4 report is laid out at full width and scaled to the pane. */
    function fitInterviewSheet() {
        if (!ivSheet || ivReportPane.hidden) return;
        var paper = ivReportPane.querySelector(".consult-paper");
        var width = paper.clientWidth;
        if (!width) return;
        var scale = Math.min(1, width / 794);
        ivSheet.el.style.transform = "scale(" + scale + ")";
        paper.style.height = Math.ceil(ivSheet.el.offsetHeight * scale) + "px";
    }

    if (window.ResizeObserver) new ResizeObserver(fitInterviewSheet).observe(ivReportPane);

    function renderInterviewReportPane(i) {
        ivSheet = null;
        ivReportPane.innerHTML = "";
        ivDownloadBtn.hidden = true;
        var ev = i.evaluation;
        if (!ev || !window.MeetMindInterviewReport) {
            ivReportPane.innerHTML = '<div class="meeting-none">' +
                "This interview hasn't been evaluated yet.</div>";
            return;
        }
        var info = document.createElement("div");
        info.className = "consult-rx-info";
        info.innerHTML = evalPill(ev.status) +
            '<span class="hint">' +
            (ev.status === "final"
                ? "Downloaded by the interviewer " + esc(fmtDateTime(ev.finalizedAt)) + " — this is the copy they issued."
                : "Saved " + esc(fmtDateTime(ev.updatedAt)) + " — not downloaded as final yet.") +
            (ev.modelLabel ? " Evaluated by " + esc(ev.modelLabel) + "." : "") +
            "</span>";
        ivReportPane.appendChild(info);

        var desk = document.createElement("div");
        desk.className = "consult-desk interview-desk";
        var paper = document.createElement("div");
        paper.className = "consult-paper";
        desk.appendChild(paper);
        ivReportPane.appendChild(desk);

        ivSheet = window.MeetMindInterviewReport.createSheet();
        ivSheet.setProfile(i.interviewerProfile);
        ivSheet.setData(ev, { interviewId: i.id, createdAt: i.createdAt, durationSeconds: i.durationSeconds });
        paper.appendChild(ivSheet.el);
        ivDownloadBtn.hidden = false;
        requestAnimationFrame(fitInterviewSheet);
    }

    function showInterviewTab(which) {
        ivReportPane.hidden = which !== "report";
        ivTranscriptPane.hidden = which !== "transcript";
        ivDialog.querySelectorAll("[data-itab]").forEach(function (t) {
            var active = t.getAttribute("data-itab") === which;
            t.classList.toggle("is-active", active);
            t.setAttribute("aria-selected", String(active));
        });
        if (which === "report") requestAnimationFrame(fitInterviewSheet);
    }

    ivDialog.querySelectorAll("[data-itab]").forEach(function (tab) {
        tab.addEventListener("click", function () { showInterviewTab(tab.getAttribute("data-itab")); });
    });

    function setInterviewExpanded(expanded) {
        ivDialog.classList.toggle("is-expanded", expanded);
        ivExpandBtn.setAttribute("aria-pressed", String(expanded));
        ivExpandBtn.setAttribute("aria-label", expanded ? "Exit full view" : "Expand the viewer");
        ivExpandBtn.title = expanded ? "Exit full view" : "Expand";
        requestAnimationFrame(fitInterviewSheet);
    }

    ivExpandBtn.addEventListener("click", function () {
        setInterviewExpanded(!ivDialog.classList.contains("is-expanded"));
    });

    function openInterview(id) {
        api("/api/interview/interviews/" + encodeURIComponent(id)).then(function (i) {
            viewedInterview = i;
            var setup = i.setup || {};
            ivTitle.textContent = [setup.candidate_name || i.title || "Untitled interview", setup.position]
                .filter(Boolean).join(" · ");
            var length = fmtDuration(i.durationSeconds);
            ivMeta.textContent = "Recorded by " + (i.username || "") + " · " + (i.email || "") +
                " · " + fmtDateTime(i.createdAt) + (length ? " · " + length : "");

            showPlayer(ivPlayer, i.hasAudio && i.audio, "Interview recording", "interview_" + i.id);
            ivTranscript.reset();
            renderInterviewReportPane(i);
            setInterviewExpanded(false);
            showInterviewTab("report");
            ivDialog.showModal();
            requestAnimationFrame(fitInterviewSheet);
        }).catch(function () {
            D.alert({ title: "Couldn't open interview", message: "Could not open that interview. Please try again." });
        });
    }

    ivBody.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-view-interview]");
        if (btn) openInterview(btn.getAttribute("data-view-interview"));
    });

    ivDownloadBtn.addEventListener("click", function () {
        if (!ivSheet) return;
        ivDownloadBtn.disabled = true;
        ivSheet.downloadPdf().catch(function (error) {
            D.alert({ title: "Couldn't create the PDF", message: error.message || "Please try again." });
        }).then(function () {
            ivDownloadBtn.disabled = false;
        });
    });

    document.getElementById("interviewDialogClose")
        .addEventListener("click", function () { ivDialog.close(); });

    ivDialog.addEventListener("click", function (e) {
        if (e.target === ivDialog) ivDialog.close();
    });

    ivDialog.addEventListener("close", function () {
        setInterviewExpanded(false);
        ivPlayer.clear();
    });

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
            loadConsults();
            loadInterviews();
        });
    }

})();
