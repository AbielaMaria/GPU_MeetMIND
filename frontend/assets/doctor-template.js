/* ============================================================
   MeetMind — Doctor–Patient template (loaded by index.html)
   ------------------------------------------------------------
   Everything the Doctor–Patient template adds to the recorder
   page. The recorder, upload and transcript are shared with the
   Meeting (MOM) template; this file adds, in page order:

     1. Doctor / Clinic Profile    the letterhead details, saved
                                   per user (/api/doctor/profile).
                                   Open until first saved, then
                                   collapsed (never hidden).
     2. Generate Prescription      in the transcript panel, in
                                   place of the MOM model picker.
     3. Doctor Prescription        review & edit the AI draft.
     4. Download Prescription      the letterhead page exactly as
                                   it will print, editable in
                                   place; Download PDF saves the
                                   final copy to the consultation.

   Consultations are saved in their own tables (see
   backend/database.py), never in meeting history.

   Hooks it relies on from index.html: selectMeetMindTemplate()
   is called by the template pills; window.meetmindHistory
   (loadConsultation / reset) and window.meetmindRecordingPlayer;
   the "meetmind:transcript-state" event; and the globals
   `transcript`, `isRecording`, `recordBtn`, `setStatus`.
   It exposes window.meetmindDoctor for index.html / history.js.
============================================================ */

(function () {
    "use strict";

    var Rx = window.MeetMindRx;
    var D = window.MeetMindDialog;
    if (!Rx) return;

    var PRESCRIPTION_MODEL = "mistral";

    var HINTS = {
        mom: "Summary, decisions, tasks and a mind map for each model, side by side.",
        doctor: "Transcribe the consultation and draft a prescription on your clinic letterhead."
    };

    var SUBTITLES = {
        mom: "AI meeting transcription and meeting intelligence",
        doctor: "AI consultation transcription and prescription drafting"
    };

    var ICON = {
        stethoscope: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 2v2"/><path d="M5 2v2"/><path d="M5 3H4a2 2 0 0 0-2 2v4a6 6 0 0 0 12 0V5a2 2 0 0 0-2-2h-1"/><path d="M8 15a6 6 0 0 0 12 0v-3"/><circle cx="20" cy="10" r="2"/></svg>',
        chevron: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
        image: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/></svg>',
        pen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.38 3.62a1 1 0 0 1 3 3L7.37 18.64a2 2 0 0 1-.86.5l-2.87.84a.5.5 0 0 1-.62-.62l.84-2.87a2 2 0 0 1 .5-.86Z"/></svg>',
        sparkles: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0l1.58 6.14a2 2 0 0 0 1.44 1.44l6.14 1.58a.5.5 0 0 1 0 .96l-6.14 1.58a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0Z"/></svg>',
        shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>',
        download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>',
        arrowDown: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="m19 12-7 7-7-7"/></svg>',
        trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
        mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/></svg>',
        alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>',
        pointer: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.38 3.62a1 1 0 0 1 3 3L7.37 18.64a2 2 0 0 1-.86.5l-2.87.84a.5.5 0 0 1-.62-.62l.84-2.87a2 2 0 0 1 .5-.86Z"/></svg>'
    };

    /* Review & edit form: groups of prescription fields, in the order
       a prescription is read. Every field exists in the backend. */
    var FORM_GROUPS = [
        { title: "Patient", fields: [
            ["patient_name", "Patient name"],
            ["age_sex", "Age / Sex", "e.g. 45 / Male"],
            ["visit_date", "Visit date"],
            ["doctor_name", "Doctor"]
        ] },
        { title: "Complaint & history", fields: [
            ["chief_complaint", "Chief complaint", "", "area"],
            ["symptoms_history", "Symptoms & history", "", "area"],
            ["allergies", "Allergies", "Patient-reported allergy status"]
        ] },
        { title: "Examination & vitals", fields: [
            ["temperature", "Temperature"],
            ["blood_pressure", "Blood pressure"],
            ["pulse_rate", "Pulse rate"],
            ["spo2", "SpO₂"],
            ["examination_findings", "Examination findings", "", "area"]
        ] },
        { title: "Diagnosis / assessment", single: true, fields: [
            ["diagnosis", "Diagnosis", "As stated by the doctor", "area"]
        ] },
        { title: "Medicines prescribed", medicines: true },
        { title: "Tests / investigations advised", single: true, fields: [
            ["tests_advised", "Tests advised", "", "area"]
        ] },
        { title: "Advice", single: true, fields: [
            ["advice", "Advice", "", "area"]
        ] },
        { title: "Warning signs — return if", single: true, alert: true, fields: [
            ["warning_signs", "Warning signs", "", "area"]
        ] },
        { title: "Next visit", single: true, fields: [
            ["next_visit", "Next visit", "Follow-up interval and instructions", "area"]
        ] }
    ];

    var PROFILE_FIELDS = [
        "doctor_name", "qualifications", "specialization", "clinic_name",
        "address", "phone", "email", "timings"
    ];

    var IMAGE_TYPES = /^image\/(png|jpeg|webp)$/;
    var IMAGE_MAX_BYTES = 5 * 1024 * 1024;

    /* ---------------- state ---------------- */

    var state = {
        template: "mom",
        profile: null,
        profileLoaded: false,
        consultationId: null,
        createdAt: null,
        prescription: null,      // Rx.normalize()d, or null
        status: "none",          // none | generating | draft | final | error
        model: null,
        modelLabel: "Mistral 128B",
        updatedAt: null,
        finalizedAt: null,
        editedSinceFinal: false,
        error: "",
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
                    throw new Error(typeof detail === "string" ? detail : "Request failed (HTTP " + res.status + ").");
                }
                return body;
            });
        });
    }

    function autoGrow(textarea) {
        textarea.style.height = "auto";
        textarea.style.height = Math.min(textarea.scrollHeight + 2, 420) + "px";
    }

    function emitConsultationChanged() {
        document.dispatchEvent(new CustomEvent("meetmind:consultation-changed", {
            detail: { consultationId: state.consultationId }
        }));
    }

    /* ============================================================
       1. TEMPLATE SWITCH
    ============================================================ */

    var subtitleEl = document.querySelector(".app-header .subtitle");
    var transcriptTitle = document.querySelector(".panel--transcript .panel-head h2");
    var hintEl = document.getElementById("templateHint");

    function applyTemplate(template) {
        state.template = template;
        document.body.dataset.meetmindTemplate = template;

        document.querySelectorAll(".template-choice").forEach(function (btn) {
            var active = btn.dataset.template === template;
            btn.classList.toggle("active", active);
            btn.setAttribute("aria-checked", String(active));
            btn.tabIndex = active ? 0 : -1;
        });

        if (hintEl) hintEl.textContent = HINTS[template];
        if (subtitleEl) subtitleEl.textContent = SUBTITLES[template];
        if (transcriptTitle) {
            transcriptTitle.textContent = template === "doctor" ? "Consultation Transcript" : "Complete Transcript";
        }

        if (template === "doctor") {
            if (!state.profileLoaded) loadProfile();
            else if (!state.profile) setProfileOpen(true);
        }

        document.dispatchEvent(new CustomEvent("meetmind:template-changed", { detail: { template: template } }));
    }

    function hasContentOnScreen() {
        return !!currentTranscript() || !!state.prescription || !!state.consultationId;
    }

    window.selectMeetMindTemplate = function (template) {
        if (template !== "mom" && template !== "doctor") return;
        if (template === state.template) return;

        if (recorderBusy()) {
            status("Finish the current recording or upload before switching templates.");
            return;
        }
        if (state.status === "generating" || (window.meetmindHistory && window.meetmindHistory.isGenerating())) {
            status("Wait for the current generation to finish before switching templates.");
            return;
        }

        var proceed = Promise.resolve(true);
        if (hasContentOnScreen()) {
            var from = state.template === "doctor" ? "consultation" : "meeting";
            proceed = D ? D.confirm({
                title: template === "doctor" ? "Switch to Doctor–Patient?" : "Switch to Meeting (MOM)?",
                message: "This clears the current " + from + " from the screen. It stays saved in your " +
                    (from === "consultation" ? "past consultations." : "past meetings."),
                confirmText: "Switch template"
            }) : Promise.resolve(window.confirm("Switch template? The current screen will be cleared."));
        }

        proceed.then(function (ok) {
            if (!ok) return;
            if (hasContentOnScreen() && window.meetmindHistory) window.meetmindHistory.reset();
            resetDoctor();
            applyTemplate(template);
        });
    };

    // Arrow keys move between the two pills (radio-group behaviour).
    var pills = document.querySelector(".template-pills");
    if (pills) {
        pills.addEventListener("keydown", function (e) {
            if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
            e.preventDefault();
            var next = state.template === "mom" ? "doctor" : "mom";
            window.selectMeetMindTemplate(next);
            var btn = pills.querySelector('[data-template="' + next + '"]');
            if (btn) btn.focus();
        });
    }

    /* ============================================================
       2. DOCTOR / CLINIC PROFILE
    ============================================================ */

    var profileCard = el("section", "card dr-card dr-profile dr-only");
    profileCard.id = "doctorProfileCard";
    profileCard.setAttribute("aria-label", "Doctor / Clinic profile");
    profileCard.innerHTML =
        '<button type="button" class="dr-profile-toggle" aria-expanded="false" aria-controls="drProfileBody">' +
            '<span class="dr-card-icon">' + ICON.stethoscope + "</span>" +
            '<span class="dr-profile-heading">' +
                '<span class="dr-profile-title">Doctor / Clinic Profile</span>' +
                '<span class="dr-profile-summary" data-summary>Loading…</span>' +
            "</span>" +
            '<span class="dr-status" data-profile-chip>…</span>' +
            '<span class="dr-profile-edit"><span class="dr-profile-edit-text" data-toggle-text>Edit</span>' + ICON.chevron + "</span>" +
        "</button>" +
        '<div class="dr-profile-body" id="drProfileBody" hidden>' +
            '<p class="dr-profile-note">These details are printed on the letterhead of every prescription you download. ' +
                "Only your name is required — you can change them any time.</p>" +
            '<div class="dr-profile-layout">' +
                '<form class="dr-profile-form" novalidate>' +
                    '<fieldset class="dr-fieldset"><legend><span class="dr-step">1</span>Doctor</legend>' +
                        '<div class="dr-grid">' +
                            profileInput("doctor_name", "Full name", "Dr. S. Meenakshi", "dr-span", true) +
                            profileInput("qualifications", "Qualifications", "MBBS, MD (General Medicine)") +
                            profileInput("specialization", "Specialization", "Consultant Physician") +
                        "</div>" +
                    "</fieldset>" +
                    '<fieldset class="dr-fieldset"><legend><span class="dr-step">2</span>Clinic / hospital</legend>' +
                        '<div class="dr-grid">' +
                            profileInput("clinic_name", "Clinic / hospital name", "Sunrise Family Clinic", "dr-span") +
                            '<label class="dr-field dr-span"><span class="dr-field-label">Address</span>' +
                                '<textarea name="address" rows="2" placeholder="Street, area, city – PIN"></textarea></label>' +
                            profileInput("phone", "Phone", "+91 98765 43210", "", false, "tel") +
                            profileInput("email", "Email", "clinic@example.com", "", false, "email") +
                            profileInput("timings", "Consultation timings", "Mon–Sat · 10 AM–1 PM, 5 PM–8 PM", "dr-span") +
                        "</div>" +
                    "</fieldset>" +
                    '<fieldset class="dr-fieldset"><legend><span class="dr-step">3</span>Branding <small>optional</small></legend>' +
                        '<div class="dr-grid">' +
                            uploadTile("logo", "Clinic logo", "Shown at the top-left of the letterhead", ICON.image) +
                            uploadTile("signature", "Signature / stamp", "Printed above your name; a transparent PNG works best", ICON.pen) +
                        "</div>" +
                    "</fieldset>" +
                    '<div class="dr-form-actions">' +
                        '<button type="submit" class="dr-btn-primary" data-save>Save profile</button>' +
                        '<button type="button" class="dr-btn-ghost" data-discard>Discard changes</button>' +
                        '<span class="dr-form-status" data-form-status role="status"></span>' +
                    "</div>" +
                "</form>" +
                '<aside class="dr-preview" aria-label="Letterhead preview">' +
                    '<div class="dr-preview-label">Letterhead preview<span>updates as you type</span></div>' +
                    '<div class="dr-preview-paper" data-preview></div>' +
                    '<ul class="dr-checklist" data-checklist></ul>' +
                "</aside>" +
            "</div>" +
        "</div>";

    function profileInput(name, label, placeholder, extraClass, required, type) {
        return '<label class="dr-field ' + (extraClass || "") + '"><span class="dr-field-label">' +
            '<span>' + esc(label) + (required ? ' <span class="dr-req">*</span>' : "") + "</span>" +
            (required ? "" : "<small>optional</small>") + "</span>" +
            '<input name="' + name + '" type="' + (type || "text") + '" placeholder="' + esc(placeholder) + '"' +
            (required ? " required" : "") + ' autocomplete="off"></label>';
    }

    function uploadTile(kind, title, help, icon) {
        return '<div class="dr-upload" data-upload="' + kind + '">' +
            '<div class="dr-upload-thumb" data-thumb>' + icon + "</div>" +
            '<div class="dr-upload-text"><strong>' + esc(title) + "</strong>" +
                "<span>" + esc(help) + "</span><span>PNG, JPG or WEBP · up to 5 MB</span>" +
                '<div class="dr-upload-actions">' +
                    '<button type="button" class="dr-link" data-pick>Upload</button>' +
                    '<button type="button" class="dr-link dr-link--danger" data-remove hidden>Remove</button>' +
                "</div>" +
                '<input type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" tabindex="-1" aria-hidden="true">' +
            "</div>" +
        "</div>";
    }

    var profileToggle = profileCard.querySelector(".dr-profile-toggle");
    var profileBody = profileCard.querySelector(".dr-profile-body");
    var profileForm = profileCard.querySelector("form");
    var profileSummary = profileCard.querySelector("[data-summary]");
    var profileChip = profileCard.querySelector("[data-profile-chip]");
    var toggleText = profileCard.querySelector("[data-toggle-text]");
    var formStatus = profileCard.querySelector("[data-form-status]");
    var saveBtn = profileCard.querySelector("[data-save]");
    var previewHost = profileCard.querySelector("[data-preview]");
    var checklist = profileCard.querySelector("[data-checklist]");

    // Per image: a newly picked File, or a request to remove the saved one.
    var images = {
        logo: { file: null, remove: false, objectUrl: null },
        signature: { file: null, remove: false, objectUrl: null }
    };

    function setProfileOpen(open) {
        profileBody.hidden = !open;
        profileToggle.setAttribute("aria-expanded", String(open));
        toggleText.textContent = open ? "Hide" : (state.profile ? "Edit" : "Set up");
        if (open) requestAnimationFrame(fitPreview);
    }

    profileToggle.addEventListener("click", function () {
        setProfileOpen(profileBody.hidden);
    });

    function formValues() {
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
            profileChip.removeAttribute("data-tone");
            return;
        }
        if (p) {
            profileSummary.textContent = [p.doctor_name, p.clinic_name].filter(Boolean).join(" · ");
            profileChip.textContent = "Saved";
            profileChip.dataset.tone = "final";
        } else {
            profileSummary.textContent = "Add your name and clinic details for the prescription letterhead";
            profileChip.textContent = "Not set up";
            profileChip.dataset.tone = "draft";
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
        renderPreview();
    }

    function renderUpload(kind) {
        var tile = profileCard.querySelector('[data-upload="' + kind + '"]');
        var url = imageUrl(kind);
        var thumb = tile.querySelector("[data-thumb]");
        thumb.innerHTML = url ? '<img src="' + esc(url) + '" alt="">' : (kind === "logo" ? ICON.image : ICON.pen);
        tile.querySelector("[data-pick]").textContent = url ? "Replace" : "Upload";
        tile.querySelector("[data-remove]").hidden = !url;
    }

    function draftProfile() {
        var values = formValues();
        values.logo_url = imageUrl("logo");
        values.signature_url = imageUrl("signature");
        return values;
    }

    function renderPreview() {
        var p = draftProfile();
        previewHost.innerHTML =
            '<div class="rx-sheet">' +
                '<div class="rx-band"></div><div class="rx-band-gold"></div>' +
                Rx.letterheadHTML(p) +
                '<div class="rx-rule"></div>' +
                '<div class="rx-mini-lines"><i></i><i></i><i></i><i></i></div>' +
            "</div>";
        fitPreview();

        var items = [
            ["Doctor name", p.doctor_name],
            ["Qualifications", p.qualifications],
            ["Clinic name", p.clinic_name],
            ["Address", p.address],
            ["Phone", p.phone],
            ["Logo", p.logo_url],
            ["Signature", p.signature_url]
        ];
        checklist.innerHTML = items.map(function (item) {
            return '<li class="' + (item[1] ? "is-done" : "") + '">' + esc(item[0]) + "</li>";
        }).join("");
    }

    // The preview is a full-width (794 px) letterhead scaled to the panel.
    function fitPreview() {
        var sheet = previewHost.querySelector(".rx-sheet");
        if (!sheet || !previewHost.clientWidth) return;
        var scale = previewHost.clientWidth / 794;
        sheet.style.transform = "scale(" + scale + ")";
        previewHost.style.height = Math.ceil(sheet.offsetHeight * scale) + "px";
    }

    if (window.ResizeObserver) {
        new ResizeObserver(fitPreview).observe(previewHost);
    }

    profileForm.addEventListener("input", function (e) {
        if (e.target.type === "file") return;
        formStatus.textContent = "";
        renderPreview();
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
            renderPreview();
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
            renderPreview();
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
        if (tone) formStatus.dataset.tone = tone; else formStatus.removeAttribute("data-tone");
    }

    profileCard.querySelector("[data-discard]").addEventListener("click", function () {
        fillProfileForm();
        setFormStatus("");
        if (state.profile) setProfileOpen(false);
    });

    profileForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var values = formValues();
        var nameInput = profileForm.elements.namedItem("doctor_name");
        if (!values.doctor_name) {
            setFormStatus("Your name is required — it heads the letterhead.", "error");
            nameInput.focus();
            return;
        }

        var payload = new FormData();
        PROFILE_FIELDS.forEach(function (name) { payload.append(name, values[name]); });
        ["logo", "signature"].forEach(function (kind) {
            var img = images[kind];
            if (img.file) payload.append(kind, img.file, img.file.name);
            else if (img.remove) payload.append("remove_" + kind, "true");
        });

        saveBtn.disabled = true;
        saveBtn.classList.add("dr-btn-busy");
        setFormStatus("Saving…");

        requestJSON("/api/doctor/profile", { method: "POST", body: payload }).then(function (result) {
            state.profile = result.profile || null;
            fillProfileForm();
            renderProfileHeader();
            applyProfileEverywhere();
            setFormStatus("Profile saved. It's on your letterhead now.", "ok");
            setTimeout(function () {
                setProfileOpen(false);
                setFormStatus("");
            }, 900);
        }).catch(function (error) {
            setFormStatus(error.message || "The profile was not saved. Check your sign-in and try again.", "error");
        }).then(function () {
            saveBtn.disabled = false;
            saveBtn.classList.remove("dr-btn-busy");
        });
    });

    function loadProfile() {
        state.profileLoaded = false;
        renderProfileHeader();
        return requestJSON("/api/doctor/profile").then(function (result) {
            state.profile = result.profile || null;
        }).catch(function () {
            state.profile = null;
        }).then(function () {
            state.profileLoaded = true;
            fillProfileForm();
            renderProfileHeader();
            applyProfileEverywhere();
            // Open until the doctor has saved a profile; collapsed after.
            setProfileOpen(!state.profile);
        });
    }

    function applyProfileEverywhere() {
        sheet.setProfile(state.profile);
        // A fresh draft without a doctor's name takes the profile's.
        if (state.prescription && !state.prescription.doctor_name && state.profile) {
            state.prescription.doctor_name = state.profile.doctor_name;
            syncFromState();
        }
    }

    /* ============================================================
       3. GENERATE PRESCRIPTION (transcript panel)
    ============================================================ */

    var actions = el("div", "doctor-actions dr-only");
    actions.innerHTML =
        '<span class="doctor-actions-meta">' + ICON.shield + '<span data-model-note>Drafted by Mistral 128B · always reviewed by you</span></span>' +
        '<button type="button" class="dr-btn-primary" id="generatePrescriptionBtn" disabled>' +
            ICON.sparkles + "<span>Generate Prescription</span></button>";
    var generateBtn = actions.querySelector("#generatePrescriptionBtn");
    var generateLabel = generateBtn.querySelector("span");
    var modelNote = actions.querySelector("[data-model-note]");

    function renderGenerateButton() {
        var busy = state.status === "generating";
        generateBtn.disabled = busy || !currentTranscript() || recorderBusy();
        generateBtn.classList.toggle("dr-btn-busy", busy);
        generateLabel.textContent = busy
            ? "Drafting prescription…"
            : (state.prescription ? "Regenerate Prescription" : "Generate Prescription");
    }

    document.addEventListener("meetmind:transcript-state", renderGenerateButton);

    // The recorder button is disabled while a recording is being finalised
    // or a file uploads; Generate follows it.
    if (typeof recordBtn !== "undefined" && recordBtn && window.MutationObserver) {
        new MutationObserver(renderGenerateButton).observe(recordBtn, {
            attributes: true,
            attributeFilter: ["disabled"]
        });
    }

    // The label of the model the prescription is drafted with.
    fetch("/api/models", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : []; })
        .then(function (models) {
            var entry = (models || []).filter(function (m) { return m.key === PRESCRIPTION_MODEL; })[0];
            if (entry && entry.label) {
                state.modelLabel = entry.label;
                modelNote.textContent = "Drafted by " + entry.label + " · always reviewed by you";
            }
        }).catch(function () {});

    generateBtn.addEventListener("click", function () {
        var text = currentTranscript();
        if (!text) {
            status("Record or upload the consultation first.");
            return;
        }
        var proceed = Promise.resolve(true);
        if (state.prescription && D) {
            proceed = D.confirm({
                title: "Replace this prescription?",
                message: "A new AI draft will replace the prescription below, including any edits you made.",
                confirmText: "Generate new draft",
                danger: true
            });
        }
        proceed.then(function (ok) { if (ok) generate(text); });
    });

    function generate(text) {
        var epoch = state.epoch;
        var previous = { prescription: state.prescription, status: state.status };

        state.status = "generating";
        state.error = "";
        renderAll();
        rxCard.scrollIntoView({ behavior: "smooth", block: "start" });
        status("Drafting the prescription from the consultation…");

        requestJSON("/api/doctor/prescription", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                transcript: text,
                model: PRESCRIPTION_MODEL,
                consultation_id: state.consultationId
            })
        }).then(function (result) {
            if (epoch !== state.epoch) return;
            if (!result.success || !result.prescription) {
                throw new Error(result.error || "The prescription could not be generated.");
            }
            if (result.consultation_id) state.consultationId = result.consultation_id;
            var data = Rx.normalize(result.prescription);
            if (!data.visit_date) data.visit_date = Rx.formatDate(state.createdAt);
            if (!data.doctor_name && state.profile) data.doctor_name = state.profile.doctor_name;
            state.prescription = data;
            state.status = "draft";
            state.model = result.model || PRESCRIPTION_MODEL;
            state.updatedAt = new Date().toISOString();
            state.finalizedAt = null;
            state.editedSinceFinal = false;
            renderAll();
            fillForm();
            syncFromState();
            status("Prescription drafted. Review every detail, then download it.");
            emitConsultationChanged();
        }).catch(function (error) {
            if (epoch !== state.epoch) return;
            state.prescription = previous.prescription;
            state.status = previous.prescription ? previous.status : "error";
            state.error = error.message || "The prescription could not be generated.";
            renderAll();
            status(state.error);
            if (previous.prescription && D) {
                D.alert({ title: "Couldn't draft a new prescription", message: state.error });
            }
        });
    }

    /* ============================================================
       4. DOCTOR PRESCRIPTION — review & edit
    ============================================================ */

    var rxCard = el("section", "card dr-card dr-rx dr-only");
    rxCard.id = "prescriptionCard";
    rxCard.setAttribute("aria-labelledby", "drRxTitle");
    rxCard.innerHTML =
        '<div class="dr-card-head">' +
            '<div class="dr-card-title"><span class="dr-card-icon dr-card-icon--rx" aria-hidden="true">&#8478;</span>' +
                '<div><h2 id="drRxTitle">Doctor Prescription</h2>' +
                "<p>Review and correct everything the AI took from the consultation. Changes appear on the letterhead below.</p></div>" +
            "</div>" +
            '<span class="dr-status" data-rx-status>Not generated</span>' +
        "</div>" +
        '<div data-rx-empty class="dr-empty">' +
            '<span class="dr-empty-icon">&#8478;</span>' +
            "<strong>No prescription yet</strong>" +
            '<p data-empty-text>Record or upload the consultation, then click <b>Generate Prescription</b> under the transcript.</p>' +
        "</div>" +
        '<div data-rx-error class="dr-empty dr-empty--error" hidden>' +
            '<span class="dr-empty-icon">' + ICON.alert + "</span>" +
            "<strong>The prescription couldn't be drafted</strong>" +
            '<p data-error-text></p>' +
            '<button type="button" class="dr-btn-ghost" data-retry>Try again</button>' +
        "</div>" +
        '<div data-rx-loading class="dr-loading" hidden>' +
            '<div class="dr-loading-head">Reading the consultation and drafting the prescription…</div>' +
            '<div class="dr-loading-grid"><div class="dr-skel"></div><div class="dr-skel"></div>' +
                '<div class="dr-skel dr-skel--wide"></div><div class="dr-skel"></div><div class="dr-skel"></div></div>' +
        "</div>" +
        '<form data-rx-form novalidate hidden>' +
            '<div class="dr-safety">' + ICON.shield +
                "<span><strong>Draft for clinician review.</strong> The AI only copies what was said in the consultation — " +
                "confirm every diagnosis, vital sign, medicine and dose before issuing.</span></div>" +
            '<div class="dr-rx-grid" data-rx-grid></div>' +
            '<div class="dr-rx-foot"><span data-rx-meta></span>' +
                '<button type="button" class="dr-link" data-goto-download>Review the final page &amp; download ' + ICON.arrowDown + "</button></div>" +
        "</form>";

    var rxStatus = rxCard.querySelector("[data-rx-status]");
    var rxEmpty = rxCard.querySelector("[data-rx-empty]");
    var rxEmptyText = rxCard.querySelector("[data-empty-text]");
    var rxError = rxCard.querySelector("[data-rx-error]");
    var rxLoading = rxCard.querySelector("[data-rx-loading]");
    var rxForm = rxCard.querySelector("[data-rx-form]");
    var rxGrid = rxCard.querySelector("[data-rx-grid]");
    var rxMeta = rxCard.querySelector("[data-rx-meta]");
    var medBody = null;

    rxCard.querySelector("[data-retry]").addEventListener("click", function () {
        if (currentTranscript()) generate(currentTranscript());
    });

    rxCard.querySelector("[data-goto-download]").addEventListener("click", function () {
        downloadCard.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    function buildForm() {
        rxGrid.innerHTML = "";
        FORM_GROUPS.forEach(function (group) {
            var fs = el("fieldset", "dr-group" +
                (group.medicines ? " dr-group--wide" : "") +
                (group.alert ? " dr-group--alert" : "") +
                (group.single ? " dr-single" : ""));
            fs.appendChild(el("legend", null, esc(group.title)));

            if (group.medicines) {
                fs.innerHTML +=
                    '<div class="dr-med-wrap"><table class="dr-med-table"><thead><tr><th>#</th>' +
                    Rx.MEDICINE_FIELDS.map(function (f) { return "<th>" + Rx.MEDICINE_LABELS[f] + "</th>"; }).join("") +
                    '<th><span class="sr-only" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)">Remove</span></th></tr></thead>' +
                    "<tbody data-med-body></tbody></table></div>" +
                    '<button type="button" class="dr-add-med" data-add-med>+ Add medicine</button>';
                rxGrid.appendChild(fs);
                return;
            }

            var grid = el("div", group.single ? "" : "dr-grid");
            group.fields.forEach(function (f) {
                var name = f[0];
                var isArea = f[3] === "area";
                var label = el("label", "dr-field" + (isArea && !group.single ? " dr-span" : ""));
                if (!group.single) label.appendChild(el("span", "dr-field-label", "<span>" + esc(f[1]) + "</span>"));
                var input = isArea ? document.createElement("textarea") : document.createElement("input");
                input.name = name;
                if (isArea) input.rows = 2; else input.type = "text";
                if (f[2]) input.placeholder = f[2];
                if (group.single) input.setAttribute("aria-label", f[1]);
                label.appendChild(input);
                grid.appendChild(label);
            });
            fs.appendChild(grid);
            rxGrid.appendChild(fs);
        });
        medBody = rxGrid.querySelector("[data-med-body]");
        rxGrid.querySelector("[data-add-med]").addEventListener("click", function () {
            var med = {};
            Rx.MEDICINE_FIELDS.forEach(function (f) { med[f] = ""; });
            state.prescription.medicines.push(med);
            renderMedicineRows();
            syncFromState();
            onEdited();
            var last = medBody.querySelector('tr:last-child input[data-med-field="medicine"]');
            if (last) last.focus();
        });
    }

    function renderMedicineRows() {
        var meds = state.prescription ? state.prescription.medicines : [];
        medBody.innerHTML = "";
        if (!meds.length) {
            medBody.innerHTML = '<tr class="dr-med-empty"><td colspan="' + (Rx.MEDICINE_FIELDS.length + 2) +
                '">No medicines were mentioned in the consultation. Add one if you prescribed any.</td></tr>';
            return;
        }
        meds.forEach(function (med, index) {
            var tr = document.createElement("tr");
            var html = "<td>" + (index + 1) + "</td>";
            Rx.MEDICINE_FIELDS.forEach(function (f) {
                html += '<td><input type="text" data-med="' + index + '" data-med-field="' + f + '" value="' +
                    esc(med[f]) + '" aria-label="' + Rx.MEDICINE_LABELS[f] + " " + (index + 1) + '"></td>';
            });
            html += '<td><button type="button" class="dr-icon-btn" data-remove-med="' + index +
                '" aria-label="Remove medicine ' + (index + 1) + '" title="Remove">' + ICON.trash + "</button></td>";
            tr.innerHTML = html;
            medBody.appendChild(tr);
        });
    }

    function fillForm() {
        if (!state.prescription) return;
        var data = state.prescription;
        Rx.TEXT_FIELDS.forEach(function (name) {
            var input = rxForm.elements.namedItem(name);
            if (!input || document.activeElement === input) return;
            input.value = data[name] || "";
            if (input.tagName === "TEXTAREA") autoGrow(input);
        });
        var rows = medBody.querySelectorAll("tr:not(.dr-med-empty)").length;
        if (rows !== data.medicines.length) {
            renderMedicineRows();
        } else {
            medBody.querySelectorAll("[data-med-field]").forEach(function (input) {
                if (document.activeElement === input) return;
                var med = data.medicines[Number(input.dataset.med)];
                input.value = med ? med[input.dataset.medField] : "";
            });
        }
    }

    rxForm.addEventListener("input", function (e) {
        var t = e.target;
        if (!state.prescription) return;
        if (t.dataset.medField) {
            var med = state.prescription.medicines[Number(t.dataset.med)];
            if (med) med[t.dataset.medField] = t.value;
        } else if (t.name) {
            state.prescription[t.name] = t.value;
            if (t.tagName === "TEXTAREA") autoGrow(t);
        }
        syncFromState();
        onEdited();
    });

    rxForm.addEventListener("click", function (e) {
        var remove = e.target.closest("[data-remove-med]");
        if (!remove || !state.prescription) return;
        state.prescription.medicines.splice(Number(remove.dataset.removeMed), 1);
        renderMedicineRows();
        syncFromState();
        onEdited();
    });

    rxForm.addEventListener("submit", function (e) { e.preventDefault(); });

    function onEdited() {
        if (state.status === "final") state.editedSinceFinal = true;
        renderStatus();
        setSaveState("");
    }

    function renderStatus() {
        var text = "Not generated";
        var tone = null;
        if (state.status === "generating") {
            text = "Drafting…";
            tone = "busy";
        } else if (state.status === "final" && !state.editedSinceFinal) {
            text = "Final · downloaded " + fmtTime(state.finalizedAt);
            tone = "final";
        } else if (state.status === "final") {
            text = "Edited since download";
            tone = "draft";
        } else if (state.status === "draft") {
            text = "AI draft · review required";
            tone = "draft";
        } else if (state.status === "error") {
            text = "Not generated";
        }
        rxStatus.textContent = text;
        if (tone) rxStatus.dataset.tone = tone; else rxStatus.removeAttribute("data-tone");

        var label = state.model === PRESCRIPTION_MODEL || !state.model ? state.modelLabel : state.model;
        rxMeta.textContent = state.prescription
            ? "Drafted by " + label + (state.updatedAt ? " · last saved " + fmtTime(state.updatedAt) : "")
            : "";
    }

    /* ============================================================
       5. DOWNLOAD PRESCRIPTION — the letterhead page
    ============================================================ */

    var downloadCard = el("section", "card dr-card dr-download dr-only");
    downloadCard.id = "prescriptionDownloadCard";
    downloadCard.setAttribute("aria-labelledby", "drDownloadTitle");
    downloadCard.innerHTML =
        '<div class="dr-card-head">' +
            '<div class="dr-card-title"><span class="dr-card-icon">' + ICON.download + "</span>" +
                '<div><h2 id="drDownloadTitle">Download Prescription</h2>' +
                "<p>This is exactly how the PDF will look. Click any text on the page to make a final correction.</p></div>" +
            "</div>" +
            '<div class="dr-download-actions">' +
                '<span class="dr-save-state" data-save-state aria-live="polite"></span>' +
                '<button type="button" class="dr-btn-primary" data-download disabled>' + ICON.download + "<span>Download PDF</span></button>" +
            "</div>" +
        "</div>" +
        '<div data-download-empty class="dr-empty">' +
            '<span class="dr-empty-icon">' + ICON.download + "</span>" +
            "<strong>Your prescription will appear here on your letterhead</strong>" +
            "<p>Generate a prescription to preview it, make final corrections and download it as a PDF.</p>" +
        "</div>" +
        '<div class="dr-desk" data-desk hidden>' +
            '<div class="dr-desk-hint">' + ICON.pointer + "<span>Click to edit · Empty sections are left out of the PDF</span></div>" +
        "</div>";

    var desk = downloadCard.querySelector("[data-desk]");
    var downloadEmpty = downloadCard.querySelector("[data-download-empty]");
    var downloadBtn = downloadCard.querySelector("[data-download]");
    var downloadLabel = downloadBtn.querySelector("span");
    var saveState = downloadCard.querySelector("[data-save-state]");

    var sheet = Rx.createSheet({
        editable: true,
        onChange: function (data) {
            if (!state.prescription) return;
            state.prescription = data;
            fillForm();
            onEdited();
        },
        onEditProfile: function () {
            setProfileOpen(true);
            profileCard.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    });
    desk.appendChild(sheet.el);

    function syncFromState() {
        if (!state.prescription) return;
        sheet.setData(state.prescription, { consultationId: state.consultationId, createdAt: state.createdAt });
    }

    function setSaveState(text, tone) {
        saveState.textContent = text || "";
        if (tone) saveState.dataset.tone = tone; else saveState.removeAttribute("data-tone");
    }

    downloadBtn.addEventListener("click", function () {
        if (!state.prescription) return;
        var data = sheet.getData();
        var epoch = state.epoch;
        downloadBtn.disabled = true;
        downloadBtn.classList.add("dr-btn-busy");
        downloadLabel.textContent = "Preparing PDF…";
        setSaveState("");

        // Downloading is the doctor signing off: save this copy as final.
        var save = state.consultationId
            ? requestJSON("/api/doctor/consultations/" + encodeURIComponent(state.consultationId) + "/prescription", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prescription: data, final: true })
            }).then(function (result) { return { ok: true, result: result }; },
                function (error) { return { ok: false, error: error }; })
            : Promise.resolve({ ok: false, error: new Error("This consultation isn't saved to your history.") });

        save.then(function (saved) {
            if (saved.ok && epoch === state.epoch) {
                var p = saved.result.prescription || {};
                state.status = "final";
                state.finalizedAt = p.finalizedAt || new Date().toISOString();
                state.updatedAt = p.updatedAt || state.finalizedAt;
                state.editedSinceFinal = false;
                renderStatus();
                emitConsultationChanged();
            }
            return sheet.downloadPdf().then(function () {
                if (saved.ok) {
                    setSaveState("Saved to this consultation · " + fmtTime(state.finalizedAt), "ok");
                    status("Prescription downloaded and saved to the consultation.");
                } else {
                    setSaveState("Downloaded, but not saved: " + saved.error.message, "error");
                    status("The PDF was downloaded, but the prescription couldn't be saved to history.");
                }
            });
        }).catch(function (error) {
            setSaveState(error.message || "The PDF couldn't be created.", "error");
            if (D) D.alert({ title: "Couldn't create the PDF", message: error.message || "Please try again." });
        }).then(function () {
            downloadBtn.classList.remove("dr-btn-busy");
            downloadLabel.textContent = "Download PDF";
            renderAll();
        });
    });

    /* ============================================================
       RENDER
    ============================================================ */

    function renderAll() {
        var has = !!state.prescription;
        var generating = state.status === "generating";

        rxLoading.hidden = !generating;
        rxError.hidden = generating || state.status !== "error";
        rxForm.hidden = generating || !has;
        rxEmpty.hidden = generating || has || state.status === "error";
        rxCard.querySelector("[data-error-text]").textContent = state.error;
        rxEmptyText.innerHTML = currentTranscript()
            ? "The consultation is transcribed. Click <b>Generate Prescription</b> under the transcript to draft it."
            : "Record or upload the consultation, then click <b>Generate Prescription</b> under the transcript.";

        desk.hidden = !has;
        downloadEmpty.hidden = has;
        downloadBtn.disabled = !has || generating;

        renderStatus();
        renderGenerateButton();
    }

    /* ============================================================
       RESET / LOAD (bridge for index.html and history.js)
    ============================================================ */

    function resetDoctor() {
        state.epoch++;
        state.consultationId = null;
        state.createdAt = null;
        state.prescription = null;
        state.status = "none";
        state.model = null;
        state.updatedAt = null;
        state.finalizedAt = null;
        state.editedSinceFinal = false;
        state.error = "";
        setSaveState("");
        sheet.setData(Rx.empty(), { consultationId: null, createdAt: null });
        renderAll();
    }

    window.meetmindDoctor = {
        isActive: function () { return state.template === "doctor"; },

        currentId: function () { return state.consultationId; },

        isGenerating: function () { return state.status === "generating"; },

        /* A new live recording or upload is starting. */
        clearForNewRecording: resetDoctor,

        reset: resetDoctor,

        /* The recording just transcribed was saved as consultation `id`. */
        onTranscribed: function (info) {
            resetDoctor();
            state.consultationId = info && info.consultationId ? info.consultationId : null;
            state.createdAt = new Date().toISOString();
            renderAll();
            emitConsultationChanged();
        },

        /* Show a saved consultation (GET /api/doctor/consultations/{id}). */
        load: function (consultation) {
            resetDoctor();
            state.consultationId = consultation.id;
            state.createdAt = consultation.createdAt;
            if (consultation.doctorProfile && !state.profile) sheet.setProfile(consultation.doctorProfile);
            var p = consultation.prescription;
            if (p) {
                state.prescription = Rx.normalize(p);
                state.status = p.status === "final" ? "final" : "draft";
                state.model = p.model;
                state.updatedAt = p.updatedAt;
                state.finalizedAt = p.finalizedAt;
                fillForm();
                syncFromState();
            }
            renderAll();
        }
    };

    /* ============================================================
       MOUNT
    ============================================================ */

    var header = document.querySelector(".app-header");
    var transcriptPanel = document.querySelector(".panel--transcript");
    if (header && header.parentNode) header.parentNode.insertBefore(profileCard, header.nextSibling);

    var meetingActions = transcriptPanel && transcriptPanel.querySelector(".intelligence-actions");
    if (meetingActions) meetingActions.parentNode.insertBefore(actions, meetingActions.nextSibling);
    else if (transcriptPanel) transcriptPanel.appendChild(actions);

    if (transcriptPanel) {
        transcriptPanel.parentNode.insertBefore(downloadCard, transcriptPanel.nextSibling);
        transcriptPanel.parentNode.insertBefore(rxCard, transcriptPanel.nextSibling);
    }

    buildForm();
    renderProfileHeader();
    renderAll();
    applyTemplate("mom");
})();
