(function () {
    "use strict";

    var EVALUATIONS = ["Correct", "Partially Correct", "Incorrect", "Unable to Evaluate"];
    var LEVELS = ["Advanced", "Intermediate", "Beginner", "Not Demonstrated", "Insufficient Evidence"];
    var DECISIONS = ["", "Strongly recommend", "Recommend", "On hold", "Do not recommend"];
    var TYPES = ["Technical", "HR", "Behavioral", "Mixed"];
    var UNCLASSIFIED = "Unclassified";
    var SCORING_RULE = "Correct = 1, Partially Correct = 0.5, Incorrect = 0; " +
        "Unable to Evaluate is left out of the denominator";

    var ICON = {
        brief: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/><rect width="20" height="14" x="2" y="6" rx="2"/></svg>',
        pin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/></svg>',
        phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
        mail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>',
        globe: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>'
    };

    function str(value) {
        return value == null ? "" : String(value).trim();
    }

    function esc(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function para(value) {
        return esc(str(value)).replace(/\n/g, "<br>");
    }

    function list(value) {
        if (!Array.isArray(value)) return [];
        return value.map(function (item) {
            return typeof item === "object" && item ? str(item.text || item.description || item.point) : str(item);
        }).filter(Boolean);
    }

    function formatDate(iso) {
        var d = iso ? new Date(iso) : new Date();
        if (isNaN(d)) d = new Date();
        return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    }

    function formatDuration(seconds) {
        var total = Math.round(Number(seconds));
        if (!total || total < 0) return "";
        var h = Math.floor(total / 3600);
        var m = Math.floor((total % 3600) / 60);
        return h ? h + " h " + m + " min" : (m ? m + " min" : total + " sec");
    }

    function reportNumber(interviewId, createdAt) {
        if (!interviewId) return "";
        var d = createdAt ? new Date(createdAt) : new Date();
        var year = isNaN(d) ? new Date().getFullYear() : d.getFullYear();
        return "IV-" + year + "-" + String(interviewId).padStart(4, "0");
    }

    function fileName(report, interviewId, createdAt) {
        var parts = ["Interview_Evaluation"];
        var no = reportNumber(interviewId, createdAt);
        if (no) parts.push(no);
        var who = str(report && report.interview_details && report.interview_details.candidate_name)
            .replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "");
        if (who) parts.push(who);
        return parts.join("_") + ".pdf";
    }

    function skillList(skills) {
        var seen = {};
        return (Array.isArray(skills) ? skills : []).map(str).filter(function (s) {
            var key = s.toLowerCase();
            if (!s || seen[key] || key === UNCLASSIFIED.toLowerCase()) return false;
            seen[key] = true;
            return true;
        });
    }

    function parseSkills(text) {
        return skillList(String(text || "").split(/[,;\n]+/));
    }

    function score(c, p, i) {
        var judged = c + p + i;
        return judged ? Math.round((c + 0.5 * p) / judged * 100) : null;
    }

    function tally(rows) {
        var t = { correct: 0, partially_correct: 0, incorrect: 0, unable_to_evaluate: 0 };
        rows.forEach(function (r) {
            if (r.evaluation === "Correct") t.correct++;
            else if (r.evaluation === "Partially Correct") t.partially_correct++;
            else if (r.evaluation === "Incorrect") t.incorrect++;
            else t.unable_to_evaluate++;
        });
        return t;
    }

    function recompute(report) {
        var skills = report.interview_details.required_skills;
        var byFold = {};
        skills.forEach(function (s) { byFold[s.toLowerCase()] = s; });

        report.qa_analysis.forEach(function (q, i) {
            q.question_number = i + 1;
            q.related_skill = byFold[str(q.related_skill).toLowerCase()] || UNCLASSIFIED;
            if (EVALUATIONS.indexOf(q.evaluation) === -1) q.evaluation = "Unable to Evaluate";
        });

        var previous = {};
        (report.skill_assessment || []).forEach(function (s) {
            if (s && s.skill) previous[str(s.skill).toLowerCase()] = s;
        });

        report.skill_assessment = skills.map(function (skill) {
            var rows = report.qa_analysis.filter(function (q) { return q.related_skill === skill; });
            var t = tally(rows);
            var prev = previous[skill.toLowerCase()] || {};
            var level = LEVELS.indexOf(prev.proficiency_level) !== -1 ? prev.proficiency_level : null;
            if (!level) {
                level = !rows.length ? "Not Demonstrated" : "Insufficient Evidence";
            }
            return {
                skill: skill,
                questions_assessed: rows.length,
                correct: t.correct,
                partially_correct: t.partially_correct,
                incorrect: t.incorrect,
                unable_to_evaluate: t.unable_to_evaluate,
                score_percent: score(t.correct, t.partially_correct, t.incorrect),
                proficiency_level: level,
                evidence: str(prev.evidence)
            };
        });

        var totals = tally(report.qa_analysis);
        report.unclassified_questions = report.qa_analysis.filter(function (q) {
            return q.related_skill === UNCLASSIFIED;
        }).length;
        report.scoring = {
            total_questions: report.qa_analysis.length,
            correct: totals.correct,
            partially_correct: totals.partially_correct,
            incorrect: totals.incorrect,
            unable_to_evaluate: totals.unable_to_evaluate,
            score_percent: score(totals.correct, totals.partially_correct, totals.incorrect),
            scoring_rule: SCORING_RULE
        };
        return report;
    }

    function normalize(source) {
        source = source || {};
        var d = source.interview_details || {};
        var report = {
            interview_details: {
                candidate_name: str(d.candidate_name),
                interviewer_name: str(d.interviewer_name),
                position: str(d.position),
                interview_type: TYPES.indexOf(str(d.interview_type)) !== -1 ? str(d.interview_type) : "Technical",
                required_skills: skillList(d.required_skills)
            },
            interview_summary: str(source.interview_summary),
            qa_analysis: (Array.isArray(source.qa_analysis) ? source.qa_analysis : []).filter(function (q) {
                return q && typeof q === "object";
            }).map(function (q) {
                return {
                    question_number: 0,
                    question: str(q.question),
                    related_skill: str(q.related_skill) || UNCLASSIFIED,
                    participant_answer: str(q.participant_answer),
                    evaluation: str(q.evaluation),
                    correct_answer: str(q.correct_answer),
                    remarks: str(q.remarks)
                };
            }),
            skill_assessment: (Array.isArray(source.skill_assessment) ? source.skill_assessment : []).map(function (s) {
                return { skill: str(s && s.skill), proficiency_level: str(s && s.proficiency_level), evidence: str(s && s.evidence) };
            }),
            strengths: list(source.strengths),
            improvement_areas: list(source.improvement_areas),
            conclusion: str(source.conclusion),
            interviewer_decision: DECISIONS.indexOf(str(source.interviewer_decision)) !== -1 ? str(source.interviewer_decision) : "",
            interviewer_notes: str(source.interviewer_notes)
        };
        return recompute(report);
    }

    function toPayload(report) {
        var r = normalize(report);
        r.qa_analysis = r.qa_analysis.filter(function (q) { return q.question || q.participant_answer; });
        return recompute(r);
    }

    function verdictTone(evaluation) {
        return {
            "Correct": "correct",
            "Partially Correct": "partial",
            "Incorrect": "incorrect"
        }[evaluation] || "unknown";
    }

    function levelTone(level) {
        return {
            "Advanced": "advanced",
            "Intermediate": "intermediate",
            "Beginner": "beginner"
        }[level] || "none";
    }

    function decisionTone(decision) {
        return {
            "Strongly recommend": "strong",
            "Recommend": "yes",
            "On hold": "hold",
            "Do not recommend": "no"
        }[decision] || "";
    }

    function pct(value) {
        return value == null ? "—" : value + "%";
    }

    function letterheadHTML(profile) {
        profile = profile || {};
        var org = str(profile.organization_name);
        var name = str(profile.interviewer_name);
        var logo = profile.logo_url
            ? '<div class="ivr-logo ivr-logo--image"><img src="' + esc(profile.logo_url) + '" alt=""></div>'
            : '<div class="ivr-logo" aria-hidden="true">' + ICON.brief + "</div>";

        var lines = [];
        if (str(profile.address)) lines.push([ICON.pin, profile.address]);
        if (str(profile.phone)) lines.push([ICON.phone, profile.phone]);
        if (str(profile.email)) lines.push([ICON.mail, profile.email]);
        if (str(profile.website)) lines.push([ICON.globe, profile.website]);

        var role = [str(profile.designation), str(profile.department)].filter(Boolean).join(" · ");

        return '<header class="ivr-letterhead' + (org || name ? "" : " ivr-letterhead-empty") + '">' +
            '<div class="ivr-brand">' + logo +
                "<div>" +
                    '<h1 class="ivr-org">' + esc(org || name || "Your organisation") + "</h1>" +
                    (org && name ? '<div class="ivr-person">' + esc(name) + "</div>" : "") +
                    (role ? '<div class="ivr-role">' + esc(role) + "</div>" : "") +
                "</div>" +
            "</div>" +
            '<div class="ivr-contact">' +
                lines.map(function (l) {
                    return '<div class="ivr-contact-line"><span>' + esc(str(l[1])) + "</span>" + l[0] + "</div>";
                }).join("") +
            "</div>" +
        "</header>";
    }

    function detailCell(label, value) {
        return '<div class="ivr-detail"><span class="ivr-k">' + esc(label) + '</span><span class="ivr-v">' +
            (str(value) ? esc(value) : '<span class="ivr-muted">—</span>') + "</span></div>";
    }

    function scorePanelHTML(s) {
        var total = s.correct + s.partially_correct + s.incorrect + s.unable_to_evaluate;
        function seg(n, tone) {
            return n ? '<span class="ivr-bar-seg ivr-bar-seg--' + tone + '" data-flex="' + n + '"></span>' : "";
        }
        return '<section class="ivr-score" data-keep>' +
            '<div class="ivr-score-ring" data-p="' + (s.score_percent || 0) + '">' +
                '<div class="ivr-score-value">' + (s.score_percent == null ? "—" : s.score_percent + "<small>%</small>") + "</div>" +
                '<div class="ivr-score-label">Score</div>' +
            "</div>" +
            '<div class="ivr-score-body">' +
                '<div class="ivr-bar">' + (total
                    ? seg(s.correct, "correct") + seg(s.partially_correct, "partial") +
                      seg(s.incorrect, "incorrect") + seg(s.unable_to_evaluate, "unknown")
                    : '<span class="ivr-bar-seg ivr-bar-seg--empty" data-flex="1"></span>') + "</div>" +
                '<div class="ivr-legend">' +
                    '<span><b>' + s.total_questions + "</b> questions</span>" +
                    '<span class="ivr-dot ivr-dot--correct"><b>' + s.correct + "</b> correct</span>" +
                    '<span class="ivr-dot ivr-dot--partial"><b>' + s.partially_correct + "</b> partially correct</span>" +
                    '<span class="ivr-dot ivr-dot--incorrect"><b>' + s.incorrect + "</b> incorrect</span>" +
                    '<span class="ivr-dot ivr-dot--unknown"><b>' + s.unable_to_evaluate + "</b> not evaluable</span>" +
                "</div>" +
                '<p class="ivr-rule-note">Score: ' + esc(SCORING_RULE) + ".</p>" +
            "</div>" +
        "</section>";
    }

    function skillTableHTML(report) {
        if (!report.skill_assessment.length) return "";
        return '<section class="ivr-section">' +
            '<div class="ivr-label">Skill-wise assessment</div>' +
            '<table class="ivr-table"><thead><tr>' +
                "<th>Skill</th><th class=\"ivr-num\">Qs</th><th class=\"ivr-num\" title=\"Correct\">✓</th>" +
                "<th class=\"ivr-num\" title=\"Partially correct\">½</th><th class=\"ivr-num\" title=\"Incorrect\">✗</th>" +
                "<th class=\"ivr-num\">Score</th><th>Proficiency</th><th>Evidence</th>" +
            "</tr></thead><tbody>" +
            report.skill_assessment.map(function (s) {
                return '<tr data-keep><td class="ivr-strong">' + esc(s.skill) + "</td>" +
                    '<td class="ivr-num">' + s.questions_assessed + "</td>" +
                    '<td class="ivr-num">' + s.correct + "</td>" +
                    '<td class="ivr-num">' + s.partially_correct + "</td>" +
                    '<td class="ivr-num">' + s.incorrect + "</td>" +
                    '<td class="ivr-num ivr-strong">' + pct(s.score_percent) + "</td>" +
                    '<td><span class="ivr-level ivr-level--' + levelTone(s.proficiency_level) + '">' +
                        esc(s.proficiency_level) + "</span></td>" +
                    "<td>" + (s.evidence ? para(s.evidence) : '<span class="ivr-muted">—</span>') + "</td></tr>";
            }).join("") +
            "</tbody></table></section>";
    }

    function qaHTML(report) {
        if (!report.qa_analysis.length) {
            return '<section class="ivr-section"><div class="ivr-label">Question &amp; answer analysis</div>' +
                '<p class="ivr-muted">No interview questions were identified in the transcript.</p></section>';
        }
        return '<section class="ivr-section">' +
            '<div class="ivr-label">Question &amp; answer analysis</div>' +
            report.qa_analysis.map(function (q) {
                var tone = verdictTone(q.evaluation);
                return '<article class="ivr-qa ivr-qa--' + tone + '" data-keep>' +
                    '<div class="ivr-qa-head">' +
                        '<span class="ivr-qa-no">Q' + q.question_number + "</span>" +
                        '<span class="ivr-qa-skill">' + esc(q.related_skill) + "</span>" +
                        '<span class="ivr-verdict ivr-verdict--' + tone + '">' + esc(q.evaluation) + "</span>" +
                    "</div>" +
                    '<div class="ivr-qa-q">' + (q.question ? para(q.question) : '<span class="ivr-muted">Question not captured</span>') + "</div>" +
                    '<div class="ivr-qa-grid">' +
                        '<div><span class="ivr-k">Candidate\'s answer</span><p>' +
                            (q.participant_answer ? para(q.participant_answer) : '<span class="ivr-muted">No answer captured</span>') + "</p></div>" +
                        '<div><span class="ivr-k">' + (tone === "correct" ? "Reference answer" : "Expected answer") + "</span><p>" +
                            (q.correct_answer ? para(q.correct_answer) : '<span class="ivr-muted">—</span>') + "</p></div>" +
                    "</div>" +
                    (q.remarks ? '<div class="ivr-qa-remarks"><span class="ivr-k">Remarks</span><p>' + para(q.remarks) + "</p></div>" : "") +
                "</article>";
            }).join("") +
        "</section>";
    }

    function bulletsHTML(title, items, tone) {
        return '<div class="ivr-col ivr-col--' + tone + '" data-keep><div class="ivr-label">' + esc(title) + "</div>" +
            (items.length
                ? "<ul>" + items.map(function (x) { return "<li>" + para(x) + "</li>"; }).join("") + "</ul>"
                : '<p class="ivr-muted">None noted.</p>') +
        "</div>";
    }

    function sheetHTML(report, profile, ctx) {
        profile = profile || {};
        ctx = ctx || {};
        var d = report.interview_details;
        var no = reportNumber(ctx.interviewId, ctx.createdAt);
        var signer = str(profile.interviewer_name) || d.interviewer_name;
        var signerRole = [str(profile.designation), str(profile.organization_name)].filter(Boolean).join(" · ");

        return '<div class="ivr-band"></div>' +
            letterheadHTML(profile) +
            '<div class="ivr-titlebar">' +
                '<div><div class="ivr-title">Interview Evaluation Report</div>' +
                    '<div class="ivr-subtitle">' + esc(d.interview_type) + " interview" +
                        (d.position ? " · " + esc(d.position) : "") + "</div></div>" +
                '<div class="ivr-refs">' +
                    (no ? '<div><span class="ivr-k">Report No.</span> ' + esc(no) + "</div>" : "") +
                    '<div><span class="ivr-k">Date</span> ' + esc(formatDate(ctx.createdAt)) + "</div>" +
                "</div>" +
            "</div>" +
            '<div class="ivr-body">' +
                '<section class="ivr-details" data-keep>' +
                    detailCell("Candidate", d.candidate_name) +
                    detailCell("Position / role", d.position) +
                    detailCell("Interviewer", d.interviewer_name) +
                    detailCell("Interview type", d.interview_type) +
                    detailCell("Duration", formatDuration(ctx.durationSeconds)) +
                    detailCell("Questions assessed", String(report.scoring.total_questions)) +
                    '<div class="ivr-detail ivr-detail--wide"><span class="ivr-k">Required skills</span><span class="ivr-skills">' +
                        (d.required_skills.length
                            ? d.required_skills.map(function (s) { return '<span class="ivr-skill">' + esc(s) + "</span>"; }).join("")
                            : '<span class="ivr-muted">—</span>') +
                    "</span></div>" +
                "</section>" +
                scorePanelHTML(report.scoring) +
                (report.interviewer_decision || report.interviewer_notes
                    ? '<section class="ivr-decision ivr-decision--' + decisionTone(report.interviewer_decision) + '" data-keep>' +
                        '<div class="ivr-label">Interviewer\'s decision</div>' +
                        (report.interviewer_decision ? '<div class="ivr-decision-value">' + esc(report.interviewer_decision) + "</div>" : "") +
                        (report.interviewer_notes ? '<p>' + para(report.interviewer_notes) + "</p>" : "") +
                      "</section>"
                    : "") +
                (report.interview_summary
                    ? '<section class="ivr-section" data-keep><div class="ivr-label">Summary</div><p>' + para(report.interview_summary) + "</p></section>"
                    : "") +
                skillTableHTML(report) +
                qaHTML(report) +
                '<section class="ivr-cols">' +
                    bulletsHTML("Strengths", report.strengths, "good") +
                    bulletsHTML("Areas for improvement", report.improvement_areas, "work") +
                "</section>" +
                (report.conclusion
                    ? '<section class="ivr-section" data-keep><div class="ivr-label">Conclusion</div><p>' + para(report.conclusion) + "</p></section>"
                    : "") +
                '<div class="ivr-sign" data-keep>' +
                    '<div class="ivr-signature">' +
                        '<div class="ivr-signature-img">' +
                            (profile.signature_url ? '<img src="' + esc(profile.signature_url) + '" alt="Signature">' : "") + "</div>" +
                        '<div class="ivr-signature-line"></div>' +
                        '<div class="ivr-signature-name">' + esc(signer || "Interviewer") + "</div>" +
                        (signerRole ? '<div class="ivr-signature-sub">' + esc(signerRole) + "</div>" : "") +
                    "</div>" +
                "</div>" +
            "</div>" +
            '<footer class="ivr-footer">' +
                "<span>AI-assisted evaluation by <strong>Vidatha</strong> from the interview transcript, " +
                "reviewed by the interviewer. Verify before using it in a hiring decision.</span>" +
                "<span>" + esc([str(profile.organization_name), str(profile.website || profile.email)].filter(Boolean).join(" · ")) + "</span>" +
            "</footer>";
    }

    function createSheet() {
        var root = document.createElement("article");
        root.className = "ivr-sheet";
        var report = normalize({});
        var profile = null;
        var context = { interviewId: null, createdAt: null, durationSeconds: null };

        function render() {
            root.innerHTML = sheetHTML(report, profile, context);
            root.querySelectorAll("[data-flex]").forEach(function (el) {
                el.style.flex = el.getAttribute("data-flex");
            });
            root.querySelectorAll("[data-p]").forEach(function (el) {
                el.style.setProperty("--p", el.getAttribute("data-p"));
            });
        }

        render();

        return {
            el: root,
            setData: function (next, ctx) {
                report = normalize(next);
                if (ctx) {
                    context.interviewId = ctx.interviewId || null;
                    context.createdAt = ctx.createdAt || null;
                    context.durationSeconds = ctx.durationSeconds || null;
                }
                render();
            },
            setProfile: function (next) {
                profile = next || null;
                render();
            },
            fileName: function () { return fileName(report, context.interviewId, context.createdAt); },
            downloadPdf: function (name) {
                return exportPdf(root, name || fileName(report, context.interviewId, context.createdAt));
            }
        };
    }

    function waitForImages(node) {
        return Promise.all(Array.prototype.map.call(node.querySelectorAll("img"), function (img) {
            if (img.complete) return Promise.resolve();
            return new Promise(function (resolve) {
                img.addEventListener("load", resolve, { once: true });
                img.addEventListener("error", resolve, { once: true });
            });
        }));
    }

    function exportPdf(sheetEl, name) {
        if (!window.html2canvas || !window.jspdf || !window.jspdf.jsPDF) {
            return Promise.reject(new Error("The PDF library didn't load. Refresh the page and try again."));
        }

        var holder = document.createElement("div");
        holder.style.cssText = "position:fixed;left:-12000px;top:0;width:794px;pointer-events:none;";
        var clone = sheetEl.cloneNode(true);
        clone.classList.add("ivr-sheet--export");
        clone.style.transform = "none";
        holder.appendChild(clone);
        document.body.appendChild(holder);

        var fontsReady = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
        var keeps = [];

        return Promise.all([fontsReady, waitForImages(clone)]).then(function () {
            var top = clone.getBoundingClientRect().top;
            keeps = Array.prototype.map.call(clone.querySelectorAll("[data-keep]"), function (node) {
                var r = node.getBoundingClientRect();
                return { start: r.top - top, end: r.bottom - top };
            });
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
            var pxPerMm = canvas.width / pageW;
            var ratio = canvas.width / clone.offsetWidth;
            var marginPx = Math.round(10 * pxPerMm);
            var fullPagePx = Math.floor(pageH * pxPerMm);

            var y = 0;
            var page = 0;
            while (y < canvas.height - 2) {
                var room = page ? fullPagePx - 2 * marginPx : fullPagePx - marginPx;
                var end = Math.min(canvas.height, y + room);
                if (end < canvas.height) {
                    keeps.forEach(function (k) {
                        var s = k.start * ratio;
                        var e = k.end * ratio;
                        if (s < end && e > end && s > y + room * 0.3) end = Math.min(end, Math.floor(s) - 4);
                    });
                }
                var slice = document.createElement("canvas");
                slice.width = canvas.width;
                slice.height = end - y;
                var ctx = slice.getContext("2d");
                ctx.fillStyle = "#ffffff";
                ctx.fillRect(0, 0, slice.width, slice.height);
                ctx.drawImage(canvas, 0, y, canvas.width, slice.height, 0, 0, canvas.width, slice.height);
                if (page) pdf.addPage();
                pdf.addImage(slice.toDataURL("image/jpeg", 0.93), "JPEG", 0, page ? 10 : 0,
                    pageW, slice.height / pxPerMm);
                pdf.setFontSize(8);
                pdf.setTextColor(140);
                pdf.text(String(page + 1), pageW - 12, pageH - 6);
                y = end;
                page++;
            }
            pdf.setProperties({ title: name.replace(/\.pdf$/i, ""), creator: "Vidatha" });
            pdf.save(name);
        }).finally(function () {
            holder.remove();
        });
    }

    window.MeetMindInterviewReport = {
        EVALUATIONS: EVALUATIONS,
        LEVELS: LEVELS,
        DECISIONS: DECISIONS,
        TYPES: TYPES,
        UNCLASSIFIED: UNCLASSIFIED,
        SCORING_RULE: SCORING_RULE,
        normalize: normalize,
        recompute: recompute,
        toPayload: toPayload,
        parseSkills: parseSkills,
        reportNumber: reportNumber,
        fileName: fileName,
        formatDate: formatDate,
        verdictTone: verdictTone,
        levelTone: levelTone,
        letterheadHTML: letterheadHTML,
        createSheet: createSheet,
        exportPdf: exportPdf
    };
})();
