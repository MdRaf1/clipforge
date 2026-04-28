// Main Alpine state + UI logic. Wires footage upload, generation mode,
// overrides, platforms, series, and the Generate button.

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

        async init() {
            await this.loadFootage();
            await this.loadSeries();
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
            } catch (e) {
                this.errorMessage = e.message;
            } finally {
                this.submitting = false;
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
