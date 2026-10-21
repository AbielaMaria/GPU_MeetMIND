/* ============================================================
   MeetMind — recording player
   ------------------------------------------------------------
   A small, self-contained player for recordings stored in the
   database (GET /api/meetings/{id}/audio,
   /api/doctor/consultations/{id}/audio and
   /api/interview/interviews/{id}/audio — all answer HTTP Range
   requests, so seeking works without downloading everything).
   Options: { teal: true } (consultations), { indigo: true }
   (interviews).

   Controls: play / pause, back 10 s, forward 10 s, a seek bar
   (with buffered progress), elapsed / total time, playback speed
   and a download link. Keyboard, while focus is in the player:
   Space or K play/pause, ← / → 10 s, Home / End.

   Usage:
       var player = MeetMindAudioPlayer.create({ teal: true });
       container.appendChild(player.el);
       player.load("/api/meetings/12/audio", {
           title: "Meeting recording",
           meta: "MP3 · 1.2 MB",
           downloadName: "meeting_12.mp3"
       });
       player.clear();   // stop and hide
============================================================ */

(function () {
    "use strict";

    var SKIP_SECONDS = 10;
    var SPEEDS = [1, 1.25, 1.5, 2, 0.75];

    var ICONS = {
        wave: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/></svg>',
        play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.14v13.72a1 1 0 0 0 1.52.85l10.9-6.86a1 1 0 0 0 0-1.7L9.52 4.29A1 1 0 0 0 8 5.14Z"/></svg>',
        pause: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4.5" width="4" height="15" rx="1.2"/><rect x="14" y="4.5" width="4" height="15" rx="1.2"/></svg>',
        loading: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.2-8.56"/></svg>',
        back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>',
        forward: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/></svg>',
        volume: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>',
        muted: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="m23 9-6 6"/><path d="m17 9 6 6"/></svg>',
        download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>'
    };

    function el(tag, className, html) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (html != null) node.innerHTML = html;
        return node;
    }

    function button(className, label, html) {
        var b = el("button", "mm-player-btn " + className, html);
        b.type = "button";
        b.setAttribute("aria-label", label);
        b.title = label;
        return b;
    }

    /* 75 -> "1:15", 3725 -> "1:02:05" */
    function fmt(seconds) {
        if (!isFinite(seconds) || seconds < 0) return "0:00";
        var total = Math.floor(seconds);
        var h = Math.floor(total / 3600);
        var m = Math.floor((total % 3600) / 60);
        var s = total % 60;
        var mm = h ? String(m).padStart(2, "0") : String(m);
        return (h ? h + ":" : "") + mm + ":" + String(s).padStart(2, "0");
    }

    function fmtBytes(bytes) {
        var n = Number(bytes);
        if (!n) return "";
        if (n < 1024 * 1024) return Math.max(1, Math.round(n / 1024)) + " KB";
        return (n / (1024 * 1024)).toFixed(1) + " MB";
    }

    var EXT_BY_MIME = {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/mp4": "m4a",
        "audio/aac": "aac",
        "audio/flac": "flac",
        "audio/ogg": "ogg",
        "audio/webm": "webm"
    };

    /* filename="meeting_12.mp3" from a Content-Disposition header, or "". */
    function dispositionName(header) {
        var match = /filename="?([^";]+)"?/i.exec(header || "");
        return match ? match[1].trim() : "";
    }

    /* Read a fetch() response to a Blob, reporting progress (0–1). */
    function readWithProgress(response, onProgress) {
        var total = Number(response.headers.get("Content-Length")) || 0;
        if (!response.body || !response.body.getReader || !total) {
            return response.blob();
        }
        var reader = response.body.getReader();
        var chunks = [];
        var received = 0;
        function pump() {
            return reader.read().then(function (step) {
                if (step.done) {
                    if (received < total) throw new Error("incomplete");
                    return new Blob(chunks, { type: response.headers.get("Content-Type") || "" });
                }
                chunks.push(step.value);
                received += step.value.length;
                onProgress(received / total);
                return pump();
            });
        }
        return pump();
    }

    function create(options) {
        options = options || {};

        var root = el("div", "mm-player" + (options.teal ? " mm-player--teal" : "") +
            (options.indigo ? " mm-player--indigo" : ""));
        root.setAttribute("role", "group");
        root.setAttribute("aria-label", "Recording player");
        root.dataset.state = "idle";
        root.hidden = true;

        var audio = document.createElement("audio");
        audio.preload = "metadata";

        /* head */
        var head = el("div", "mm-player-head");
        head.appendChild(el("span", "mm-player-icon", ICONS.wave));
        var titles = el("div", "mm-player-titles");
        var titleEl = el("span", "mm-player-title");
        var metaEl = el("span", "mm-player-meta");
        titles.appendChild(titleEl);
        titles.appendChild(metaEl);
        head.appendChild(titles);
        var download = el("a", "mm-player-download",
            ICONS.download + '<span class="mm-player-download-text">Download</span>');
        download.setAttribute("aria-label", "Download recording");
        head.appendChild(download);

        /* controls */
        var controls = el("div", "mm-player-controls");
        var backBtn = button("mm-player-skip", "Back " + SKIP_SECONDS + " seconds",
            ICONS.back + "<span>" + SKIP_SECONDS + "</span>");
        var playBtn = button("mm-player-play", "Play", ICONS.play);
        var fwdBtn = button("mm-player-skip", "Forward " + SKIP_SECONDS + " seconds",
            ICONS.forward + "<span>" + SKIP_SECONDS + "</span>");
        var currentEl = el("span", "mm-player-time", "0:00");
        currentEl.setAttribute("aria-label", "Elapsed time");

        var track = el("div", "mm-player-track");
        track.appendChild(el("span", "mm-player-rail"));
        var buffered = el("span", "mm-player-buffered");
        var played = el("span", "mm-player-played");
        track.appendChild(buffered);
        track.appendChild(played);
        var range = el("input", "mm-player-range");
        range.type = "range";
        range.min = "0";
        range.max = "0";
        range.step = "any";
        range.value = "0";
        range.disabled = true;
        range.setAttribute("aria-label", "Seek");
        track.appendChild(range);

        var durationEl = el("span", "mm-player-time", "0:00");
        durationEl.setAttribute("aria-label", "Total time");
        var speedBtn = button("mm-player-speed", "Playback speed", "1×");
        var muteBtn = button("mm-player-mute", "Mute", ICONS.volume);

        [backBtn, playBtn, fwdBtn, currentEl, track, durationEl, speedBtn, muteBtn].forEach(function (n) {
            controls.appendChild(n);
        });

        var statusEl = el("div", "mm-player-status");
        statusEl.setAttribute("aria-live", "polite");

        root.appendChild(audio);
        root.appendChild(head);
        root.appendChild(controls);
        root.appendChild(statusEl);

        var speedIndex = 0;
        var seeking = false;
        var downloadName = "";
        var downloadMime = "";
        var downloading = null;   // the download in progress: { cancelled }

        /* Download: the page fetches the file itself, over the same
           connection playback already uses, then saves the finished Blob.
           Handing the link to the browser's download manager instead
           failed intermittently on this HTTPS deployment: its separate
           request sometimes never reached the server, the Save dialog
           showed "All files" (no response, so no type) and the download
           ended in "Check internet connection". */
        var downloadText = download.querySelector(".mm-player-download-text");

        /* Other Download buttons on the page (e.g. next to Upload
           Recording) follow this player through onDownloadState(fn):
           fn({ available, busy, percent, error }) on every change. */
        var downloadListeners = [];
        var downloadState = { available: false, busy: false, percent: 0, error: "" };

        function setDownloadState(changes) {
            for (var key in changes) downloadState[key] = changes[key];
            var snapshot = {
                available: downloadState.available,
                busy: downloadState.busy,
                percent: downloadState.percent,
                error: downloadState.error
            };
            downloadListeners.forEach(function (fn) {
                try { fn(snapshot); } catch (e) { /* a listener's bug is its own */ }
            });
        }

        function setDownloadText(text) {
            downloadText.textContent = text;
        }

        function finishDownload(job, message) {
            if (downloading !== job) return;
            downloading = null;
            download.removeAttribute("aria-busy");
            download.classList.remove("is-busy");
            setDownloadText("Download");
            if (message != null) statusEl.textContent = message;
            setDownloadState({ busy: false, percent: 0, error: message || "" });
        }

        function saveBlob(blob, name) {
            var url = URL.createObjectURL(blob);
            var link = document.createElement("a");
            link.href = url;
            link.download = name;
            link.style.display = "none";
            document.body.appendChild(link);
            link.click();
            link.remove();
            // Long enough for the browser to start writing the file.
            setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
        }

        function fetchRecording(href, job, attempt) {
            return fetch(href, { credentials: "same-origin", cache: "no-store" })
                .then(function (response) {
                    if (job.cancelled) return null;
                    if (response.status === 401) throw new Error("signed-out");
                    if (response.status === 403) throw new Error("forbidden");
                    if (response.status === 404) throw new Error("missing");
                    if (!response.ok) throw new Error("http-" + response.status);
                    var name = dispositionName(response.headers.get("Content-Disposition"));
                    return readWithProgress(response, function (fraction) {
                        if (job.cancelled) return;
                        var percent = Math.floor(fraction * 100);
                        setDownloadText(percent + "%");
                        setDownloadState({ percent: percent });
                    }).then(function (blob) {
                        return { blob: blob, name: name };
                    });
                })
                .catch(function (error) {
                    var known = /^(signed-out|forbidden|missing|http-)/.test(error && error.message);
                    // A dropped connection is retried once before giving up.
                    if (!known && attempt < 2 && !job.cancelled) {
                        return fetchRecording(href, job, attempt + 1);
                    }
                    throw error;
                });
        }

        /* Download the loaded recording. Resolves true once the file has
           been handed to the browser to save, false if it failed, was
           cancelled, or nothing is loaded. */
        function startDownload() {
            if (downloading || !download.getAttribute("href")) return Promise.resolve(false);
            var job = { cancelled: false };
            downloading = job;
            download.setAttribute("aria-busy", "true");
            download.classList.add("is-busy");
            setDownloadText("0%");
            statusEl.textContent = "";
            setDownloadState({ busy: true, percent: 0, error: "" });

            return fetchRecording(download.getAttribute("href"), job, 1)
                .then(function (result) {
                    if (!result || job.cancelled) return false;
                    var ext = EXT_BY_MIME[(result.blob.type || downloadMime).split(";")[0]] || "mp3";
                    var name = result.name || ((downloadName || "recording").replace(/\.[a-z0-9]+$/i, "") + "." + ext);
                    saveBlob(result.blob, name);
                    finishDownload(job, "");
                    return true;
                })
                .catch(function (error) {
                    var reason = error && error.message;
                    finishDownload(job,
                        reason === "signed-out" ? "Your session has ended. Sign in again to download this recording." :
                        reason === "forbidden" ? "You don't have access to this recording." :
                        reason === "missing" ? "This recording is no longer stored." :
                        "Couldn't download the recording. Check the connection to the MeetMind server and try again.");
                    return false;
                });
        }

        download.addEventListener("click", function (e) {
            e.preventDefault();
            startDownload();
        });

        function cancelDownload() {
            if (!downloading) return;
            downloading.cancelled = true;
            finishDownload(downloading, null);
        }

        function duration() {
            var d = audio.duration;
            return isFinite(d) && d > 0 ? d : 0;
        }

        function setState(state) {
            root.dataset.state = state;
            var playing = state === "playing";
            playBtn.innerHTML = state === "loading" ? ICONS.loading : (playing ? ICONS.pause : ICONS.play);
            playBtn.setAttribute("aria-label", playing ? "Pause" : "Play");
            playBtn.title = playing ? "Pause" : "Play";
        }

        function paintProgress() {
            var d = duration();
            var t = seeking ? Number(range.value) : audio.currentTime;
            played.style.width = d ? Math.min(100, (t / d) * 100) + "%" : "0";
            currentEl.textContent = fmt(t);
            if (!seeking) range.value = String(t);
            range.setAttribute("aria-valuetext", fmt(t) + " of " + fmt(d));
        }

        function paintBuffered() {
            var d = duration();
            if (!d || !audio.buffered.length) return;
            var end = audio.buffered.end(audio.buffered.length - 1);
            buffered.style.width = Math.min(100, (end / d) * 100) + "%";
        }

        function paintDuration() {
            var d = duration();
            range.max = String(d);
            range.disabled = !d;
            durationEl.textContent = fmt(d);
            paintProgress();
        }

        function seekTo(seconds) {
            var d = duration();
            if (!d) return;
            audio.currentTime = Math.max(0, Math.min(d, seconds));
            paintProgress();
        }

        function toggle() {
            if (!audio.src) return;
            if (audio.paused) {
                var p = audio.play();
                if (p && p.catch) p.catch(function () {});
            } else {
                audio.pause();
            }
        }

        playBtn.addEventListener("click", toggle);
        backBtn.addEventListener("click", function () { seekTo(audio.currentTime - SKIP_SECONDS); });
        fwdBtn.addEventListener("click", function () { seekTo(audio.currentTime + SKIP_SECONDS); });

        speedBtn.addEventListener("click", function () {
            speedIndex = (speedIndex + 1) % SPEEDS.length;
            audio.playbackRate = SPEEDS[speedIndex];
            speedBtn.textContent = SPEEDS[speedIndex] + "×";
        });

        muteBtn.addEventListener("click", function () {
            audio.muted = !audio.muted;
            muteBtn.innerHTML = audio.muted ? ICONS.muted : ICONS.volume;
            muteBtn.setAttribute("aria-label", audio.muted ? "Unmute" : "Mute");
            muteBtn.title = audio.muted ? "Unmute" : "Mute";
        });

        range.addEventListener("input", function () {
            seeking = true;
            paintProgress();
        });
        range.addEventListener("change", function () {
            seeking = false;
            seekTo(Number(range.value));
        });

        root.addEventListener("keydown", function (e) {
            if (e.target.tagName === "A") return;
            var key = e.key;
            // Space on a focused button is that button's own click.
            if (key === "k" || key === "K" || (key === " " && e.target.tagName !== "BUTTON")) {
                e.preventDefault();
                toggle();
            } else if (key === "ArrowLeft" || key === "ArrowRight") {
                e.preventDefault();
                seekTo(audio.currentTime + (key === "ArrowLeft" ? -SKIP_SECONDS : SKIP_SECONDS));
            } else if (key === "Home") {
                e.preventDefault();
                seekTo(0);
            } else if (key === "End") {
                e.preventDefault();
                seekTo(duration());
            }
        });

        audio.addEventListener("loadedmetadata", function () {
            statusEl.textContent = "";
            paintDuration();
            if (root.dataset.state === "loading") setState("ready");
        });
        audio.addEventListener("durationchange", paintDuration);
        audio.addEventListener("timeupdate", paintProgress);
        audio.addEventListener("progress", paintBuffered);
        audio.addEventListener("play", function () { setState("playing"); });
        audio.addEventListener("pause", function () { setState("ready"); });
        audio.addEventListener("waiting", function () { if (!audio.paused) setState("loading"); });
        audio.addEventListener("playing", function () { setState("playing"); });
        audio.addEventListener("ended", function () { setState("ready"); paintProgress(); });
        audio.addEventListener("error", function () {
            if (!audio.getAttribute("src")) return;
            setState("error");
            statusEl.textContent = "Couldn't load this recording. Try again, or download it instead.";
        });

        function load(src, info) {
            info = info || {};
            audio.pause();
            speedIndex = 0;
            audio.playbackRate = 1;
            speedBtn.textContent = "1×";
            statusEl.textContent = "";
            titleEl.textContent = info.title || "Recording";
            var meta = info.meta;
            if (meta == null) {
                meta = [
                    info.mimeType ? String(info.mimeType).replace(/^audio\//, "").replace("mpeg", "mp3").toUpperCase() : "",
                    fmtBytes(info.sizeBytes)
                ].filter(Boolean).join(" · ");
            }
            metaEl.textContent = meta || "Saved recording";
            cancelDownload();
            /* A separate URL from the <audio> src: the server sends it as an
               attachment, uncached, so it never shares the player's partial
               (range-only) cache entry. The click handler above fetches it. */
            download.href = src + (src.indexOf("?") === -1 ? "?" : "&") + "download=1";
            downloadName = info.downloadName || "";
            downloadMime = info.mimeType || "";
            setDownloadState({ available: true, busy: false, percent: 0, error: "" });
            played.style.width = "0";
            buffered.style.width = "0";
            range.value = "0";
            range.max = "0";
            range.disabled = true;
            currentEl.textContent = "0:00";
            durationEl.textContent = "0:00";
            setState("loading");
            audio.src = src;
            audio.load();
            root.hidden = false;
        }

        function clear() {
            cancelDownload();
            download.removeAttribute("href");
            setDownloadState({ available: false, busy: false, percent: 0, error: "" });
            audio.pause();
            audio.removeAttribute("src");
            audio.load();
            root.hidden = true;
            setState("idle");
        }

        return {
            el: root,
            audio: audio,
            load: load,
            clear: clear,
            download: startDownload,
            onDownloadState: function (fn) {
                downloadListeners.push(fn);
                fn({
                    available: downloadState.available,
                    busy: downloadState.busy,
                    percent: downloadState.percent,
                    error: downloadState.error
                });
            },
            isLoaded: function () { return !root.hidden; }
        };
    }

    window.MeetMindAudioPlayer = {
        create: create,
        formatBytes: fmtBytes
    };
})();
