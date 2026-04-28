// Pipeline WebSocket client.
//
// Opens ws://.../ws/jobs/{job_id}, handles:
//   - state_sync   → seed the 11-step list (handles race where steps complete before WS connects)
//   - step_update  → reactive status update on matching step
//   - review_pause → show the human-in-the-loop UI
//   - complete     → reveal outputs (video players, thumbnail, per-platform metadata, zip, etc.)
//
// The module mutates Alpine reactive state on the clipforgeApp instance passed in,
// which keeps Alpine's reactivity working without this file needing to know about Alpine.

(function () {
    const STEP_ORDER = [
        "script",
        "voiceover_full",
        "voiceover_short",
        "cutting_full",
        "cutting_short",
        "subtitles_full",
        "subtitles_short",
        "render_full",
        "render_short",
        "thumbnail",
        "metadata",
    ];

    let currentSocket = null;
    let currentJobId = null;

    function seedSteps(app, steps) {
        // Build a map of any existing step statuses (from the server payload on connect),
        // then produce a fixed-length array in canonical order so the UI is stable even
        // if the payload is partial.
        const byName = {};
        for (const s of steps || []) {
            byName[s.step_name] = s;
        }
        app.pipeline.steps = STEP_ORDER.map((name) => {
            const row = byName[name];
            return {
                step_name: name,
                status: (row && row.status) || "pending",
                message: "",
            };
        });
    }

    function updateStep(app, stepName, status, message) {
        const idx = app.pipeline.steps.findIndex((s) => s.step_name === stepName);
        if (idx === -1) {
            app.pipeline.steps.push({
                step_name: stepName,
                status: status || "pending",
                message: message || "",
            });
            return;
        }
        // Replace the object so Alpine's reactivity fires
        app.pipeline.steps[idx] = {
            ...app.pipeline.steps[idx],
            status: status || app.pipeline.steps[idx].status,
            message: message || "",
        };
    }

    async function fetchMetadata(jobId) {
        try {
            const res = await fetch(`/outputs/${jobId}/metadata.json`, { cache: "no-store" });
            if (!res.ok) return {};
            return await res.json();
        } catch {
            return {};
        }
    }

    async function handleComplete(app, jobId, event) {
        const metadata = await fetchMetadata(jobId);
        app.outputs = {
            jobId,
            videoFullUrl: `/outputs/${jobId}/video_full.mp4`,
            videoShortUrl: `/outputs/${jobId}/video_short.mp4`,
            thumbnailUrl: `/outputs/${jobId}/thumbnail.jpg`,
            zipUrl: `/api/history/${jobId}/zip`,
            metadata: metadata || {},
        };
        app.pipeline.complete = true;
        app.pipeline.running = false;

        // Refresh history panel so the new session shows up.
        if (window.ClipForgeHistory) {
            window.ClipForgeHistory.load(app).catch(() => {});
        }
    }

    function handleMessage(app, jobId, raw) {
        let event;
        try {
            event = JSON.parse(raw);
        } catch {
            console.warn("pipeline: non-JSON message", raw);
            return;
        }

        switch (event.type) {
            case "state_sync":
                seedSteps(app, event.steps || []);
                break;

            case "step_update":
                updateStep(app, event.step, event.status, event.message);
                break;

            case "review_pause":
                app.review.active = true;
                app.review.script = event.script || "";
                app.review.editedScript = event.script || "";
                app.review.score = event.score || 0;
                app.review.summary = event.user_summary || "";
                break;

            case "complete":
                handleComplete(app, jobId, event);
                break;

            default:
                // Unknown events are harmless; log for debugging.
                console.debug("pipeline: unknown event", event);
        }
    }

    function start(jobId, app) {
        // Tear down any existing connection before opening a new one.
        if (currentSocket) {
            try { currentSocket.close(); } catch (_) { /* ignore */ }
            currentSocket = null;
        }

        currentJobId = jobId;
        app.pipeline.jobId = jobId;
        app.pipeline.running = true;
        app.pipeline.complete = false;
        app.pipeline.error = null;
        // Prime with all-pending steps until state_sync arrives (usually within a few ms).
        seedSteps(app, []);

        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        const url = `${proto}://${window.location.host}/ws/jobs/${jobId}`;
        const socket = new WebSocket(url);
        currentSocket = socket;

        socket.onmessage = (ev) => handleMessage(app, jobId, ev.data);
        socket.onerror = (e) => {
            console.error("pipeline: websocket error", e);
            app.pipeline.error = "WebSocket connection error — see devtools console.";
        };
        socket.onclose = () => {
            // If the pipeline already completed we just leave things as-is.
            // Otherwise mark as not running so the UI reflects the disconnect.
            if (!app.pipeline.complete) {
                app.pipeline.running = false;
            }
            if (currentSocket === socket) currentSocket = null;
        };
    }

    function stop() {
        if (currentSocket) {
            try { currentSocket.close(); } catch (_) { /* ignore */ }
            currentSocket = null;
        }
        currentJobId = null;
    }

    window.ClipForgePipeline = { start, stop, STEP_ORDER };
})();
