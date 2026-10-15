/* ============================================================
   MeetMind — meeting history drawer (loaded by index.html)
   ------------------------------------------------------------
   Lists the signed-in user's past meetings and, when one is
   picked, shows it in the page's existing transcript and
   per-model result panels via window.meetmindHistory (defined at
   the bottom of index.html).

   Each meeting is one entry, tagged with the models that have
   results for it (from the `models` field of /api/meetings).

   It follows the page's template: in the Doctor–Patient template
   it lists the user's consultations (/api/doctor/consultations)
   instead, and opens them through bridge.loadConsultation(). The
   two histories are stored and shown separately — never mixed.

   This file builds its own markup and never touches the
   recorder's ids, classes or state directly.
============================================================ */

(function () {
    "use strict";

    var bridge = window.meetmindHistory;
    if (!bridge) return;

    var D = window.MeetMindDialog;

    var openMeetingId = null;

    /* "doctor" (consultations) or "meeting", from the page's template. */
    function mode() {
        return document.body.dataset.meetmindTemplate === "doctor" ? "doctor" : "meeting";
    }

    var WORDS = {
        meeting: {
            heading: "Past meetings",
            sub: "Your saved transcripts, summaries and mind maps",
            one: "saved meeting",
            many: "saved meetings",
            empty: "No saved meetings yet. Record or upload a meeting — it will appear here.",
            failed: "Could not load your meetings.",
            viewing: "Viewing saved meeting",
            untitled: "Untitled meeting",
            busyGenerating: "A summary or mind map is still being generated. Open the saved meeting anyway?",
            open: "Open meeting",
            cantOpen: "Could not open that meeting. Please try again."
        },
        doctor: {
            heading: "Past consultations",
            sub: "Your saved consultations, prescriptions and recordings",
            one: "saved consultation",
            many: "saved consultations",
            empty: "No saved consultations yet. Record or upload a consultation in the Doctor–Patient template — it will appear here.",
            failed: "Could not load your consultations.",
            viewing: "Viewing saved consultation",
            untitled: "Untitled consultation",
            busyGenerating: "A prescription is still being drafted. Open the saved consultation anyway?",
            open: "Open consultation",
            cantOpen: "Could not open that consultation. Please try again."
        }
    };

    function words() {
        return WORDS[mode()];
    }

    /* ---- helpers --------------------------------------- */

    function api(path) {
        return fetch(path, { credentials: "same-origin" }).then(function (res) {
            if (!res.ok) throw new Error("Request failed.");
            return res.json();
        });
    }

    function fmtTime(d) {
        return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    }

    function fmtDay(d) {
        return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
    }

    function fmtDate(iso) {
        var d = new Date(iso);
        if (isNaN(d)) return "";
        return fmtDay(d) + " · " + fmtTime(d);
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

    /* "<when> · <how long>", or just <when> without a known duration. */
    function withDuration(when, seconds) {
        var length = fmtDuration(seconds);
        if (!length) return when;
        return when ? when + " · " + length : length;
    }

    /* "Today", "Yesterday", or the date — the list's group headings. */
    function dayLabel(d) {
        var today = new Date();
        today.setHours(0, 0, 0, 0);
        var day = new Date(d);
        day.setHours(0, 0, 0, 0);
        var diff = Math.round((today - day) / 86400000);
        if (diff === 0) return "Today";
        if (diff === 1) return "Yesterday";
        return d.toLocaleDateString(undefined, {
            weekday: "short", year: "numeric", month: "short", day: "numeric"
        });
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    /* One tag per model with results. A model that only has one of
       the two outputs says which. A meeting with a saved recording
       also gets a recording tag. */
    function modelTags(models, hasAudio) {
        var wrap = el("span", "history-tags");
        if (hasAudio) wrap.appendChild(audioTag());
        (models || []).forEach(function (m) {
            var tag = el("span", "history-tag", m.label || m.key);
            var only = null;
            if (m.hasSummary && !m.hasMindmap) only = "summary only";
            if (m.hasMindmap && !m.hasSummary) only = "mind map only";
            if (only) {
                tag.appendChild(el("span", "history-tag-note", " · " + only));
            }
            tag.title = (m.label || m.key) + ": " +
                (m.hasSummary && m.hasMindmap ? "summary and mind map" : only);
            wrap.appendChild(tag);
        });
        return wrap;
    }

    function audioTag() {
        var tag = el("span", "history-tag history-tag--audio", "Recording");
        tag.title = "The recording is saved and can be played back";
        return tag;
    }

    /* A consultation's tags: its prescription status and recording. */
    function consultationTags(c) {
        var wrap = el("span", "history-tags");
        var tag;
        if (c.prescriptionStatus === "final") {
            tag = el("span", "history-tag history-tag--final", "Prescription · final");
            tag.title = "Prescription downloaded" + (c.finalizedAt ? " on " + fmtDate(c.finalizedAt) : "");
        } else if (c.prescriptionStatus === "draft") {
            tag = el("span", "history-tag history-tag--draft", "Prescription · draft");
            tag.title = "AI draft, not downloaded yet";
        } else {
            tag = el("span", "history-tag history-tag--none", "No prescription");
        }
        wrap.appendChild(tag);
        if (c.hasAudio) wrap.appendChild(audioTag());
        return wrap;
    }

    /* What a consultation is listed as: the patient, else its title. */
    function consultationTitle(c) {
        var name = c.patientName || c.title || words().untitled;
        return c.ageSex ? name + " (" + c.ageSex + ")" : name;
    }

    /* ---- build the drawer ------------------------------ */

    var scrim = el("div", "history-scrim");

    var drawer = el("aside", "history-drawer");
    drawer.setAttribute("aria-label", "Past meetings");
    drawer.setAttribute("aria-hidden", "true");

    var head = el("div", "history-head");
    head.appendChild(el("span", "history-head-icon"));
    var headText = el("div", "history-head-text");
    var headTitle = el("h2", null, "Past meetings");
    headText.appendChild(headTitle);
    var sub = el("p", "history-sub", "Your saved transcripts, summaries and mind maps");
    headText.appendChild(sub);
    head.appendChild(headText);

    var closeBtn = el("button", "history-close");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", "Close past meetings");
    closeBtn.title = "Close (Esc)";
    head.appendChild(closeBtn);

    var list = el("div", "history-list");

    drawer.appendChild(head);
    drawer.appendChild(list);

    document.body.appendChild(scrim);
    document.body.appendChild(drawer);

    /* ---- "viewing a saved meeting" bar ----------------- */

    var viewing = el("div", "history-viewing");
    viewing.setAttribute("role", "status");
    viewing.appendChild(el("span", "history-viewing-icon"));
    var viewingBody = el("div", "history-viewing-body");
    var viewingText = el("div", "history-viewing-text");
    var viewingTags = el("div", "history-viewing-tags");
    viewingBody.appendChild(viewingText);
    viewingBody.appendChild(viewingTags);
    viewing.appendChild(viewingBody);
    var exitBtn = el("button", "btn-secondary history-exit", "Back to recording");
    exitBtn.type = "button";
    viewing.appendChild(exitBtn);

    // Sits between the header card and the transcript.
    var anchor = document.querySelector(".panel--transcript");
    if (anchor && anchor.parentNode) {
        anchor.parentNode.insertBefore(viewing, anchor);
    }

    function showViewingBar(item) {
        var doctor = mode() === "doctor";
        var rx = item.prescription || {};
        viewingText.innerHTML = "";
        viewingText.appendChild(el("span", "history-viewing-label", words().viewing));
        viewingText.appendChild(el("strong", null, doctor
            ? consultationTitle({ patientName: rx.patient_name, ageSex: rx.age_sex, title: item.title })
            : (item.title || words().untitled)));
        viewingText.appendChild(el("span", "history-viewing-date",
            withDuration(fmtDate(item.createdAt), item.durationSeconds)));
        viewingTags.innerHTML = "";
        viewingTags.appendChild(doctor
            ? consultationTags({
                prescriptionStatus: rx.status,
                finalizedAt: rx.finalizedAt,
                hasAudio: item.hasAudio
            })
            : modelTags(item.models, item.hasAudio));
        viewing.classList.add("is-shown");
    }

    function hideViewingBar() {
        viewing.classList.remove("is-shown");
        openMeetingId = null;
        markActive();
    }

    exitBtn.addEventListener("click", function () {
        bridge.reset();
        hideViewingBar();
    });

    // Starting a new recording or upload clears the panels, so the
    // "viewing a saved meeting" bar has to go with them.
    document.addEventListener("meetmind:new-session", hideViewingBar);

    // Switching template: the other history, and nothing open from it.
    document.addEventListener("meetmind:template-changed", function () {
        hideViewingBar();
        applyWords();
        if (drawer.classList.contains("is-open")) loadList();
    });

    // A prescription drafted / downloaded for the consultation on screen.
    document.addEventListener("meetmind:consultation-changed", function (e) {
        var id = e.detail && e.detail.consultationId;
        if (mode() !== "doctor" || !openMeetingId || String(id) !== String(openMeetingId)) return;
        api("/api/doctor/consultations/" + encodeURIComponent(id)).then(function (c) {
            if (String(c.id) === String(openMeetingId)) showViewingBar(c);
        }).catch(function () {});
    });

    // Another model generated (or a title edited) for the meeting on
    // screen: refresh the bar's title and tags from the server.
    document.addEventListener("meetmind:results-changed", function (e) {
        var id = e.detail && e.detail.meetingId;
        if (mode() !== "meeting" || !openMeetingId || String(id) !== String(openMeetingId)) return;
        api("/api/meetings/" + encodeURIComponent(id)).then(function (meeting) {
            if (String(meeting.id) === String(openMeetingId)) showViewingBar(meeting);
        }).catch(function () {});
    });

    /* ---- open / close ---------------------------------- */

    var returnFocusTo = null;

    function openDrawer() {
        returnFocusTo = document.activeElement;
        drawer.classList.add("is-open");
        scrim.classList.add("is-open");
        drawer.setAttribute("aria-hidden", "false");
        loadList();
        closeBtn.focus();
    }

    function closeDrawer() {
        if (!drawer.classList.contains("is-open")) return;
        drawer.classList.remove("is-open");
        scrim.classList.remove("is-open");
        drawer.setAttribute("aria-hidden", "true");
        if (returnFocusTo && document.contains(returnFocusTo)) returnFocusTo.focus();
        returnFocusTo = null;
    }

    closeBtn.addEventListener("click", closeDrawer);
    scrim.addEventListener("click", closeDrawer);

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && drawer.classList.contains("is-open")) closeDrawer();
    });

    /* ---- list rendering -------------------------------- */

    function markActive() {
        list.querySelectorAll(".history-item").forEach(function (node) {
            var active = String(node.dataset.id) === String(openMeetingId);
            node.classList.toggle("is-active", active);
            if (active) {
                node.setAttribute("aria-current", "true");
            } else {
                node.removeAttribute("aria-current");
            }
        });
    }

    function showLoading() {
        list.innerHTML = "";
        list.setAttribute("aria-busy", "true");
        for (var i = 0; i < 4; i++) {
            var card = el("div", "history-skeleton");
            card.appendChild(el("div", "skeleton-line history-skeleton-title"));
            card.appendChild(el("div", "skeleton-line history-skeleton-meta"));
            list.appendChild(card);
        }
    }

    function showMessage(className, text, retry) {
        list.innerHTML = "";
        list.removeAttribute("aria-busy");
        var box = el("div", className);
        box.appendChild(el("p", null, text));
        if (retry) {
            var again = el("button", "btn-secondary history-retry", "Try again");
            again.type = "button";
            again.addEventListener("click", loadList);
            box.appendChild(again);
        }
        list.appendChild(box);
    }

    function renderItem(m) {
        var doctor = mode() === "doctor";
        var item = el("button", "history-item");
        item.type = "button";
        item.dataset.id = m.id;

        item.appendChild(el("span", "history-item-title",
            doctor ? consultationTitle(m) : (m.title || words().untitled)));

        var d = new Date(m.createdAt);
        item.appendChild(el("span", "history-item-time",
            withDuration(isNaN(d) ? "" : fmtTime(d), m.durationSeconds)));
        if (doctor && m.diagnosis) {
            item.appendChild(el("span", "history-item-note", m.diagnosis));
        }
        item.appendChild(doctor ? consultationTags(m) : modelTags(m.models, m.hasAudio));

        item.addEventListener("click", function () { openMeeting(m.id); });
        return item;
    }

    var listRequest = 0;

    function loadList() {
        showLoading();
        var request = ++listRequest;

        api(mode() === "doctor" ? "/api/doctor/consultations" : "/api/meetings").then(function (meetings) {
            // A template switch while this was loading started a new list.
            if (request !== listRequest) return;
            list.innerHTML = "";
            list.removeAttribute("aria-busy");

            sub.textContent = meetings.length
                ? meetings.length + " " + (meetings.length === 1 ? words().one : words().many)
                : words().sub;

            if (!meetings.length) {
                showMessage("history-empty", words().empty);
                return;
            }

            // Newest first, grouped under a heading per day.
            var currentDay = null;
            var group = null;
            meetings.forEach(function (m) {
                var d = new Date(m.createdAt);
                var label = isNaN(d) ? "Earlier" : dayLabel(d);
                if (label !== currentDay) {
                    currentDay = label;
                    group = el("section", "history-group");
                    group.appendChild(el("h3", "history-group-label", label));
                    list.appendChild(group);
                }
                group.appendChild(renderItem(m));
            });

            markActive();

        }).catch(function () {
            if (request !== listRequest) return;
            showMessage("history-state", words().failed, true);
        });
    }

    /* ---- opening one meeting --------------------------- */

    function openMeeting(id) {
        var proceed = Promise.resolve(true);

        // Never overwrite a recording that is still in progress.
        if (bridge.isBusy()) {
            proceed = proceed.then(function (ok) {
                return ok && D.confirm({
                    title: "Recording in progress",
                    message: "A recording is in progress. Open the saved " +
                        (mode() === "doctor" ? "consultation" : "meeting") + " anyway?",
                    confirmText: words().open
                });
            });
        }

        // Same for a summary/mind map still being generated: loading
        // another meeting here re-points the panels while that request
        // is in flight (its result is still saved to its own meeting).
        if (bridge.isGenerating && bridge.isGenerating()) {
            proceed = proceed.then(function (ok) {
                return ok && D.confirm({
                    title: "Still generating",
                    message: words().busyGenerating,
                    confirmText: words().open
                });
            });
        }

        var doctor = mode() === "doctor";

        proceed.then(function (ok) {
            if (!ok) return;
            api(doctor
                ? "/api/doctor/consultations/" + encodeURIComponent(id)
                : "/api/meetings/" + encodeURIComponent(id)
            ).then(function (meeting) {
                if (doctor) bridge.loadConsultation(meeting); else bridge.load(meeting);
                openMeetingId = meeting.id;
                showViewingBar(meeting);
                markActive();
                returnFocusTo = null;
                closeDrawer();
                window.scrollTo({ top: 0, behavior: "smooth" });

            }).catch(function () {
                D.alert({
                    title: doctor ? "Couldn't open consultation" : "Couldn't open meeting",
                    message: words().cantOpen
                });
            });
        });
    }

    /* ---- the header trigger ---------------------------- */

    var btn = el("button", "history-btn");
    btn.type = "button";
    btn.addEventListener("click", openDrawer);

    function applyWords() {
        var w = words();
        headTitle.textContent = w.heading;
        sub.textContent = w.sub;
        drawer.setAttribute("aria-label", w.heading);
        closeBtn.setAttribute("aria-label", "Close " + w.heading.toLowerCase());
        btn.setAttribute("aria-label", w.heading);
        btn.title = w.heading;
    }

    applyWords();

    var host = document.querySelector(".header-actions");
    if (host) {
        var themeToggle = host.querySelector(".theme-toggle");
        if (themeToggle) {
            host.insertBefore(btn, themeToggle);
        } else {
            host.appendChild(btn);
        }
    }

})();
