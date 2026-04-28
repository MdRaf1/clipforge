// History panel.
//
// Mutates Alpine state on the clipforgeApp instance passed in:
//   - app.history.items         — [{id, title, created_at, status}]
//   - app.history.detail        — full job detail object (from GET /api/history/:id) + outputs URLs
//   - app.history.deleteTargetId / deleteTargetTitle — controls the delete warning modal

(function () {
    async function load(app) {
        app.history.loading = true;
        try {
            const res = await fetch("/api/history", { cache: "no-store" });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            app.history.items = await res.json();
        } catch (e) {
            console.error("history: load failed", e);
        } finally {
            app.history.loading = false;
        }
    }

    async function openDetail(app, jobId) {
        try {
            const res = await fetch(`/api/history/${jobId}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const job = await res.json();

            // Try to fetch metadata.json for this job so the detail view shows per-platform copy.
            let metadata = {};
            try {
                const mres = await fetch(`/outputs/${jobId}/metadata.json`, { cache: "no-store" });
                if (mres.ok) metadata = await mres.json();
            } catch {
                // Missing metadata is non-fatal — older/incomplete jobs simply won't have it.
            }

            // platform_flags is stored as a JSON string in the DB
            let platforms = [];
            try {
                platforms = JSON.parse(job.platform_flags || "[]");
            } catch {
                platforms = [];
            }

            app.history.detail = {
                id: job.id,
                title: job.title || `Job #${job.id}`,
                created_at: job.created_at,
                status: job.status,
                series_type: job.series_type,
                platforms,
                videoFullUrl: `/outputs/${jobId}/video_full.mp4`,
                videoShortUrl: `/outputs/${jobId}/video_short.mp4`,
                thumbnailUrl: `/outputs/${jobId}/thumbnail.jpg`,
                zipUrl: `/api/history/${jobId}/zip`,
                metadata,
            };
        } catch (e) {
            console.error("history: detail failed", e);
            app.errorMessage = `Failed to load job ${jobId}: ${e.message}`;
        }
    }

    async function confirmDelete(app) {
        const jobId = app.history.deleteTargetId;
        if (!jobId) return;
        try {
            const res = await fetch(`/api/history/${jobId}`, { method: "DELETE" });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            // If the deleted job is currently open in the detail panel, close it.
            if (app.history.detail && app.history.detail.id === jobId) {
                app.history.detail = null;
            }
            // Also clear outputs panel if it was showing this job.
            if (app.outputs.jobId === jobId) {
                app.outputs = {
                    jobId: null,
                    videoFullUrl: null,
                    videoShortUrl: null,
                    thumbnailUrl: null,
                    zipUrl: null,
                    metadata: {},
                };
                app.pipeline.complete = false;
            }
        } catch (e) {
            app.errorMessage = `Delete failed: ${e.message}`;
        } finally {
            app.history.deleteTargetId = null;
            app.history.deleteTargetTitle = "";
            await load(app);
        }
    }

    window.ClipForgeHistory = { load, openDetail, confirmDelete };
})();
