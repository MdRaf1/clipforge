// Main Alpine state + UI logic. Wires footage upload, generation mode,
// overrides, platforms, series, and the Generate button. Also owns the
// pipeline/history reactive state; the pipeline.js and history.js modules
// mutate this state via helper methods exposed on the window.

function clipforgeApp() {
    return {
        // ---- Footage ----
        footageList: [],
        selectedFootageId: null,
        dragging: false,
        uploadStatus: "",

        // ---- Script mode ----
        generationMode: "full_ai",   // full_ai | topic_guided | manual
        topic: "",
        rawScript: "",

        // ---- Overrides ----
        manualOverrideScript: false,
        manualOverrideVoiceover: false,

        // ---- Platforms ----
        platforms: [
            { id: "youtube_shorts",  label: "YouTube Shorts" },
            { id: "tiktok",          label: "TikTok" },
            { id: "instagram_reels", label: "Instagram Reels" },
            { id: "facebook_reels",  label: "Facebook Reels" },
        ],
        selectedPlatforms: [],

        // ---- Series ----
        seriesType: "standalone",    // standalone | first_episode | continuation
        seriesList: [],
        seriesFilter: "",
        selectedSeriesId: null,
        newSeriesName: "",

        // ---- Job submission ----
        submitting: false,
        lastJobId: null,
        errorMessage: "",

        // ---- Live pipeline (mutated by pipeline.js) ----
        pipeline: {
            jobId: null,
            steps: [],           // [{ step_name, status, message }]
            running: false,
            complete: false,
            error: null,
        },

        // ---- Human-in-the-loop review pause ----
        review: {
            active: false,
            script: "",
            score: 0,
            summary: "",
            editedScript: "",
            submitting: false,
        },

        // ---- Completed outputs ----
        outputs: {
            jobId: null,
            videoFullUrl: null,
            videoShortUrl: null,
            thumbnailUrl: null,
            zipUrl: null,
            metadata: {},        // keyed by platform: {title, description}
        },

        // ---- History ----
        history: {
            items: [],
            detail: null,
            deleteTargetId: null,
            deleteTargetTitle: "",
            loading: false,
        },

        // Labels shown for each pipeline step
        stepLabels: {
            script:           "Generating script",
            voiceover_full:   "Creating voiceover (full)",
            voiceover_short:  "Creating voiceover (short)",
            cutting_full:     "Cutting footage (full)",
            cutting_short:    "Cutting footage (short)",
            subtitles_full:   "Generating subtitles (full)",
            subtitles_short:  "Generating subtitles (short)",
            render_full:      "Rendering video (full)",
            render_short:     "Rendering video (short)",
            thumbnail:        "Creating thumbnail",
            metadata:         "Generating metadata",
        },

        async init() {
            await this.loadFootage();
            await this.loadSeries();
            await this.loadHistory();
            // Wizard bootstrap is handled by wizard.js, which reads settings itself.
        },

        // ----- Footage -----
        async loadFootage() {
            try {
                const res = await fetch("/api/footage");
                this.footageList = await res.json();
                if (!this.selectedFootageId && this.footageList.length > 0) {
                    this.selectedFootageId = this.footageList[0].id;
                }
            } catch (e) {
                console.error("Failed to load footage", e);
            }
        },

        handleFilePicker(event) {
            const files = Array.from(event.target.files || []);
            this.uploadFiles(files);
            event.target.value = ""; // reset so re-picking same file works
        },

        handleDrop(event) {
            this.dragging = false;
            const files = Array.from(event.dataTransfer.files || []);
            this.uploadFiles(files);
        },

        async uploadFiles(files) {
            for (const file of files) {
                if (!/\.(mp4|mkv)$/i.test(file.name)) {
                    this.uploadStatus = `Skipped ${file.name} (only MP4/MKV allowed)`;
                    continue;
                }
                this.uploadStatus = `Uploading ${file.name}...`;
                const fd = new FormData();
                fd.append("file", file);
                try {
                    const res = await fetch("/api/footage", { method: "POST", body: fd });
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    const data = await res.json();
                    this.uploadStatus = `Uploaded ${data.filename}`;
                    await this.loadFootage();
                    this.selectedFootageId = data.footage_id;
                } catch (e) {
                    this.uploadStatus = `Upload failed: ${e.message}`;
                }
            }
        },

        // ----- Series -----
        async loadSeries() {
            try {
                const res = await fetch("/api/series");
                this.seriesList = await res.json();
            } catch (e) {
                console.error("Failed to load series", e);
            }
        },

        filteredSeries() {
            const q = this.seriesFilter.trim().toLowerCase();
            if (!q) return this.seriesList;
            return this.seriesList.filter(s => s.name.toLowerCase().includes(q));
        },

        // ----- Validation -----
        canGenerate() {
            if (!this.selectedFootageId) return false;
            if (this.selectedPlatforms.length === 0) return false;
            if (this.generationMode === "topic_guided" && !this.topic.trim()) return false;
            if (this.generationMode === "manual" && !this.rawScript.trim()) return false;
            if (this.seriesType === "continuation" && !this.selectedSeriesId) return false;
            if (this.seriesType === "first_episode" && !this.newSeriesName.trim()) return false;
            return true;
        },

        // ----- Submit -----
        async submitJob() {
            this.submitting = true;
            this.errorMessage = "";
            this.lastJobId = null;

            let seriesId = null;
            if (this.seriesType === "continuation") {
                seriesId = this.selectedSeriesId;
            } else if (this.seriesType === "first_episode") {
                try {
                    const res = await fetch("/api/series", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ name: this.newSeriesName.trim() }),
                    });
                    if (!res.ok) throw new Error(`Series create failed: ${res.status}`);
                    const data = await res.json();
                    seriesId = data.series_id;
                } catch (e) {
                    this.errorMessage = e.message;
                    this.submitting = false;
                    return;
                }
            }

            const payload = {
                footage_id: this.selectedFootageId,
                platform_flags: this.selectedPlatforms,
                series_type: this.seriesType,
                series_id: seriesId,
                generation_mode: this.generationMode,
                topic: this.generationMode === "topic_guided" ? this.topic.trim() : null,
                raw_script: this.generationMode === "manual" ? this.rawScript : null,
                manual_override_script: this.manualOverrideScript,
                manual_override_voiceover: this.manualOverrideVoiceover,
            };

            try {
                const res = await fetch("/api/jobs", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });
                if (!res.ok) {
                    const text = await res.text();
                    throw new Error(`Job creation failed: ${res.status} ${text}`);
                }
                const data = await res.json();
                this.lastJobId = data.job_id;

                // Reset pipeline + outputs state, then hand off to pipeline.js.
                this._resetPipelineState();
                if (window.ClipForgePipeline) {
                    window.ClipForgePipeline.start(data.job_id, this);
                }
            } catch (e) {
                this.errorMessage = e.message;
            } finally {
                this.submitting = false;
            }
        },

        _resetPipelineState() {
            this.pipeline = {
                jobId: null,
                steps: [],
                running: false,
                complete: false,
                error: null,
            };
            this.review = {
                active: false,
                script: "",
                score: 0,
                summary: "",
                editedScript: "",
                submitting: false,
            };
            this.outputs = {
                jobId: null,
                videoFullUrl: null,
                videoShortUrl: null,
                thumbnailUrl: null,
                zipUrl: null,
                metadata: {},
            };
        },

        // ----- Review pause actions -----
        async submitReviewChoice(action) {
            if (!this.pipeline.jobId) return;
            this.review.submitting = true;
            const body = { action };
            if (action === "edit_resubmit") {
                body.edited_script = this.review.editedScript || this.review.script;
            }
            try {
                const res = await fetch(`/api/jobs/${this.pipeline.jobId}/review`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(body),
                });
                if (!res.ok) throw new Error(`Review submit failed: ${res.status}`);
                this.review.active = false;
            } catch (e) {
                this.errorMessage = e.message;
            } finally {
                this.review.submitting = false;
            }
        },

        // ----- Output helpers -----
        async copyToClipboard(text, label) {
            try {
                await navigator.clipboard.writeText(text || "");
                this.uploadStatus = `Copied ${label}`;
                setTimeout(() => {
                    if (this.uploadStatus === `Copied ${label}`) this.uploadStatus = "";
                }, 1500);
            } catch (e) {
                this.uploadStatus = `Copy failed: ${e.message}`;
            }
        },

        async openOutputFolder() {
            if (!this.outputs.jobId) return;
            try {
                const res = await fetch(`/api/history/${this.outputs.jobId}/open-folder`, { method: "POST" });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
            } catch (e) {
                this.errorMessage = `Could not open folder: ${e.message}`;
            }
        },

        platformLabel(platformId) {
            const p = this.platforms.find(pp => pp.id === platformId);
            return p ? p.label : platformId;
        },

        selectedPlatformMetadata() {
            // Return only platforms the user actually selected for this job
            return this.selectedPlatforms
                .filter(pid => this.outputs.metadata[pid])
                .map(pid => ({
                    id: pid,
                    label: this.platformLabel(pid),
                    title: this.outputs.metadata[pid].title || "",
                    description: this.outputs.metadata[pid].description || "",
                }));
        },

        // ----- History -----
        async loadHistory() {
            if (window.ClipForgeHistory) {
                await window.ClipForgeHistory.load(this);
            }
        },

        async openHistoryDetail(jobId) {
            if (window.ClipForgeHistory) {
                await window.ClipForgeHistory.openDetail(this, jobId);
            }
        },

        closeHistoryDetail() {
            this.history.detail = null;
        },

        requestHistoryDelete(jobId, title) {
            this.history.deleteTargetId = jobId;
            this.history.deleteTargetTitle = title;
        },

        cancelHistoryDelete() {
            this.history.deleteTargetId = null;
            this.history.deleteTargetTitle = "";
        },

        async confirmHistoryDelete() {
            if (window.ClipForgeHistory) {
                await window.ClipForgeHistory.confirmDelete(this);
            }
        },

        formatDate(iso) {
            if (!iso) return "";
            try {
                return new Date(iso).toLocaleString();
            } catch {
                return iso;
            }
        },

        // ----- Re-run wizard -----
        runWizard() {
            if (window.ClipForgeWizard) {
                window.ClipForgeWizard.start();
            }
        },
    };
}
