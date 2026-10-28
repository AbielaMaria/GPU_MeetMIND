(function () {

    var root = document.getElementById("templates");
    if (!root) return;

    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    var PAPER_WIDTH = 520;
    var HOLD_MS = 4000;

    function icon(paths) {
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
            'stroke-linejoin="round" aria-hidden="true">' + paths + "</svg>";
    }

    var ARROW = icon('<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>');

    var ORDER = ["mom", "doctor", "interview"];

    var T = {
        mom: {
            label: "Meeting (MOM)",
            icon: icon('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'),
            title: "Q4 Roadmap Sync",
            duration: "32:14",
            chunks: [
                "Okay, let’s go through the roadmap. ",
                "I think we’re all agreed that we <mark data-to=\"d1\">ship the beta on 14 November</mark>. ",
                "<mark data-to=\"a1\">Arjun, can you finish the export API by Friday?</mark> ",
                "Yes, that’s the last blocker on my side. ",
                "<mark data-to=\"a2\">Meera, can you draft the release notes by next Wednesday?</mark> ",
                "Sure. Honestly, we should <mark data-to=\"d2\">drop the Teams plugin from this release</mark>, it’s not ready. ",
                "Agreed, let’s move it to December."
            ],
            doc:
                '<div class="ts-paper"><span class="ts-sample">SAMPLE</span>' +
                    '<div class="ts-lh"><div><div class="ts-lh-name">Minutes of Meeting</div>' +
                        '<div class="ts-lh-sub">Q4 Roadmap Sync · 32 min</div></div><span class="ts-badge">MOM</span></div>' +
                    "<h4>Summary</h4>" +
                    '<p data-f="sum">The team confirmed the beta date and trimmed scope to protect it. The export API and the release notes are the remaining blockers.</p>' +
                    "<h4>Decisions</h4>" +
                    '<ul><li data-f="d1">Beta ships on 14 November</li>' +
                        '<li data-f="d2">Teams plugin moved out of this release (target: December)</li></ul>' +
                    "<h4>Action items</h4>" +
                    '<div class="ts-task" data-f="a1"><span class="ts-chk"></span><span>Finish the export API</span><span class="ts-own">Arjun · by Friday</span></div>' +
                    '<div class="ts-task" data-f="a2"><span class="ts-chk"></span><span>Draft the release notes</span><span class="ts-own">Meera · by next Wednesday</span></div>' +
                    "<h4>Mind map</h4>" +
                    '<div class="ts-mindmap" data-f="mm">' +
                        '<div class="ts-mm-root">Q4 Roadmap Sync</div>' +
                        '<div class="ts-mm-branches">' +
                            '<div class="ts-mm-col"><div class="ts-mm-node ts-mm-branch">Decisions</div>' +
                                '<div class="ts-mm-node">Beta ships 14 November</div>' +
                                '<div class="ts-mm-node">Teams plugin moved to December</div></div>' +
                            '<div class="ts-mm-col"><div class="ts-mm-node ts-mm-branch">Action items</div>' +
                                '<div class="ts-mm-node">Finish the export API</div>' +
                                '<div class="ts-mm-node ts-mm-sub">Arjun · by Friday</div>' +
                                '<div class="ts-mm-node">Draft the release notes</div>' +
                                '<div class="ts-mm-node ts-mm-sub">Meera · by next Wednesday</div></div>' +
                            '<div class="ts-mm-col"><div class="ts-mm-node ts-mm-branch">Blockers</div>' +
                                '<div class="ts-mm-node">Export API</div>' +
                                '<div class="ts-mm-node">Release notes</div></div>' +
                        "</div>" +
                    "</div>" +
                "</div>"
        },
        doctor: {
            label: "Doctor–Patient",
            icon: icon('<path d="M11 2v2"/><path d="M5 2v2"/><path d="M5 3H4a2 2 0 0 0-2 2v4a6 6 0 0 0 12 0V5a2 2 0 0 0-2-2h-1"/><path d="M8 15a6 6 0 0 0 12 0v-3"/><circle cx="20" cy="10" r="2"/>'),
            title: "Consultation",
            duration: "06:48",
            chunks: [
                "So when did the fever start, and is there any cough? ",
                "Since Monday. <mark data-to=\"cc\">Fever and a dry cough, and a runny nose</mark>. ",
                "Okay, this <mark data-to=\"dx\">looks like a viral infection</mark>. ",
                "<mark data-to=\"r1\">Take paracetamol 500 mg twice a day after meals, for three days</mark>, ",
                "and <mark data-to=\"r2\">cetirizine 10 mg once at night for five days</mark> for the cold. ",
                "<mark data-to=\"adv\">Drink plenty of fluids and rest, and come back if the fever lasts beyond three days.</mark>"
            ],
            doc:
                '<div class="ts-paper"><span class="ts-sample">SAMPLE</span>' +
                    '<div class="ts-lh"><div><div class="ts-lh-name">Dr. A. Rao</div>' +
                        '<div class="ts-lh-sub">MBBS, MD · General Medicine</div></div>' +
                        '<div class="ts-lh-right">Sunrise Family Clinic<br>12 Sample Road, Example City</div></div>' +
                    '<div class="ts-meta">Patient: <b>R. Kumar</b> &nbsp;·&nbsp; Age / Sex: 34 / M</div>' +
                    "<h4>Chief complaints</h4>" +
                    '<p data-f="cc">Fever and dry cough for 2 days, with a runny nose</p>' +
                    "<h4>Diagnosis</h4>" +
                    '<p data-f="dx">Viral upper respiratory tract infection</p>' +
                    '<div class="ts-rx-head"><span class="ts-rx-symbol" aria-hidden="true">&#8478;</span><h4>Medicines prescribed</h4></div>' +
                    '<div class="ts-rx ts-rx--head"><span>Medicine</span><span>Dosage</span><span>Duration</span></div>' +
                    '<div class="ts-rx" data-f="r1"><b>Paracetamol 500 mg</b><span>1-0-1 · after meals</span><span>3 days</span></div>' +
                    '<div class="ts-rx" data-f="r2"><b>Cetirizine 10 mg</b><span>0-0-1 · at night</span><span>5 days</span></div>' +
                    "<h4>Advice</h4>" +
                    '<p data-f="adv">Plenty of fluids and rest. Review if the fever lasts beyond 3 days.</p>' +
                    '<div class="ts-sig"><div><em>A. Rao</em>Doctor’s signature</div></div>' +
                "</div>"
        },
        interview: {
            label: "Interview",
            icon: icon('<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>'),
            title: "Technical round",
            duration: "24:05",
            chunks: [
                "How would you find duplicate emails in a users table? ",
                "<mark data-to=\"sql\">Group by email, having count greater than one, with an index on email</mark>. ",
                "Good. Walk me through designing a URL shortener. ",
                "<mark data-to=\"sd\">A single table and a hash of the URL…</mark> I haven’t really thought about scaling it. ",
                "Tell me about your Python experience. ",
                "In my last role <mark data-to=\"py\">I built our Python ETL pipeline with asyncio</mark>."
            ],
            doc:
                '<div class="ts-paper"><span class="ts-sample">SAMPLE</span>' +
                    '<div class="ts-lh"><div><div class="ts-lh-name">Acme Software</div>' +
                        '<div class="ts-lh-sub">Interview Evaluation Report</div></div>' +
                        '<div class="ts-lh-right">Interviewer: K. Menon</div></div>' +
                    '<div class="ts-meta">Candidate: <b>S. Iyer</b> &nbsp;·&nbsp; Backend Engineer &nbsp;·&nbsp; Technical</div>' +
                    "<h4>Score</h4>" +
                    '<div class="ts-score" data-f="ov"><span class="ts-score-value">83%</span>' +
                        '<span class="ts-meta">3 questions · 2 correct · 1 partially correct</span></div>' +
                    "<h4>Skill-wise assessment</h4>" +
                    '<div class="ts-skill" data-f="sql"><span>SQL<small>Advanced</small></span><div class="ts-bar"><i data-w="100"></i></div><b>100%</b></div>' +
                    '<div class="ts-skill" data-f="sd"><span>System design<small>Beginner</small></span><div class="ts-bar"><i data-w="50"></i></div><b>50%</b></div>' +
                    '<div class="ts-skill" data-f="py"><span>Python<small>Advanced</small></span><div class="ts-bar"><i data-w="100"></i></div><b>100%</b></div>' +
                    "<h4>Strengths</h4>" +
                    '<p data-f="str">Hands-on Python and SQL, with production experience.</p>' +
                    "<h4>Improvement areas</h4>" +
                    '<p data-f="imp">Scaling and system design.</p>' +
                    "<h4>Interviewer’s decision</h4>" +
                    '<div data-f="dec"><span class="ts-decision">Recommend</span></div>' +
                    '<div class="ts-sig"><div><em>K. Menon</em>Interviewer</div></div>' +
                "</div>"
        }
    };

    var tabsEl = root.querySelector("[data-ts-tabs]");
    var titleEl = root.querySelector("[data-ts-title]");
    var durationEl = root.querySelector("[data-ts-duration]");
    var textEl = root.querySelector("[data-ts-text]");
    var labelEl = root.querySelector("[data-ts-label]");
    var statusEl = root.querySelector("[data-ts-status]");
    var replayBtn = root.querySelector("[data-ts-replay]");
    var docEl = root.querySelector("[data-ts-doc]");
    var ctaEl = root.querySelector("[data-ts-cta]");
    var gridEl = root.querySelector(".ts-grid");

    var current = ORDER[0];
    var runId = 0;
    var timer = null;
    var inView = false;
    var hovering = false;
    var paperHeight = 0;

    tabsEl.innerHTML = ORDER.map(function (key) {
        return '<button type="button" class="ts-tab" role="tab" data-key="' + key + '">' +
            T[key].icon + T[key].label + "</button>";
    }).join("");

    tabsEl.addEventListener("click", function (e) {
        var tab = e.target.closest(".ts-tab");
        if (tab) play(tab.dataset.key);
    });

    tabsEl.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        e.preventDefault();
        var step = e.key === "ArrowRight" ? 1 : ORDER.length - 1;
        var next = ORDER[(ORDER.indexOf(current) + step) % ORDER.length];
        play(next);
        tabsEl.querySelector('[data-key="' + next + '"]').focus();
    });

    function measurePapers() {
        var probe = document.createElement("div");
        probe.style.cssText = "position:absolute;left:-9999px;top:0;visibility:hidden;width:" + PAPER_WIDTH + "px";
        root.appendChild(probe);
        paperHeight = 0;
        ORDER.forEach(function (key) {
            probe.innerHTML = T[key].doc;
            paperHeight = Math.max(paperHeight, probe.firstChild.offsetHeight);
        });
        probe.remove();
    }

    function fitPaper() {
        var scaler = docEl.querySelector(".ts-scaler");
        if (!scaler) return;
        var k = Math.min(1, docEl.clientWidth / PAPER_WIDTH);
        scaler.style.transform = "scale(" + k + ")";
        docEl.style.height = Math.ceil(paperHeight * k) + "px";
    }

    function setStatus(text, done) {
        statusEl.classList.toggle("is-done", !!done);
        statusEl.querySelector("span").textContent = text;
    }

    function render(key) {
        var t = T[key];
        current = key;

        tabsEl.querySelectorAll(".ts-tab").forEach(function (tab) {
            var on = tab.dataset.key === key;
            tab.setAttribute("aria-selected", String(on));
            tab.tabIndex = on ? 0 : -1;
        });

        titleEl.textContent = t.title + " · Transcript";
        durationEl.textContent = t.duration;
        labelEl.textContent = t.label;
        textEl.innerHTML = "";

        docEl.innerHTML = '<div class="ts-scaler">' + t.doc + "</div>";
        fitPaper();

        ctaEl.href = "/sign-up?next=" + encodeURIComponent("/app?template=" + key);
        ctaEl.innerHTML = "Try the " + t.label + " template " + ARROW;

        setStatus("Transcribing…");
    }

    function field(name) {
        return docEl.querySelector('[data-f="' + name + '"]');
    }

    function showFinished() {
        textEl.innerHTML = T[current].chunks.join("");
        docEl.querySelectorAll("[data-f]").forEach(function (f) { f.classList.add("is-filled"); });
        setStatus("Ready to review & download", true);
    }

    function appendChunk(html) {
        var span = document.createElement("span");
        span.className = "ts-chunk";
        span.innerHTML = html;
        textEl.appendChild(span);
    }

    function flyPhrase(mark, target) {
        var from = mark.getBoundingClientRect();
        var to = target.getBoundingClientRect();
        var ghost = document.createElement("div");
        ghost.className = "ts-ghost";
        ghost.setAttribute("aria-hidden", "true");
        ghost.textContent = mark.textContent;
        ghost.style.left = from.left + "px";
        ghost.style.top = from.top + "px";
        document.body.appendChild(ghost);
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                ghost.style.transform = "translate(" + (to.left - from.left) + "px," + (to.top - from.top) + "px) scale(.8)";
                ghost.style.opacity = ".15";
            });
        });
        setTimeout(function () { ghost.remove(); }, 820);
    }

    function stop() {
        runId++;
        clearTimeout(timer);
        document.querySelectorAll(".ts-ghost").forEach(function (g) { g.remove(); });
    }

    function buildSteps(t) {
        var steps = [function () { return 500; }];

        t.chunks.forEach(function (html) {
            steps.push(function () {
                appendChunk(html);
                return 650;
            });
        });

        steps.push(function () {
            setStatus("Extracting details…");
            return 500;
        });

        var phrases = t.chunks.join("").match(/data-to="[^"]+"/g) || [];
        phrases.forEach(function (attr) {
            var name = attr.slice(9, -1);
            var mark;
            steps.push(function () {
                mark = textEl.querySelector('mark[data-to="' + name + '"]');
                mark.classList.add("is-hot");
                return 350;
            });
            steps.push(function () {
                flyPhrase(mark, field(name));
                return 820;
            });
            steps.push(function () {
                field(name).classList.add("is-filled");
                mark.classList.remove("is-hot");
                return 300;
            });
        });

        steps.push(function () {
            setStatus("Generating the rest of the document…");
            return 300;
        });

        var rest = (t.doc.match(/data-f="/g) || []).length - phrases.length;
        for (var i = 0; i < rest; i++) {
            steps.push(function () {
                docEl.querySelector("[data-f]:not(.is-filled)").classList.add("is-filled");
                return 450;
            });
        }

        steps.push(function () {
            setStatus("Ready to review & download", true);
            return HOLD_MS;
        });

        return steps;
    }

    function play(key) {
        stop();
        render(key);

        if (reduce) {
            showFinished();
            return;
        }

        var id = runId;
        var steps = buildSteps(T[key]);
        var i = 0;

        function next() {
            if (id !== runId) return;
            if (i === steps.length) {
                if (hovering) {
                    timer = setTimeout(next, 500);
                    return;
                }
                play(ORDER[(ORDER.indexOf(key) + 1) % ORDER.length]);
                return;
            }
            var wait = steps[i++]();
            if (id === runId) timer = setTimeout(next, wait);
        }

        next();
    }

    replayBtn.addEventListener("click", function () { play(current); });

    gridEl.addEventListener("mouseenter", function () { hovering = true; });
    gridEl.addEventListener("mouseleave", function () { hovering = false; });

    measurePapers();
    render(current);
    if (reduce) showFinished();

    function resume() {
        if (inView && !document.hidden) play(current);
    }

    if ("IntersectionObserver" in window) {
        new IntersectionObserver(function (entries) {
            var visible = entries[entries.length - 1].isIntersecting;
            if (visible === inView) return;
            inView = visible;
            if (inView) resume();
            else stop();
        }, { threshold: 0.25 }).observe(root);
    } else {
        inView = true;
        resume();
    }

    document.addEventListener("visibilitychange", function () {
        if (document.hidden) stop();
        else resume();
    });

    window.addEventListener("resize", fitPaper);

    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(function () {
            measurePapers();
            fitPaper();
        });
    }

})();
