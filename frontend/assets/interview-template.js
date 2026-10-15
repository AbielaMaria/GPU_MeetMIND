/* ============================================================
   MeetMind — Interview template (loaded by index.html)
   ------------------------------------------------------------
   Everything the Interview template adds to the recorder page.
   The recorder, upload and transcript are shared with the other
   templates; this file adds, in page order:

     1. Interviewer Profile      the letterhead (organisation,
                                 interviewer, logo, signature),
                                 saved per user (/api/interview/profile).
     2. Interview Setup          candidate, interviewer, position,
                                 type and the required skills. Saved
                                 to the interview once it is recorded.
     3. Evaluate Interview       in the transcript panel, in place of
                                 the MOM model picker (Qwen3 27B).
     4. Interview Evaluation     review & edit the AI evaluation:
                                 verdicts, skills, proficiency, and
                                 the interviewer's own decision.
                                 Scores recompute as you edit.
     5. Download Report          the report on the letterhead; the
                                 PDF download saves the final copy.

   Interviews are saved in their own tables (backend/
   interview_database.py), never in meeting or consultation history.

   Hooks it relies on from index.html: window.meetmindHistory
   (reset), window.meetmindRecordingPlayer, the
   "meetmind:template-changed" / "meetmind:transcript-state" events
   and the globals `transcript`, `isRecording`, `recordBtn`,
   `setStatus`, `currentMeetingDuration`. The template pills live in
   assets/doctor-template.js. Exposes window.meetmindInterview for
   index.html / history.js / doctor-template.js.
============================================================ */

(function () {
    "use strict";

    var R = window.MeetMindInterviewReport;
    var D = window.MeetMindDialog;
    if (!R) return;

    var ICON = {
        brief: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/><rect width="20" height="14" x="2" y="6" rx="2"/></svg>',
        user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
        chevron: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
        image: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/></svg>',
        pen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.38 3.62a1 1 0 0 1 3 3L7.37 18.64a2 2 0 0 1-.86.5l-2.87.84a.5.5 0 0 1-.62-.62l.84-2.87a2 2 0 0 1 .5-.86Z"/></svg>',
        sparkles: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0l1.58 6.14a2 2 0 0 0 1.44 1.44l6.14 1.58a.5.5 0 0 1 0 .96l-6.14 1.58a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0Z"/></svg>',
        shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>',
        download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>',
        arrowDown: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="m19 12-7 7-7-7"/></svg>',
        trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
        alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>',
        check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.801 10A10 10 0 1 1 17 3.335"/><path d="m9 11 3 3L22 4"/></svg>',
        gavel: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m14 13-8.381 8.38a1 1 0 0 1-3.001-3L11 9.999"/><path d="M15.973 4.027 9.027 10.973"/><path d="m16 16 6-6"/><path d="m8 8 6-6"/><path d="m9 7 8 8"/><path d="m21 11-8-8"/></svg>'
    };

    var PROFILE_FIELDS = [
        "interviewer_name", "organization_name", "designation", "department",
        "address", "phone", "email", "website"
    ];
    var SETUP_TEXT_FIELDS = ["candidate_name", "interviewer_name", "position", "interview_type"];

    var IMAGE_TYPES = /^image\/(png|jpeg|webp)$/;
    var IMAGE_MAX_BYTES = 5 * 1024 * 1024;

    var VERDICTS = [
        ["Correct", "correct", "Correct"],
        ["Partially Correct", "partial", "Partial"],
        ["Incorrect", "incorrect", "Incorrect"],
        ["Unable to Evaluate", "unknown", "Can't judge"]
    ];

    /* ---------------- state ---------------- */

    function emptySetup() {
        return { candidate_name: "", interviewer_name: "", position: "", interview_type: "Technical", required_skills: [] };
    }

    var state = {
        active: false,
        profile: null,
        profileLoaded: false,
        setup: emptySetup(),
        setupFromSaved: false,   // the setup shown belongs to a saved interview
        interviewId: null,
        createdAt: null,
        durationSeconds: null,
        report: null,            // R.normalize()d, or null
        status: "none",          // none | generating | draft | final | error
        modelLabel: "Qwen3 27B",
        updatedAt: null,
        finalizedAt: null,
        editedSinceSave: false,
        draftSaved: false,       // the interviewer has saved their edits (not downloaded)
        error: "",
        filter: "all",
        epoch: 0                 // bumps whenever the screen is reset
    };

    /* ---------------- helpers ---------------- */

    function el(tag, className, html) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (html != null) node.innerHTML = html;
        return node;
    }

    function esc(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function fmtTime(iso) {
        var d = iso ? new Date(iso) : new Date();
        if (isNaN(d)) return "";
        var sameDay = d.toDateString() === new Date().toDateString();
        return (sameDay ? "" : d.toLocaleDateString(undefined, { day: "numeric", month: "short" }) + ", ") +
            d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    }

    function currentTranscript() {
        return (typeof transcript === "string" ? transcript : "").trim();
    }

    function recorderBusy() {
        return (typeof isRecording !== "undefined" && isRecording) ||
            (typeof recordBtn !== "undefined" && recordBtn && recordBtn.disabled);
    }

    function status(message) {
        if (typeof setStatus === "function") setStatus(message);
    }

    function requestJSON(url, options) {
        return fetch(url, Object.assign({ credentials: "same-origin" }, options || {})).then(function (res) {
            return res.json().catch(function () { return {}; }).then(function (body) {
                if (!res.ok) {
                    var detail = body && (body.detail || body.error || body.message);
                    if (res.status === 401) detail = "You're signed out. Sign in again to continue.";
                    throw new Error(typeof detail === "string" ? detail : "Request failed (HTTP " + res.status + ").");
                }
                return body;
            });
        });
    }

    function autoGrow(textarea) {
        textarea.style.height = "auto";
        textarea.style.height = Math.min(textarea.scrollHeight + 2, 360) + "px";
    }

    function emitChanged() {
        document.dispatchEvent(new CustomEvent("meetmind:interview-changed", {
            detail: { interviewId: state.interviewId }
        }));
    }

    function setTone(node, tone) {
        if (tone) node.dataset.tone = tone; else node.removeAttribute("data-tone");
    }

    /* ============================================================
       1. INTERVIEWER PROFILE (letterhead)
    ============================================================ */

    var profileCard = el("section", "card iv-card iv-profile iv-only");
    profileCard.id = "interviewProfileCard";
    profileCard.setAttribute("aria-label", "Interviewer profile");
    profileCard.innerHTML =
        '<button type="button" class="iv-profile-toggle" aria-expanded="false" aria-controls="ivProfileBody">' +
            '<span class="iv-card-icon">' + ICON.brief + "</span>" +
            '<span class="iv-profile-heading">' +
                '<span class="iv-profile-title">Interviewer Profile</span>' +
                '<span class="iv-profile-summary" data-summary>Loading…</span>' +
            "</span>" +
            '<span class="iv-chip" data-profile-chip>…</span>' +
            '<span class="iv-profile-edit"><span class="iv-profile-edit-text" data-toggle-text>Edit</span>' + ICON.chevron + "</span>" +
        "</button>" +
        '<div class="iv-profile-body" id="ivProfileBody" hidden>' +
            '<p class="iv-note">These details head every evaluation report you download. ' +
                "Only your name is required — you can change them any time.</p>" +
            '<div class="iv-profile-layout">' +
                '<form class="iv-profile-form" novalidate>' +
                    '<fieldset class="iv-fieldset"><legend><span class="iv-step">1</span>Interviewer</legend>' +
                        '<div class="iv-grid">' +
                            profileInput("interviewer_name", "Full name", "e.g. Priya Raman", "iv-span", true) +
                            profileInput("designation", "Designation", "e.g. Engineering Manager") +
                            profileInput("department", "Department / team", "e.g. Platform Engineering") +
                        "</div>" +
                    "</fieldset>" +
                    '<fieldset class="iv-fieldset"><legend><span class="iv-step">2</span>Organisation</legend>' +
                        '<div class="iv-grid">' +
                            profileInput("organization_name", "Organisation name", "e.g. Acme Technologies", "iv-span") +
                            '<label class="iv-field iv-span"><span class="iv-field-label"><span>Address</span><small>optional</small></span>' +
                                '<textarea name="address" rows="2" placeholder="Street, area, city – PIN"></textarea></label>' +
                            profileInput("phone", "Phone", "+91 98765 43210", "", false, "tel") +
                            profileInput("email", "Email", "careers@example.com", "", false, "email") +
                            profileInput("website", "Website", "www.example.com", "iv-span") +
                        "</div>" +
                    "</fieldset>" +
                    '<fieldset class="iv-fieldset"><legend><span class="iv-step">3</span>Branding <small>optional</small></legend>' +
                        '<div class="iv-grid">' +
                            uploadTile("logo", "Organisation logo", "Shown at the top-left of the report", ICON.image) +
                            uploadTile("signature", "Signature", "Printed above your name; a transparent PNG works best", ICON.pen) +
                        "</div>" +
                    "</fieldset>" +
                    '<div class="iv-form-actions">' +
                        '<button type="submit" class="iv-btn-primary" data-save>Save profile</button>' +
                        '<button type="button" class="iv-btn-ghost" data-discard>Discard changes</button>' +
                        '<span class="iv-form-status" data-form-status role="status"></span>' +
                    "</div>" +
                "</form>" +
                '<aside class="iv-preview" aria-label="Letterhead preview">' +
                    '<div class="iv-preview-label">Letterhead preview<span>updates as you type</span></div>' +
                    '<div class="iv-preview-paper" data-preview></div>' +
                "</aside>" +
            "</div>" +
        "</div>";

    function profileInput(name, label, placeholder, extraClass, required, type) {
        return '<label class="iv-field ' + (extraClass || "") + '"><span class="iv-field-label">' +
            "<span>" + esc(label) + (required ? ' <span class="iv-req">*</span>' : "") + "</span>" +
            (required ? "" : "<small>optional</small>") + "</span>" +
            '<input name="' + name + '" type="' + (type || "text") + '" placeholder="' + esc(placeholder) + '"' +
            (required ? " required" : "") + ' autocomplete="off"></label>';
    }

    function uploadTile(kind, title, help, icon) {
        return '<div class="iv-upload" data-upload="' + kind + '">' +
            '<div class="iv-upload-thumb" data-thumb>' + icon + "</div>" +
            '<div class="iv-upload-text"><strong>' + esc(title) + "</strong>" +
                "<span>" + esc(help) + "</span><span>PNG, JPG or WEBP · up to 5 MB</span>" +
                '<div class="iv-upload-actions">' +
                    '<button type="button" class="iv-link" data-pick>Upload</button>' +
                    '<button type="button" class="iv-link iv-link--danger" data-remove hidden>Remove</button>' +
                "</div>" +
                '<input type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" tabindex="-1" aria-hidden="true">' +
            "</div>" +
        "</div>";
    }

    var profileToggle = profileCard.querySelector(".iv-profile-toggle");
    var profileBody = profileCard.querySelector(".iv-profile-body");
    var profileForm = profileCard.querySelector("form");
    var profileSummary = profileCard.querySelector("[data-summary]");
    var profileChip = profileCard.querySelector("[data-profile-chip]");
    var toggleText = profileCard.querySelector("[data-toggle-text]");
    var formStatus = profileCard.querySelector("[data-form-status]");
    var saveProfileBtn = profileCard.querySelector("[data-save]");
    var previewHost = profileCard.querySelector("[data-preview]");

    var images = {
        logo: { file: null, remove: false, objectUrl: null },
        signature: { file: null, remove: false, objectUrl: null }
    };

    function setProfileOpen(open) {
        profileBody.hidden = !open;
        profileToggle.setAttribute("aria-expanded", String(open));
        toggleText.textContent = open ? "Hide" : (state.profile ? "Edit" : "Set up");
        if (open) requestAnimationFrame(fitLetterheadPreview);
    }

    profileToggle.addEventListener("click", function () {
        setProfileOpen(profileBody.hidden);
    });

    function profileFormValues() {
        var values = {};
        PROFILE_FIELDS.forEach(function (name) {
            var input = profileForm.elements.namedItem(name);
            values[name] = input ? input.value.trim() : "";
        });
        return values;
    }

    function imageUrl(kind) {
        var img = images[kind];
        if (img.file) return img.objectUrl;
        if (img.remove) return null;
        return state.profile ? state.profile[kind + "_url"] : null;
    }

    function renderProfileHeader() {
        var p = state.profile;
        if (!state.profileLoaded) {
            profileSummary.textContent = "Loading…";
            profileChip.textContent = "…";
            setTone(profileChip, null);
            return;
        }
        if (p) {
            profileSummary.textContent = [p.interviewer_name, p.designation, p.organization_name].filter(Boolean).join(" · ");
            profileChip.textContent = "Saved";
            setTone(profileChip, "final");
        } else {
            profileSummary.textContent = "Add your name and organisation for the report letterhead";
            profileChip.textContent = "Not set up";
            setTone(profileChip, "draft");
        }
        if (profileBody.hidden) toggleText.textContent = p ? "Edit" : "Set up";
    }

    function fillProfileForm() {
        var p = state.profile || {};
        PROFILE_FIELDS.forEach(function (name) {
            var input = profileForm.elements.namedItem(name);
            if (input) input.value = p[name] || "";
        });
        ["logo", "signature"].forEach(function (kind) {
            var img = images[kind];
            if (img.objectUrl) URL.revokeObjectURL(img.objectUrl);
            img.file = null;
            img.remove = false;
            img.objectUrl = null;
            renderUpload(kind);
        });
        renderLetterheadPreview();
    }

    function renderUpload(kind) {
        var tile = profileCard.querySelector('[data-upload="' + kind + '"]');
        var url = imageUrl(kind);
        tile.querySelector("[data-thumb]").innerHTML = url
            ? '<img src="' + esc(url) + '" alt="">'
            : (kind === "logo" ? ICON.image : ICON.pen);
        tile.querySelector("[data-pick]").textContent = url ? "Replace" : "Upload";
        tile.querySelector("[data-remove]").hidden = !url;
    }

    function renderLetterheadPreview() {
        var p = profileFormValues();
        p.logo_url = imageUrl("logo");
        p.signature_url = imageUrl("signature");
        previewHost.innerHTML = '<div class="ivr-sheet">' +
            '<div class="ivr-band"></div>' + R.letterheadHTML(p) +
            '<div class="iv-mini-lines"><i></i><i></i><i></i><i></i></div></div>';
        fitLetterheadPreview();
    }

    // The preview is a full-width (794 px) letterhead scaled to the panel.
    function fitLetterheadPreview() {
        var sheetEl = previewHost.querySelector(".ivr-sheet");
        if (!sheetEl || !previewHost.clientWidth) return;
        var scale = previewHost.clientWidth / 794;
        sheetEl.style.transform = "scale(" + scale + ")";
        previewHost.style.height = Math.ceil(sheetEl.offsetHeight * scale) + "px";
    }

    if (window.ResizeObserver) new ResizeObserver(fitLetterheadPreview).observe(previewHost);

    profileForm.addEventListener("input", function (e) {
        if (e.target.type === "file") return;
        setFormStatus("");
        renderLetterheadPreview();
    });

    profileCard.querySelectorAll("[data-upload]").forEach(function (tile) {
        var kind = tile.dataset.upload;
        var input = tile.querySelector('input[type="file"]');

        function take(file) {
            if (!file) return;
            if (!IMAGE_TYPES.test(file.type)) {
                setFormStatus("Choose a PNG, JPG or WEBP image.", "error");
                return;
            }
            if (file.size > IMAGE_MAX_BYTES) {
                setFormStatus("That image is larger than 5 MB.", "error");
                return;
            }
            var img = images[kind];
            if (img.objectUrl) URL.revokeObjectURL(img.objectUrl);
            img.file = file;
            img.remove = false;
            img.objectUrl = URL.createObjectURL(file);
            setFormStatus("");
            renderUpload(kind);
            renderLetterheadPreview();
        }

        tile.querySelector("[data-pick]").addEventListener("click", function () { input.click(); });
        input.addEventListener("change", function () {
            take(input.files && input.files[0]);
            input.value = "";
        });
        tile.querySelector("[data-remove]").addEventListener("click", function () {
            var img = images[kind];
            if (img.objectUrl) URL.revokeObjectURL(img.objectUrl);
            img.file = null;
            img.objectUrl = null;
            img.remove = !!(state.profile && state.profile[kind + "_url"]);
            renderUpload(kind);
            renderLetterheadPreview();
        });
        tile.addEventListener("dragover", function (e) {
            e.preventDefault();
            tile.classList.add("is-dragover");
        });
        tile.addEventListener("dragleave", function () { tile.classList.remove("is-dragover"); });
        tile.addEventListener("drop", function (e) {
            e.preventDefault();
            tile.classList.remove("is-dragover");
            take(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]);
        });
    });

    function setFormStatus(text, tone) {
        formStatus.textContent = text || "";
        setTone(formStatus, tone);
    }

    profileCard.querySelector("[data-discard]").addEventListener("click", function () {
        fillProfileForm();
        setFormStatus("");
        if (state.profile) setProfileOpen(false);
    });

    profileForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var values = profileFormValues();
        if (!values.interviewer_name) {
            setFormStatus("Your name is required — it signs every report.", "error");
            profileForm.elements.namedItem("interviewer_name").focus();
            return;
        }

        var payload = new FormData();
        PROFILE_FIELDS.forEach(function (name) { payload.append(name, values[name]); });
        ["logo", "signature"].forEach(function (kind) {
            var img = images[kind];
            if (img.file) payload.append(kind, img.file, img.file.name);
            else if (img.remove) payload.append("remove_" + kind, "true");
        });

        saveProfileBtn.disabled = true;
        saveProfileBtn.classList.add("iv-btn-busy");
        setFormStatus("Saving…");

        requestJSON("/api/interview/profile", { method: "POST", body: payload }).then(function (result) {
            state.profile = result.profile || null;
            fillProfileForm();
            renderProfileHeader();
            applyProfileEverywhere();
            setFormStatus("Profile saved. It's on your report letterhead now.", "ok");
            setTimeout(function () {
                setProfileOpen(false);
                setFormStatus("");
            }, 900);
        }).catch(function (error) {
            setFormStatus(error.message || "The profile was not saved. Check your sign-in and try again.", "error");
        }).then(function () {
            saveProfileBtn.disabled = false;
            saveProfileBtn.classList.remove("iv-btn-busy");
        });
    });

    function loadProfile() {
        state.profileLoaded = false;
        renderProfileHeader();
        return requestJSON("/api/interview/profile").then(function (result) {
            state.profile = result.profile || null;
        }).catch(function () {
            state.profile = null;
        }).then(function () {
            state.profileLoaded = true;
            fillProfileForm();
            renderProfileHeader();
            applyProfileEverywhere();
            // Open until the interviewer has saved a profile; collapsed after.
            setProfileOpen(!state.profile);
        });
    }

    function applyProfileEverywhere() {
        var name = state.profile ? state.profile.interviewer_name : "";
        setupInputs.interviewer_name.placeholder = name || "Interviewer name";
        sheet.setProfile(state.profile);
        schedulePreview();
    }

    /* ============================================================
       2. INTERVIEW SETUP
    ============================================================ */

    var setupCard = el("section", "card iv-card iv-setup iv-only");
    setupCard.id = "interviewSetupCard";
    setupCard.setAttribute("aria-labelledby", "ivSetupTitle");
    setupCard.innerHTML =
        '<div class="iv-card-head">' +
            '<div class="iv-card-title"><span class="iv-card-icon">' + ICON.user + "</span>" +
                '<div><h2 id="ivSetupTitle">Interview Setup</h2>' +
                "<p>Who is being interviewed, for what role, and which skills to assess. " +
                "Fill this in before or after recording — it is saved with the interview.</p></div>" +
            "</div>" +
            '<span class="iv-chip" data-setup-chip>Not saved yet</span>' +
        "</div>" +
        '<div class="iv-grid iv-grid--setup">' +
            setupInput("candidate_name", "Candidate name", "e.g. Arjun Mehta") +
            setupInput("position", "Position / role", "e.g. Backend Developer") +
            setupInput("interviewer_name", "Interviewer", "Interviewer name") +
            '<label class="iv-field"><span class="iv-field-label"><span>Interview type</span></span>' +
                '<select name="interview_type">' +
                    R.TYPES.map(function (t) { return "<option>" + esc(t) + "</option>"; }).join("") +
                "</select></label>" +
            '<div class="iv-field iv-span">' +
                '<span class="iv-field-label"><span>Required skills <span class="iv-req">*</span></span>' +
                    "<small>Enter or comma to add · every question is mapped to one of these</small></span>" +
                '<div class="iv-skills" data-skills>' +
                    '<span class="iv-skill-chips" data-chips></span>' +
                    '<input type="text" data-skill-input placeholder="e.g. Python, SQL, REST APIs" autocomplete="off" aria-label="Add a required skill">' +
                "</div>" +
                '<p class="iv-skill-note" data-skill-note hidden></p>' +
            "</div>" +
        "</div>";

    function setupInput(name, label, placeholder) {
        return '<label class="iv-field"><span class="iv-field-label"><span>' + esc(label) + "</span></span>" +
            '<input name="' + name + '" type="text" placeholder="' + esc(placeholder) + '" autocomplete="off" maxlength="200"></label>';
    }

    var setupInputs = {};
    SETUP_TEXT_FIELDS.forEach(function (name) {
        setupInputs[name] = setupCard.querySelector('[name="' + name + '"]');
    });
    var setupChip = setupCard.querySelector("[data-setup-chip]");
    var skillsBox = setupCard.querySelector("[data-skills]");
    var chipsHost = setupCard.querySelector("[data-chips]");
    var skillInput = setupCard.querySelector("[data-skill-input]");
    var skillNote = setupCard.querySelector("[data-skill-note]");

    function renderSkillChips() {
        chipsHost.innerHTML = state.setup.required_skills.map(function (skill, i) {
            return '<span class="iv-skill-chip">' + esc(skill) +
                '<button type="button" data-remove-skill="' + i + '" aria-label="Remove ' + esc(skill) + '">&times;</button></span>';
        }).join("");
        renderSkillNote();
    }

    /* Changing skills after an evaluation needs a new evaluation. */
    function renderSkillNote() {
        var stale = false;
        if (state.report) {
            var a = state.report.interview_details.required_skills.map(function (s) { return s.toLowerCase(); }).sort().join("|");
            var b = state.setup.required_skills.map(function (s) { return s.toLowerCase(); }).sort().join("|");
            stale = a !== b;
        }
        skillNote.hidden = !stale;
        skillNote.textContent = stale
            ? "The evaluation below was made against: " + state.report.interview_details.required_skills.join(", ") +
              ". Evaluate the interview again to assess the new skill list."
            : "";
    }

    function fillSetupForm() {
        SETUP_TEXT_FIELDS.forEach(function (name) {
            setupInputs[name].value = state.setup[name] || (name === "interview_type" ? "Technical" : "");
        });
        renderSkillChips();
    }

    function addSkills(text) {
        var added = R.parseSkills(text);
        if (!added.length) return false;
        var have = state.setup.required_skills.map(function (s) { return s.toLowerCase(); });
        added.forEach(function (s) {
            if (have.indexOf(s.toLowerCase()) === -1) {
                state.setup.required_skills.push(s);
                have.push(s.toLowerCase());
            }
        });
        renderSkillChips();
        onSetupChanged();
        return true;
    }

    skillInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            if (addSkills(skillInput.value)) skillInput.value = "";
        } else if (e.key === "Backspace" && !skillInput.value && state.setup.required_skills.length) {
            state.setup.required_skills.pop();
            renderSkillChips();
            onSetupChanged();
        }
    });

    skillInput.addEventListener("input", function () {
        // Pasted "a, b, c": take every complete entry.
        if (/[,;\n]/.test(skillInput.value)) {
            var parts = skillInput.value.split(/[,;\n]/);
            var rest = parts.pop();
            addSkills(parts.join(","));
            skillInput.value = rest.trimStart();
        }
    });

    skillInput.addEventListener("blur", function () {
        if (addSkills(skillInput.value)) skillInput.value = "";
    });

    skillsBox.addEventListener("click", function (e) {
        var remove = e.target.closest("[data-remove-skill]");
        if (remove) {
            state.setup.required_skills.splice(Number(remove.dataset.removeSkill), 1);
            renderSkillChips();
            onSetupChanged();
            return;
        }
        if (e.target === skillsBox || e.target === chipsHost) skillInput.focus();
    });

    setupCard.addEventListener("input", function (e) {
        var name = e.target.name;
        if (SETUP_TEXT_FIELDS.indexOf(name) === -1) return;
        state.setup[name] = e.target.value.trim();
        onSetupChanged();
    });

    setupCard.addEventListener("change", function (e) {
        if (e.target.name === "interview_type") {
            state.setup.interview_type = e.target.value;
            onSetupChanged();
        }
    });

    var setupSaveTimer = null;
    var setupSaveSeq = 0;

    function renderSetupChip(text, tone) {
        setupChip.textContent = text;
        setTone(setupChip, tone);
    }

    function setupPayload() {
        var s = state.setup;
        return {
            candidate_name: s.candidate_name,
            interviewer_name: s.interviewer_name || (state.profile ? state.profile.interviewer_name : ""),
            position: s.position,
            interview_type: s.interview_type || "Technical",
            required_skills: s.required_skills.slice()
        };
    }

    function hasSetup() {
        var s = state.setup;
        return !!(s.candidate_name || s.position || s.interviewer_name || s.required_skills.length);
    }

    function onSetupChanged() {
        // The report's header shows the setup; its skills stay the ones it was evaluated against.
        if (state.report) {
            var details = state.report.interview_details;
            var p = setupPayload();
            details.candidate_name = p.candidate_name;
            details.interviewer_name = p.interviewer_name;
            details.position = p.position;
            details.interview_type = p.interview_type;
            onEdited();
            schedulePreview();
        }
        renderSkillNote();
        renderEvaluateButton();
        scheduleSetupSave();
    }

    function scheduleSetupSave() {
        clearTimeout(setupSaveTimer);
        if (!state.interviewId) {
            renderSetupChip(hasSetup() ? "Saved when recorded" : "Not saved yet", null);
            return;
        }
        renderSetupChip("Saving…", "busy");
        setupSaveTimer = setTimeout(saveSetupNow, 700);
    }

    function saveSetupNow() {
        clearTimeout(setupSaveTimer);
        if (!state.interviewId) return Promise.resolve();
        var id = state.interviewId;
        var seq = ++setupSaveSeq;
        return requestJSON("/api/interview/interviews/" + encodeURIComponent(id), {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(setupPayload())
        }).then(function () {
            if (seq !== setupSaveSeq || id !== state.interviewId) return;
            renderSetupChip("Saved to this interview", "final");
            emitChanged();
        }).catch(function (error) {
            if (seq !== setupSaveSeq) return;
            renderSetupChip("Not saved", "error");
            status(error.message || "The interview setup couldn't be saved.");
        });
    }

    /* ============================================================
       3. EVALUATE INTERVIEW (transcript panel)
    ============================================================ */

    var actions = el("div", "iv-actions-bar iv-only");
    actions.innerHTML =
        '<span class="iv-actions-meta">' + ICON.shield +
            '<span data-model-note>Evaluated by Qwen3 27B · always reviewed by you</span></span>' +
        '<button type="button" class="iv-btn-primary" id="analyzeInterviewBtn" disabled>' +
            ICON.sparkles + "<span>Evaluate Interview</span></button>";
    var evaluateBtn = actions.querySelector("#analyzeInterviewBtn");
    var evaluateLabel = evaluateBtn.querySelector("span");

    function renderEvaluateButton() {
        var busy = state.status === "generating";
        evaluateBtn.disabled = busy || !currentTranscript() || recorderBusy();
        evaluateBtn.classList.toggle("iv-btn-busy", busy);
        evaluateLabel.textContent = busy
            ? "Evaluating interview…"
            : (state.report ? "Re-evaluate Interview" : "Evaluate Interview");
    }

    document.addEventListener("meetmind:transcript-state", function () {
        renderEvaluateButton();
        renderAll();
    });

    if (typeof recordBtn !== "undefined" && recordBtn && window.MutationObserver) {
        new MutationObserver(renderEvaluateButton).observe(recordBtn, {
            attributes: true,
            attributeFilter: ["disabled"]
        });
    }

    evaluateBtn.addEventListener("click", function () {
        var text = currentTranscript();
        if (!text) {
            status("Record or upload the interview first.");
            return;
        }
        if (skillInput.value.trim()) {
            addSkills(skillInput.value);
            skillInput.value = "";
        }
        if (!state.setup.required_skills.length) {
            status("Add at least one required skill to evaluate against.");
            setupCard.scrollIntoView({ behavior: "smooth", block: "start" });
            skillsBox.classList.add("is-invalid");
            setTimeout(function () { skillsBox.classList.remove("is-invalid"); }, 2400);
            skillInput.focus({ preventScroll: true });
            return;
        }
        var proceed = Promise.resolve(true);
        if (state.report && D) {
            proceed = D.confirm({
                title: "Replace this evaluation?",
                message: "A new AI evaluation will replace the one below, including any changes you made to it.",
                confirmText: "Evaluate again",
                danger: true
            });
        }
        proceed.then(function (ok) { if (ok) evaluate(text); });
    });

    function evaluate(text) {
        var epoch = state.epoch;
        var previous = { report: state.report, status: state.status };

        state.status = "generating";
        state.error = "";
        renderAll();
        reviewCard.scrollIntoView({ behavior: "smooth", block: "start" });
        status("Evaluating the interview… long interviews can take a few minutes.");

        requestJSON("/api/interview/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(Object.assign({
                transcript: text,
                interview_id: state.interviewId
            }, setupPayload()))
        }).then(function (result) {
            if (epoch !== state.epoch) return;
            if (!result.success || !result.evaluation) {
                throw new Error(result.error || "The interview could not be evaluated.");
            }
            if (result.interview_id) state.interviewId = result.interview_id;
            if (!state.createdAt) state.createdAt = new Date().toISOString();
            applyEvaluation(result.evaluation);
            state.editedSinceSave = false;
            renderSetupChip("Saved to this interview", "final");
            renderAll();
            buildReview();
            schedulePreview();
            status("Interview evaluated. Review every verdict, then download the report.");
            emitChanged();
        }).catch(function (error) {
            if (epoch !== state.epoch) return;
            state.report = previous.report;
            state.status = previous.report ? previous.status : "error";
            state.error = error.message || "The interview could not be evaluated.";
            renderAll();
            status(state.error);
            if (previous.report && D) {
                D.alert({ title: "Couldn't evaluate the interview again", message: state.error });
            }
        });
    }

    function applyEvaluation(evaluation) {
        state.report = R.normalize(evaluation);
        state.status = evaluation.status === "final" ? "final" : "draft";
        state.modelLabel = evaluation.modelLabel || state.modelLabel;
        state.updatedAt = evaluation.updatedAt || new Date().toISOString();
        state.finalizedAt = evaluation.finalizedAt || null;
        // A saved draft edited since the AI wrote it (the server bumps updatedAt on every save).
        state.draftSaved = !!(evaluation.createdAt && evaluation.updatedAt &&
            evaluation.updatedAt !== evaluation.createdAt);
    }

    /* ============================================================
       4. INTERVIEW EVALUATION — review & edit
    ============================================================ */

    var reviewCard = el("section", "card iv-card iv-review iv-only");
    reviewCard.id = "interviewReportCard";
    reviewCard.setAttribute("aria-labelledby", "ivReviewTitle");
    reviewCard.innerHTML =
        '<div class="iv-card-head">' +
            '<div class="iv-card-title"><span class="iv-card-icon">' + ICON.check + "</span>" +
                '<div><h2 id="ivReviewTitle">Interview Evaluation</h2>' +
                "<p>Check every verdict the AI gave. Change a verdict, skill or level and the scores update instantly.</p></div>" +
            "</div>" +
            '<span class="iv-chip" data-review-status>Not evaluated</span>' +
        "</div>" +
        '<div data-review-empty class="iv-empty">' +
            '<span class="iv-empty-icon">' + ICON.check + "</span>" +
            "<strong>No evaluation yet</strong>" +
            '<p data-empty-text></p>' +
        "</div>" +
        '<div data-review-error class="iv-empty iv-empty--error" hidden>' +
            '<span class="iv-empty-icon">' + ICON.alert + "</span>" +
            "<strong>The interview couldn't be evaluated</strong>" +
            '<p data-error-text></p>' +
            '<button type="button" class="iv-btn-ghost" data-retry>Try again</button>' +
        "</div>" +
        '<div data-review-loading class="iv-loading" hidden>' +
            '<div class="iv-loading-head">Pairing questions with answers and judging each one…</div>' +
            '<div class="iv-loading-grid"><div class="iv-skel"></div><div class="iv-skel"></div><div class="iv-skel"></div>' +
                '<div class="iv-skel iv-skel--wide"></div><div class="iv-skel iv-skel--wide"></div></div>' +
        "</div>" +
        '<div data-review-body hidden>' +
            '<div class="iv-safety">' + ICON.shield +
                "<span><strong>AI-assisted, interviewer-approved.</strong> The model judges answers from an automatic " +
                "transcript without speaker labels — confirm each verdict before relying on this report.</span></div>" +
            '<div class="iv-tiles" data-tiles></div>' +
            '<div class="iv-section-head"><h3>Question &amp; answer analysis</h3>' +
                '<div class="iv-filters" role="group" aria-label="Show questions" data-filters></div></div>' +
            '<div class="iv-qa-list" data-qa-list></div>' +
            '<button type="button" class="iv-add" data-add-q>+ Add a question the AI missed</button>' +
            '<div class="iv-section-head"><h3>Skill-wise assessment</h3>' +
                '<span class="iv-hint">Counts and scores come from the verdicts above; the proficiency level is yours to set.</span></div>' +
            '<div class="iv-table-wrap"><table class="iv-skill-table"><thead><tr>' +
                '<th>Skill</th><th class="iv-num">Qs</th><th class="iv-num">✓ / ½ / ✗</th><th class="iv-num">Score</th>' +
                "<th>Proficiency</th><th>Evidence</th></tr></thead><tbody data-skill-rows></tbody></table></div>" +
            '<p class="iv-hint" data-unclassified hidden></p>' +
            '<div class="iv-section-head"><h3>Overall assessment</h3></div>' +
            '<div class="iv-grid">' +
                textArea("interview_summary", "Summary", "iv-span") +
                textArea("strengths", "Strengths", "", "One per line") +
                textArea("improvement_areas", "Areas for improvement", "", "One per line") +
                textArea("conclusion", "Conclusion", "iv-span") +
            "</div>" +
            '<div class="iv-decision">' +
                '<div class="iv-decision-head">' + ICON.gavel +
                    "<div><h3>Your decision</h3><p>The AI never fills this in — it's your call, printed on the report.</p></div></div>" +
                '<div class="iv-grid">' +
                    '<label class="iv-field"><span class="iv-field-label"><span>Recommendation</span><small>optional</small></span>' +
                        '<select data-rf="interviewer_decision">' +
                            R.DECISIONS.map(function (d) {
                                return '<option value="' + esc(d) + '">' + esc(d || "— Not decided —") + "</option>";
                            }).join("") +
                        "</select></label>" +
                    textArea("interviewer_notes", "Notes", "iv-span", "Anything you want on the report") +
                "</div>" +
            "</div>" +
            '<div class="iv-review-foot"><span data-review-meta></span>' +
                '<span class="iv-review-foot-actions">' +
                    '<button type="button" class="iv-btn-ghost" data-save-draft>Save changes</button>' +
                    '<button type="button" class="iv-link" data-goto-download>Review the final report &amp; download ' + ICON.arrowDown + "</button>" +
                "</span></div>" +
        "</div>";

    function textArea(name, label, extraClass, placeholder) {
        return '<label class="iv-field ' + (extraClass || "") + '"><span class="iv-field-label"><span>' + esc(label) + "</span></span>" +
            '<textarea data-rf="' + name + '" rows="2"' + (placeholder ? ' placeholder="' + esc(placeholder) + '"' : "") + "></textarea></label>";
    }

    var reviewStatus = reviewCard.querySelector("[data-review-status]");
    var reviewEmpty = reviewCard.querySelector("[data-review-empty]");
    var reviewEmptyText = reviewCard.querySelector("[data-empty-text]");
    var reviewError = reviewCard.querySelector("[data-review-error]");
    var reviewLoading = reviewCard.querySelector("[data-review-loading]");
    var reviewBody = reviewCard.querySelector("[data-review-body]");
    var tilesHost = reviewCard.querySelector("[data-tiles]");
    var filtersHost = reviewCard.querySelector("[data-filters]");
    var qaList = reviewCard.querySelector("[data-qa-list]");
    var skillRows = reviewCard.querySelector("[data-skill-rows]");
    var unclassifiedNote = reviewCard.querySelector("[data-unclassified]");
    var reviewMeta = reviewCard.querySelector("[data-review-meta]");
    var saveDraftBtn = reviewCard.querySelector("[data-save-draft]");

    reviewCard.querySelector("[data-retry]").addEventListener("click", function () {
        if (currentTranscript()) evaluate(currentTranscript());
    });

    reviewCard.querySelector("[data-goto-download]").addEventListener("click", function () {
        downloadCard.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    reviewCard.querySelector("[data-add-q]").addEventListener("click", function () {
        if (!state.report) return;
        state.report.qa_analysis.push({
            question_number: 0, question: "", related_skill: R.UNCLASSIFIED, participant_answer: "",
            evaluation: "Unable to Evaluate", correct_answer: "", remarks: ""
        });
        state.filter = "all";
        R.recompute(state.report);
        buildQaList();
        refreshDerived();
        onEdited();
        var last = qaList.querySelector('article:last-child [data-qf="question"]');
        if (last) last.focus();
    });

    /* ---- building ---- */

    function verdictTone(evaluation) {
        return R.verdictTone(evaluation);
    }

    function skillOptions(selected) {
        var skills = state.report.interview_details.required_skills.concat([R.UNCLASSIFIED]);
        return skills.map(function (s) {
            return '<option value="' + esc(s) + '"' + (s === selected ? " selected" : "") + ">" + esc(s) + "</option>";
        }).join("");
    }

    function qaItemHTML(q, index) {
        return '<article class="iv-qa iv-qa--' + verdictTone(q.evaluation) + '" data-q="' + index + '">' +
            '<div class="iv-qa-head">' +
                '<span class="iv-qa-no">Q' + (index + 1) + "</span>" +
                '<select class="iv-qa-skill" data-qf="related_skill" aria-label="Related skill for question ' + (index + 1) + '">' +
                    skillOptions(q.related_skill) + "</select>" +
                '<div class="iv-verdicts" role="radiogroup" aria-label="Evaluation of question ' + (index + 1) + '">' +
                    VERDICTS.map(function (v) {
                        var on = q.evaluation === v[0];
                        return '<button type="button" role="radio" class="iv-verdict iv-verdict--' + v[1] + '" data-verdict="' +
                            esc(v[0]) + '" aria-checked="' + on + '" title="' + esc(v[0]) + '">' + esc(v[2]) + "</button>";
                    }).join("") +
                "</div>" +
                '<button type="button" class="iv-icon-btn" data-remove-q aria-label="Remove question ' + (index + 1) + '" title="Remove question">' +
                    ICON.trash + "</button>" +
            "</div>" +
            '<div class="iv-qa-grid">' +
                qaField("question", "Question", index, q.question, "iv-span") +
                qaField("participant_answer", "Candidate's answer", index, q.participant_answer) +
                qaField("correct_answer", "Expected / reference answer", index, q.correct_answer) +
                qaField("remarks", "Remarks", index, q.remarks, "iv-span") +
            "</div>" +
        "</article>";
    }

    function qaField(name, label, index, value, extraClass) {
        return '<label class="iv-field ' + (extraClass || "") + '"><span class="iv-field-label"><span>' + esc(label) + "</span></span>" +
            '<textarea data-qf="' + name + '" rows="2" aria-label="' + esc(label) + " " + (index + 1) + '">' + esc(value) + "</textarea></label>";
    }

    function buildQaList() {
        var qa = state.report ? state.report.qa_analysis : [];
        qaList.innerHTML = qa.length
            ? qa.map(qaItemHTML).join("")
            : '<div class="iv-qa-none">No interview questions were identified in the transcript. ' +
              "Add them yourself, or check that the recording captured the interview.</div>";
        qaList.querySelectorAll("textarea").forEach(autoGrow);
        applyFilter();
    }

    function buildSkillRows() {
        var skills = state.report ? state.report.skill_assessment : [];
        skillRows.innerHTML = skills.map(function (s, i) {
            return '<tr data-s="' + i + '">' +
                '<td class="iv-strong">' + esc(s.skill) + "</td>" +
                '<td class="iv-num" data-cell="qs"></td>' +
                '<td class="iv-num" data-cell="split"></td>' +
                '<td class="iv-num iv-strong" data-cell="score"></td>' +
                '<td><select data-sf="proficiency_level" aria-label="Proficiency in ' + esc(s.skill) + '">' +
                    R.LEVELS.map(function (l) {
                        return '<option' + (l === s.proficiency_level ? " selected" : "") + ">" + esc(l) + "</option>";
                    }).join("") + "</select></td>" +
                '<td><textarea data-sf="evidence" rows="1" aria-label="Evidence for ' + esc(s.skill) + '">' + esc(s.evidence) + "</textarea></td>" +
            "</tr>";
        }).join("");
        skillRows.querySelectorAll("textarea").forEach(autoGrow);
    }

    function fillOverall() {
        var r = state.report;
        reviewBody.querySelectorAll("[data-rf]").forEach(function (node) {
            var name = node.dataset.rf;
            var value = r[name];
            node.value = Array.isArray(value) ? value.join("\n") : (value || "");
            if (node.tagName === "TEXTAREA") autoGrow(node);
        });
    }

    function buildReview() {
        if (!state.report) return;
        buildQaList();
        buildSkillRows();
        fillOverall();
        refreshDerived();
    }

    /* ---- derived parts (counts, scores, tones) ---- */

    function tile(value, label, tone) {
        return '<div class="iv-tile' + (tone ? " iv-tile--" + tone : "") + '"><strong>' + value + "</strong><span>" + esc(label) + "</span></div>";
    }

    function refreshDerived() {
        if (!state.report) return;
        var s = state.report.scoring;
        tilesHost.innerHTML =
            tile(s.score_percent == null ? "—" : s.score_percent + "%", "Overall score", "score") +
            tile(s.total_questions, "Questions") +
            tile(s.correct, "Correct", "correct") +
            tile(s.partially_correct, "Partially correct", "partial") +
            tile(s.incorrect, "Incorrect", "incorrect") +
            tile(s.unable_to_evaluate, "Not evaluable", "unknown");

        var counts = { all: s.total_questions, correct: s.correct, partial: s.partially_correct,
            incorrect: s.incorrect, unknown: s.unable_to_evaluate };
        filtersHost.innerHTML = [["all", "All"], ["correct", "Correct"], ["partial", "Partial"],
            ["incorrect", "Incorrect"], ["unknown", "Not evaluable"]].map(function (f) {
            return '<button type="button" class="iv-filter" data-filter="' + f[0] + '" aria-pressed="' +
                (state.filter === f[0]) + '">' + f[1] + " <b>" + counts[f[0]] + "</b></button>";
        }).join("");

        qaList.querySelectorAll("[data-q]").forEach(function (item) {
            var q = state.report.qa_analysis[Number(item.dataset.q)];
            if (!q) return;
            item.className = "iv-qa iv-qa--" + verdictTone(q.evaluation);
            item.querySelectorAll("[data-verdict]").forEach(function (b) {
                b.setAttribute("aria-checked", String(b.dataset.verdict === q.evaluation));
            });
        });

        state.report.skill_assessment.forEach(function (sk, i) {
            var row = skillRows.querySelector('[data-s="' + i + '"]');
            if (!row) return;
            row.querySelector('[data-cell="qs"]').textContent = sk.questions_assessed;
            row.querySelector('[data-cell="split"]').textContent = sk.correct + " / " + sk.partially_correct + " / " + sk.incorrect;
            row.querySelector('[data-cell="score"]').textContent = sk.score_percent == null ? "—" : sk.score_percent + "%";
        });

        var unclassified = state.report.unclassified_questions;
        unclassifiedNote.hidden = !unclassified;
        unclassifiedNote.textContent = unclassified
            ? unclassified + " question" + (unclassified === 1 ? " isn't" : "s aren't") +
              " mapped to a required skill. They count towards the overall score but not towards any skill."
            : "";
        applyFilter();
    }

    function applyFilter() {
        var shown = 0;
        qaList.querySelectorAll("[data-q]").forEach(function (item) {
            var q = state.report && state.report.qa_analysis[Number(item.dataset.q)];
            var match = !q || state.filter === "all" || verdictTone(q.evaluation) === state.filter;
            item.hidden = !match;
            if (match) shown++;
        });
        var none = qaList.querySelector(".iv-qa-filtered");
        if (!shown && state.report && state.report.qa_analysis.length) {
            if (!none) qaList.appendChild(el("div", "iv-qa-none iv-qa-filtered", "No questions with this verdict."));
        } else if (none) {
            none.remove();
        }
    }

    filtersHost.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-filter]");
        if (!btn) return;
        state.filter = btn.dataset.filter;
        refreshDerived();
    });

    /* ---- editing ---- */

    function changed(structural) {
        R.recompute(state.report);
        if (structural) buildQaList();
        refreshDerived();
        onEdited();
        schedulePreview();
    }

    qaList.addEventListener("input", function (e) {
        var t = e.target;
        var item = t.closest("[data-q]");
        if (!item || !state.report || !t.dataset.qf) return;
        var q = state.report.qa_analysis[Number(item.dataset.q)];
        if (!q) return;
        if (t.tagName !== "TEXTAREA") return;  // the skill <select> is handled on "change"
        q[t.dataset.qf] = t.value;
        autoGrow(t);
        onEdited();
        schedulePreview();
    });

    qaList.addEventListener("change", function (e) {
        var t = e.target;
        var item = t.closest("[data-q]");
        if (!item || !state.report || t.dataset.qf !== "related_skill") return;
        state.report.qa_analysis[Number(item.dataset.q)].related_skill = t.value;
        changed(false);
    });

    qaList.addEventListener("click", function (e) {
        var item = e.target.closest("[data-q]");
        if (!item || !state.report) return;
        var index = Number(item.dataset.q);
        var verdict = e.target.closest("[data-verdict]");
        if (verdict) {
            state.report.qa_analysis[index].evaluation = verdict.dataset.verdict;
            changed(false);
            return;
        }
        if (e.target.closest("[data-remove-q]")) {
            var q = state.report.qa_analysis[index];
            var confirm = (q.question || q.participant_answer) && D
                ? D.confirm({ title: "Remove question " + (index + 1) + "?",
                    message: "It is taken out of the report and the scores.", confirmText: "Remove", danger: true })
                : Promise.resolve(true);
            confirm.then(function (ok) {
                if (!ok) return;
                state.report.qa_analysis.splice(index, 1);
                changed(true);
            });
        }
    });

    // Arrow keys move between the verdict buttons (radio-group behaviour).
    qaList.addEventListener("keydown", function (e) {
        var btn = e.target.closest && e.target.closest("[data-verdict]");
        if (!btn || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return;
        e.preventDefault();
        var group = Array.prototype.slice.call(btn.parentNode.querySelectorAll("[data-verdict]"));
        var next = group[(group.indexOf(btn) + (e.key === "ArrowRight" ? 1 : group.length - 1)) % group.length];
        next.click();
        var item = next.closest("[data-q]");
        var same = item && item.querySelector('[data-verdict="' + next.dataset.verdict + '"]');
        if (same) same.focus();
    });

    skillRows.addEventListener("input", function (e) {
        var t = e.target;
        var row = t.closest("[data-s]");
        if (!row || !state.report || t.dataset.sf !== "evidence") return;
        state.report.skill_assessment[Number(row.dataset.s)].evidence = t.value;
        autoGrow(t);
        onEdited();
        schedulePreview();
    });

    skillRows.addEventListener("change", function (e) {
        var t = e.target;
        var row = t.closest("[data-s]");
        if (!row || !state.report || t.dataset.sf !== "proficiency_level") return;
        state.report.skill_assessment[Number(row.dataset.s)].proficiency_level = t.value;
        onEdited();
        schedulePreview();
    });

    function onOverallInput(e) {
        var t = e.target;
        if (!t.dataset || !t.dataset.rf || !state.report) return;
        var name = t.dataset.rf;
        if (name === "strengths" || name === "improvement_areas") {
            state.report[name] = t.value.split("\n").map(function (x) { return x.trim(); }).filter(Boolean);
        } else {
            state.report[name] = t.value;
        }
        if (t.tagName === "TEXTAREA") autoGrow(t);
        onEdited();
        schedulePreview();
    }

    reviewBody.addEventListener("input", function (e) {
        if (e.target.closest("[data-qa-list], [data-skill-rows]")) return;
        onOverallInput(e);
    });
    reviewBody.addEventListener("change", function (e) {
        if (e.target.dataset && e.target.dataset.rf === "interviewer_decision") onOverallInput(e);
    });

    function onEdited() {
        state.editedSinceSave = true;
        renderStatus();
        setSaveState("");
    }

    function renderStatus() {
        var text = "Not evaluated";
        var tone = null;
        if (state.status === "generating") {
            text = "Evaluating…";
            tone = "busy";
        } else if (state.status === "final" && !state.editedSinceSave) {
            text = "Final · downloaded " + fmtTime(state.finalizedAt);
            tone = "final";
        } else if (state.report && state.editedSinceSave) {
            text = "Unsaved changes";
            tone = "draft";
        } else if (state.status === "draft") {
            text = state.draftSaved ? "Draft saved · not downloaded" : "AI draft · review required";
            tone = "draft";
        }
        reviewStatus.textContent = text;
        setTone(reviewStatus, tone);

        reviewMeta.textContent = state.report
            ? "Evaluated by " + state.modelLabel + (state.updatedAt ? " · last saved " + fmtTime(state.updatedAt) : "")
            : "";
        saveDraftBtn.disabled = !state.report || !state.editedSinceSave || !state.interviewId;
    }

    /* ---- saving ---- */

    function reportPayload() {
        var payload = R.toPayload(state.report);
        var p = setupPayload();
        payload.interview_details.candidate_name = p.candidate_name;
        payload.interview_details.interviewer_name = p.interviewer_name;
        payload.interview_details.position = p.position;
        payload.interview_details.interview_type = p.interview_type;
        return payload;
    }

    function saveEvaluation(final) {
        if (!state.interviewId) {
            return Promise.reject(new Error("This interview isn't saved to your history."));
        }
        return requestJSON("/api/interview/interviews/" + encodeURIComponent(state.interviewId) + "/evaluation", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ evaluation: reportPayload(), final: final })
        });
    }

    saveDraftBtn.addEventListener("click", function () {
        var epoch = state.epoch;
        saveDraftBtn.disabled = true;
        saveEvaluation(false).then(function (result) {
            if (epoch !== state.epoch) return;
            var ev = result.evaluation || {};
            state.status = "draft";
            state.updatedAt = ev.updatedAt || new Date().toISOString();
            state.finalizedAt = null;
            state.editedSinceSave = false;
            state.draftSaved = true;
            renderStatus();
            status("Changes saved to the interview. Download the report when it's final.");
            emitChanged();
        }).catch(function (error) {
            status(error.message || "The changes couldn't be saved.");
            renderStatus();
        });
    });

    /* ============================================================
       5. DOWNLOAD REPORT
    ============================================================ */

    var downloadCard = el("section", "card iv-card iv-download iv-only");
    downloadCard.id = "interviewDownloadCard";
    downloadCard.setAttribute("aria-labelledby", "ivDownloadTitle");
    downloadCard.innerHTML =
        '<div class="iv-card-head">' +
            '<div class="iv-card-title"><span class="iv-card-icon">' + ICON.download + "</span>" +
                '<div><h2 id="ivDownloadTitle">Download Report</h2>' +
                "<p>Exactly how the PDF will look. Downloading saves this copy to the interview as final.</p></div>" +
            "</div>" +
            '<div class="iv-download-actions">' +
                '<span class="iv-save-state" data-save-state aria-live="polite"></span>' +
                '<button type="button" class="iv-btn-primary" data-download disabled>' + ICON.download + "<span>Download PDF</span></button>" +
            "</div>" +
        "</div>" +
        '<div data-download-empty class="iv-empty">' +
            '<span class="iv-empty-icon">' + ICON.download + "</span>" +
            "<strong>Your report will appear here on your letterhead</strong>" +
            "<p>Evaluate the interview to preview the report and download it as a PDF.</p>" +
        "</div>" +
        '<div class="iv-desk" data-desk hidden><div class="iv-desk-paper" data-paper></div></div>';

    var desk = downloadCard.querySelector("[data-desk]");
    var paper = downloadCard.querySelector("[data-paper]");
    var downloadEmpty = downloadCard.querySelector("[data-download-empty]");
    var downloadBtn = downloadCard.querySelector("[data-download]");
    var downloadLabel = downloadBtn.querySelector("span");
    var saveState = downloadCard.querySelector("[data-save-state]");

    var sheet = R.createSheet();
    paper.appendChild(sheet.el);

    function fitSheet() {
        if (desk.hidden || !paper.clientWidth) return;
        var scale = Math.min(1, paper.clientWidth / 794);
        sheet.el.style.transform = "scale(" + scale + ")";
        paper.style.height = Math.ceil(sheet.el.offsetHeight * scale) + "px";
    }

    if (window.ResizeObserver) new ResizeObserver(fitSheet).observe(paper);

    var previewQueued = false;

    function schedulePreview() {
        if (previewQueued) return;
        previewQueued = true;
        requestAnimationFrame(function () {
            previewQueued = false;
            if (!state.report) return;
            sheet.setData(state.report, {
                interviewId: state.interviewId,
                createdAt: state.createdAt,
                durationSeconds: state.durationSeconds
            });
            fitSheet();
        });
    }

    function setSaveState(text, tone) {
        saveState.textContent = text || "";
        setTone(saveState, tone);
    }

    downloadBtn.addEventListener("click", function () {
        if (!state.report) return;
        var epoch = state.epoch;
        downloadBtn.disabled = true;
        downloadBtn.classList.add("iv-btn-busy");
        downloadLabel.textContent = "Preparing PDF…";
        setSaveState("");

        // Downloading is the interviewer signing off: save this copy as final.
        var save = saveEvaluation(true).then(function (result) { return { ok: true, result: result }; },
            function (error) { return { ok: false, error: error }; });

        save.then(function (saved) {
            if (saved.ok && epoch === state.epoch) {
                var ev = saved.result.evaluation || {};
                state.report = R.normalize(ev);
                state.status = "final";
                state.finalizedAt = ev.finalizedAt || new Date().toISOString();
                state.updatedAt = ev.updatedAt || state.finalizedAt;
                state.editedSinceSave = false;
                // The server drops empty questions and renumbers: show its copy.
                buildReview();
                renderStatus();
                emitChanged();
            }
            schedulePreview();
            return new Promise(function (resolve) { requestAnimationFrame(resolve); }).then(function () {
                return sheet.downloadPdf();
            }).then(function () {
                if (saved.ok) {
                    setSaveState("Saved to this interview · " + fmtTime(state.finalizedAt), "ok");
                    status("Report downloaded and saved to the interview.");
                } else {
                    setSaveState("Downloaded, but not saved: " + saved.error.message, "error");
                    status("The PDF was downloaded, but the report couldn't be saved to history.");
                }
            });
        }).catch(function (error) {
            setSaveState(error.message || "The PDF couldn't be created.", "error");
            if (D) D.alert({ title: "Couldn't create the PDF", message: error.message || "Please try again." });
        }).then(function () {
            downloadBtn.classList.remove("iv-btn-busy");
            downloadLabel.textContent = "Download PDF";
            renderAll();
        });
    });

    /* ============================================================
       RENDER
    ============================================================ */

    function renderAll() {
        var has = !!state.report;
        var generating = state.status === "generating";

        reviewLoading.hidden = !generating;
        reviewError.hidden = generating || state.status !== "error";
        reviewBody.hidden = generating || !has;
        reviewEmpty.hidden = generating || has || state.status === "error";
        reviewCard.querySelector("[data-error-text]").textContent = state.error;
        reviewEmptyText.innerHTML = currentTranscript()
            ? "The interview is transcribed. Add the required skills above, then click <b>Evaluate Interview</b> under the transcript."
            : "Record or upload the interview, then click <b>Evaluate Interview</b> under the transcript.";

        desk.hidden = !has;
        downloadEmpty.hidden = has;
        downloadBtn.disabled = !has || generating;
        if (has) requestAnimationFrame(fitSheet);

        renderStatus();
        renderEvaluateButton();
    }

    /* ============================================================
       RESET / LOAD (bridge for index.html, history.js and
       doctor-template.js)
    ============================================================ */

    function resetInterview(keepSetup) {
        state.epoch++;
        clearTimeout(setupSaveTimer);
        setupSaveSeq++;
        state.interviewId = null;
        state.createdAt = null;
        state.durationSeconds = null;
        state.report = null;
        state.status = "none";
        state.updatedAt = null;
        state.finalizedAt = null;
        state.editedSinceSave = false;
        state.error = "";
        state.filter = "all";
        if (!keepSetup || state.setupFromSaved) {
            state.setup = emptySetup();
            state.setupFromSaved = false;
            fillSetupForm();
        }
        renderSetupChip(hasSetup() ? "Saved when recorded" : "Not saved yet", null);
        setSaveState("");
        qaList.innerHTML = "";
        skillRows.innerHTML = "";
        sheet.setData({}, { interviewId: null, createdAt: null });
        renderAll();
    }

    window.meetmindInterview = {
        isActive: function () { return state.active; },

        currentId: function () { return state.interviewId; },

        isGenerating: function () { return state.status === "generating"; },

        hasContent: function () { return !!state.report || !!state.interviewId; },

        /* A new live recording or upload is starting: keep a setup the
           interviewer typed for it, drop one that came from history. */
        clearForNewRecording: function () { resetInterview(true); },

        reset: function () { resetInterview(true); },

        /* The recording just transcribed was saved as interview `id`. */
        onTranscribed: function (info) {
            resetInterview(true);
            state.interviewId = info && info.interviewId ? info.interviewId : null;
            state.createdAt = new Date().toISOString();
            state.durationSeconds = typeof currentMeetingDuration !== "undefined" ? currentMeetingDuration : null;
            if (state.interviewId && hasSetup()) {
                renderSetupChip("Saving…", "busy");
                saveSetupNow();
            } else {
                renderSetupChip(state.interviewId ? "Saved to this interview" : "Not saved — sign in to keep it",
                    state.interviewId ? "final" : "error");
            }
            renderAll();
            emitChanged();
        },

        /* Show a saved interview (GET /api/interview/interviews/{id}). */
        load: function (interview) {
            resetInterview(false);
            state.interviewId = interview.id;
            state.createdAt = interview.createdAt;
            state.durationSeconds = interview.durationSeconds;
            var s = interview.setup || {};
            state.setup = {
                candidate_name: s.candidate_name || "",
                interviewer_name: s.interviewer_name || "",
                position: s.position || "",
                interview_type: s.interview_type || "Technical",
                required_skills: (s.required_skills || []).slice()
            };
            state.setupFromSaved = true;
            fillSetupForm();
            renderSetupChip("Saved to this interview", "final");
            if (interview.interviewerProfile && !state.profile) sheet.setProfile(interview.interviewerProfile);
            if (interview.evaluation) {
                applyEvaluation(interview.evaluation);
                buildReview();
                schedulePreview();
            }
            renderAll();
        }
    };

    /* ============================================================
       TEMPLATE
    ============================================================ */

    document.addEventListener("meetmind:template-changed", function (e) {
        state.active = !!(e.detail && e.detail.template === "interview");
        if (!state.active) return;
        if (!state.profileLoaded) loadProfile();
        else if (!state.profile) setProfileOpen(true);
        renderAll();
        requestAnimationFrame(fitSheet);
    });

    /* ============================================================
       MOUNT
    ============================================================ */

    var header = document.querySelector(".app-header");
    var transcriptPanel = document.querySelector(".panel--transcript");
    if (header && header.parentNode) {
        header.parentNode.insertBefore(setupCard, header.nextSibling);
        header.parentNode.insertBefore(profileCard, header.nextSibling);
    }

    var meetingActions = transcriptPanel && transcriptPanel.querySelector(".intelligence-actions");
    if (meetingActions) meetingActions.parentNode.insertBefore(actions, meetingActions.nextSibling);
    else if (transcriptPanel) transcriptPanel.appendChild(actions);

    if (transcriptPanel) {
        transcriptPanel.parentNode.insertBefore(downloadCard, transcriptPanel.nextSibling);
        transcriptPanel.parentNode.insertBefore(reviewCard, transcriptPanel.nextSibling);
    }

    fillSetupForm();
    renderProfileHeader();
    renderSetupChip("Not saved yet", null);
    renderAll();
})();
