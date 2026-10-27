/* ============================================================
   MeetMind — prescription sheet
   ------------------------------------------------------------
   Renders a consultation's prescription as an A4 letterhead page
   (styles: assets/prescription.css) and turns it into a PDF.

   The fields are exactly the ones the backend extracts
   (meeting_intelligence.DOCTOR_PRESCRIPTION_FIELDS) and stores
   (database.doctor_prescriptions); the letterhead comes from the
   doctor's saved profile (/api/doctor/profile).

     var sheet = MeetMindRx.createSheet({
         editable: true,                 // click-to-edit text
         onChange: function (data) {},   // after any edit in the sheet
         onEditProfile: function () {}   // letterhead clicked
     });
     host.appendChild(sheet.el);
     sheet.setProfile(profile);          // or null
     sheet.setData(prescription, { consultationId: 4, createdAt: iso });
     sheet.getData();                    // current values
     sheet.downloadPdf();                // -> Promise

   Used by assets/doctor-template.js (recorder page) and
   assets/admin.js (read-only viewer).
============================================================ */

(function () {
    "use strict";

    var TEXT_FIELDS = [
        "patient_name", "age_sex", "visit_date", "doctor_name",
        "chief_complaint", "symptoms_history", "allergies",
        "temperature", "blood_pressure", "pulse_rate", "spo2",
        "examination_findings", "diagnosis", "tests_advised",
        "advice", "warning_signs", "next_visit"
    ];

    var MEDICINE_FIELDS = ["medicine", "dose", "route", "frequency", "duration", "instructions"];

    var MEDICINE_LABELS = {
        medicine: "Medicine",
        dose: "Dose",
        route: "Route",
        frequency: "Frequency",
        duration: "Duration",
        instructions: "Instructions"
    };

    var ICON = {
        cross: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M9.5 3h5a1 1 0 0 1 1 1v4.5H20a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-4.5V20a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1v-4.5H4a1 1 0 0 1-1-1v-5a1 1 0 0 1 1-1h4.5V4a1 1 0 0 1 1-1Z"/></svg>',
        pin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>',
        phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92Z"/></svg>',
        mail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/></svg>',
        clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',
        alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
        calendar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/><path d="m9 16 2 2 4-4"/></svg>'
    };

    function esc(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function str(value) {
        return value == null ? "" : String(value).trim();
    }

    /* A blank prescription with every field the backend knows. */
    function empty() {
        var data = {};
        TEXT_FIELDS.forEach(function (name) { data[name] = ""; });
        data.medicines = [];
        return data;
    }

    /* Copy of `source` holding only known fields, all strings. */
    function normalize(source) {
        var data = empty();
        source = source || {};
        TEXT_FIELDS.forEach(function (name) { data[name] = str(source[name]); });
        (Array.isArray(source.medicines) ? source.medicines : []).forEach(function (item) {
            if (!item || typeof item !== "object") return;
            var med = {};
            MEDICINE_FIELDS.forEach(function (f) { med[f] = str(item[f]); });
            data.medicines.push(med);
        });
        return data;
    }

    function formatDate(value) {
        var d = value ? new Date(value) : new Date();
        if (isNaN(d)) return "";
        return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
    }

    /* "RX-2026-0042" from the consultation id and the year it was recorded. */
    function rxNumber(consultationId, createdAt) {
        if (!consultationId) return "";
        var d = createdAt ? new Date(createdAt) : new Date();
        var year = isNaN(d) ? new Date().getFullYear() : d.getFullYear();
        return "RX-" + year + "-" + String(consultationId).padStart(4, "0");
    }

    function fileName(data, consultationId, createdAt) {
        var parts = ["Prescription"];
        var rx = rxNumber(consultationId, createdAt);
        if (rx) parts.push(rx);
        var patient = str(data && data.patient_name).replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "");
        if (patient) parts.push(patient);
        return parts.join("_") + ".pdf";
    }

    /* ---- letterhead (also used for the profile card's live preview) ---- */

    function letterheadHTML(profile) {
        profile = profile || {};
        var name = str(profile.doctor_name);
        var logo = profile.logo_url
            ? '<div class="rx-logo rx-logo--image"><img src="' + esc(profile.logo_url) + '" alt=""></div>'
            : '<div class="rx-logo" aria-hidden="true">' + ICON.cross + "</div>";

        var lines = [];
        if (str(profile.address)) lines.push([ICON.pin, profile.address]);
        if (str(profile.phone)) lines.push([ICON.phone, profile.phone]);
        if (str(profile.email)) lines.push([ICON.mail, profile.email]);
        if (str(profile.timings)) lines.push([ICON.clock, profile.timings]);

        return '<header class="rx-letterhead' + (name ? "" : " rx-letterhead-empty") + '">' +
            '<div class="rx-brand">' + logo +
                "<div>" +
                    '<h1 class="rx-doctor">' + esc(name || "Your name here") + "</h1>" +
                    (str(profile.qualifications) ? '<div class="rx-quals">' + esc(profile.qualifications) + "</div>" : "") +
                    (str(profile.specialization) ? '<div class="rx-spec">' + esc(profile.specialization) + "</div>" : "") +
                "</div>" +
            "</div>" +
            '<div class="rx-clinic">' +
                (str(profile.clinic_name) ? '<div class="rx-clinic-name">' + esc(profile.clinic_name) + "</div>" : "") +
                lines.map(function (l) {
                    return '<div class="rx-clinic-line"><span>' + esc(str(l[1])) + "</span>" + l[0] + "</div>";
                }).join("") +
            "</div>" +
        "</header>";
    }

    /* ---- the sheet ---- */

    function field(name, placeholder, extraClass) {
        return '<span class="rx-field ' + (extraClass || "") + '" data-field="' + name + '" data-placeholder="' +
            esc(placeholder) + '"></span>';
    }

    function section(name, label, placeholder, strong) {
        return '<section class="rx-section" data-section="' + name + '">' +
            '<div class="rx-label">' + esc(label) + "</div>" +
            '<div class="rx-field rx-text' + (strong ? " rx-text--strong" : "") + '" data-field="' + name +
                '" data-placeholder="' + esc(placeholder) + '" data-multiline="1"></div>' +
        "</section>";
    }

    function vitalChip(name, label, placeholder) {
        return '<span class="rx-chip" data-chip="' + name + '">' +
            '<span class="rx-chip-k">' + esc(label) + "</span>" + field(name, placeholder) + "</span>";
    }

    function sheetHTML() {
        return '<div class="rx-band"></div><div class="rx-band-gold"></div>' +
            '<div class="rx-glow"></div>' +
            '<div class="rx-watermark" aria-hidden="true">&#8478;</div>' +
            '<div class="rx-letterhead-slot"></div>' +
            '<div class="rx-rule"></div>' +
            '<div class="rx-body">' +
                '<div class="rx-patient">' +
                    '<div class="rx-patient-cell"><span class="rx-k">Patient</span>' + field("patient_name", "Patient name", "rx-v") + "</div>" +
                    '<div class="rx-patient-cell"><span class="rx-k">Age / Sex</span>' + field("age_sex", "e.g. 45 / M", "rx-v") + "</div>" +
                    '<div class="rx-patient-cell"><span class="rx-k">Date</span>' + field("visit_date", "Visit date", "rx-v") + "</div>" +
                    '<div class="rx-patient-cell"><span class="rx-k">Rx No.</span><span class="rx-v rx-rxno" data-rxno></span></div>' +
                "</div>" +
                '<div class="rx-flags">' +
                    '<span class="rx-chip rx-chip--allergy" data-chip="allergies">' + ICON.alert +
                        '<span class="rx-chip-k">Allergies</span>' + field("allergies", "None stated") + "</span>" +
                    vitalChip("temperature", "Temp", "—") +
                    vitalChip("blood_pressure", "BP", "—") +
                    vitalChip("pulse_rate", "Pulse", "—") +
                    vitalChip("spo2", "SpO₂", "—") +
                "</div>" +
                section("chief_complaint", "Chief complaints", "Main symptoms and how long they have lasted") +
                section("symptoms_history", "History", "Associated symptoms, relevant history") +
                section("examination_findings", "Examination", "Findings on examination") +
                section("diagnosis", "Diagnosis", "Diagnosis as stated by the doctor", true) +
                '<div class="rx-meds">' +
                    '<div class="rx-meds-head"><span class="rx-symbol" aria-hidden="true">&#8478;</span>' +
                        '<span class="rx-meds-title">Medicines prescribed</span></div>' +
                    '<div class="rx-table-wrap"><table class="rx-table"><thead><tr><th>#</th>' +
                        MEDICINE_FIELDS.map(function (f) { return "<th>" + MEDICINE_LABELS[f] + "</th>"; }).join("") +
                        '<th class="rx-edit-only"></th></tr></thead><tbody data-meds></tbody></table></div>' +
                    '<button type="button" class="rx-add-med rx-edit-only">+ Add medicine</button>' +
                "</div>" +
                '<div class="rx-cols" data-cols>' +
                    section("tests_advised", "Investigations", "Tests advised") +
                    section("advice", "Advice", "Advice given to the patient") +
                "</div>" +
                '<div class="rx-alert" data-box="warning_signs">' +
                    '<div class="rx-label">Return immediately if</div>' +
                    '<div class="rx-field rx-text" data-field="warning_signs" data-placeholder="Warning signs" data-multiline="1"></div>' +
                "</div>" +
                '<div class="rx-next" data-box="next_visit">' +
                    '<span class="rx-next-icon">' + ICON.calendar + "</span>" +
                    '<div><div class="rx-label">Next visit</div>' +
                    '<div class="rx-field rx-text" data-field="next_visit" data-placeholder="Follow-up" data-multiline="1"></div></div>' +
                "</div>" +
                '<div class="rx-sign">' +
                    '<div class="rx-stamp">Clinic<br>seal</div>' +
                    '<div class="rx-signature">' +
                        '<div class="rx-signature-img" data-signature></div>' +
                        '<div class="rx-signature-line"></div>' +
                        field("doctor_name", "Doctor's name") +
                        '<div class="rx-signature-sub" data-signature-sub></div>' +
                    "</div>" +
                "</div>" +
            "</div>" +
            '<footer class="rx-footer">' +
                "<span>Generated by <strong>Vidatha</strong> from the consultation transcript. " +
                "Valid only after review and signature by the doctor.</span>" +
                '<span data-footer-contact></span>' +
            "</footer>" +
            '<div class="rx-footer-band"></div>';
    }

    function setPlainText(node, value) {
        node.textContent = value || "";
    }

    function readText(node) {
        // innerText keeps the line breaks typed with Enter.
        return (node.innerText || node.textContent || "").replace(/ /g, " ").replace(/\n{3,}/g, "\n\n").trim();
    }

    function makeEditable(node) {
        node.setAttribute("contenteditable", "plaintext-only");
        if (node.contentEditable !== "plaintext-only") node.setAttribute("contenteditable", "true");
        node.setAttribute("spellcheck", "true");
        node.setAttribute("role", "textbox");
        if (node.dataset.multiline) node.setAttribute("aria-multiline", "true");
        if (node.dataset.placeholder) node.setAttribute("aria-label", node.dataset.placeholder);
    }

    function createSheet(options) {
        options = options || {};
        var editable = !!options.editable;

        var root = document.createElement("article");
        root.className = "rx-sheet" + (editable ? " is-editable" : "");
        root.innerHTML = sheetHTML();

        var data = empty();
        var profile = null;
        var context = { consultationId: null, createdAt: null };

        var medsBody = root.querySelector("[data-meds]");
        var addMedBtn = root.querySelector(".rx-add-med");

        // Unlike getData(), keeps a just-added blank medicine row, so
        // whatever mirrors the sheet shows that row too.
        function emitChange() {
            if (options.onChange) options.onChange(normalize(data));
        }

        function refreshEmptyFlags() {
            root.querySelectorAll("[data-section]").forEach(function (s) {
                s.classList.toggle("is-empty", !data[s.dataset.section]);
            });
            root.querySelectorAll("[data-box]").forEach(function (b) {
                b.classList.toggle("is-empty", !data[b.dataset.box]);
            });
            var flagsEmpty = true;
            root.querySelectorAll("[data-chip]").forEach(function (c) {
                var isEmpty = !data[c.dataset.chip];
                c.classList.toggle("is-empty", isEmpty);
                if (!isEmpty) flagsEmpty = false;
            });
            root.querySelector(".rx-flags").classList.toggle("is-empty", flagsEmpty);
            root.querySelector("[data-cols]").classList.toggle("is-empty", !data.tests_advised && !data.advice);
        }

        function renderMedicines() {
            medsBody.innerHTML = "";
            var meds = data.medicines;
            if (!meds.length) {
                var tr = document.createElement("tr");
                tr.className = "rx-table-empty";
                tr.innerHTML = '<td colspan="' + (MEDICINE_FIELDS.length + 2) + '">' +
                    (editable ? "No medicines yet — add one below." : "No medicines were prescribed in this consultation.") +
                    "</td>";
                medsBody.appendChild(tr);
                return;
            }
            meds.forEach(function (med, index) {
                var tr = document.createElement("tr");
                var html = '<td class="rx-num">' + (index + 1) + "</td>";
                MEDICINE_FIELDS.forEach(function (f) {
                    html += '<td><span class="rx-field' + (f === "medicine" ? " rx-med-name" : "") +
                        '" data-med="' + index + '" data-med-field="' + f + '" data-placeholder="' +
                        (f === "medicine" ? "Medicine" : "—") + '"></span></td>';
                });
                html += '<td class="rx-row-tools rx-edit-only"><button type="button" class="rx-row-remove" data-remove="' +
                    index + '" aria-label="Remove ' + esc(med.medicine || "this medicine") + '" title="Remove">&times;</button></td>';
                tr.innerHTML = html;
                tr.querySelectorAll("[data-med-field]").forEach(function (cell) {
                    setPlainText(cell, med[cell.dataset.medField]);
                    if (editable) makeEditable(cell);
                });
                medsBody.appendChild(tr);
            });
        }

        function renderLetterhead() {
            root.querySelector(".rx-letterhead-slot").innerHTML = letterheadHTML(profile);

            var sig = root.querySelector("[data-signature]");
            sig.innerHTML = profile && profile.signature_url
                ? '<img src="' + esc(profile.signature_url) + '" alt="Signature">'
                : "";
            var sub = [profile && profile.qualifications, profile && profile.specialization]
                .map(str).filter(Boolean).join(" · ");
            root.querySelector("[data-signature-sub]").textContent = sub;
            var contact = profile ? [str(profile.clinic_name), str(profile.phone)].filter(Boolean).join(" · ") : "";
            root.querySelector("[data-footer-contact]").textContent = contact;
        }

        function renderFields() {
            root.querySelectorAll("[data-field]").forEach(function (node) {
                setPlainText(node, data[node.dataset.field]);
            });
            var rxNode = root.querySelector("[data-rxno]");
            rxNode.textContent = rxNumber(context.consultationId, context.createdAt) || "—";
            renderMedicines();
            refreshEmptyFlags();
        }

        if (editable) {
            root.querySelectorAll("[data-field]").forEach(makeEditable);

            root.addEventListener("input", function (e) {
                var node = e.target.closest("[data-field], [data-med-field]");
                if (!node) return;
                var value = readText(node);
                if (node.dataset.field) {
                    data[node.dataset.field] = value;
                } else {
                    var med = data.medicines[Number(node.dataset.med)];
                    if (med) med[node.dataset.medField] = value;
                }
                // An emptied field shows its placeholder again.
                if (!value && node.innerHTML !== "") node.innerHTML = "";
                refreshEmptyFlags();
                emitChange();
            });

            root.addEventListener("keydown", function (e) {
                var node = e.target.closest && e.target.closest("[data-field], [data-med-field]");
                if (node && e.key === "Enter" && !node.dataset.multiline) {
                    e.preventDefault();
                    node.blur();
                }
            });

            root.addEventListener("paste", function (e) {
                var node = e.target.closest && e.target.closest("[contenteditable]");
                if (!node || node.getAttribute("contenteditable") === "plaintext-only") return;
                e.preventDefault();
                var text = (e.clipboardData || window.clipboardData).getData("text/plain");
                document.execCommand("insertText", false, text);
            });

            root.addEventListener("click", function (e) {
                var remove = e.target.closest("[data-remove]");
                if (remove) {
                    data.medicines.splice(Number(remove.dataset.remove), 1);
                    renderMedicines();
                    emitChange();
                    return;
                }
                if (e.target.closest(".rx-letterhead") && options.onEditProfile) {
                    options.onEditProfile();
                }
            });

            addMedBtn.addEventListener("click", function () {
                var med = {};
                MEDICINE_FIELDS.forEach(function (f) { med[f] = ""; });
                data.medicines.push(med);
                renderMedicines();
                emitChange();
                var first = medsBody.querySelector('tr:last-child [data-med-field="medicine"]');
                if (first) first.focus();
            });
        }

        function getData() {
            var copy = normalize(data);
            copy.medicines = copy.medicines.filter(function (m) {
                return MEDICINE_FIELDS.some(function (f) { return m[f]; });
            });
            return copy;
        }

        function setData(prescription, ctx) {
            data = normalize(prescription);
            if (ctx) {
                context.consultationId = ctx.consultationId || null;
                context.createdAt = ctx.createdAt || null;
            }
            renderFields();
        }

        function setProfile(next) {
            profile = next || null;
            renderLetterhead();
        }

        function downloadPdf(name) {
            return exportPdf(root, name || fileName(getData(), context.consultationId, context.createdAt));
        }

        setProfile(null);
        renderFields();

        return {
            el: root,
            setData: setData,
            setProfile: setProfile,
            getData: getData,
            downloadPdf: downloadPdf,
            fileName: function () { return fileName(getData(), context.consultationId, context.createdAt); }
        };
    }

    /* ---- PDF ------------------------------------------------- */

    function waitForImages(node) {
        var images = Array.prototype.slice.call(node.querySelectorAll("img"));
        return Promise.all(images.map(function (img) {
            if (img.complete) return Promise.resolve();
            return new Promise(function (resolve) {
                img.addEventListener("load", resolve, { once: true });
                img.addEventListener("error", resolve, { once: true });
            });
        }));
    }

    /*
     * Renders a copy of the sheet at full A4 width (no editing outlines,
     * no empty sections) and saves it as an A4 PDF. A prescription longer
     * than one page continues on further pages.
     */
    function exportPdf(sheetEl, name) {
        if (!window.html2canvas || !window.jspdf || !window.jspdf.jsPDF) {
            return Promise.reject(new Error("The PDF library didn't load. Refresh the page and try again."));
        }

        var holder = document.createElement("div");
        holder.style.cssText = "position:fixed;left:-12000px;top:0;width:794px;pointer-events:none;";
        var clone = sheetEl.cloneNode(true);
        clone.classList.remove("is-editable");
        clone.classList.add("rx-sheet--export");
        clone.querySelectorAll("[contenteditable]").forEach(function (n) { n.removeAttribute("contenteditable"); });
        clone.querySelectorAll(".rx-table-empty td").forEach(function (td) {
            td.textContent = "No medicines were prescribed in this consultation.";
        });
        holder.appendChild(clone);
        document.body.appendChild(holder);

        var fontsReady = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();

        return Promise.all([fontsReady, waitForImages(clone)]).then(function () {
            return window.html2canvas(clone, {
                scale: 2,
                backgroundColor: "#ffffff",
                useCORS: true,
                logging: false,
                windowWidth: 794
            });
        }).then(function (canvas) {
            var pdf = new window.jspdf.jsPDF({ unit: "mm", format: "a4", orientation: "portrait" });
            var pageW = 210;
            var pageH = 297;
            var pagePx = Math.floor(canvas.width * pageH / pageW);

            if (canvas.height <= pagePx + 4) {
                pdf.addImage(canvas.toDataURL("image/jpeg", 0.95), "JPEG", 0, 0, pageW, canvas.height * pageW / canvas.width);
            } else if (canvas.height <= pagePx * 1.15) {
                // Just over one page: shrink it onto one page rather than
                // pushing the signature or footer onto a page of its own.
                var fitW = pageW * pagePx / canvas.height;
                pdf.addImage(canvas.toDataURL("image/jpeg", 0.95), "JPEG", (pageW - fitW) / 2, 0, fitW, pageH);
            } else {
                for (var y = 0, page = 0; y < canvas.height; y += pagePx, page++) {
                    var slice = document.createElement("canvas");
                    slice.width = canvas.width;
                    slice.height = Math.min(pagePx, canvas.height - y);
                    var ctx = slice.getContext("2d");
                    ctx.fillStyle = "#ffffff";
                    ctx.fillRect(0, 0, slice.width, slice.height);
                    ctx.drawImage(canvas, 0, y, canvas.width, slice.height, 0, 0, canvas.width, slice.height);
                    if (page) pdf.addPage();
                    pdf.addImage(slice.toDataURL("image/jpeg", 0.95), "JPEG", 0, 0, pageW, slice.height * pageW / canvas.width);
                }
            }
            pdf.setProperties({ title: name.replace(/\.pdf$/i, ""), creator: "Vidatha" });
            pdf.save(name);
        }).finally(function () {
            holder.remove();
        });
    }

    window.MeetMindRx = {
        TEXT_FIELDS: TEXT_FIELDS,
        MEDICINE_FIELDS: MEDICINE_FIELDS,
        MEDICINE_LABELS: MEDICINE_LABELS,
        empty: empty,
        normalize: normalize,
        formatDate: formatDate,
        rxNumber: rxNumber,
        fileName: fileName,
        letterheadHTML: letterheadHTML,
        createSheet: createSheet,
        exportPdf: exportPdf
    };
})();
