(function () {

    var STORAGE_KEY =
        "meetmind-theme";

    var root =
        document.documentElement;

    var toggle =
        document.getElementById(
            "themeToggle"
        );


    function stored() {

        try {

            var value =
                localStorage.getItem(
                    STORAGE_KEY
                );

            return (
                value === "light" ||
                value === "dark"
            )
                ? value
                : null;

        } catch (e) {

            return null;
        }
    }


    function current() {

        return (
            root.getAttribute(
                "data-theme"
            ) ||
            stored() ||
            "light"
        );
    }


    function apply(theme) {

        root.setAttribute(
            "data-theme",
            theme
        );

        if (toggle) {

            toggle.setAttribute(
                "aria-pressed",
                String(theme === "dark")
            );
        }
    }


    apply(current());


    if (toggle) {

        toggle.addEventListener(
            "click",
            function () {

                var next =
                    current() === "dark"
                        ? "light"
                        : "dark";

                try {

                    localStorage.setItem(
                        STORAGE_KEY,
                        next
                    );

                } catch (e) {}

                apply(next);
            }
        );
    }

})();


const pristineTranscriptHTML =
    transcriptEl.innerHTML;


function savedMeetingResults(
    meeting
) {

    if (
        meeting.results
        &&
        typeof meeting.results === "object"
    ) {

        return meeting.results;
    }

    if (
        meeting.summary
        ||
        meeting.mindmap
    ) {

        return {
            [slotForModel(null).model.key]: {
                summary: meeting.summary || null,
                mindmap: meeting.mindmap || null
            }
        };
    }

    return {};
}


function activeTemplate() {

    const template =
        document.body.dataset.meetmindTemplate;

    return template === "doctor" || template === "interview"
        ? template
        : "meeting";
}


const recordingPlayer = (() => {

    const player =
        window.MeetMindAudioPlayer
            ? window.MeetMindAudioPlayer.create()
            : null;

    const panelHead =
        document.querySelector(
            ".panel--transcript .panel-head"
        );

    if (player && panelHead) {

        player.el.classList.add(
            "recording-player"
        );

        panelHead.insertAdjacentElement(
            "afterend",
            player.el
        );
    }

    function sourceLabel(audio) {

        if (!audio || !audio.source) {
            return "";
        }

        return audio.source === "upload"
            ? "Uploaded" + (audio.originalFilename ? " · " + audio.originalFilename : "")
            : "Live recording";
    }

    return {

        show: function (kind, id, audio) {

            if (!player || !id) return;

            const consultation =
                kind === "consultation";

            const interview =
                kind === "interview";

            const url =
                (audio && audio.url)
                ||
                (consultation
                    ? `/api/doctor/consultations/${id}/audio`
                    : interview
                        ? `/api/interview/interviews/${id}/audio`
                        : `/api/meetings/${id}/audio`);

            player.el.classList.toggle(
                "mm-player--teal",
                consultation
            );

            player.el.classList.toggle(
                "mm-player--indigo",
                interview
            );

            const parts = [
                audio && audio.mimeType
                    ? (audio.mimeType === "audio/mpeg"
                        ? "MP3"
                        : audio.mimeType.replace(/^audio\//, "").toUpperCase())
                    : "",
                audio && audio.sizeBytes
                    ? window.MeetMindAudioPlayer.formatBytes(audio.sizeBytes)
                    : "",
                sourceLabel(audio)
            ].filter(Boolean);

            player.load(
                url,
                {
                    title:
                        consultation
                            ? "Consultation recording"
                            : interview
                                ? "Interview recording"
                                : "Meeting recording",
                    meta:
                        parts.length
                            ? parts.join(" · ")
                            : "Saved with this " + (consultation ? "consultation" : interview ? "interview" : "meeting"),
                    downloadName:
                        (consultation ? "consultation_" : interview ? "interview_" : "meeting_") + id
                }
            );
        },

        hide: function () {

            if (player) player.clear();
        }
    };
})();

window.meetmindRecordingPlayer =
    recordingPlayer;


function startNewSession() {

    recordingPlayer.hide();

    if (window.meetmindDoctor) {
        window.meetmindDoctor.clearForNewRecording();
    }

    if (window.meetmindInterview) {
        window.meetmindInterview.clearForNewRecording();
    }

    document.dispatchEvent(
        new CustomEvent("meetmind:new-session")
    );
}


function transcriptReadyMessage(template) {

    if (template === "doctor") {
        return "Transcript ready. Click Generate Prescription to draft the prescription.";
    }

    if (template === "interview") {
        return "Transcript ready. Check the required skills, then click Evaluate Interview.";
    }

    return "Transcript ready. Choose the model(s) and click Generate.";
}


window.meetmindHistory = {

    loadConsultation: function (consultation) {

        sessionEpoch++;

        clearReportReady();

        clearReportSelection();

        transcript =
            (consultation.transcript || "").trim();

        currentMeetingId =
            null;

        currentMeetingDuration =
            consultation.durationSeconds || null;

        renderTranscript(
            transcript
        );

        resetTranscriptSearch();

        modelSlots.forEach(
            slot => resetSlot(
                slot,
                "ready"
            )
        );

        updateGenerateButton();

        if (window.meetmindDoctor) {
            window.meetmindDoctor.load(consultation);
        }

        if (consultation.hasAudio) {
            recordingPlayer.show("consultation", consultation.id, consultation.audio);
        } else {
            recordingPlayer.hide();
        }

        setStatus(
            "Viewing a saved consultation."
        );
    },

    loadInterview: function (interview) {

        sessionEpoch++;

        clearReportReady();

        clearReportSelection();

        transcript =
            (interview.transcript || "").trim();

        currentMeetingId =
            null;

        currentMeetingDuration =
            interview.durationSeconds || null;

        renderTranscript(
            transcript
        );

        resetTranscriptSearch();

        modelSlots.forEach(
            slot => resetSlot(
                slot,
                "ready"
            )
        );

        updateGenerateButton();

        if (window.meetmindInterview) {
            window.meetmindInterview.load(interview);
        }

        if (interview.hasAudio) {
            recordingPlayer.show("interview", interview.id, interview.audio);
        } else {
            recordingPlayer.hide();
        }

        setStatus(
            "Viewing a saved interview."
        );
    },

    load: function (meeting) {

        sessionEpoch++;

        clearReportReady();

        clearReportSelection();

        transcript =
            (meeting.transcript || "").trim();

        currentMeetingId =
            meeting.id || null;

        currentMeetingDuration =
            meeting.durationSeconds || null;

        renderTranscript(
            transcript
        );

        resetTranscriptSearch();

        const results =
            savedMeetingResults(
                meeting
            );

        Object.keys(results).forEach(
            ensureSlot
        );

        renderModelPicker();

        modelSlots.forEach(
            slot => {

                const result =
                    results[slot.model.key] || {};

                resetSlot(
                    slot,
                    "ready"
                );

                if (result.summary) {

                    renderIntelligence(
                        slot,
                        {
                            ...result.summary,
                            transcript: transcript
                        },
                        true
                    );

                    setGenerationStatus(
                        slot,
                        "summary",
                        "done"
                    );
                }

                if (result.mindmap) {

                    renderMindMap(
                        slot,
                        result.mindmap
                    );

                    if (slot.mindmap) {

                        setGenerationStatus(
                            slot,
                            "mindmap",
                            "done"
                        );
                    }
                }
            }
        );

        const withResults =
            [
                ...modelSlots.values()
            ].filter(
                slot => results[slot.model.key]
            );

        if (
            withResults.some(
                slot => !selectedSlots().includes(slot)
            )
        ) {

            selectedModelValue =
                withResults.length === 1
                    ? withResults[0].model.key
                    : ALL_MODELS;

            renderModelPicker();
        }

        applyModelSelection();

        if (meeting.hasAudio) {
            recordingPlayer.show("meeting", meeting.id, meeting.audio);
        } else {
            recordingPlayer.hide();
        }

        setStatus(
            "Viewing a saved meeting."
        );
    },

    reset: function () {

        sessionEpoch++;

        clearReportReady();

        clearReportSelection();

        transcript =
            "";

        currentMeetingId =
            null;

        currentMeetingDuration =
            null;

        transcriptEl.innerHTML =
            pristineTranscriptHTML;

        resetTranscriptSearch();

        modelSlots.forEach(
            slot => resetSlot(
                slot,
                "ready"
            )
        );

        recordingPlayer.hide();

        if (window.meetmindDoctor) {
            window.meetmindDoctor.reset();
        }

        if (window.meetmindInterview) {
            window.meetmindInterview.reset();
        }

        updateGenerateButton();

        setStatus(
            "Ready"
        );
    },

    isBusy: function () {

        return isRecording;
    },

    isGenerating: function () {

        return isAnyGenerating()
            ||
            !!(window.meetmindDoctor && window.meetmindDoctor.isGenerating())
            ||
            !!(window.meetmindInterview && window.meetmindInterview.isGenerating());
    }
};
