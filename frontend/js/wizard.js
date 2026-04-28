// Spotlight first-run wizard.
// Dims the page, highlights each UI section in sequence with a tooltip.
// Reads wizard_completed from /api/settings; re-runnable via the header button.

(function () {
    const STEPS = [
        {
            target: "#section-footage",
            title: "Upload your footage",
            body: "Drop one or more gameplay clips (MP4 or MKV). Your library persists across sessions — upload once, reuse forever.",
            required: true,
        },
        {
            target: "#section-mode",
            title: "Choose your script mode",
            body: "Full AI picks the topic and writes the script. Topic-guided: you give a topic, AI writes. Manual: you provide the script yourself.",
            required: true,
        },
        {
            target: "#section-overrides",
            title: "Manual overrides",
            body: "Toggle per-feature AI off. Skip the script reviewer loop, or use a local Kokoro voice instead of cloud TTS.",
            required: false,
        },
        {
            target: "#section-platforms",
            title: "Select target platforms",
            body: "Pick any combination of YouTube Shorts, TikTok, Instagram Reels, and Facebook Reels. Platform rules (length, aspect, title limits) are baked in.",
            required: true,
        },
        {
            target: "#section-series",
            title: "Series tagging",
            body: "Standalone for one-offs. First Episode creates a new series. Continuation picks an existing series for auto-generated recap and outro.",
            required: false,
        },
        {
            target: "#section-generate",
            title: "Generate",
            body: "Click Generate to kick off the full pipeline: script, voiceover, cutting, subtitles, render, thumbnail, metadata. Takes a few minutes end-to-end.",
            required: true,
        },
    ];

    let currentIdx = 0;
    let backdrop, spotlight, tooltip;

    async function shouldRunOnLoad() {
        try {
            const res = await fetch("/api/settings");
            const settings = await res.json();
            // Settings are stored JSON-encoded; "true" / "false" as strings
            const flag = settings.wizard_completed;
            return flag === false || flag === "false" || flag === undefined;
        } catch (e) {
            console.error("Wizard: failed to read settings", e);
            return false;
        }
    }

    async function markCompleted() {
        try {
            await fetch("/api/settings", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ wizard_completed: "true" }),
            });
        } catch (e) {
            console.error("Wizard: failed to save completion", e);
        }
    }

    function buildOverlay() {
        const root = document.getElementById("wizard-root");
        root.innerHTML = "";

        backdrop = document.createElement("div");
        backdrop.className = "wizard-backdrop";
        backdrop.addEventListener("click", () => { /* block clicks; don't close */ });

        spotlight = document.createElement("div");
        spotlight.className = "wizard-spotlight";

        tooltip = document.createElement("div");
        tooltip.className = "wizard-tooltip";

        root.appendChild(backdrop);
        root.appendChild(spotlight);
        root.appendChild(tooltip);
    }

    function teardown() {
        const root = document.getElementById("wizard-root");
        root.innerHTML = "";
    }

    function positionStep(step) {
        const targetEl = document.querySelector(step.target);
        if (!targetEl) {
            console.warn("Wizard: target missing", step.target);
            next();
            return;
        }

        targetEl.scrollIntoView({ behavior: "smooth", block: "center" });

        // Wait for scroll to settle before measuring.
        setTimeout(() => {
            const rect = targetEl.getBoundingClientRect();
            const pad = 8;
            // Use pageYOffset to account for scroll position
            const top = rect.top + window.scrollY - pad;
            const left = rect.left + window.scrollX - pad;
            const width = rect.width + pad * 2;
            const height = rect.height + pad * 2;

            spotlight.style.top = `${top}px`;
            spotlight.style.left = `${left}px`;
            spotlight.style.width = `${width}px`;
            spotlight.style.height = `${height}px`;

            // Tooltip position: below the target if space, otherwise above.
            const viewportH = window.innerHeight;
            const tooltipTop = rect.bottom + 16 + window.scrollY;
            const tooltipFitsBelow = (rect.bottom + 200) < viewportH;

            tooltip.style.left = `${left}px`;
            if (tooltipFitsBelow) {
                tooltip.style.top = `${tooltipTop}px`;
            } else {
                tooltip.style.top = `${rect.top + window.scrollY - 200}px`;
            }

            renderTooltip(step);
        }, 350);
    }

    function renderTooltip(step) {
        const badge = step.required
            ? '<span class="wizard-required">Required</span>'
            : '<span class="wizard-optional">Optional</span>';

        const isLast = currentIdx === STEPS.length - 1;
        const nextLabel = isLast ? "Finish" : "Next →";
        const skipLabel = step.required ? "Skip tour" : "Skip";

        tooltip.innerHTML = `
            <div class="wizard-title">${step.title}${badge}</div>
            <div>${step.body}</div>
            <div class="wizard-progress">Step ${currentIdx + 1} of ${STEPS.length}</div>
            <div class="wizard-tooltip-actions">
                <button class="wizard-btn wizard-btn-skip" id="wiz-skip">${skipLabel}</button>
                <button class="wizard-btn wizard-btn-primary" id="wiz-next">${nextLabel}</button>
            </div>
        `;
        document.getElementById("wiz-next").addEventListener("click", next);
        document.getElementById("wiz-skip").addEventListener("click", finish);
    }

    function next() {
        currentIdx++;
        if (currentIdx >= STEPS.length) {
            finish();
            return;
        }
        positionStep(STEPS[currentIdx]);
    }

    function finish() {
        teardown();
        markCompleted();
    }

    async function start() {
        currentIdx = 0;
        buildOverlay();
        positionStep(STEPS[0]);
    }

    async function bootstrap() {
        if (await shouldRunOnLoad()) {
            // Give Alpine a tick to render the DOM before we measure rects
            setTimeout(start, 300);
        }
    }

    // Expose for re-run from header button
    window.ClipForgeWizard = { start };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bootstrap);
    } else {
        bootstrap();
    }
})();
