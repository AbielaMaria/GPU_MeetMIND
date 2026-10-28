let websocket = null;

let recordingPcmChunks = [];

let recordingAudioMode = "microphone";

let connectionLost = false;

let reconnectTimer = null;

let reconnectAttempts = 0;

let reconnecting = false;

let replayingRecording = false;

let stopRequested = false;

let intentionalSocketClose = false;

let audioContext = null;

let microphoneStream = null;

let meetTabStream = null;

let sourceNode = null;

let meetTabSourceNode = null;

let processorNode = null;

let silentGainNode = null;

let isRecording = false;

let recordingPaused = false;

let startTime = 0;

let timerInterval = null;

let timerPausedAt = 0;

let transcript = "";

let currentMeetingId = null;

let currentMeetingDuration = null;

let sessionEpoch = 0;

let searchMatches = [];

let currentSearchIndex = -1;


const recordBtn =
    document.getElementById(
        "recordBtn"
    );

const cancelRecordingBtn =
    document.getElementById("cancelRecordingBtn");

const uploadRecordingBtn =
    document.getElementById("uploadRecordingBtn");

const recordingFileInput =
    document.getElementById("recordingFileInput");

const MAX_UPLOAD_BYTES = 500 * 1024 * 1024;

const generateBtn =
    document.getElementById(
        "generateBtn"
    );

const modelPickerBtn =
    document.getElementById(
        "modelPickerBtn"
    );

const modelPickerValue =
    document.getElementById(
        "modelPickerValue"
    );

const modelMenu =
    document.getElementById(
        "modelMenu"
    );

const modelGrid =
    document.getElementById(
        "modelGrid"
    );

const timerEl =
    document.getElementById(
        "timer"
    );

const statusEl =
    document.getElementById(
        "status"
    );

const transcriptEl =
    document.getElementById(
        "transcript"
    );

const logsEl =
    document.getElementById(
        "logs"
    );

const connectionEl =
    document.getElementById(
        "connection"
    );

const statusDot =
    document.getElementById(
        "statusDot"
    );

const transcriptSearch =
    document.getElementById(
        "transcriptSearch"
    );

const searchPrevBtn =
    document.getElementById(
        "searchPrevBtn"
    );

const searchNextBtn =
    document.getElementById(
        "searchNextBtn"
    );

const searchCount =
    document.getElementById(
        "searchCount"
    );

const downloadFullReportBtn =
    document.getElementById(
        "downloadFullReportBtn"
    );

const reportBuilder =
    document.getElementById(
        "reportBuilder"
    );

const reportOptionsEl =
    document.getElementById(
        "reportOptions"
    );

const reportSelectAllBtn =
    document.getElementById(
        "reportSelectAllBtn"
    );

const reportClearBtn =
    document.getElementById(
        "reportClearBtn"
    );

const reportCount =
    document.getElementById(
        "reportCount"
    );

const reportOutlineLabel =
    document.getElementById(
        "reportOutlineLabel"
    );

const reportOutline =
    document.getElementById(
        "reportOutline"
    );

const reportProgressBar =
    document.getElementById(
        "reportProgressBar"
    );

const reportTriggerLabel =
    document.getElementById(
        "reportTriggerLabel"
    );

const reportReady =
    document.getElementById(
        "reportReady"
    );

const reportReadyText =
    document.getElementById(
        "reportReadyText"
    );

const reportReadyBtn =
    document.getElementById(
        "reportReadyBtn"
    );

const fullReportHint =
    document.getElementById(
        "fullReportHint"
    );


function log(message) {

    const now =
        new Date();

    const time =
        now.toLocaleTimeString();

    logsEl.textContent +=
        `[${time}] ${message}\n`;

    logsEl.scrollTop =
        logsEl.scrollHeight;
}


function setStatus(message) {

    statusEl.textContent =
        message;
}


function startTimer() {

    startTime =
        Date.now();

    timerPausedAt =
        0;

    timerEl.textContent =
        "00:00";

    runTimer();
}


function runTimer() {

    if (timerInterval) {

        clearInterval(
            timerInterval
        );
    }

    timerInterval =
        setInterval(
            () => {

                const elapsed =
                    Math.floor(
                        (
                            Date.now()
                            -
                            startTime
                        ) / 1000
                    );

                const minutes =
                    Math.floor(
                        elapsed / 60
                    );

                const seconds =
                    elapsed % 60;

                timerEl.textContent =
                    `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;

            },
            250
        );
}


function pauseTimer() {

    stopTimer();

    timerPausedAt =
        Date.now();
}


function resumeTimer() {

    if (timerPausedAt) {

        startTime +=
            Date.now() - timerPausedAt;

        timerPausedAt =
            0;
    }

    runTimer();
}


function stopTimer() {

    if (timerInterval) {

        clearInterval(
            timerInterval
        );
    }

    timerInterval =
        null;
}


function formatDuration(
    seconds
) {

    const total =
        Math.round(
            Number(seconds)
        );

    if (
        !total
        ||
        total < 0
    ) {

        return "";
    }

    const hours =
        Math.floor(
            total / 3600
        );

    const minutes =
        Math.floor(
            (total % 3600) / 60
        );

    const secs =
        total % 60;

    const parts =
        [];

    if (hours) {

        parts.push(
            `${hours} h`
        );
    }

    if (minutes) {

        parts.push(
            `${minutes} min`
        );
    }

    if (secs) {

        parts.push(
            `${secs} sec`
        );
    }

    return parts.join(
        " "
    );
}


function downsampleBuffer(
    input,
    inputRate,
    outputRate
) {

    if (
        inputRate ===
        outputRate
    ) {

        return input;
    }

    if (
        outputRate >
        inputRate
    ) {

        throw new Error(
            "Output sample rate must be <= input sample rate."
        );
    }

    const ratio =
        inputRate /
        outputRate;

    const newLength =
        Math.round(
            input.length /
            ratio
        );

    const result =
        new Float32Array(
            newLength
        );

    let offsetResult =
        0;

    let offsetBuffer =
        0;

    while (
        offsetResult <
        result.length
    ) {

        const nextOffsetBuffer =
            Math.round(
                (
                    offsetResult + 1
                ) * ratio
            );

        let accum =
            0;

        let count =
            0;

        for (
            let i = offsetBuffer;
            i < nextOffsetBuffer &&
            i < input.length;
            i++
        ) {

            accum +=
                input[i];

            count++;
        }

        result[offsetResult] =
            count > 0
                ? accum / count
                : 0;

        offsetResult++;

        offsetBuffer =
            nextOffsetBuffer;
    }

    return result;
}


function floatToPCM16(
    float32Array
) {

    const buffer =
        new ArrayBuffer(
            float32Array.length * 2
        );

    const view =
        new DataView(
            buffer
        );

    for (
        let i = 0;
        i < float32Array.length;
        i++
    ) {

        const sample =
            Math.max(
                -1,
                Math.min(
                    1,
                    float32Array[i]
                )
            );

        const value =
            sample < 0
                ? sample * 0x8000
                : sample * 0x7fff;

        view.setInt16(
            i * 2,
            value,
            true
        );
    }

    return buffer;
}


function getWebSocketUrl() {

    const protocol =
        window.location.protocol ===
        "https:"
            ? "wss"
            : "ws";

    const host =
        window.location.host;

    return `${protocol}://${host}/ws/meeting`;
}


function createWebSocketConnection() {

    return new Promise(
        (
            resolve,
            reject
        ) => {

            const socket =
                new WebSocket(
                    getWebSocketUrl()
                );

            socket.binaryType =
                "arraybuffer";

            websocket = socket;

            let settled =
                false;

            socket.onopen =
                () => {

                    if (
                        settled
                    ) {

                        return;
                    }

                    settled =
                        true;

                    connectionLost =
                        false;

                    connectionEl.textContent =
                        "Connected";

                    statusDot.style.background =
                        "#22c55e";

                    log(
                        reconnecting
                            ? "WebSocket reconnected."
                            : "WebSocket connected."
                    );

                    resolve();
                };

            socket.onmessage =
                handleServerMessage;

            socket.onerror =
                () => {

                    if (
                        !settled
                    ) {

                        settled =
                            true;

                        reject(
                            new Error(
                                "WebSocket connection failed."
                            )
                        );
                    }
                };

            socket.onclose =
                (event) => {

                    connectionEl.textContent =
                        "Disconnected";

                    statusDot.style.background =
                        "#dc2626";

                    log(
                        `WebSocket closed. Code=${event.code}, Reason=${event.reason || "(none)"}, Clean=${event.wasClean}`
                    );

                    connectionLost =
                        true;

                    if (
                        isRecording
                        ||
                        stopRequested
                    ) {

                        if (
                            isRecording
                        ) {

                            setStatus(
                                "Internet connection lost. Recording continues locally. Reconnecting..."
                            );

                            log(
                                "WebSocket lost. Audio is being retained locally while reconnecting."
                            );
                        }

                        scheduleWebSocketReconnect();

                        return;
                    }

                    if (
                        !isRecording
                        &&
                        !transcript
                        &&
                        transcriptEl.querySelector(
                            ".wave-loader"
                        )
                    ) {

                        renderTranscript(
                            ""
                        );
                    }
                };
        }
    );
}


async function replayRecordingToWebSocket() {

    if (
        !websocket
        ||
        websocket.readyState !==
            WebSocket.OPEN
    ) {

        throw new Error(
            "WebSocket is not open for recording recovery."
        );
    }

    replayingRecording =
        true;

    try {

        websocket.send(
            JSON.stringify({
                command: "start",
                template:
                    activeTemplate(),
                audio_mode:
                    recordingAudioMode,
                audio_sources:
                    recordingAudioMode ===
                        "microphone_and_meet_tab"
                        ? [
                            "microphone",
                            "google_meet_tab"
                        ]
                        : [
                            "microphone"
                        ]
            })
        );

        log(
            `Reconnected WebSocket. Replaying ${recordingPcmChunks.length} buffered PCM chunks...`
        );

        for (
            let i = 0;
            i < recordingPcmChunks.length;
            i++
        ) {

            if (
                !websocket
                ||
                websocket.readyState !==
                    WebSocket.OPEN
            ) {

                throw new Error(
                    "WebSocket closed while replaying buffered audio."
                );
            }

            websocket.send(
                recordingPcmChunks[i]
            );

            if (
                websocket.bufferedAmount >
                1024 * 1024
            ) {

                await waitForWebSocketDrain();
            }
        }

        const tailStart =
            recordingPcmChunks.length;

        await new Promise(
            resolve =>
                setTimeout(resolve, 0)
        );

        let sentCount =
            Math.min(
                tailStart,
                recordingPcmChunks.length
            );

        while (
            sentCount <
            recordingPcmChunks.length
        ) {

            if (
                !websocket
                ||
                websocket.readyState !==
                    WebSocket.OPEN
            ) {

                throw new Error(
                    "WebSocket closed while sending recovered audio."
                );
            }

            websocket.send(
                recordingPcmChunks[sentCount]
            );

            sentCount++;

            if (
                websocket.bufferedAmount >
                1024 * 1024
            ) {

                await waitForWebSocketDrain();
            }
        }

        log(
            "Buffered recording replay complete. Live audio can continue."
        );

    } finally {

        replayingRecording =
            false;
    }
}


function waitForWebSocketDrain() {

    return new Promise(
        resolve => {

            const check =
                () => {

                    if (
                        !websocket
                        ||
                        websocket.readyState !==
                            WebSocket.OPEN
                        ||
                        websocket.bufferedAmount <=
                            256 * 1024
                    ) {

                        resolve();
                        return;
                    }

                    setTimeout(
                        check,
                        10
                    );
                };

            check();
        }
    );
}


function scheduleWebSocketReconnect() {

    if (
        reconnectTimer
        ||
        reconnecting
    ) {

        return;
    }

    if (
        !isRecording
        &&
        !stopRequested
    ) {

        return;
    }

    const delay =
        Math.min(
            1000 *
                Math.pow(
                    2,
                    reconnectAttempts
                ),
            10000
        );

    reconnectAttempts++;

    log(
        `WebSocket reconnect attempt ${reconnectAttempts} in ${Math.round(delay / 1000)}s...`
    );

    reconnectTimer =
        setTimeout(
            async () => {

                reconnectTimer =
                    null;

                await reconnectWebSocket();
            },
            delay
        );
}


async function reconnectWebSocket() {

    if (
        !isRecording
        &&
        !stopRequested
    ) {

        return;
    }

    if (
        reconnecting
    ) {

        return;
    }

    reconnecting =
        true;

    try {

        await createWebSocketConnection();

        if (
            !isRecording
            &&
            !stopRequested
        ) {

            return;
        }

        await replayRecordingToWebSocket();

        reconnectAttempts =
            0;

        connectionLost =
            false;

        if (
            stopRequested
        ) {

            websocket.send(
                JSON.stringify({
                    command: "stop"
                })
            );

            stopRequested =
                false;

            log(
                "Recovered WebSocket connected. Stop command sent. Waiting for Parrotlet..."
            );

        } else {

            setStatus(
                "Recording system microphone" +
                (
                    recordingAudioMode ===
                    "microphone_and_meet_tab"
                        ? " + Google Meet tab audio"
                        : ""
                ) +
                "..."
            );

            log(
                "Recording resumed after WebSocket reconnection."
            );
        }

    } catch (error) {

        log(
            `WebSocket reconnect failed: ${error.message}`
        );

        reconnecting =
            false;

        scheduleWebSocketReconnect();

        return;

    } finally {

        reconnecting =
            false;
    }
}


async function openWebSocket() {

    reconnectAttempts =
        0;

    connectionLost =
        false;

    stopRequested =
        false;

    reconnecting =
        false;

    await createWebSocketConnection();
}


function handleServerMessage(
    event
) {

    let data;

    try {

        data =
            JSON.parse(
                event.data
            );

    } catch (error) {

        log(
            "Invalid server message received."
        );

        return;
    }


    switch (
        data.type
    ) {


        case "connected":

            log(
                `Meeting ID: ${data.meeting_id}`
            );

            break;


        case "recording_started":

            setStatus(
                "Recording meeting..."
            );

            recordBtn.disabled =
                false;

            break;


        case "processing_started":

            setStatus(
                "Recording complete. Transcribing with Parrotlet..."
            );

            transcriptEl.innerHTML =
                loadingHtml(
                    "Transcribing the recording with Parrotlet..."
                );

            mountWaveLoaders(
                transcriptEl
            );

            log(
                data.message
                ||
                "Parrotlet transcription started."
            );

            break;


        case "final_transcript":

            transcript =
                (
                    data.transcript
                    ||
                    ""
                ).trim();

            currentMeetingDuration =
                Number(
                    data.duration
                )
                ||
                null;

            if (data.template === "doctor") {

                if (window.meetmindDoctor) {
                    window.meetmindDoctor.onTranscribed({
                        consultationId: data.consultation_id || null
                    });
                }

                if (data.has_audio) {
                    recordingPlayer.show("consultation", data.consultation_id);
                }

            } else if (data.template === "interview") {

                if (window.meetmindInterview) {
                    window.meetmindInterview.onTranscribed({
                        interviewId: data.interview_id || null
                    });
                }

                if (data.has_audio) {
                    recordingPlayer.show("interview", data.interview_id);
                }

            } else {

                if (data.saved_meeting_id) {

                    currentMeetingId =
                        data.saved_meeting_id;
                }

                if (data.has_audio) {
                    recordingPlayer.show("meeting", data.saved_meeting_id);
                }
            }

            renderTranscript(
                transcript
            );

            resetTranscriptSearch();

            updateGenerateButton();

            recordBtn.disabled =
                false;

            if (transcript) {

                setStatus(
                    transcriptReadyMessage(
                        data.template
                    )
                );

            } else {

                setStatus(
                    "No transcript was produced."
                );
            }

            log(
                "Complete transcript received."
            );

            break;


        case "transcript_ready":

            if (
                data.message
            ) {

                setStatus(
                    data.message
                );
            }

            break;


        case "summary_started":

            setStatus(
                "Generating meeting intelligence with Mistral 128B..."
            );

            log(
                "Mistral 128B analysis started."
            );

            break;


        case "meeting_result":

            transcript =
                (
                    data.transcript
                    ||
                    transcript
                    ||
                    ""
                ).trim();

            renderTranscript(
                transcript
            );

            resetTranscriptSearch();

            {
                const slot =
                    slotForModel(
                        data.model
                    );

                renderIntelligence(
                    slot,
                    data
                );

                setGenerationStatus(
                    slot,
                    "summary",
                    "done"
                );
            }

            recordBtn.disabled =
                false;

            setStatus(
                "Meeting intelligence generated."
            );

            log(
                "Meeting intelligence received."
            );

            break;


        case "error":

            log(
                `ERROR [${data.stage || "backend"}]: ${data.message}`
            );

            setStatus(
                `Error: ${data.message}`
            );

            if (
                !transcript
                &&
                transcriptEl.querySelector(
                    ".wave-loader"
                )
            ) {

                renderTranscript(
                    ""
                );
            }

            recordBtn.disabled =
                false;

            break;


        default:

            log(
                `Server event: ${data.type}`
            );

            break;
    }
}


function renderTranscript(
    text
) {

    transcriptEl.innerHTML =
        "";

    if (!text) {

        transcriptEl.innerHTML =
            `
            <div class="placeholder">
                No transcript was produced.
            </div>
            `;

        return;
    }

    const div =
        document.createElement(
            "div"
        );

    div.textContent =
        text;

    transcriptEl.appendChild(
        div
    );
}


const FALLBACK_MODELS = [
    { key: "mistral", label: "Mistral 128B", modelId: "" },
    { key: "qwen", label: "Qwen3 27B", modelId: "" }
];

const ALL_MODELS = "all";

const modelSlots = new Map();


function deepClone(
    value
) {

    return JSON.parse(
        JSON.stringify(
            value
        )
    );
}


function placeholderHtml(
    text
) {

    return `<div class="placeholder">${escapeHtml(text)}</div>`;
}


function createModelSlot(
    model
) {

    const column =
        document.createElement(
            "section"
        );

    column.className =
        "model-column";

    column.dataset.model =
        model.key;

    column.innerHTML =
        `
        <div class="model-column-head">
            <span class="model-mark" aria-hidden="true"></span>
            <h2 class="model-name"></h2>
            <span class="model-chip" title="Model ID"></span>
        </div>

        <div class="model-panels">

            <div class="card panel panel--intel">

                <div class="panel-head">
                    <h2>
                        Meeting Intelligence
                        <span class="panel-model"></span>
                    </h2>
                    <div class="panel-head-tools">
                        <span class="gen-badge" role="status" hidden></span>
                    </div>
                </div>

                <div class="edit-hint">
                    Click any field to edit it.
                </div>

                <div class="download-actions">
                    <button class="btn-tool download-btn download-pdf-btn" type="button" disabled>Download PDF</button>
                    <button class="btn-tool download-btn download-md-btn" type="button" disabled>Download Markdown</button>
                </div>

                <div class="panel-body scroll-fade">
                    <div class="intelligence"></div>
                </div>

            </div>

            <div class="card panel panel--mindmap">

                <div class="panel-head">
                    <h2>
                        Mind Map
                        <span class="panel-model"></span>
                    </h2>
                    <div class="panel-head-tools">
                        <span class="gen-badge" role="status" hidden></span>
                        <button class="btn-tool btn-icon expand-btn" type="button" aria-pressed="false"></button>
                    </div>
                </div>

                <div class="edit-hint">
                    Click any mind-map node to edit it.
                </div>

                <div class="download-actions">
                    <button class="btn-tool download-btn download-mindmap-btn" type="button" disabled>Download Mind Map Image</button>
                </div>

                <div class="panel-body scroll-fade">
                    <div class="mindmap-container"></div>
                </div>

                <div class="summary-actions mindmap-actions">
                    <button class="btn-primary save-mindmap-btn" type="button">Save Changes</button>
                    <button class="btn-secondary cancel-mindmap-btn" type="button">Cancel</button>
                </div>

            </div>

            <div class="mindmap-spacer" hidden></div>

        </div>
        `;

    const intelPanel =
        column.querySelector(
            ".panel--intel"
        );

    const mindmapPanel =
        column.querySelector(
            ".panel--mindmap"
        );

    const slot = {

        model,

        column,

        intel: null,

        intelSaved: null,

        mindmap: null,

        mindmapSaved: null,

        status: {
            summary: "idle",
            mindmap: "idle"
        },

        els: {
            name: column.querySelector(".model-name"),
            chip: column.querySelector(".model-chip"),
            panelModels: column.querySelectorAll(".panel-model"),

            intelligence: intelPanel.querySelector(".intelligence"),
            editHint: intelPanel.querySelector(".edit-hint"),
            downloadActions: intelPanel.querySelector(".download-actions"),
            downloadPdfBtn: intelPanel.querySelector(".download-pdf-btn"),
            downloadMarkdownBtn: intelPanel.querySelector(".download-md-btn"),
            summaryBadge: intelPanel.querySelector(".gen-badge"),

            mindmapPanel: mindmapPanel,
            mindMapContainer: mindmapPanel.querySelector(".mindmap-container"),
            mindMapEditHint: mindmapPanel.querySelector(".edit-hint"),
            mindMapDownloadActions: mindmapPanel.querySelector(".download-actions"),
            downloadMindMapBtn: mindmapPanel.querySelector(".download-mindmap-btn"),
            mindMapActions: mindmapPanel.querySelector(".mindmap-actions"),
            saveMindMapBtn: mindmapPanel.querySelector(".save-mindmap-btn"),
            cancelMindMapBtn: mindmapPanel.querySelector(".cancel-mindmap-btn"),
            mindmapBadge: mindmapPanel.querySelector(".gen-badge"),
            expandBtn: mindmapPanel.querySelector(".expand-btn"),
            mindmapSpacer: column.querySelector(".mindmap-spacer")
        }
    };

    const els =
        slot.els;

    els.downloadPdfBtn.addEventListener(
        "click",
        () => downloadPdf(slot)
    );

    els.downloadMarkdownBtn.addEventListener(
        "click",
        () => downloadMarkdown(slot)
    );

    els.downloadMindMapBtn.addEventListener(
        "click",
        () => downloadMindMapImage(slot)
    );

    els.saveMindMapBtn.addEventListener(
        "click",
        () => saveMindMapEdits(slot)
    );

    els.cancelMindMapBtn.addEventListener(
        "click",
        () => cancelMindMapEdits(slot)
    );

    els.expandBtn.addEventListener(
        "click",
        () => setMindMapExpanded(
            slot,
            !els.mindmapPanel.classList.contains("is-expanded")
        )
    );

    fullReportObserver.observe(
        els.intelligence,
        { childList: true }
    );

    fullReportObserver.observe(
        els.mindMapContainer,
        { childList: true }
    );

    modelSlots.set(
        model.key,
        slot
    );

    modelGrid.appendChild(
        column
    );

    applyModelLabels(
        slot
    );

    resetSlot(
        slot,
        isRecording ? "recording" : "ready"
    );

    return slot;
}


function ensureSlot(
    key
) {

    return modelSlots.get(key)
        || createModelSlot(
            {
                key: key,
                label: key,
                modelId: ""
            }
        );
}


function slotForModel(
    key
) {

    return modelSlots.get(key)
        || modelSlots.values().next().value;
}


function applyModelLabels(
    slot
) {

    const {
        model,
        els
    } = slot;

    els.name.textContent =
        model.label;

    els.chip.textContent =
        model.modelId || "";

    els.panelModels.forEach(
        span => {

            span.textContent =
                `(${model.label})`;
        }
    );

    updateExpandButton(
        slot
    );
}


function slotHasContent(
    slot
) {

    return !!(
        slot.intel
        ||
        slot.mindmap
        ||
        slot.status.summary !== "idle"
        ||
        slot.status.mindmap !== "idle"
    );
}


function resetSlot(
    slot,
    phase = "ready"
) {

    const {
        model,
        els
    } = slot;

    setMindMapExpanded(
        slot,
        false
    );

    slot.intel =
        null;

    slot.intelSaved =
        null;

    els.intelligence.innerHTML =
        placeholderHtml(
            phase === "recording"
                ? "Meeting intelligence will be generated after transcription."
                : `Click Generate to create meeting intelligence with ${model.label}.`
        );

    els.editHint.classList.remove(
        "visible"
    );

    els.downloadActions.classList.remove(
        "visible"
    );

    els.downloadPdfBtn.disabled =
        true;

    els.downloadMarkdownBtn.disabled =
        true;

    clearMindMap(
        slot,
        placeholderHtml(
            phase === "recording"
                ? "Mind map will be generated after transcription."
                : `Click Generate to create the meeting mind map with ${model.label}.`
        )
    );

    setGenerationStatus(
        slot,
        "summary",
        "idle"
    );

    setGenerationStatus(
        slot,
        "mindmap",
        "idle"
    );
}


const dropdowns =
    [];


function createDropdown(
    trigger,
    menu,
    render
) {

    const dropdown = {

        trigger,

        menu,

        isOpen() {

            return !menu.hidden;
        },

        open() {

            if (
                trigger.disabled
            ) {

                return;
            }

            dropdowns.forEach(
                other => {

                    if (
                        other !== dropdown
                    ) {

                        other.close();
                    }
                }
            );

            render(
                menu
            );

            menu.hidden =
                false;

            trigger.setAttribute(
                "aria-expanded",
                "true"
            );

            const target =
                menu.querySelector(
                    '.dropdown-item[aria-checked="true"]'
                )
                ||
                menu.querySelector(
                    '.dropdown-item:not([aria-disabled="true"])'
                )
                ||
                menu.querySelector(
                    ".dropdown-item"
                );

            if (
                target
            ) {

                target.focus();
            }
        },

        close(
            returnFocus = false
        ) {

            if (
                menu.hidden
            ) {

                return;
            }

            menu.hidden =
                true;

            trigger.setAttribute(
                "aria-expanded",
                "false"
            );

            if (
                returnFocus
            ) {

                trigger.focus();
            }
        },

        refresh() {

            if (
                menu.hidden
            ) {

                return;
            }

            const focused =
                menu.contains(
                    document.activeElement
                )
                    ? document.activeElement.dataset.value
                    : null;

            render(
                menu
            );

            if (
                focused
            ) {

                const again =
                    [
                        ...menu.querySelectorAll(
                            ".dropdown-item"
                        )
                    ].find(
                        item => item.dataset.value === focused
                    );

                if (
                    again
                ) {

                    again.focus();
                }
            }
        }
    };

    trigger.addEventListener(
        "click",
        () => {

            if (
                dropdown.isOpen()
            ) {

                dropdown.close();

            } else {

                dropdown.open();
            }
        }
    );

    menu.addEventListener(
        "keydown",
        event => {

            const items =
                [
                    ...menu.querySelectorAll(
                        ".dropdown-item"
                    )
                ];

            const index =
                items.indexOf(
                    document.activeElement
                );

            let next =
                null;

            if (
                event.key === "ArrowDown"
            ) {

                next =
                    items[(index + 1) % items.length];

            } else if (
                event.key === "ArrowUp"
            ) {

                next =
                    items[(index - 1 + items.length) % items.length];

            } else if (
                event.key === "Home"
            ) {

                next =
                    items[0];

            } else if (
                event.key === "End"
            ) {

                next =
                    items[items.length - 1];

            } else if (
                event.key === "Tab"
            ) {

                dropdown.close();
            }

            if (
                next
            ) {

                event.preventDefault();

                next.focus();
            }
        }
    );

    dropdowns.push(
        dropdown
    );

    return dropdown;
}


function dropdownItem(
    {
        value,
        label,
        meta = "",
        disabled = false,
        checked = null,
        onSelect
    }
) {

    const item =
        document.createElement(
            "button"
        );

    item.type =
        "button";

    item.className =
        "dropdown-item";

    item.dataset.value =
        value;

    item.setAttribute(
        "role",
        checked === null
            ? "menuitem"
            : "menuitemradio"
    );

    if (
        checked !== null
    ) {

        item.setAttribute(
            "aria-checked",
            String(
                checked
            )
        );
    }

    if (
        disabled
    ) {

        item.setAttribute(
            "aria-disabled",
            "true"
        );
    }

    item.innerHTML =
        `<span class="dropdown-item-label">${escapeHtml(label)}</span>`
        +
        (
            meta
                ? `<span class="dropdown-item-meta">${escapeHtml(meta)}</span>`
                : ""
        );

    item.addEventListener(
        "click",
        () => {

            if (
                !disabled
            ) {

                onSelect();
            }
        }
    );

    return item;
}


document.addEventListener(
    "click",
    event => {

        dropdowns.forEach(
            dropdown => {

                if (
                    dropdown.isOpen()
                    &&
                    event.target.closest(".dropdown")
                        !== dropdown.trigger.closest(".dropdown")
                ) {

                    dropdown.close();
                }
            }
        );
    }
);


let selectedModelValue =
    ALL_MODELS;


function selectedSlots() {

    if (
        modelSlots.has(
            selectedModelValue
        )
    ) {

        return [
            modelSlots.get(
                selectedModelValue
            )
        ];
    }

    return [
        ...modelSlots.values()
    ];
}


function modelChoices() {

    const slots =
        [
            ...modelSlots.values()
        ];

    const choices =
        [];

    if (
        slots.length > 1
    ) {

        choices.push(
            {
                value: ALL_MODELS,
                label: slots.length === 2
                    ? "Both models"
                    : `All ${slots.length} models`,
                meta: slots
                    .map(
                        slot => slot.model.label
                    )
                    .join(
                        " + "
                    )
            }
        );
    }

    slots.forEach(
        slot => {

            choices.push(
                {
                    value: slot.model.key,
                    label: slot.model.label,
                    meta: slot.model.modelId
                        || "This model only"
                }
            );
        }
    );

    return choices;
}


function renderModelPicker() {

    const choices =
        modelChoices();

    if (
        !choices.some(
            choice => choice.value === selectedModelValue
        )
    ) {

        selectedModelValue =
            choices.length
                ? choices[0].value
                : ALL_MODELS;
    }

    const current =
        choices.find(
            choice => choice.value === selectedModelValue
        );

    modelPickerValue.textContent =
        current
            ? current.label
            : "";

    modelPickerBtn.title =
        current
            ? current.meta
            : "";

    modelPickerBtn.setAttribute(
        "aria-label",
        current
            ? `Models: ${current.label} (${current.meta})`
            : "Models"
    );

    modelDropdown.refresh();
}


function renderModelMenu(
    menu
) {

    menu.innerHTML =
        "";

    modelChoices().forEach(
        choice => {

            menu.appendChild(
                dropdownItem(
                    {
                        ...choice,
                        checked: choice.value === selectedModelValue,
                        onSelect: () => {

                            modelDropdown.close(
                                true
                            );

                            setModelSelection(
                                choice.value
                            );
                        }
                    }
                )
            );
        }
    );
}


function setModelSelection(
    value
) {

    selectedModelValue =
        value;

    renderModelPicker();

    applyModelSelection();
}


const modelDropdown =
    createDropdown(
        modelPickerBtn,
        modelMenu,
        renderModelMenu
    );


function applyModelSelection() {

    const visible =
        selectedSlots();

    modelSlots.forEach(
        slot => {

            const shown =
                visible.includes(
                    slot
                );

            if (
                !shown
            ) {

                setMindMapExpanded(
                    slot,
                    false
                );
            }

            slot.column.hidden =
                !shown;
        }
    );

    modelGrid.dataset.count =
        String(
            visible.length
        );

    modelGrid.style.setProperty(
        "--model-count",
        String(
            visible.length
        )
    );

    visible.forEach(
        slot => {

            if (
                slot.mindmap
            ) {

                centerMindMap(
                    slot
                );
            }
        }
    );

    updateGenerateButton();
}


async function loadModelCatalog() {

    let models =
        null;

    try {

        const response =
            await fetch(
                "/api/models",
                {
                    credentials:
                        "same-origin"
                }
            );

        if (
            response.ok
        ) {

            const list =
                await response.json();

            if (
                Array.isArray(
                    list
                )
            ) {

                models =
                    list
                        .filter(
                            item => item && item.key
                        )
                        .map(
                            item => ({
                                key: String(item.key),
                                label: String(item.label || item.key),
                                modelId: String(item.modelId || "")
                            })
                        );
            }
        }

    } catch (
        error
    ) {}

    if (
        !models
        ||
        !models.length
    ) {

        log(
            "Could not load the model list — using the built-in defaults."
        );

        return;
    }

    models.forEach(
        model => {

            const slot =
                modelSlots.get(
                    model.key
                );

            if (
                !slot
            ) {

                createModelSlot(
                    model
                );

                return;
            }

            slot.model =
                model;

            applyModelLabels(
                slot
            );

            if (
                !slotHasContent(
                    slot
                )
            ) {

                resetSlot(
                    slot,
                    isRecording ? "recording" : "ready"
                );
            }
        }
    );

    const unoffered =
        [
            ...modelSlots.entries()
        ].filter(
            ([key, slot]) =>
                !models.some(
                    model => model.key === key
                )
                &&
                !slotHasContent(
                    slot
                )
        );

    unoffered.forEach(
        ([key, slot]) => {

            slot.column.remove();

            modelSlots.delete(
                key
            );
        }
    );

    const ordered =
        new Map();

    models.forEach(
        model => {

            if (
                modelSlots.has(
                    model.key
                )
            ) {

                ordered.set(
                    model.key,
                    modelSlots.get(model.key)
                );
            }
        }
    );

    modelSlots.forEach(
        (
            slot,
            key
        ) => {

            if (
                !ordered.has(
                    key
                )
            ) {

                ordered.set(
                    key,
                    slot
                );
            }
        }
    );

    modelSlots.clear();

    ordered.forEach(
        (
            slot,
            key
        ) => {

            modelSlots.set(
                key,
                slot
            );

            modelGrid.appendChild(
                slot.column
            );
        }
    );

    renderModelPicker();

    applyModelSelection();

    refreshReportBuilder();
}


function setGenerationStatus(
    slot,
    kind,
    status,
    message = ""
) {

    slot.status[kind] =
        status;

    const badge =
        kind === "summary"
            ? slot.els.summaryBadge
            : slot.els.mindmapBadge;

    badge.className =
        "gen-badge";

    badge.removeAttribute(
        "title"
    );

    badge.hidden =
        status === "idle";

    if (
        status === "generating"
    ) {

        badge.classList.add(
            "is-generating"
        );

        badge.innerHTML =
            'Generating<span class="gen-dots" aria-hidden="true"><span>.</span><span>.</span><span>.</span></span>';

    } else if (
        status === "done"
    ) {

        badge.classList.add(
            "is-done"
        );

        badge.textContent =
            "Generated";

    } else if (
        status === "error"
    ) {

        badge.classList.add(
            "is-error"
        );

        badge.textContent =
            "Failed";

        badge.title =
            message;

    } else {

        badge.textContent =
            "";
    }

    updateGenerateButton();

    refreshReportBuilder();
}


function isAnyGenerating() {

    return [
        ...modelSlots.values()
    ].some(
        slot =>
            slot.status.summary === "generating"
            ||
            slot.status.mindmap === "generating"
    );
}


function pendingGenerations(
    slots
) {

    const jobs =
        [];

    slots.forEach(
        slot => {

            if (
                !slot.intel
                &&
                slot.status.summary !== "generating"
            ) {

                jobs.push(
                    {
                        slot: slot,
                        kind: "summary"
                    }
                );
            }

            if (
                !slot.mindmap
                &&
                slot.status.mindmap !== "generating"
            ) {

                jobs.push(
                    {
                        slot: slot,
                        kind: "mindmap"
                    }
                );
            }
        }
    );

    return jobs;
}


function updateGenerateButton() {

    generateBtn.disabled =
        !transcript
        ||
        !pendingGenerations(
            selectedSlots()
        ).length;

    document.dispatchEvent(
        new CustomEvent("meetmind:transcript-state")
    );
}


let waveAnimationRequest =
    null;

const waveAnimations =
    new Set();


function loadWaveAnimation() {

    if (
        !waveAnimationRequest
    ) {

        waveAnimationRequest =
            fetch(
                "/assets/sound-waves.json"
            )
                .then(
                    response => {

                        if (
                            !response.ok
                        ) {

                            throw new Error(
                                `HTTP ${response.status}`
                            );
                        }

                        return response.json();
                    }
                )
                .catch(
                    () => null
                );
    }

    return waveAnimationRequest;
}


function loadingHtml(
    message
) {

    return `
        <div class="placeholder placeholder--loading" role="status">
            <div class="wave-loader" aria-hidden="true">
                <span></span><span></span><span></span><span></span><span></span>
            </div>
            <div>${escapeHtml(message)}</div>
        </div>
        `;
}


async function mountWaveLoaders(
    root
) {

    waveAnimations.forEach(
        animation => {

            if (
                !animation.wrapper
                ||
                !animation.wrapper.isConnected
            ) {

                animation.destroy();

                waveAnimations.delete(
                    animation
                );
            }
        }
    );

    if (
        window.matchMedia(
            "(prefers-reduced-motion: reduce)"
        ).matches
    ) {

        return;
    }

    const data =
        await loadWaveAnimation();

    if (
        !data
        ||
        !window.lottie
    ) {

        return;
    }

    root.querySelectorAll(
        ".wave-loader:not([data-lottie])"
    ).forEach(
        element => {

            if (
                !element.isConnected
            ) {

                return;
            }

            element.dataset.lottie =
                "true";

            element.innerHTML =
                "";

            waveAnimations.add(
                window.lottie.loadAnimation(
                    {
                        container: element,
                        renderer: "svg",
                        loop: true,
                        autoplay: true,
                        animationData: deepClone(data)
                    }
                )
            );
        }
    );
}


function sectionLabel(
    icon,
    text
) {

    return `
        <div class="label">
            <span class="section-icon section-icon--${icon}" aria-hidden="true"></span>
            ${text}
        </div>
        `;
}


function renderIntelligence(
    slot,
    data,
    resetSaved = true
) {

    if (
        !data
    ) {

        return;
    }

    const els =
        slot.els;

    const merged =
        {
            ...data,
            transcript:
                data.transcript
                ||
                transcript
                ||
                ""
        };

    slot.intel =
        deepClone(
            merged
        );

    if (
        resetSaved
        ||
        !slot.intelSaved
    ) {

        slot.intelSaved =
            deepClone(
                merged
            );
    }

    els.editHint.classList.add(
        "visible"
    );

    els.downloadActions.classList.add(
        "visible"
    );

    els.downloadPdfBtn.disabled =
        false;

    els.downloadMarkdownBtn.disabled =
        false;

    const title =
        data.title
        ||
        "Untitled Meeting";

    const objective =
        data.objective
        ||
        "Objective could not be generated.";

    const summary =
        data.meeting_summary
        ||
        "No summary available.";

    const tasks =
        Array.isArray(
            data.tasks_assigned
        )
            ? data.tasks_assigned
            : [];

    const decisions =
        Array.isArray(
            data.decision_points
        )
            ? data.decision_points
            : [];

    const objections =
        Array.isArray(
            data.objections
        )
            ? data.objections
            : [];

    const actions =
        Array.isArray(
            data.action_items
        )
            ? data.action_items
            : [];


    let html =
        "";


    html +=
        `
        <div class="result-section">

            ${sectionLabel("title", "TITLE")}

            <div
                class="title-result editable-field"
                contenteditable="true"
                spellcheck="true"
                data-edit-path="title"
                role="textbox"
                aria-label="Editable meeting title"
            >${escapeHtml(title)}</div>

        </div>
        `;


    html +=
        `
        <div class="result-section">

            ${sectionLabel("summary", "MEETING SUMMARY")}

            <textarea
                class="editable-summary meeting-summary-editor"
                spellcheck="true"
                aria-label="Editable meeting summary"
            >${escapeHtml(summary)}</textarea>

        </div>
        `;


    html +=
        `
        <div class="result-section">

            ${sectionLabel("objective", "OBJECTIVE")}

            <div
                class="summary editable-field"
                contenteditable="true"
                spellcheck="true"
                data-edit-path="objective"
                role="textbox"
                aria-label="Editable meeting objective"
            >${escapeHtml(objective)}</div>

        </div>
        `;


    html +=
        `
        <div class="result-section">

            ${sectionLabel("tasks", "TASKS")}
        `;


    if (
        tasks.length === 0
    ) {

        html +=
            `
            <div class="meta">
                No tasks identified.
            </div>
            `;

    } else {

        tasks.forEach(
            (task, taskIndex) => {

                if (
                    !task
                    ||
                    !task.task
                ) {

                    return;
                }

                html +=
                    `
                    <div class="item">

                        <strong
                            class="editable-field"
                            contenteditable="true"
                            spellcheck="true"
                            data-edit-path="tasks_assigned.${taskIndex}.task"
                            role="textbox"
                            aria-label="Editable task"
                        >${escapeHtml(
                                task.task
                            )}</strong>
                    `;


                if (
                    task.assignee
                    &&
                    String(
                        task.assignee
                    ).trim()
                ) {

                    html +=
                        `
                        <div class="meta">
                            Assignee:
                            <span
                                class="editable-field"
                                contenteditable="true"
                                spellcheck="true"
                                data-edit-path="tasks_assigned.${taskIndex}.assignee"
                                role="textbox"
                                aria-label="Editable task assignee"
                            >${escapeHtml(
                                task.assignee
                            )}</span>
                        </div>
                        `;
                }


                if (
                    task.deadline
                    &&
                    String(
                        task.deadline
                    ).trim()
                ) {

                    html +=
                        `
                        <div class="meta">
                            Deadline:
                            <span
                                class="editable-field"
                                contenteditable="true"
                                spellcheck="true"
                                data-edit-path="tasks_assigned.${taskIndex}.deadline"
                                role="textbox"
                                aria-label="Editable task deadline"
                            >${escapeHtml(
                                task.deadline
                            )}</span>
                        </div>
                        `;
                }


                html +=
                    `
                    </div>
                    `;
            }
        );
    }


    html +=
        `
        </div>
        `;


    html +=
        `
        <div class="result-section">

            ${sectionLabel("decisions", "DECISIONS")}
        `;


    if (
        decisions.length === 0
    ) {

        html +=
            `
            <div class="meta">
                No decisions identified.
            </div>
            `;

    } else {

        decisions.forEach(
            (decision, decisionIndex) => {

                if (
                    !decision
                    ||
                    !String(
                        decision
                    ).trim()
                ) {

                    return;
                }

                html +=
                    `
                    <div
                        class="decision editable-field"
                        contenteditable="true"
                        spellcheck="true"
                        data-edit-path="decision_points.${decisionIndex}"
                        role="textbox"
                        aria-label="Editable decision"
                    >${escapeHtml(
                            decision
                        )}</div>
                    `;
            }
        );
    }


    html +=
        `
        </div>
        `;


    if (
        objections.length > 0
    ) {

        html +=
            `
            <div class="result-section">

                ${sectionLabel("objections", "OBJECTIONS")}
            `;


        objections.forEach(
            (objection, objectionIndex) => {

                if (
                    !objection
                    ||
                    !String(
                        objection
                    ).trim()
                ) {

                    return;
                }

                html +=
                    `
                    <div
                        class="item objection editable-field"
                        contenteditable="true"
                        spellcheck="true"
                        data-edit-path="objections.${objectionIndex}"
                        role="textbox"
                        aria-label="Editable objection"
                    >${escapeHtml(
                            objection
                        )}</div>
                    `;
            }
        );


        html +=
            `
            </div>
            `;
    }


    if (
        actions.length > 0
    ) {

        html +=
            `
            <div class="result-section">

                ${sectionLabel("actions", "ACTION ITEMS")}
            `;


        actions.forEach(
            (action, actionIndex) => {

                if (
                    !action
                    ||
                    !String(
                        action
                    ).trim()
                ) {

                    return;
                }

                html +=
                    `
                    <div
                        class="item action editable-field"
                        contenteditable="true"
                        spellcheck="true"
                        data-edit-path="action_items.${actionIndex}"
                        role="textbox"
                        aria-label="Editable action item"
                    >${escapeHtml(
                            action
                        )}</div>
                    `;
            }
        );


        html +=
            `
            </div>
            `;
    }


    html +=
        `
        <div class="summary-actions intel-actions">
            <button class="btn-primary save-summary-btn" type="button">
                Save Changes
            </button>

            <button class="btn-secondary cancel-summary-btn" type="button">
                Cancel
            </button>
        </div>
        `;


    els.intelligence.innerHTML =
        html;

    setupSummaryEditor(
        slot
    );
}


function setupSummaryEditor(
    slot
) {

    const container =
        slot.els.intelligence;

    const label =
        slot.model.label;

    const editor =
        container.querySelector(
            ".meeting-summary-editor"
        );

    const actions =
        container.querySelector(
            ".intel-actions"
        );

    const saveBtn =
        container.querySelector(
            ".save-summary-btn"
        );

    const cancelBtn =
        container.querySelector(
            ".cancel-summary-btn"
        );

    if (
        !editor
        ||
        !actions
        ||
        !saveBtn
        ||
        !cancelBtn
    ) {

        return;
    }

    const editableFields =
        container.querySelectorAll(
            "[data-edit-path]"
        );

    function showActions() {

        actions.classList.add(
            "visible"
        );
    }

    editor.addEventListener(
        "input",
        showActions
    );

    editableFields.forEach(
        field => {

            field.addEventListener(
                "input",
                showActions
            );
        }
    );


    function setPath(
        object,
        path,
        value
    ) {

        const parts =
            path.split(
                "."
            );

        let target =
            object;

        for (
            let i = 0;
            i < parts.length - 1;
            i++
        ) {

            target =
                target[
                    parts[i]
                ];

            if (
                !target
            ) {

                return;
            }
        }

        target[
            parts[
                parts.length - 1
            ]
        ] = value;
    }


    function collectEditedData() {

        const edited =
            deepClone(
                slot.intel
                ||
                {}
            );

        editableFields.forEach(
            field => {

                const path =
                    field.dataset.editPath;

                const value =
                    field.innerText
                        .replace(
                            / /g,
                            " "
                        )
                        .trim();

                setPath(
                    edited,
                    path,
                    value
                );
            }
        );

        edited.meeting_summary =
            editor.value;

        return edited;
    }


    saveBtn.addEventListener(
        "click",
        async () => {

            const edited =
                collectEditedData();

            saveBtn.disabled =
                true;

            setStatus(
                `Saving meeting intelligence changes (${label})...`
            );

            try {

                if (
                    currentMeetingId
                ) {

                    const response =
                        await fetch(
                            `/api/meetings/${currentMeetingId}`,
                            {
                                method:
                                    "PATCH",

                                credentials:
                                    "same-origin",

                                headers: {

                                    "Content-Type":
                                        "application/json"
                                },

                                body:
                                    JSON.stringify(
                                        {
                                            model:
                                                slot.model.key,

                                            title:
                                                edited.title,

                                            objective:
                                                edited.objective,

                                            meeting_summary:
                                                edited.meeting_summary,

                                            tasks_assigned:
                                                edited.tasks_assigned,

                                            decision_points:
                                                edited.decision_points,

                                            objections:
                                                edited.objections,

                                            action_items:
                                                edited.action_items
                                        }
                                    )
                            }
                        );

                    if (
                        !response.ok
                    ) {

                        const errBody =
                            await response
                                .json()
                                .catch(
                                    () => ({})
                                );

                        throw new Error(
                            errBody.detail
                            ||
                            "The server rejected the changes."
                        );
                    }
                }

                slot.intel =
                    edited;

                slot.intelSaved =
                    deepClone(
                        edited
                    );

                actions.classList.remove(
                    "visible"
                );

                setStatus(
                    currentMeetingId
                        ? `Meeting intelligence changes saved (${label}).`
                        : `Changes kept for this session (${label}) — this summary was never saved to your history.`
                );

                log(
                    `Meeting intelligence fields manually edited and saved (${label}).`
                );

                notifyResultsChanged();

            } catch (
                error
            ) {

                setStatus(
                    `Could not save changes (${label}): ${error.message}`
                );

                log(
                    `Meeting intelligence save failed (${label}): ${error.message}`
                );

            } finally {

                saveBtn.disabled =
                    false;
            }
        }
    );

    cancelBtn.addEventListener(
        "click",
        () => {

            if (
                slot.intelSaved
            ) {

                renderIntelligence(
                    slot,
                    slot.intelSaved,
                    false
                );
            }

            setStatus(
                `Changes cancelled (${label}).`
            );

            log(
                `Meeting intelligence edits cancelled (${label}).`
            );
        }
    );
}


function escapeHtml(
    value
) {

    return String(value)
        .replaceAll(
            "&",
            "&amp;"
        )
        .replaceAll(
            "<",
            "&lt;"
        )
        .replaceAll(
            ">",
            "&gt;"
        )
        .replaceAll(
            '"',
            "&quot;"
        )
        .replaceAll(
            "'",
            "&#039;"
        );
}


function escapeRegExp(
    value
) {

    return String(value).replace(
        /[.*+?^${}()|[\]\\]/g,
        "\\$&"
    );
}


function updateSearchCount() {

    const count =
        searchMatches.length;

    if (
        !transcriptSearch.value.trim()
    ) {

        searchCount.textContent =
            "0 matches";

    } else if (
        !count
    ) {

        searchCount.textContent =
            "No matches";

    } else {

        searchCount.textContent =
            `${currentSearchIndex + 1} / ${count}`;
    }

    searchPrevBtn.disabled =
        !count;

    searchNextBtn.disabled =
        !count;
}


function setCurrentSearchMatch(
    index
) {

    if (
        !searchMatches.length
    ) {

        currentSearchIndex =
            -1;

        updateSearchCount();

        return;
    }

    currentSearchIndex =
        (
            index
            +
            searchMatches.length
        ) % searchMatches.length;

    searchMatches.forEach(
        (
            mark,
            i
        ) => {

            mark.classList.toggle(
                "current",
                i === currentSearchIndex
            );
        }
    );

    searchMatches[
        currentSearchIndex
    ].scrollIntoView(
        {
            behavior:
                "smooth",
            block:
                "center"
        }
    );

    updateSearchCount();
}


function highlightTranscriptSearch() {

    const query =
        transcriptSearch.value.trim();

    searchMatches =
        [];

    currentSearchIndex =
        -1;

    if (
        !transcript
    ) {

        updateSearchCount();

        return;
    }

    const div =
        document.createElement(
            "div"
        );

    if (
        !query
    ) {

        div.textContent =
            transcript;

        transcriptEl.innerHTML =
            "";

        transcriptEl.appendChild(
            div
        );

        updateSearchCount();

        return;
    }

    const regex =
        new RegExp(
            escapeRegExp(
                query
            ),
            "gi"
        );

    let lastIndex =
        0;

    let match;

    while (
        (
            match =
                regex.exec(
                    transcript
                )
        ) !== null
    ) {

        if (
            match.index > lastIndex
        ) {

            div.appendChild(
                document.createTextNode(
                    transcript.slice(
                        lastIndex,
                        match.index
                    )
                )
            );
        }

        const mark =
            document.createElement(
                "mark"
            );

        mark.className =
            "transcript-match";

        mark.textContent =
            match[0];

        div.appendChild(
            mark
        );

        searchMatches.push(
            mark
        );

        lastIndex =
            match.index
            +
            match[0].length;

        if (
            match[0].length === 0
        ) {

            regex.lastIndex++;
        }
    }

    if (
        lastIndex < transcript.length
    ) {

        div.appendChild(
            document.createTextNode(
                transcript.slice(
                    lastIndex
                )
            )
        );
    }

    transcriptEl.innerHTML =
        "";

    transcriptEl.appendChild(
        div
    );

    if (
        searchMatches.length
    ) {

        setCurrentSearchMatch(
            0
        );

    } else {

        updateSearchCount();
    }
}


function resetTranscriptSearch() {

    searchMatches =
        [];

    currentSearchIndex =
        -1;

    transcriptSearch.value =
        "";

    transcriptSearch.disabled =
        !transcript;

    updateSearchCount();
}


transcriptSearch.addEventListener(
    "input",
    highlightTranscriptSearch
);


transcriptSearch.addEventListener(
    "keydown",
    event => {

        if (
            event.key === "Enter"
        ) {

            event.preventDefault();

            if (
                searchMatches.length
            ) {

                setCurrentSearchMatch(
                    currentSearchIndex
                    +
                    (
                        event.shiftKey
                            ? -1
                            : 1
                    )
                );
            }
        }

        if (
            event.key === "Escape"
        ) {

            transcriptSearch.value =
                "";

            highlightTranscriptSearch();
        }
    }
);


searchPrevBtn.addEventListener(
    "click",
    () => {

        setCurrentSearchMatch(
            currentSearchIndex - 1
        );
    }
);


searchNextBtn.addEventListener(
    "click",
    () => {

        setCurrentSearchMatch(
            currentSearchIndex + 1
        );
    }
);


async function startRecording() {

    if (isRecording) return;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
        setStatus("This browser does not support screen/tab audio sharing. Use a supported desktop browser.");
        return;
    }

    let modeChoice = "2";

    recordBtn.disabled = true;
    sessionEpoch++;
    clearReportReady();
    clearReportSelection();

    transcript = "";
    currentMeetingId = null;
    currentMeetingDuration = null;

    startNewSession();
    updateGenerateButton();

    setStatus("Preparing microphone and selected audio source...");

    transcriptEl.innerHTML = `
        <div class="placeholder">
            Recording in progress...
        </div>
    `;
    resetTranscriptSearch();
    modelSlots.forEach(slot => resetSlot(slot, "recording"));

    try {
        setStatus("Choose the Teams tab/window/screen in the browser sharing popup and enable audio sharing if available...");
        try {
            meetTabStream = await navigator.mediaDevices.getDisplayMedia({
                video: true,
                audio: true
            });
        } catch (shareError) {
            throw new Error(
                "The browser sharing popup was cancelled or could not be opened. " +
                "No recording was started. Click Start Recording again and select the Teams tab/window/screen. Details: " +
                (shareError.message || shareError)
            );
        }

        const sharedAudioTracks = meetTabStream.getAudioTracks();
        let sharedRemoteAudioAvailable = sharedAudioTracks.length > 0;

        if (!sharedRemoteAudioAvailable) {
            const noAudioMessage =
                "The selected tab, window, or screen did not provide an audio track. Vidatha may record only your microphone audio, so other participants' voices may be missing from the transcript.\n\n" +
                "To capture both sides, Select the tab or window where your meeting or interview is open, and turn on audio sharing.";
            const noAudioChoices = [
                "OK: Continue recording with microphone audio only.",
                "Cancel: Stop recording and try again."
            ];

            const continueMicOnly = window.MeetMindDialog
                ? await window.MeetMindDialog.confirm({
                    title: "Meeting Audio Not Shared",
                    message: noAudioMessage,
                    items: noAudioChoices,
                    confirmText: "OK",
                    cancelText: "Cancel"
                })
                : window.confirm(
                    "Meeting Audio Not Shared\n\n" +
                    noAudioMessage + "\n\n" +
                    noAudioChoices.join("\n")
                );

            if (!continueMicOnly) {
                meetTabStream.getTracks().forEach(t => {
                    try { t.stop(); } catch (e) {}
                });
                meetTabStream = null;
                throw new Error(
                    "Recording cancelled because meeting audio was not shared. Click Start Recording again and enable Share tab audio for the Teams tab, if available."
                );
            }

            meetTabStream.getTracks().forEach(t => {
                try { t.stop(); } catch (e) {}
            });
            meetTabStream = null;
            setStatus("Warning: microphone-only recording selected. Other participants may be missing from the transcript.");
            log("User chose to continue with microphone-only recording because the shared source had no audio track.");
        }

        if (meetTabStream) {
            meetTabStream.getVideoTracks().forEach(t => {
                try { t.stop(); } catch (e) {}
            });
        }

        await openWebSocket();

        if (!websocket || websocket.readyState !== WebSocket.OPEN) {
            throw new Error("WebSocket connection failed.");
        }

        setStatus("Requesting microphone permission...");
        microphoneStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });

        if (!microphoneStream.getAudioTracks().length) {
            throw new Error("No microphone input was detected.");
        }

        log("Microphone ready: " + microphoneStream.getAudioTracks()
            .map(t => `${t.label || "default microphone"} (${t.readyState})`)
            .join(" | "));

        let remoteAudioAvailable = sharedRemoteAudioAvailable && !!meetTabStream;
        const remoteTracks = meetTabStream ? meetTabStream.getAudioTracks() : [];
        let remoteSourceLabel = remoteTracks.map(t => t.label || "shared browser audio").join(", ");
        let requestedAudioMode = remoteAudioAvailable ? "microphone_and_meet_tab" : "microphone";
        let requestedAudioSources = remoteAudioAvailable
            ? ["microphone", "teams_browser_tab"]
            : ["microphone"];

        remoteTracks.forEach(track => {
            track.addEventListener("ended", () => {
                log("Shared Teams audio ended. Two-way capture may no longer be available.");
                if (isRecording) {
                    setStatus("Warning: Teams shared audio ended. Check the sharing permission.");
                }
            });
        });

        if (remoteAudioAvailable) {
            log("Remote audio source ready: " + remoteSourceLabel);
        } else {
            log("Remote audio source unavailable; continuing with microphone-only recording as confirmed by the user.");
        }

        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        if (audioContext.state === "suspended") await audioContext.resume();

        sourceNode = audioContext.createMediaStreamSource(microphoneStream);

        if (remoteAudioAvailable && meetTabStream) {
            meetTabSourceNode = audioContext.createMediaStreamSource(meetTabStream);
        }

        processorNode = audioContext.createScriptProcessor(4096, 1, 1);

        const mixBus = audioContext.createGain();
        mixBus.gain.value = 0.5;
        sourceNode.connect(mixBus);

        if (meetTabSourceNode) {
            const remoteGain = audioContext.createGain();
            remoteGain.gain.value = 0.5;
            meetTabSourceNode.connect(remoteGain);
            remoteGain.connect(mixBus);
        }

        mixBus.connect(processorNode);

        processorNode.onaudioprocess = function(event) {
            if (!isRecording || recordingPaused) return;

            const input = event.inputBuffer.getChannelData(0);
            if (!input || !input.length) return;

            const pcm16k = downsampleBuffer(
                input,
                audioContext.sampleRate,
                16000
            );
            if (!pcm16k || !pcm16k.length) return;

            const pcmBuffer = floatToPCM16(pcm16k);
            if (!pcmBuffer || !pcmBuffer.byteLength) return;

            recordingPcmChunks.push(pcmBuffer.slice(0));

            if (
                websocket &&
                websocket.readyState === WebSocket.OPEN &&
                !connectionLost &&
                !replayingRecording
            ) {
                websocket.send(pcmBuffer);
            }
        };

        silentGainNode = audioContext.createGain();
        silentGainNode.gain.value = 0;
        processorNode.connect(silentGainNode);
        silentGainNode.connect(audioContext.destination);

        recordingAudioMode = requestedAudioMode;
        recordingPcmChunks = [];

        websocket.send(JSON.stringify({
            command: "start",
            template: activeTemplate(),
            audio_mode: recordingAudioMode,
            audio_sources: requestedAudioSources
        }));

        isRecording = true;
        recordingPaused = false;
        startTimer();

        recordBtn.disabled = false;
        recordBtn.textContent = "Stop Recording";
        recordBtn.classList.add("recording");
        cancelRecordingBtn.hidden = false;

        if (remoteAudioAvailable) {
            setStatus("Recording microphone + remote Teams audio. Verify both voices in the transcript.");
            log("Recording started with two audio sources: microphone + " + remoteSourceLabel);
        } else {
            setStatus("Recording microphone only. Other participant's questions may be missing.");
            log("Recording started in microphone-only mode.");
        }

    } catch (error) {
        log(`Start error: ${error.message}`);
        setStatus(error.message || "Could not start recording.");
        cleanupAudio();

        if (websocket) {
            try { websocket.close(); } catch (e) {}
            websocket = null;
        }

        isRecording = false;
        stopRequested = false;
        connectionLost = false;
        recordingPcmChunks = [];
        recordBtn.disabled = false;
        recordBtn.textContent = "Start Recording";
        recordBtn.classList.remove("recording");
        cancelRecordingBtn.hidden = true;
    }
}

function cleanupAudio() {

    if (processorNode) {
        try {
            processorNode.disconnect();
        } catch (error) {}

        processorNode.onaudioprocess = null;
        processorNode = null;
    }

    if (sourceNode) {
        try {
            sourceNode.disconnect();
        } catch (error) {}

        sourceNode = null;
    }

    if (meetTabSourceNode) {
        try {
            meetTabSourceNode.disconnect();
        } catch (error) {}

        meetTabSourceNode = null;
    }

    if (silentGainNode) {
        try {
            silentGainNode.disconnect();
        } catch (error) {}

        silentGainNode = null;
    }

    if (audioContext) {
        try {
            audioContext.close();
        } catch (error) {}

        audioContext = null;
    }

    if (microphoneStream) {
        microphoneStream.getTracks().forEach(track => {
            try {
                track.stop();
            } catch (error) {}
        });

        microphoneStream = null;
    }

    if (meetTabStream) {
        meetTabStream.getTracks().forEach(track => {
            try {
                track.stop();
            } catch (error) {}
        });

        meetTabStream = null;
    }
}

function stopRecording() {

    if (
        !isRecording
    ) {

        return;
    }


    isRecording =
        false;

    recordingPaused =
        false;

    stopRequested =
        true;

    stopTimer();

    setStatus(
        "Stopping recording and finalizing audio..."
    );

    recordBtn.disabled =
        true;

    recordBtn.textContent =
        "Start Recording";

    recordBtn.classList.remove(
        "recording"
    );

    cancelRecordingBtn.hidden =
        true;

    cleanupAudio();


    if (
        websocket
    ) {

        intentionalSocketClose =
            true;

        try {
            websocket.close();
        } catch (error) {}

        websocket =
            null;
    }

    intentionalSocketClose =
        false;

    connectionLost =
        true;

    reconnectAttempts =
        0;

    log(
        `Stop requested. ${recordingPcmChunks.length} PCM chunks retained locally. Establishing a fresh WebSocket to finalize the complete recording...`
    );

    scheduleWebSocketReconnect();
}


function cancelRecording() {

    if (
        !isRecording
    ) {

        return;
    }

    isRecording =
        false;

    recordingPaused =
        false;

    stopRequested =
        false;

    stopTimer();

    cleanupAudio();

    if (
        reconnectTimer
    ) {

        clearTimeout(
            reconnectTimer
        );

        reconnectTimer =
            null;
    }

    reconnectAttempts =
        0;

    if (
        websocket
    ) {

        websocket.onclose =
            null;

        websocket.onmessage =
            null;

        try {

            if (
                websocket.readyState ===
                    WebSocket.OPEN
            ) {

                websocket.send(
                    JSON.stringify({
                        command: "cancel"
                    })
                );
            }

            websocket.close();

        } catch (error) {}

        websocket =
            null;
    }

    connectionLost =
        false;

    connectionEl.textContent =
        "Ready";

    statusDot.style.background =
        "";

    recordingPcmChunks =
        [];

    timerEl.textContent =
        "00:00";

    recordBtn.disabled =
        false;

    recordBtn.textContent =
        "Start Recording";

    recordBtn.classList.remove(
        "recording"
    );

    cancelRecordingBtn.hidden =
        true;

    transcriptEl.innerHTML = `
        <div class="placeholder">
            Your complete transcript will appear here
            after you stop recording.
        </div>
    `;

    resetTranscriptSearch();

    modelSlots.forEach(
        slot => resetSlot(slot)
    );

    updateGenerateButton();

    setStatus(
        "Recording cancelled. Nothing was transcribed or saved."
    );

    log(
        "Recording cancelled by user. Audio discarded."
    );
}


function adoptMeetingId(
    meetingId
) {

    if (
        meetingId
        &&
        !currentMeetingId
    ) {

        currentMeetingId =
            meetingId;
    }
}


function notifyResultsChanged() {

    document.dispatchEvent(
        new CustomEvent(
            "meetmind:results-changed",
            {
                detail: {
                    meetingId: currentMeetingId
                }
            }
        )
    );
}


async function postGeneration(
    path,
    slot,
    failureMessage
) {

    const response =
        await fetch(
            path,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    transcript: transcript,
                    meeting_id: currentMeetingId,
                    duration_seconds: currentMeetingDuration,
                    model: slot.model.key
                })
            }
        );

    const data =
        await response.json();

    if (!response.ok) {
        throw new Error(
            data.detail || data.error || failureMessage
        );
    }

    if (!data.success) {
        throw new Error(
            data.error || failureMessage
        );
    }

    return data;
}


async function generateSummary(
    slot
) {

    const epoch = sessionEpoch;
    const label = slot.model.label;

    setGenerationStatus(slot, "summary", "generating");
    slot.els.intelligence.innerHTML = loadingHtml(
        `${label} is analyzing the complete transcript...`
    );
    mountWaveLoaders(slot.els.intelligence);
    log(`Sending complete transcript to ${label} for meeting intelligence.`);

    try {
        const data = await postGeneration(
            "/api/meeting/summarize",
            slot,
            "Summary generation failed."
        );

        if (epoch !== sessionEpoch) {
            log(`${label} summary arrived after the meeting on screen changed — not shown.`);
            return null;
        }

        adoptMeetingId(data.meeting_id);
        renderIntelligence(slot, data);
        setGenerationStatus(slot, "summary", "done");
        log(`Meeting intelligence received from ${label}.`);
        notifyResultsChanged();
        return true;

    } catch (error) {
        if (epoch !== sessionEpoch) return null;

        log(`${label} summary error: ${error.message}`);
        slot.els.intelligence.innerHTML = `
            <div class="mindmap-empty result-error">
                Summary generation failed: ${escapeHtml(error.message)}
            </div>
        `;
        setGenerationStatus(slot, "summary", "error", error.message);
        return false;
    }
}


async function generateMindMap(
    slot
) {

    const epoch = sessionEpoch;
    const label = slot.model.label;

    setGenerationStatus(slot, "mindmap", "generating");
    slot.els.mindMapContainer.innerHTML = loadingHtml(
        `${label} is mapping the complete transcript...`
    );
    mountWaveLoaders(slot.els.mindMapContainer);
    log(`Sending complete transcript to ${label} for mind-map generation.`);

    try {
        const data = await postGeneration(
            "/api/meeting/mindmap",
            slot,
            "Mind-map generation failed."
        );

        if (epoch !== sessionEpoch) {
            log(`${label} mind map arrived after the meeting on screen changed — not shown.`);
            return null;
        }

        adoptMeetingId(data.meeting_id);
        renderMindMap(slot, data.mindmap);
        setGenerationStatus(
            slot,
            "mindmap",
            slot.mindmap ? "done" : "error",
            slot.mindmap ? "" : "No mind map was generated."
        );
        log(`Mind map received from ${label}.`);
        notifyResultsChanged();
        return !!slot.mindmap;

    } catch (error) {
        if (epoch !== sessionEpoch) return null;

        log(`${label} mind-map error: ${error.message}`);
        clearMindMap(slot, `
            <div class="mindmap-empty result-error">
                Mind map generation failed: ${escapeHtml(error.message)}
            </div>
        `);
        setGenerationStatus(slot, "mindmap", "error", error.message);
        return false;
    }
}


async function generateCombinedForModel(
    slot
) {
    const needsSummary = !slot.intel;
    const needsMindMap = !slot.mindmap;
    const outcomes = [];

    if (needsSummary && slot.status.summary !== "generating") {
        outcomes.push(await generateSummary(slot));
    }

    if (needsMindMap && slot.status.mindmap !== "generating") {
        outcomes.push(await generateMindMap(slot));
    }

    return outcomes;
}


async function generateSelected() {

    if (!transcript || !transcript.trim()) {
        setStatus("No transcript available.");
        return;
    }

    const slots = selectedSlots().filter(
        slot =>
            (!slot.intel && slot.status.summary !== "generating")
            ||
            (!slot.mindmap && slot.status.mindmap !== "generating")
    );

    if (!slots.length) {
        setStatus(
            "The selected model(s) already have a summary and mind map — edit them with Save Changes."
        );
        return;
    }

    const epoch = sessionEpoch;
    const labels = slots.map(slot => slot.model.label).join(" and ");
    setStatus(`Generating summary and mind map with ${labels}...`);

    const outcomes = await Promise.all(
        slots.map(slot => generateCombinedForModel(slot))
    );

    if (epoch !== sessionEpoch) return;

    const flattened = outcomes.flat();
    const failed = flattened.filter(outcome => outcome === false).length;
    const succeeded = flattened.filter(outcome => outcome === true).length;

    if (failed && succeeded) {
        setStatus(
            `Generation finished with ${failed} failure(s). Successful results were kept; retry Generate for failed outputs.`
        );
    } else if (failed) {
        setStatus(
            `Generation finished with ${failed} failure(s). Retry Generate for failed outputs.`
        );
    } else {
        setStatus(`Summary and mind-map generation complete (${labels}).`);
    }
}


function createMindMapNode(
    node,
    isRoot = false,
    path = []
) {

    if (
        !node
        ||
        !node.title
    ) {
        return null;
    }

    const wrapper =
        document.createElement(
            "div"
        );

    wrapper.className =
        isRoot
            ? "mindmap-root"
            : "mindmap-branch";


    const nodeElement =
        document.createElement(
            "div"
        );

    nodeElement.className =
        isRoot
            ? "mindmap-root-title"
            : "mindmap-node";

    nodeElement.textContent =
        node.title;

    nodeElement.contentEditable =
        "true";

    nodeElement.spellcheck =
        true;

    nodeElement.setAttribute(
        "role",
        "textbox"
    );

    nodeElement.setAttribute(
        "aria-label",
        isRoot
            ? "Editable mind-map title"
            : "Editable mind-map node"
    );

    nodeElement.dataset.editPath =
        path.concat(
            "title"
        ).join(".");

    wrapper.appendChild(
        nodeElement
    );


    const children =
        Array.isArray(
            node.children
        )
            ? node.children
            : [];


    if (
        children.length > 0
    ) {

        const childrenContainer =
            document.createElement(
                "div"
            );

        childrenContainer.className =
            isRoot
                ? "mindmap-children"
                : "mindmap-node-children";


        children.forEach(
            (
                child,
                childIndex
            ) => {

                const childNode =
                    createMindMapNode(
                        child,
                        false,
                        path.concat(
                            "children",
                            childIndex
                        )
                    );

                if (
                    childNode
                ) {

                    childrenContainer.appendChild(
                        childNode
                    );
                }
            }
        );


        wrapper.appendChild(
            childrenContainer
        );
    }


    return wrapper;
}


function clearMindMap(
    slot,
    html
) {

    const els =
        slot.els;

    slot.mindmap =
        null;

    slot.mindmapSaved =
        null;

    els.mindMapContainer.innerHTML =
        html;

    els.mindMapEditHint.classList.remove(
        "visible"
    );

    els.mindMapDownloadActions.classList.remove(
        "visible"
    );

    els.mindMapActions.classList.remove(
        "visible"
    );

    els.downloadMindMapBtn.disabled =
        true;

    els.mindMapContainer.style.removeProperty(
        "--mindmap-columns"
    );
}


function centerMindMap(
    slot
) {

    requestAnimationFrame(
        () => {

            const container =
                slot.els.mindMapContainer;

            container.scrollLeft =
                (
                    container.scrollWidth
                    -
                    container.clientWidth
                )
                / 2;
        }
    );
}


function renderMindMap(
    slot,
    mindmap,
    resetSaved = true
) {

    const els =
        slot.els;

    const emptyHtml =
        `
        <div class="mindmap-empty">
            No mind map was generated.
        </div>
        `;

    if (
        !mindmap
        ||
        !mindmap.title
    ) {

        clearMindMap(
            slot,
            emptyHtml
        );

        return;
    }


    slot.mindmap =
        deepClone(
            mindmap
        );

    const topLevelCount =
        Array.isArray(slot.mindmap.children)
            ? slot.mindmap.children.length
            : 0;

    const columnCount =
        Math.max(
            1,
            Math.min(
                topLevelCount || 1,
                5
            )
        );

    els.mindMapContainer.style.setProperty(
        "--mindmap-columns",
        columnCount
    );

    if (
        resetSaved
        ||
        !slot.mindmapSaved
    ) {

        slot.mindmapSaved =
            deepClone(
                mindmap
            );
    }


    const root =
        createMindMapNode(
            slot.mindmap,
            true,
            []
        );


    if (
        !root
    ) {

        clearMindMap(
            slot,
            emptyHtml
        );

        return;
    }


    els.mindMapContainer.innerHTML =
        "";

    els.mindMapContainer.appendChild(
        root
    );

    els.mindMapEditHint.classList.add(
        "visible"
    );

    els.mindMapDownloadActions.classList.add(
        "visible"
    );

    els.downloadMindMapBtn.disabled =
        false;

    setupMindMapEditor(
        slot
    );

    centerMindMap(
        slot
    );
}


function setupMindMapEditor(
    slot
) {

    const editableFields =
        slot.els.mindMapContainer.querySelectorAll(
            "[data-edit-path]"
        );

    editableFields.forEach(
        field => {

            field.addEventListener(
                "input",
                () => {

                    field.classList.add(
                        "mindmap-editable-active"
                    );

                    slot.els.mindMapActions.classList.add(
                        "visible"
                    );
                }
            );
        }
    );
}


function setMindMapPath(
    object,
    path,
    value
) {

    const parts =
        path.split(
            "."
        );

    let target =
        object;

    for (
        let i = 0;
        i < parts.length - 1;
        i++
    ) {

        target =
            target[
                parts[i]
            ];

        if (
            target === undefined
            ||
            target === null
        ) {

            return;
        }
    }

    target[
        parts[
            parts.length - 1
        ]
    ] = value;
}


function collectEditedMindMap(
    slot
) {

    const edited =
        deepClone(
            slot.mindmap
            ||
            {}
        );

    slot.els.mindMapContainer.querySelectorAll(
        "[data-edit-path]"
    ).forEach(
        field => {

            const value =
                field.innerText
                    .replace(
                        / /g,
                        " "
                    )
                    .trim();

            setMindMapPath(
                edited,
                field.dataset.editPath,
                value
            );
        }
    );

    return edited;
}


async function saveMindMapEdits(
    slot
) {

    const els =
        slot.els;

    const label =
        slot.model.label;

    const edited =
        collectEditedMindMap(
            slot
        );


    if (
        !edited
        ||
        !edited.title
    ) {

        setStatus(
            "Mind-map title cannot be empty."
        );

        return;
    }


    els.saveMindMapBtn.disabled =
        true;


    if (
        currentMeetingId
    ) {

        try {

            const response =
                await fetch(
                    `/api/meetings/${currentMeetingId}`,
                    {
                        method:
                            "PATCH",

                        credentials:
                            "same-origin",

                        headers: {

                            "Content-Type":
                                "application/json"
                        },

                        body:
                            JSON.stringify(
                                {
                                    model:
                                        slot.model.key,
                                    mindmap:
                                        edited,
                                    title:
                                        edited.title
                                }
                            )
                    }
                );

            if (
                !response.ok
            ) {

                const errBody =
                    await response
                        .json()
                        .catch(
                            () => ({})
                        );

                throw new Error(
                    errBody.detail
                    ||
                    "The server rejected the mind-map changes."
                );
            }

        } catch (
            error
        ) {

            log(
                `Mind-map save error (${label}): ${error.message}`
            );

            setStatus(
                `Mind-map save failed (${label}): ${error.message}`
            );

            els.saveMindMapBtn.disabled =
                false;

            return;
        }
    }


    slot.mindmapSaved =
        deepClone(
            edited
        );

    els.saveMindMapBtn.disabled =
        false;

    els.mindMapActions.classList.remove(
        "visible"
    );


    renderMindMap(
        slot,
        slot.mindmapSaved,
        false
    );


    setStatus(
        `Mind map changes saved (${label}).`
    );

    log(
        `Mind map fields manually edited and saved (${label}).`
    );

    notifyResultsChanged();
}


function cancelMindMapEdits(
    slot
) {

    if (
        slot.mindmapSaved
    ) {

        renderMindMap(
            slot,
            slot.mindmapSaved,
            false
        );
    }


    slot.els.mindMapActions.classList.remove(
        "visible"
    );


    setStatus(
        `Mind map changes cancelled (${slot.model.label}).`
    );

    log(
        `Mind map edits cancelled (${slot.model.label}).`
    );
}


const mindMapBackdrop =
    document.createElement(
        "div"
    );

mindMapBackdrop.className =
    "mindmap-backdrop";

mindMapBackdrop.hidden =
    true;

document.body.appendChild(
    mindMapBackdrop
);

let expandedMindMapSlot =
    null;


function updateExpandButton(
    slot
) {

    const expanded =
        slot.els.mindmapPanel.classList.contains(
            "is-expanded"
        );

    slot.els.expandBtn.setAttribute(
        "aria-pressed",
        String(
            expanded
        )
    );

    slot.els.expandBtn.setAttribute(
        "aria-label",
        expanded
            ? `Exit full view of the ${slot.model.label} mind map`
            : `Expand the ${slot.model.label} mind map`
    );

    slot.els.expandBtn.title =
        expanded
            ? "Exit full view (Esc)"
            : "Expand mind map";
}


function setMindMapExpanded(
    slot,
    expanded
) {

    const panel =
        slot.els.mindmapPanel;

    if (
        panel.classList.contains(
            "is-expanded"
        ) === expanded
    ) {

        return;
    }

    if (
        expanded
    ) {

        if (
            expandedMindMapSlot
        ) {

            setMindMapExpanded(
                expandedMindMapSlot,
                false
            );
        }

        slot.els.mindmapSpacer.style.height =
            `${panel.offsetHeight}px`;

        slot.els.mindmapSpacer.hidden =
            false;

        expandedMindMapSlot =
            slot;

    } else {

        slot.els.mindmapSpacer.hidden =
            true;

        if (
            expandedMindMapSlot === slot
        ) {

            expandedMindMapSlot =
                null;
        }
    }

    panel.classList.toggle(
        "is-expanded",
        expanded
    );

    mindMapBackdrop.hidden =
        !expandedMindMapSlot;

    document.body.classList.toggle(
        "mindmap-expanded",
        !!expandedMindMapSlot
    );

    updateExpandButton(
        slot
    );

    centerMindMap(
        slot
    );
}


mindMapBackdrop.addEventListener(
    "click",
    () => {

        if (
            expandedMindMapSlot
        ) {

            setMindMapExpanded(
                expandedMindMapSlot,
                false
            );
        }
    }
);


async function downloadMindMapImage(
    slot
) {

    const els =
        slot.els;

    if (
        !slot.mindmap
        ||
        !slot.mindmap.title
    ) {

        setStatus(
            "No mind map is available to download."
        );

        return;
    }


    if (
        typeof html2canvas !== "function"
    ) {

        setStatus(
            "Mind-map image export is unavailable."
        );

        log(
            "Mind-map export failed: html2canvas could not be loaded."
        );

        return;
    }


    slot.mindmap =
        collectEditedMindMap(
            slot
        );


    if (
        !slot.mindmap.title
    ) {

        setStatus(
            "Mind-map title cannot be empty."
        );

        return;
    }


    const originalText =
        els.downloadMindMapBtn.textContent;


    els.downloadMindMapBtn.disabled =
        true;

    els.downloadMindMapBtn.textContent =
        "Preparing Image...";


    setStatus(
        `Preparing mind-map image (${slot.model.label})...`
    );


    log(
        `Exporting the ${slot.model.label} mind map as PNG.`
    );


    let exportWrapper =
        null;


    try {

        exportWrapper =
            document.createElement(
                "div"
            );

        exportWrapper.style.position =
            "fixed";

        exportWrapper.style.left =
            "-100000px";

        exportWrapper.style.top =
            "0";

        exportWrapper.style.width =
            `${Math.max(
                els.mindMapContainer.scrollWidth,
                els.mindMapContainer.clientWidth
            ) + 80}px`;

        exportWrapper.style.padding =
            "40px";

        exportWrapper.style.background =
            "#ffffff";

        exportWrapper.style.boxSizing =
            "border-box";


        const clone =
            els.mindMapContainer.cloneNode(
                true
            );

        clone.style.width =
            "max-content";

        clone.style.height =
            "auto";

        clone.style.maxHeight =
            "none";

        clone.style.overflow =
            "visible";

        clone.style.border =
            "0";

        clone.classList.add(
            "mindmap-export-mode"
        );


        clone.querySelectorAll(
            "[contenteditable]"
        ).forEach(
            element => {

                element.removeAttribute(
                    "contenteditable"
                );

                element.removeAttribute(
                    "data-edit-path"
                );

                element.removeAttribute(
                    "role"
                );

                element.removeAttribute(
                    "aria-label"
                );
            }
        );


        exportWrapper.appendChild(
            clone
        );

        document.body.appendChild(
            exportWrapper
        );


        await new Promise(
            resolve =>
                requestAnimationFrame(
                    () =>
                        requestAnimationFrame(
                            resolve
                        )
                )
        );


        const canvas =
            await html2canvas(
                exportWrapper,
                {
                    backgroundColor:
                        "#ffffff",

                    scale:
                        Math.min(
                            2,
                            window.devicePixelRatio
                            || 1
                        ),

                    useCORS:
                        true,

                    logging:
                        false,

                    width:
                        exportWrapper.scrollWidth,

                    height:
                        exportWrapper.scrollHeight,

                    windowWidth:
                        Math.max(
                            document.documentElement.clientWidth,
                            exportWrapper.scrollWidth
                        ),

                    windowHeight:
                        Math.max(
                            document.documentElement.clientHeight,
                            exportWrapper.scrollHeight
                        )
                }
            );


        const link =
            document.createElement(
                "a"
            );

        const title =
            sanitizeFilename(
                slot.mindmap.title
            )
            ||
            "meeting-mind-map";


        link.download =
            `${title}_${sanitizeFilename(slot.model.key)}_mindmap.png`;

        link.href =
            canvas.toDataURL(
                "image/png"
            );

        document.body.appendChild(
            link
        );

        link.click();

        link.remove();


        setStatus(
            `Mind map image downloaded (${slot.model.label}).`
        );

        log(
            `Mind map PNG download completed (${slot.model.label}).`
        );

    } catch (
        error
    ) {

        log(
            `Mind-map image export failed: ${error.message}`
        );

        setStatus(
            `Mind-map image export failed: ${error.message}`
        );

    } finally {

        if (
            exportWrapper
            &&
            exportWrapper.parentNode
        ) {

            exportWrapper.parentNode.removeChild(
                exportWrapper
            );
        }

        els.downloadMindMapBtn.disabled =
            false;

        els.downloadMindMapBtn.textContent =
            originalText;
    }
}


function getExportData(
    slot
) {

    const data =
        slot.intelSaved || {};

    return {

        title:
            data.title
            ||
            "Untitled Meeting",

        duration:
            formatDuration(
                currentMeetingDuration
            ),

        objective:
            data.objective
            ||
            "Objective could not be generated.",

        meeting_summary:
            data.meeting_summary
            ||
            "No summary available.",

        tasks_assigned:
            Array.isArray(
                data.tasks_assigned
            )
                ? data.tasks_assigned
                : [],

        decision_points:
            Array.isArray(
                data.decision_points
            )
                ? data.decision_points
                : [],

        objections:
            Array.isArray(
                data.objections
            )
                ? data.objections
                : [],

        action_items:
            Array.isArray(
                data.action_items
            )
                ? data.action_items
                : []
    };
}


function exportItemText(
    item
) {

    if (
        item
        &&
        typeof item === "object"
    ) {

        let value =
            item.task
            ||
            item.text
            ||
            "";

        if (
            item.assignee
        ) {

            value +=
                ` — Assignee: ${item.assignee}`;
        }

        if (
            item.deadline
        ) {

            value +=
                ` — Deadline: ${item.deadline}`;
        }

        return value;
    }

    return String(
        item || ""
    );
}


function exportList(
    items
) {

    if (
        !items.length
    ) {

        return "- None identified.";
    }

    return items
        .map(
            (
                item,
                index
            ) =>
                `${index + 1}. ${exportItemText(item)}`
        )
        .join(
            "\n"
        );
}


function sanitizeFilename(
    value
) {

    return String(
        value || "meeting-summary"
    )
        .replace(
            /[<>:"/\\|?*]+/g,
            ""
        )
        .replace(
            /\s+/g,
            "_"
        )
        .slice(
            0,
            100
        );
}


function exportFileStem(
    slot,
    data
) {

    return `${sanitizeFilename(data.title)}_${sanitizeFilename(slot.model.key)}`;
}


function buildMarkdownSummary(
    slot
) {

    const data =
        getExportData(
            slot
        );

    const durationLine =
        data.duration
            ? `\n**Duration:** ${data.duration}\n`
            : "";

    return `# ${data.title}

_Generated by ${slot.model.label} with Vidatha._
${durationLine}
## Objective

${data.objective}

## Meeting Summary

${data.meeting_summary}

## Tasks

${exportList(data.tasks_assigned)}

## Decisions

${exportList(data.decision_points)}

## Objections

${exportList(data.objections)}

## Action Items

${exportList(data.action_items)}
`;
}


function downloadMarkdown(
    slot
) {

    const data =
        getExportData(
            slot
        );

    const blob =
        new Blob(
            [
                buildMarkdownSummary(
                    slot
                )
            ],
            {
                type:
                    "text/markdown;charset=utf-8"
            }
        );

    const url =
        URL.createObjectURL(
            blob
        );

    const anchor =
        document.createElement(
            "a"
        );

    anchor.href =
        url;

    anchor.download =
        `${exportFileStem(slot, data)}.md`;

    document.body.appendChild(
        anchor
    );

    anchor.click();

    anchor.remove();

    URL.revokeObjectURL(
        url
    );

    setStatus(
        `Markdown summary downloaded (${slot.model.label}).`
    );

    log(
        `Meeting summary exported as Markdown (${slot.model.label}).`
    );
}


function pdfWrite(
    doc,
    text,
    x,
    y,
    width
) {

    const pageHeight =
        doc.internal.pageSize.getHeight();

    const lines =
        doc.splitTextToSize(
            String(text || ""),
            width
        );

    lines.forEach(
        line => {

            if (
                y > pageHeight - 18
            ) {

                doc.addPage();

                y = 18;
            }

            doc.text(
                line,
                x,
                y
            );

            y += 5.5;
        }
    );

    return y;
}


function pdfSection(
    doc,
    heading,
    text,
    y
) {

    const width =
        doc.internal.pageSize.getWidth() - 30;

    doc.setFont(
        "helvetica",
        "bold"
    );

    doc.setFontSize(
        12
    );

    y =
        pdfWrite(
            doc,
            heading,
            15,
            y,
            width
        ) + 2;

    doc.setFont(
        "helvetica",
        "normal"
    );

    doc.setFontSize(
        10
    );

    y =
        pdfWrite(
            doc,
            text,
            15,
            y,
            width
        ) + 7;

    return y;
}


function writeSummaryPdf(
    doc,
    data,
    modelLabel
) {

    let y = 20;

    doc.setFont(
        "helvetica",
        "bold"
    );

    doc.setFontSize(
        20
    );

    y =
        pdfWrite(
            doc,
            data.title,
            15,
            y,
            doc.internal.pageSize.getWidth() - 30
        ) + 4;

    doc.setFont(
        "helvetica",
        "normal"
    );

    doc.setFontSize(
        9
    );

    y =
        pdfWrite(
            doc,
            `Vidatha — AI powered Intelligence — generated by ${modelLabel}` +
            (
                data.duration
                    ? ` — Duration: ${data.duration}`
                    : ""
            ),
            15,
            y,
            doc.internal.pageSize.getWidth() - 30
        ) + 8;

    y = pdfSection(
        doc,
        "Objective",
        data.objective,
        y
    );

    y = pdfSection(
        doc,
        "Meeting Summary",
        data.meeting_summary,
        y
    );

    y = pdfSection(
        doc,
        "Tasks",
        exportList(
            data.tasks_assigned
        ),
        y
    );

    y = pdfSection(
        doc,
        "Decisions",
        exportList(
            data.decision_points
        ),
        y
    );

    if (
        data.objections.length
    ) {

        y = pdfSection(
            doc,
            "Objections",
            exportList(
                data.objections
            ),
            y
        );
    }

    if (
        data.action_items.length
    ) {

        y = pdfSection(
            doc,
            "Action Items",
            exportList(
                data.action_items
            ),
            y
        );
    }

    return y;
}


function downloadPdf(
    slot
) {

    if (
        !window.jspdf
        ||
        !window.jspdf.jsPDF
    ) {

        setStatus(
            "PDF export is unavailable. Check your internet connection and try again."
        );

        log(
            "PDF export failed: jsPDF could not be loaded."
        );

        return;
    }

    const data =
        getExportData(
            slot
        );

    const doc =
        new window.jspdf.jsPDF(
            {
                unit: "mm",
                format: "a4"
            }
        );

    writeSummaryPdf(
        doc,
        data,
        slot.model.label
    );

    doc.save(
        `${exportFileStem(slot, data)}.pdf`
    );

    setStatus(
        `PDF summary downloaded (${slot.model.label}).`
    );

    log(
        `Meeting summary exported as PDF (${slot.model.label}).`
    );
}


const REPORT_KINDS = [
    {
        kind: "summary",
        label: "Summary"
    },
    {
        kind: "mindmap",
        label: "Mind Map"
    }
];

let fullReportBusy =
    false;

const reportSelection =
    new Set();

const reportRows =
    new Map();


function reportItemId(
    kind,
    key
) {

    return `${kind}:${key}`;
}


function isReportItemReady(
    kind,
    slot
) {

    if (
        kind === "summary"
    ) {

        return !!(
            slot.intel
            &&
            slot.intelSaved
        );
    }

    return !!(
        slot.mindmapSaved
        &&
        slot.mindmapSaved.title
    );
}


function reportItemState(
    kind,
    slot
) {

    if (
        isReportItemReady(
            kind,
            slot
        )
    ) {

        return "ready";
    }

    const status =
        slot.status[kind];

    return (
        status === "generating"
        ||
        status === "error"
    )
        ? status
        : "missing";
}


function selectedReportItems() {

    const items =
        [];

    REPORT_KINDS.forEach(
        def => {

            modelSlots.forEach(
                (
                    slot,
                    key
                ) => {

                    const id =
                        reportItemId(
                            def.kind,
                            key
                        );

                    if (
                        reportSelection.has(id)
                        &&
                        isReportItemReady(
                            def.kind,
                            slot
                        )
                    ) {

                        items.push(
                            {
                                id: id,
                                kind: def.kind,
                                label: def.label,
                                slot: slot
                            }
                        );
                    }
                }
            );
        }
    );

    return items;
}


function describeReportItems(
    items
) {

    return items
        .map(
            item => `${item.label} (${item.slot.model.label})`
        )
        .join(
            " + "
        );
}


function replayAnimation(
    element,
    className
) {

    element.classList.remove(
        className
    );

    void element.offsetWidth;

    element.classList.add(
        className
    );
}


function prefersReducedMotion() {

    return window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;
}


function createReportTile(
    key,
    def
) {

    const tile =
        document.createElement(
            "label"
        );

    tile.className =
        `report-tile report-tile--${def.kind}`;

    tile.innerHTML =
        `
        <input type="checkbox" class="report-tile-input">
        <span class="report-tile-icon" aria-hidden="true"></span>
        <span class="report-tile-text">
            <span class="report-tile-title">${def.label}</span>
            <span class="report-tile-meta"></span>
        </span>
        <span class="report-tile-check" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>
        </span>
        `;

    const input =
        tile.querySelector(
            ".report-tile-input"
        );

    input.addEventListener(
        "change",
        () => {

            const id =
                reportItemId(
                    def.kind,
                    key
                );

            if (
                input.checked
            ) {

                reportSelection.add(
                    id
                );

            } else {

                reportSelection.delete(
                    id
                );
            }

            refreshReportBuilder();
        }
    );

    tile.addEventListener(
        "animationend",
        event => {

            if (
                event.animationName === "report-tile-arrive"
            ) {

                tile.classList.remove(
                    "is-arriving"
                );
            }
        }
    );

    return {
        tile: tile,
        input: input,
        meta: tile.querySelector(
            ".report-tile-meta"
        ),
        state: null
    };
}


function createReportRow(
    key,
    index
) {

    const row =
        document.createElement(
            "div"
        );

    row.className =
        "report-model";

    row.dataset.model =
        key;

    row.innerHTML =
        `
        <div class="report-model-head">
            <span class="report-model-mark" aria-hidden="true"></span>
            <span class="report-model-name"></span>
        </div>
        <div class="report-tiles"></div>
        `;

    if (
        !prefersReducedMotion()
    ) {

        row.classList.add(
            "is-entering"
        );

        row.style.setProperty(
            "--i",
            String(index)
        );

        row.addEventListener(
            "animationend",
            event => {

                if (
                    event.target === row
                ) {

                    row.classList.remove(
                        "is-entering"
                    );
                }
            }
        );
    }

    const tilesEl =
        row.querySelector(
            ".report-tiles"
        );

    const tiles =
        {};

    REPORT_KINDS.forEach(
        def => {

            tiles[def.kind] =
                createReportTile(
                    key,
                    def
                );

            tilesEl.appendChild(
                tiles[def.kind].tile
            );
        }
    );

    return {
        row: row,
        name: row.querySelector(
            ".report-model-name"
        ),
        tiles: tiles
    };
}


function tileMetaText(
    state,
    position
) {

    if (
        state === "ready"
    ) {

        return position
            ? `Included · #${position} in report`
            : "Ready to include";
    }

    if (
        state === "generating"
    ) {

        return "Generating…";
    }

    if (
        state === "error"
    ) {

        return "Generation failed";
    }

    return "Not generated yet";
}


function renderReportOutline(
    items
) {

    const wanted =
        new Set(
            items.map(
                item => item.id
            )
        );

    const chips =
        new Map();

    [
        ...reportOutline.children
    ].forEach(
        chip => {

            if (
                chip.classList.contains(
                    "is-leaving"
                )
            ) {

                return;
            }

            if (
                wanted.has(
                    chip.dataset.id
                )
            ) {

                chips.set(
                    chip.dataset.id,
                    chip
                );

                return;
            }

            if (
                prefersReducedMotion()
            ) {

                chip.remove();

                return;
            }

            chip.classList.remove(
                "is-entering"
            );

            chip.classList.add(
                "is-leaving"
            );

            chip.addEventListener(
                "animationend",
                () => chip.remove(),
                { once: true }
            );
        }
    );

    let previous =
        null;

    items.forEach(
        (
            item,
            index
        ) => {

            let chip =
                chips.get(
                    item.id
                );

            if (
                !chip
            ) {

                chip =
                    document.createElement(
                        "li"
                    );

                chip.className =
                    `report-chip report-chip--${item.kind}`;

                chip.dataset.id =
                    item.id;

                chip.innerHTML =
                    `
                    <span class="report-chip-num"></span>
                    <span class="report-chip-icon" aria-hidden="true"></span>
                    <span class="report-chip-text"></span>
                    `;

                if (
                    !prefersReducedMotion()
                ) {

                    chip.classList.add(
                        "is-entering"
                    );

                    chip.addEventListener(
                        "animationend",
                        () => chip.classList.remove(
                            "is-entering"
                        ),
                        { once: true }
                    );
                }
            }

            chip.querySelector(
                ".report-chip-num"
            ).textContent =
                String(
                    index + 1
                );

            chip.querySelector(
                ".report-chip-text"
            ).textContent =
                `${item.label} · ${item.slot.model.label}`;

            const target =
                previous
                    ? previous.nextSibling
                    : reportOutline.firstChild;

            if (
                chip !== target
            ) {

                reportOutline.insertBefore(
                    chip,
                    target
                );
            }

            previous =
                chip;
        }
    );

    if (
        !items.length
    ) {

        reportOutlineLabel.textContent =
            "Nothing selected yet — tick what should go into the report.";

        return;
    }

    const summaries =
        items.filter(
            item => item.kind === "summary"
        ).length;

    const mindmaps =
        items.length - summaries;

    const parts =
        [];

    if (
        summaries
    ) {

        parts.push(
            `${summaries} ${summaries === 1 ? "summary" : "summaries"}`
        );
    }

    if (
        mindmaps
    ) {

        parts.push(
            `${mindmaps} mind map${mindmaps === 1 ? "" : "s"}`
        );
    }

    reportOutlineLabel.textContent =
        `${items.length} section${items.length === 1 ? "" : "s"} in this report · ${parts.join(", ")}`;
}


function refreshReportBuilder() {

    const keys =
        [
            ...modelSlots.keys()
        ];

    reportRows.forEach(
        (
            entry,
            key
        ) => {

            if (
                !modelSlots.has(key)
            ) {

                entry.row.remove();

                reportRows.delete(
                    key
                );
            }
        }
    );

    keys.forEach(
        (
            key,
            index
        ) => {

            let entry =
                reportRows.get(
                    key
                );

            if (
                !entry
            ) {

                entry =
                    createReportRow(
                        key,
                        index
                    );

                reportRows.set(
                    key,
                    entry
                );
            }

            if (
                reportOptionsEl.children[index] !== entry.row
            ) {

                reportOptionsEl.insertBefore(
                    entry.row,
                    reportOptionsEl.children[index] || null
                );
            }

            entry.name.textContent =
                modelSlots.get(key).model.label;
        }
    );

    const readyIds =
        new Set();

    modelSlots.forEach(
        (
            slot,
            key
        ) => {

            const entry =
                reportRows.get(
                    key
                );

            REPORT_KINDS.forEach(
                def => {

                    const tile =
                        entry.tiles[def.kind];

                    const state =
                        reportItemState(
                            def.kind,
                            slot
                        );

                    if (
                        state === "ready"
                    ) {

                        readyIds.add(
                            reportItemId(
                                def.kind,
                                key
                            )
                        );

                        if (
                            tile.state
                            &&
                            tile.state !== "ready"
                            &&
                            !prefersReducedMotion()
                        ) {

                            replayAnimation(
                                tile.tile,
                                "is-arriving"
                            );
                        }
                    }

                    tile.state =
                        state;

                    tile.tile.dataset.state =
                        state;

                    tile.input.setAttribute(
                        "aria-label",
                        `${def.label} (${slot.model.label})`
                    );
                }
            );
        }
    );

    [
        ...reportSelection
    ].forEach(
        id => {

            if (
                !readyIds.has(id)
            ) {

                reportSelection.delete(
                    id
                );
            }
        }
    );

    const items =
        selectedReportItems();

    const positions =
        new Map(
            items.map(
                (
                    item,
                    index
                ) => [
                    item.id,
                    index + 1
                ]
            )
        );

    reportRows.forEach(
        (
            entry,
            key
        ) => {

            REPORT_KINDS.forEach(
                def => {

                    const tile =
                        entry.tiles[def.kind];

                    const id =
                        reportItemId(
                            def.kind,
                            key
                        );

                    const checked =
                        reportSelection.has(
                            id
                        );

                    tile.input.checked =
                        checked;

                    tile.input.disabled =
                        tile.state !== "ready"
                        ||
                        fullReportBusy;

                    tile.tile.classList.toggle(
                        "is-selected",
                        checked
                    );

                    tile.meta.textContent =
                        tileMetaText(
                            tile.state,
                            positions.get(id)
                        );
                }
            );
        }
    );

    renderReportOutline(
        items
    );

    const count =
        String(
            items.length
        );

    if (
        reportCount.textContent !== count
    ) {

        reportCount.textContent =
            count;

        if (
            !prefersReducedMotion()
        ) {

            replayAnimation(
                reportCount,
                "is-bumping"
            );
        }
    }

    reportBuilder.classList.toggle(
        "has-selection",
        items.length > 0
    );

    const wasDisabled =
        downloadFullReportBtn.disabled;

    downloadFullReportBtn.disabled =
        !items.length
        ||
        fullReportBusy;

    if (
        wasDisabled
        &&
        !downloadFullReportBtn.disabled
        &&
        !prefersReducedMotion()
    ) {

        replayAnimation(
            downloadFullReportBtn,
            "is-armed"
        );
    }

    reportSelectAllBtn.disabled =
        fullReportBusy
        ||
        readyIds.size === 0
        ||
        items.length === readyIds.size;

    reportClearBtn.disabled =
        fullReportBusy
        ||
        !items.length;

    fullReportHint.textContent =
        readyIds.size
            ? "Pick what goes into your PDF — mix and match across models. Summaries come first, then mind maps."
            : "Generate a summary or a mind map to start building a report.";
}


function clearReportSelection() {

    reportSelection.clear();

    refreshReportBuilder();
}


reportSelectAllBtn.addEventListener(
    "click",
    () => {

        modelSlots.forEach(
            (
                slot,
                key
            ) => {

                REPORT_KINDS.forEach(
                    def => {

                        if (
                            isReportItemReady(
                                def.kind,
                                slot
                            )
                        ) {

                            reportSelection.add(
                                reportItemId(
                                    def.kind,
                                    key
                                )
                            );
                        }
                    }
                );
            }
        );

        refreshReportBuilder();
    }
);


reportClearBtn.addEventListener(
    "click",
    clearReportSelection
);


downloadFullReportBtn.addEventListener(
    "click",
    () => downloadFullReport(
        selectedReportItems()
    )
);


const fullReportObserver =
    new MutationObserver(
        refreshReportBuilder
    );


function getUnsavedEdits(
    items
) {

    const pending =
        [];

    items.forEach(
        item => {

            const slot =
                item.slot;

            if (
                item.kind === "summary"
            ) {

                const summaryActions =
                    slot.els.intelligence.querySelector(
                        ".intel-actions"
                    );

                if (
                    summaryActions
                    &&
                    summaryActions.classList.contains(
                        "visible"
                    )
                ) {

                    pending.push(
                        `Meeting Intelligence (${slot.model.label})`
                    );
                }

            } else if (
                slot.els.mindMapActions.classList.contains(
                    "visible"
                )
            ) {

                pending.push(
                    `Mind Map (${slot.model.label})`
                );
            }
        }
    );

    return pending;
}


async function getSignedInUsername() {

    try {

        if (
            !window.MeetMindAuth
        ) {

            return "";
        }

        const session =
            await window.MeetMindAuth.getSession();

        return (
            session
            &&
            session.username
        )
            ? session.username
            : "";

    } catch (
        error
    ) {

        return "";
    }
}


async function confirmUnsavedEdits(
    pending
) {

    const username =
        await getSignedInUsername();

    const message =
        `${username ? `${username}, you` : "You"} have unsaved changes in the panel${pending.length > 1 ? "s" : ""} below. `
        +
        "Kindly save them and try again, or continue with the previously saved version of the summary and mind map.";

    if (
        window.MeetMindDialog
    ) {

        return window.MeetMindDialog.confirm(
            {
                title:
                    "Unsaved changes",

                message:
                    message,

                items:
                    pending,

                confirmText:
                    "Use Saved Version",

                cancelText:
                    "Go Back & Save"
            }
        );
    }

    return window.confirm(
        `${message}\n\n- ${pending.join("\n- ")}`
    );
}


async function renderSavedMindMapCanvas(
    mindmap
) {

    const exportWrapper =
        document.createElement(
            "div"
        );

    exportWrapper.style.position =
        "fixed";

    exportWrapper.style.left =
        "-100000px";

    exportWrapper.style.top =
        "0";

    exportWrapper.style.width =
        "max-content";

    exportWrapper.style.padding =
        "40px";

    exportWrapper.style.background =
        "#ffffff";

    exportWrapper.style.boxSizing =
        "border-box";


    const box =
        document.createElement(
            "div"
        );

    box.className =
        "mindmap-export-mode";

    box.style.width =
        "max-content";

    box.style.padding =
        "24px";

    const topLevelCount =
        Array.isArray(mindmap.children)
            ? mindmap.children.length
            : 0;

    box.style.setProperty(
        "--mindmap-columns",
        Math.max(
            1,
            Math.min(
                topLevelCount || 1,
                5
            )
        )
    );


    const root =
        createMindMapNode(
            mindmap,
            true,
            []
        );

    if (
        !root
    ) {

        throw new Error(
            "The saved mind map is empty."
        );
    }

    box.appendChild(
        root
    );

    box.querySelectorAll(
        "[contenteditable]"
    ).forEach(
        element => {

            element.removeAttribute(
                "contenteditable"
            );

            element.removeAttribute(
                "data-edit-path"
            );

            element.removeAttribute(
                "role"
            );

            element.removeAttribute(
                "aria-label"
            );
        }
    );

    exportWrapper.appendChild(
        box
    );

    document.body.appendChild(
        exportWrapper
    );


    try {

        await new Promise(
            resolve =>
                requestAnimationFrame(
                    () =>
                        requestAnimationFrame(
                            resolve
                        )
                )
        );

        return await html2canvas(
            exportWrapper,
            {
                backgroundColor:
                    "#ffffff",

                scale:
                    2,

                useCORS:
                    true,

                logging:
                    false,

                width:
                    exportWrapper.scrollWidth,

                height:
                    exportWrapper.scrollHeight,

                windowWidth:
                    Math.max(
                        document.documentElement.clientWidth,
                        exportWrapper.scrollWidth
                    ),

                windowHeight:
                    Math.max(
                        document.documentElement.clientHeight,
                        exportWrapper.scrollHeight
                    )
            }
        );

    } finally {

        exportWrapper.remove();
    }
}


function addMindMapPdfPages(
    doc,
    canvas,
    heading = "Mind Map"
) {

    const orientation =
        canvas.width >= canvas.height
            ? "landscape"
            : "portrait";

    doc.addPage(
        "a4",
        orientation
    );

    const pageWidth =
        doc.internal.pageSize.getWidth();

    const pageHeight =
        doc.internal.pageSize.getHeight();

    const margin =
        15;

    doc.setFont(
        "helvetica",
        "bold"
    );

    doc.setFontSize(
        16
    );

    doc.text(
        heading,
        margin,
        20
    );

    const top =
        28;

    const maxWidth =
        pageWidth - margin * 2;

    const maxHeight =
        pageHeight - top - margin;

    const fitScale =
        Math.min(
            maxWidth / canvas.width,
            maxHeight / canvas.height
        );


    if (
        canvas.width * fitScale
        >=
        maxWidth * 0.6
    ) {

        const width =
            canvas.width * fitScale;

        const height =
            canvas.height * fitScale;

        doc.addImage(
            canvas.toDataURL(
                "image/jpeg",
                0.92
            ),
            "JPEG",
            (pageWidth - width) / 2,
            top,
            width,
            height
        );

        return;
    }


    const mmPerPx =
        maxWidth / canvas.width;

    let offset =
        0;

    let y =
        top;

    while (
        offset < canvas.height
    ) {

        const sliceHeight =
            Math.min(
                Math.floor(
                    (pageHeight - y - margin) / mmPerPx
                ),
                canvas.height - offset
            );

        const slice =
            document.createElement(
                "canvas"
            );

        slice.width =
            canvas.width;

        slice.height =
            sliceHeight;

        slice.getContext(
            "2d"
        ).drawImage(
            canvas,
            0,
            offset,
            canvas.width,
            sliceHeight,
            0,
            0,
            canvas.width,
            sliceHeight
        );

        doc.addImage(
            slice.toDataURL(
                "image/jpeg",
                0.92
            ),
            "JPEG",
            margin,
            y,
            maxWidth,
            sliceHeight * mmPerPx
        );

        offset +=
            sliceHeight;

        if (
            offset < canvas.height
        ) {

            doc.addPage(
                "a4",
                orientation
            );

            y =
                margin;
        }
    }
}


let reportReadyUrl =
    null;


function clearReportReady() {

    if (
        reportReadyUrl
    ) {

        URL.revokeObjectURL(
            reportReadyUrl
        );

        reportReadyUrl =
            null;
    }

    reportReady.hidden =
        true;

    reportReadyBtn.onclick =
        null;
}


function saveFile(
    url,
    fileName
) {

    const anchor =
        document.createElement(
            "a"
        );

    anchor.href =
        url;

    anchor.download =
        fileName;

    anchor.rel =
        "noopener";

    document.body.appendChild(
        anchor
    );

    anchor.click();

    anchor.remove();
}


function isEmbeddedBrowser() {

    return (
        window.self !== window.top
        ||
        /Electron\//.test(
            navigator.userAgent
        )
    );
}


function offerReportDownload(
    blob,
    fileName
) {

    clearReportReady();

    reportReadyUrl =
        URL.createObjectURL(
            blob
        );

    const url =
        reportReadyUrl;

    const size =
        `${(blob.size / 1048576).toFixed(1)} MB`;

    reportReadyText.textContent =
        "Report ready — didn't download? Open it and save it from the PDF viewer:";

    reportReadyBtn.textContent =
        `Open ${fileName} (${size})`;

    reportReadyBtn.onclick =
        () => {

            const tab =
                window.open(
                    url,
                    "_blank"
                );

            if (
                !tab
            ) {

                saveFile(
                    url,
                    fileName
                );
            }
        };

    reportReady.hidden =
        false;

    saveFile(
        url,
        fileName
    );
}


function reportMeetingTitle() {

    for (
        const slot of modelSlots.values()
    ) {

        if (
            slot.intelSaved
            &&
            slot.intelSaved.title
        ) {

            return slot.intelSaved.title;
        }
    }

    for (
        const slot of modelSlots.values()
    ) {

        if (
            slot.mindmapSaved
            &&
            slot.mindmapSaved.title
        ) {

            return slot.mindmapSaved.title;
        }
    }

    return "Untitled Meeting";
}


function reportFileName(
    items
) {

    const keys =
        new Set(
            items.map(
                item => item.slot.model.key
            )
        );

    const kinds =
        new Set(
            items.map(
                item => item.kind
            )
        );

    const contents =
        kinds.size > 1
            ? "full_report"
            : kinds.has("summary")
                ? "summary_report"
                : "mindmap_report";

    const title =
        sanitizeFilename(
            reportMeetingTitle()
        );

    return keys.size === 1
        ? `${title}_${sanitizeFilename(items[0].slot.model.key)}_${contents}.pdf`
        : `${title}_combined_${contents}.pdf`;
}


function setReportProgress(
    done,
    total
) {

    if (
        done === 0
    ) {

        reportProgressBar.style.transition =
            "none";

        reportProgressBar.style.width =
            "0%";

        void reportProgressBar.offsetWidth;

        reportProgressBar.style.transition =
            "";

        return;
    }

    reportProgressBar.style.width =
        `${Math.round(done / total * 100)}%`;
}


function nextFrame() {

    return new Promise(
        resolve => requestAnimationFrame(
            () => resolve()
        )
    );
}


async function downloadFullReport(
    items
) {

    const ready =
        () =>
            items.length > 0
            &&
            items.every(
                item => isReportItemReady(
                    item.kind,
                    item.slot
                )
            );

    if (
        fullReportBusy
    ) {

        return;
    }

    if (
        !ready()
    ) {

        setStatus(
            "Pick at least one summary or mind map for the report."
        );

        return;
    }

    if (
        !window.jspdf
        ||
        !window.jspdf.jsPDF
        ||
        typeof html2canvas !== "function"
    ) {

        setStatus(
            "PDF export is unavailable. Check your internet connection and try again."
        );

        log(
            "Full report export failed: jsPDF or html2canvas could not be loaded."
        );

        return;
    }


    const pending =
        getUnsavedEdits(
            items
        );

    if (
        pending.length
    ) {

        const proceed =
            await confirmUnsavedEdits(
                pending
            );

        if (
            !proceed
        ) {

            setStatus(
                "Report download cancelled. Save your changes and try again."
            );

            return;
        }

        if (
            !ready()
        ) {

            return;
        }
    }


    const startedAt =
        performance.now();

    const sections =
        items.map(
            item => ({
                ...item,
                data:
                    item.kind === "summary"
                        ? getExportData(item.slot)
                        : null,
                mindmap:
                    item.kind === "mindmap"
                        ? deepClone(item.slot.mindmapSaved)
                        : null
            })
        );

    const labels =
        describeReportItems(
            items
        );

    const originalText =
        reportTriggerLabel.textContent;

    fullReportBusy =
        true;

    reportBuilder.classList.add(
        "is-busy"
    );

    setReportProgress(
        0,
        sections.length
    );

    refreshReportBuilder();

    reportTriggerLabel.textContent =
        "Preparing Report...";

    setStatus(
        `Preparing meeting report (${labels})...`
    );

    log(
        `Exporting report as one PDF: ${labels}.`
    );


    try {

        clearReportReady();

        const doc =
            new window.jspdf.jsPDF(
                {
                    unit: "mm",
                    format: "a4",
                    compress: true
                }
            );

        let pageUsed =
            false;

        for (
            let i = 0;
            i < sections.length;
            i++
        ) {

            const section =
                sections[i];

            reportTriggerLabel.textContent =
                `Building ${i + 1} of ${sections.length}...`;

            await nextFrame();

            if (
                section.kind === "summary"
            ) {

                if (
                    pageUsed
                ) {

                    doc.addPage(
                        "a4",
                        "portrait"
                    );
                }

                writeSummaryPdf(
                    doc,
                    section.data,
                    section.slot.model.label
                );

            } else {

                const canvas =
                    await renderSavedMindMapCanvas(
                        section.mindmap
                    );

                addMindMapPdfPages(
                    doc,
                    canvas,
                    `Mind Map — ${section.slot.model.label}`
                );
            }

            pageUsed =
                true;

            setReportProgress(
                i + 1,
                sections.length
            );
        }

        if (
            sections[0].kind === "mindmap"
        ) {

            doc.deletePage(
                1
            );
        }

        const fileName =
            reportFileName(
                sections
            );

        const blob =
            doc.output(
                "blob"
            );

        const seconds =
            (
                performance.now()
                -
                startedAt
            ) / 1000;

        offerReportDownload(
            blob,
            fileName
        );

        const sizeLabel =
            `${(blob.size / 1048576).toFixed(1)} MB`;

        log(
            `Report built in ${seconds.toFixed(1)} s (${sizeLabel}, ${labels}) and sent to the browser to save.`
        );

        if (
            isEmbeddedBrowser()
        ) {

            setStatus(
                "Report ready, but this page is running inside an embedded window, where downloads are usually blocked. Open Vidatha in a normal browser tab to save it."
            );

            log(
                "Embedded browser detected: the browser is likely to block the download."
            );

        } else if (
            seconds > 4
        ) {

            setStatus(
                `Report ready (${labels}). Building took ${seconds.toFixed(0)} s, so the browser may have blocked the automatic download. Use the Open button under Build Your Report.`
            );

            log(
                "Building took longer than the browser's window for automatic downloads. Use the Open button."
            );

        } else {

            setStatus(
                `Report ready (${labels}). If nothing downloaded, use the Open button under Build Your Report.`
            );
        }

    } catch (
        error
    ) {

        log(
            `Report export failed: ${error.message}`
        );

        setStatus(
            `Report export failed: ${error.message}`
        );

    } finally {

        fullReportBusy =
            false;

        reportBuilder.classList.remove(
            "is-busy"
        );

        reportTriggerLabel.textContent =
            originalText;

        refreshReportBuilder();
    }
}



const newMeetingOverlay =
    document.getElementById(
        "newMeetingOverlay"
    );

const newMeetingCancelBtn =
    document.getElementById(
        "newMeetingCancelBtn"
    );

const newMeetingConfirmBtn =
    document.getElementById(
        "newMeetingConfirmBtn"
    );


function openNewMeetingModal() {

    newMeetingOverlay.classList.add(
        "visible"
    );

    newMeetingOverlay.setAttribute(
        "aria-hidden",
        "false"
    );

    newMeetingConfirmBtn.focus();
}


function closeNewMeetingModal() {

    newMeetingOverlay.classList.remove(
        "visible"
    );

    newMeetingOverlay.setAttribute(
        "aria-hidden",
        "true"
    );

    recordBtn.focus();
}


newMeetingCancelBtn.addEventListener(
    "click",
    closeNewMeetingModal
);


newMeetingConfirmBtn.addEventListener(
    "click",
    function() {

        closeNewMeetingModal();

        startRecording();
    }
);


newMeetingOverlay.addEventListener(
    "click",
    function(event) {

        if (
            event.target
            ===
            newMeetingOverlay
        ) {

            closeNewMeetingModal();
        }
    }
);


document.addEventListener(
    "keydown",
    function(event) {

        if (
            event.key
            ===
            "Escape"
            &&
            newMeetingOverlay.classList.contains(
                "visible"
            )
        ) {

            closeNewMeetingModal();
        }
    }
);


async function uploadExistingRecording(file) {

    if (!file) return;

    if (isRecording) {
        setStatus("Stop the current live recording before uploading a file.");
        return;
    }

    if (file.size > MAX_UPLOAD_BYTES) {
        setStatus("This file exceeds the 500 MB upload limit. Choose a smaller recording.");
        log(`Upload rejected: ${file.name} is larger than 500 MB.`);
        return;
    }

    if (!file.size) {
        setStatus("The selected file is empty. Choose a valid audio recording.");
        return;
    }

    
    const allowedExtensions = /\.(wav|mp3|m4a|aac|flac|ogg|opus|webm|mp4|mpeg)$/i;

    if (!allowedExtensions.test(file.name)) {
        setStatus(
            "Unsupported file type. Choose WAV, MP3, M4A, AAC, FLAC, OGG, OPUS, WEBM, MP4, or MPEG audio."
        );
        return;
    }


    sessionEpoch++;
    const uploadEpoch = sessionEpoch;
    clearReportReady();
    clearReportSelection();
    transcript = "";
    currentMeetingId = null;
    currentMeetingDuration = null;
    startNewSession();
    updateGenerateButton();
    resetTranscriptSearch();
    transcriptEl.innerHTML = `<div class="placeholder">Uploading recording and preparing transcription...</div>`;
    modelSlots.forEach(slot => resetSlot(slot, "recording"));

    const originalButtonText = "Upload Recording";
    uploadRecordingBtn.disabled = true;
    recordBtn.disabled = true;
    uploadRecordingBtn.textContent = "Uploading & Transcribing...";
    setStatus(`Uploading ${file.name} and transcribing with Parrotlet...`);
    log(`Audio upload started: ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)} MB).`);

    try {
        const template = activeTemplate();
        const formData = new FormData();
        formData.append("audio", file, file.name);
        formData.append("template", template);

        const response = await fetch("/api/meeting/upload-recording", {
            method: "POST",
            body: formData,
            credentials: "same-origin"
        });

        let data;
        try {
            data = await response.json();
        } catch (_) {
            data = {};
        }

        if (!response.ok) {
            const detail = data.detail || data.message || `Upload failed (HTTP ${response.status}).`;
            throw new Error(detail);
        }

        if (uploadEpoch !== sessionEpoch) return;

        transcript = (data.transcript || "").trim();
        currentMeetingId = data.meeting_id || null;
        currentMeetingDuration = Number(data.duration) || null;

        if (data.template === "doctor") {
            if (window.meetmindDoctor) {
                window.meetmindDoctor.onTranscribed({ consultationId: data.consultation_id || null });
            }
            if (data.has_audio) recordingPlayer.show("consultation", data.consultation_id);
        } else if (data.template === "interview") {
            if (window.meetmindInterview) {
                window.meetmindInterview.onTranscribed({ interviewId: data.interview_id || null });
            }
            if (data.has_audio) recordingPlayer.show("interview", data.interview_id);
        } else if (data.has_audio) {
            recordingPlayer.show("meeting", data.meeting_id);
        }

        renderTranscript(transcript);
        resetTranscriptSearch();
        updateGenerateButton();

        if (currentMeetingDuration !== null) {
            const totalSeconds = Math.max(0, Math.floor(currentMeetingDuration));
            const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, "0");
            const seconds = (totalSeconds % 60).toString().padStart(2, "0");
            timerEl.textContent = `${minutes}:${seconds}`;
        }

        if (transcript) {
            setStatus(transcriptReadyMessage(data.template));
            log(`Upload transcription complete: ${transcript.length} transcript characters.`);
            document.dispatchEvent(new CustomEvent("meetmind:results-changed", { detail: { meetingId: currentMeetingId } }));
        } else {
            setStatus("Transcription finished, but no speech was detected in this recording.");
            log("Upload transcription finished with an empty transcript.");
        }
    } catch (error) {
        if (uploadEpoch === sessionEpoch) {
            setStatus(error.message || "Could not upload or transcribe this recording.");
            log(`Upload error: ${error.message || error}`);
            transcriptEl.innerHTML = `<div class="placeholder">Upload failed. Select the file and try again.</div>`;
        }
    } finally {
        uploadRecordingBtn.disabled = false;
        recordBtn.disabled = false;
        uploadRecordingBtn.textContent = originalButtonText;
        recordingFileInput.value = "";
    }
}

uploadRecordingBtn.addEventListener("click", function() {
    if (isRecording) {
        setStatus("Stop the current live recording before uploading a file.");
        return;
    }
    recordingFileInput.click();
});

recordingFileInput.addEventListener("change", function() {
    const file = recordingFileInput.files && recordingFileInput.files[0];
    if (file) uploadExistingRecording(file);
});


recordBtn.addEventListener(
    "click",
    function() {

        if (
            isRecording
        ) {

            stopRecording();

        } else if (
            transcript
            &&
            !currentMeetingId
            &&
            !(window.meetmindDoctor && window.meetmindDoctor.currentId())
        ) {

            openNewMeetingModal();

        } else {

            startRecording();
        }
    }
);


cancelRecordingBtn.addEventListener(
    "click",
    function() {

        if (
            !isRecording
            ||
            recordingPaused
        ) {

            return;
        }

        recordingPaused =
            true;

        pauseTimer();

        const statusBeforePause =
            statusEl.textContent;

        setStatus(
            "Recording paused..."
        );

        log(
            "Recording paused for cancel confirmation."
        );

        const confirmed =
            window.MeetMindDialog
                ? window.MeetMindDialog.confirm({
                    title:
                        "Cancel this recording?",
                    message:
                        "The audio recorded so far will be discarded. Nothing will be transcribed or saved.",
                    confirmText:
                        "Discard Recording",
                    cancelText:
                        "Keep Recording",
                    danger:
                        true
                })
                : Promise.resolve(
                    window.confirm(
                        "Cancel this recording? The audio recorded so far will be discarded."
                    )
                );

        confirmed.then(
            ok => {

                if (ok) {

                    cancelRecording();

                    return;
                }

                if (
                    !isRecording
                    ||
                    !recordingPaused
                ) {

                    return;
                }

                recordingPaused =
                    false;

                resumeTimer();

                setStatus(
                    statusBeforePause
                );

                log(
                    "Recording resumed."
                );
            }
        );
    }
);


generateBtn.addEventListener(
    "click",
    function() {

        generateSelected();
    }
);


document.addEventListener(
    "keydown",
    function(event) {

        if (
            event.key !== "Escape"
        ) {

            return;
        }

        const openDropdown =
            dropdowns.find(
                dropdown => dropdown.isOpen()
            );

        if (
            openDropdown
        ) {

            openDropdown.close(
                true
            );

            return;
        }

        if (
            expandedMindMapSlot
            &&
            !newMeetingOverlay.classList.contains(
                "visible"
            )
        ) {

            const slot =
                expandedMindMapSlot;

            setMindMapExpanded(
                slot,
                false
            );

            slot.els.expandBtn.focus();
        }
    }
);


FALLBACK_MODELS.forEach(
    createModelSlot
);

renderModelPicker();

applyModelSelection();

refreshReportBuilder();

loadModelCatalog();
