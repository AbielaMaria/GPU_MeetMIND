/* ============================================================
   MeetMind — mock app window widget behaviour
   - typing loop for every ".mock-window" on the page
   PLACEHOLDER script — fake meeting snippet, loops forever.
============================================================ */

(function () {

    var windows = document.querySelectorAll(".mock-window");
    if (!windows.length) return;

    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    var lines = [
        { spk: "Person A", text: "Let's lock the launch date — I'm proposing the 24th." },
        { spk: "Person B", text: "Works for me. I'll own the release notes by Friday." },
        { spk: "Person A", text: "Great. Dana, can you handle the customer email?" },
        { spk: "Person B", text: "Yes — I'll draft it today and send for review tomorrow." }
    ];

    var insights = [
        "Marcus to write the release notes — due Friday.",
        "Dana to draft the customer email — review tomorrow.",
        "Decision: launch date set to the 24th."
    ];

    function run(elT, elI) {
        if (reduce) {
            elT.innerHTML = lines.map(function (l) {
                return '<span class="spk">' + l.spk + ':</span> ' + l.text;
            }).join("<br>");
            if (elI) elI.textContent = insights[insights.length - 1];
            return;
        }

        var li = 0, ci = 0, insightIdx = 0;

        function tick() {
            var line = lines[li];
            var shown = lines.slice(0, li).map(function (l) {
                return '<span class="spk">' + l.spk + ':</span> ' + l.text;
            });

            var partial = line.text.slice(0, ci);
            shown.push('<span class="spk">' + line.spk + ':</span> ' + partial + '<span class="caret"></span>');
            elT.innerHTML = shown.join("<br>");

            ci++;

            if (ci > line.text.length) {
                li++;
                ci = 0;

                if (li % 2 === 0 && insightIdx < insights.length && elI) {
                    elI.textContent = insights[insightIdx++];
                }

                if (li >= lines.length) {
                    setTimeout(function () {
                        li = 0; ci = 0; insightIdx = 0;
                        if (elI) elI.innerHTML = "&nbsp;";
                        tick();
                    }, 2600);
                    return;
                }
                setTimeout(tick, 520);
                return;
            }

            setTimeout(tick, 34 + Math.random() * 34);
        }

        tick();
    }

    windows.forEach(function (win) {
        var elT = win.querySelector(".mock-transcript");
        var elI = win.querySelector(".mock-insight-text");
        if (elT) run(elT, elI);
    });

})();
