/* ============================================================
   MeetMind — meeting history drawer (loaded by index.html)
   ------------------------------------------------------------
   Lists the signed-in user's past meetings and, when one is
   picked, shows it in the page's existing transcript and
   intelligence panels via window.meetmindHistory (defined at the
   bottom of index.html).

   This file builds its own markup and never touches the
   recorder's ids, classes or state directly.
============================================================ */

(function () {
    "use strict";

    var bridge = window.meetmindHistory;
    if (!bridge) return;

    var openMeetingId = null;

    /* ---- helpers --------------------------------------- */

    function api(path) {
        return fetch(path, { credentials: "same-origin" }).then(function (res) {
            if (!res.ok) throw new Error("Request failed.");
            return res.json();
        });
    }

    function fmtDate(iso) {
        var d = new Date(iso);
        if (isNaN(d)) return "";
        return d.toLocaleDateString(undefined, {
            year: "numeric", month: "short", day: "numeric"
        }) + " · " + d.toLocaleTimeString(undefined, {
            hour: "numeric", minute: "2-digit"
        });
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    /* ---- build the drawer ------------------------------ */

    var scrim = el("div", "history-scrim");

    var drawer = el("aside", "history-drawer");
    drawer.setAttribute("aria-label", "Past meetings");
    drawer.setAttribute("aria-hidden", "true");

    var head = el("div", "history-head");
    var headText = el("div");
    headText.appendChild(el("h2", null, "Past meetings"));
    headText.appendChild(el("p", "history-sub", "Your saved transcripts and summaries"));
    head.appendChild(headText);

    var closeBtn = el("button", "history-close", "×");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", "Close past meetings");
    head.appendChild(closeBtn);

    var list = el("div", "history-list");

    drawer.appendChild(head);
    drawer.appendChild(list);

    document.body.appendChild(scrim);
    document.body.appendChild(drawer);

    /* ---- "viewing a saved meeting" bar ----------------- */

    var viewing = el("div", "history-viewing");
    var viewingText = el("div", "history-viewing-text");
    var exitBtn = el("button", "history-exit", "Back to recording");
    exitBtn.type = "button";
    viewing.appendChild(viewingText);
    viewing.appendChild(exitBtn);

    var grid = document.querySelector(".grid");
    if (grid && grid.parentNode) {
        grid.parentNode.insertBefore(viewing, grid);
    }

    function showViewingBar(meeting) {
        viewingText.innerHTML = "";
        viewingText.appendChild(document.createTextNode("Viewing saved meeting "));
        viewingText.appendChild(el("strong", null, meeting.title || "Untitled meeting"));
        viewingText.appendChild(document.createTextNode(" · " + fmtDate(meeting.createdAt)));
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

    // Starting a new recording clears the panels, so the "viewing a saved
    // meeting" bar has to go with them.
    var recordBtn = document.getElementById("recordBtn");
    if (recordBtn) {
        recordBtn.addEventListener("click", function () {
            if (!bridge.isBusy()) hideViewingBar();
        });
    }

    /* ---- open / close ---------------------------------- */

    function openDrawer() {
        drawer.classList.add("is-open");
        scrim.classList.add("is-open");
        drawer.setAttribute("aria-hidden", "false");
        loadList();
    }

    function closeDrawer() {
        drawer.classList.remove("is-open");
        scrim.classList.remove("is-open");
        drawer.setAttribute("aria-hidden", "true");
    }

    closeBtn.addEventListener("click", closeDrawer);
    scrim.addEventListener("click", closeDrawer);

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && drawer.classList.contains("is-open")) closeDrawer();
    });

    /* ---- list rendering -------------------------------- */

    function markActive() {
        list.querySelectorAll(".history-item").forEach(function (node) {
            node.classList.toggle(
                "is-active",
                String(node.dataset.id) === String(openMeetingId)
            );
        });
    }

    function loadList() {
        list.innerHTML = "";
        list.appendChild(el("div", "history-state", "Loading…"));

        api("/api/meetings").then(function (meetings) {
            list.innerHTML = "";

            if (!meetings.length) {
                list.appendChild(el(
                    "div",
                    "history-empty",
                    "No saved meetings yet. Record a meeting and create a summary — it will appear here."
                ));
                return;
            }

            meetings.forEach(function (m) {
                var item = el("button", "history-item");
                item.type = "button";
                item.dataset.id = m.id;

                item.appendChild(el("div", "history-item-title", m.title || "Untitled meeting"));

                var meta = el("div", "history-item-meta");
                meta.appendChild(el("span", null, fmtDate(m.createdAt)));
                meta.appendChild(el("span", "dot"));
                var badgeLabel = "Transcript only";
                if (m.hasSummary && m.hasMindmap) {
                    badgeLabel = "Summary + Mind map";
                } else if (m.hasSummary) {
                    badgeLabel = "Summary";
                } else if (m.hasMindmap) {
                    badgeLabel = "Mind map";
                }
                meta.appendChild(el("span", null, badgeLabel));
                item.appendChild(meta);

                item.addEventListener("click", function () { openMeeting(m.id); });
                list.appendChild(item);
            });

            markActive();

        }).catch(function () {
            list.innerHTML = "";
            list.appendChild(el("div", "history-state", "Could not load your meetings."));
        });
    }

    /* ---- opening one meeting --------------------------- */

    function openMeeting(id) {
        // Never overwrite a recording that is still in progress.
        if (bridge.isBusy()) {
            if (!confirm("A recording is in progress. Open the saved meeting anyway?")) return;
        }

        // Same for a summary/mind map still being generated: loading
        // another meeting here re-points the panels (and the meeting id
        // the result gets saved under) while that request is in flight.
        if (bridge.isGenerating && bridge.isGenerating()) {
            if (!confirm(
                "A summary or mind map is still being generated. Open the saved meeting anyway?"
            )) return;
        }

        api("/api/meetings/" + encodeURIComponent(id)).then(function (meeting) {
            bridge.load(meeting);
            openMeetingId = meeting.id;
            showViewingBar(meeting);
            markActive();
            closeDrawer();
            window.scrollTo({ top: 0, behavior: "smooth" });

        }).catch(function () {
            alert("Could not open that meeting.");
        });
    }

    /* ---- the header trigger ---------------------------- */

    var btn = el("button", "history-btn");
    btn.type = "button";
    btn.setAttribute("aria-label", "Past meetings");
    btn.title = "Past meetings";
    btn.addEventListener("click", openDrawer);

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
