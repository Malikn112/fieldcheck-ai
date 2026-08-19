/**
 * FieldCheck AI — Inspection Studio frontend logic.
 *
 * Handles: drag-and-drop upload, async polling of inspection status,
 * and rendering of the results card. No frameworks — plain fetch + DOM.
 */
(() => {
  "use strict";

  // Resolve the API base: same-origin by default (works whether the
  // frontend is served by the FastAPI app itself at /app, or opened
  // directly as a file / from a separate static host during dev).
  const API_BASE = window.FIELDCHECK_API_BASE || `${window.location.protocol}//${window.location.host}`;
  const API_V1 = `${API_BASE}/api/v1`;
  const POLL_INTERVAL_MS = 2000;
  const POLL_TIMEOUT_MS = 120000;

  const $ = (id) => document.getElementById(id);

  const els = {
    apiBaseLabel: $("api-base-label"),
    form: $("upload-form"),
    dropzone: $("dropzone"),
    fileInput: $("file-input"),
    cameraInput: $("camera-input"),
    cameraBtn: $("camera-btn"),
    dropzoneEmpty: $("dropzone-empty"),
    dropzonePreview: $("dropzone-preview"),
    previewImg: $("preview-img"),
    previewFilename: $("preview-filename"),
    submitBtn: $("submit-btn"),
    progressPanel: $("progress-panel"),
    progressText: $("progress-text"),
    progressBar: $("progress-bar"),
    errorPanel: $("error-panel"),
    inspectorName: $("inspector-name"),
    inspectorEmail: $("inspector-email"),
    siteLocation: $("site-location"),

    resultsEmpty: $("results-empty"),
    resultsCard: $("results-card"),
    resultThumb: $("result-thumb"),
    resultAssetType: $("result-asset-type"),
    resultInspectionId: $("result-inspection-id"),
    conditionBadge: $("condition-badge"),
    passFailBadge: $("pass-fail-badge"),
    resultSummary: $("result-summary"),
    specType: $("spec-type"),
    specMfr: $("spec-mfr"),
    specModel: $("spec-model"),
    specSerial: $("spec-serial"),
    specConfidence: $("spec-confidence"),
    defectList: $("defect-list"),
    compliancePanel: $("compliance-panel"),
    viewReportBtn: $("view-report-btn"),
    newInspectionBtn: $("new-inspection-btn"),

    inspectionList: $("inspection-list"),
    refreshListBtn: $("refresh-list-btn"),
  };

  els.apiBaseLabel.textContent = API_BASE.replace(/^https?:\/\//, "");

  let selectedFile = null;

  // --- Dropzone interactions -------------------------------------------
  els.dropzone.addEventListener("click", () => els.fileInput.click());

  ["dragenter", "dragover"].forEach((evt) =>
    els.dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      els.dropzone.classList.add("dropzone-active");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    els.dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      els.dropzone.classList.remove("dropzone-active");
    })
  );
  els.dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileSelected(file);
  });
  els.fileInput.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelected(file);
  });

  // "Take Photo" — a dedicated button (in addition to plain browse) so the
  // camera opens directly on phones/tablets, rather than relying on users
  // to notice their mobile browser's file picker also offers a camera
  // option. `capture="environment"` on this input requests the rear camera;
  // desktop browsers simply ignore it and fall back to a normal file dialog.
  els.cameraBtn.addEventListener("click", (e) => {
    e.stopPropagation(); // don't also trigger the dropzone's own click->browse handler
    els.cameraInput.click();
  });
  els.cameraInput.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelected(file);
  });

  function handleFileSelected(file) {
    const allowed = ["image/jpeg", "image/png"];
    if (!allowed.includes(file.type)) {
      showError("Only JPEG or PNG images are supported.");
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      showError("File exceeds the 15MB size limit.");
      return;
    }
    hideError();
    selectedFile = file;
    els.dropzoneEmpty.classList.add("hidden");
    els.dropzonePreview.classList.remove("hidden");
    els.previewImg.src = URL.createObjectURL(file);
    els.previewFilename.textContent = `${file.name} (${(file.size / 1024).toFixed(0)} KB)`;
    els.submitBtn.disabled = false;
  }

  // --- Submit / upload ---------------------------------------------------
  els.form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!selectedFile) return;
    hideError();

    els.submitBtn.disabled = true;
    showProgress("Uploading photo…", 8);

    const formData = new FormData();
    formData.append("file", selectedFile);
    if (els.inspectorName.value) formData.append("inspector_name", els.inspectorName.value);
    if (els.inspectorEmail.value) formData.append("inspector_email", els.inspectorEmail.value);
    if (els.siteLocation.value) formData.append("site_location", els.siteLocation.value);

    try {
      const res = await fetch(`${API_V1}/inspections/upload`, { method: "POST", body: formData });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body?.detail || `Upload failed (HTTP ${res.status}).`);
      }
      const data = await res.json();
      showProgress("Analyzing asset — running OCR, defect detection & compliance checks…", 30);
      await pollForResult(data.inspection_id);
    } catch (err) {
      showError(err.message || "Upload failed. Please try again.");
      hideProgress();
      els.submitBtn.disabled = false;
    }
  });

  async function pollForResult(inspectionId) {
    const start = Date.now();
    let progress = 30;

    while (Date.now() - start < POLL_TIMEOUT_MS) {
      const res = await fetch(`${API_V1}/inspections/${inspectionId}`);
      if (!res.ok) throw new Error(`Failed to fetch inspection status (HTTP ${res.status}).`);
      const data = await res.json();

      progress = Math.min(progress + 8, 92);
      showProgress(statusMessage(data.status), progress);

      if (data.status === "COMPLETED") {
        showProgress("Analysis complete.", 100);
        setTimeout(hideProgress, 600);
        renderResult(data);
        refreshInspectionList();
        return;
      }
      if (data.status === "FAILED") {
        throw new Error(data.error_message || "Analysis failed on the server.");
      }
      await sleep(POLL_INTERVAL_MS);
    }
    throw new Error("Analysis is taking longer than expected. Check back shortly via Recent Inspections.");
  }

  function statusMessage(status) {
    switch (status) {
      case "PENDING":
        return "Queued for analysis…";
      case "PROCESSING":
        return "AI vision model is analyzing the asset…";
      default:
        return "Working…";
    }
  }

  // --- Rendering results ---------------------------------------------------
  function renderResult(data) {
    els.resultsEmpty.classList.add("hidden");
    els.resultsCard.classList.remove("hidden");

    els.resultThumb.src = `${API_V1}/inspections/${data.id}/image`;
    els.resultAssetType.textContent = data.asset?.asset_type || "Unknown Asset";
    els.resultInspectionId.textContent = `ID: ${data.id}`;

    const conditionMap = {
      GOOD: ["bg-green-100", "text-green-800", "GOOD"],
      ACCEPTABLE: ["bg-yellow-100", "text-yellow-800", "ACCEPTABLE"],
      POOR: ["bg-orange-100", "text-orange-800", "POOR"],
      CRITICAL: ["bg-red-100", "text-red-800", "CRITICAL"],
    };
    const [bg, fg, label] = conditionMap[data.overall_condition] || ["bg-gray-100", "text-gray-600", "N/A"];
    els.conditionBadge.className = `px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-wide ${bg} ${fg}`;
    els.conditionBadge.textContent = label;

    const pass = data.overall_condition === "GOOD" || data.overall_condition === "ACCEPTABLE";
    els.passFailBadge.className = `px-3 py-1 rounded-full text-xs font-semibold ${
      pass ? "bg-green-50 text-green-700 border border-green-200" : "bg-red-50 text-red-700 border border-red-200"
    }`;
    els.passFailBadge.textContent = pass ? "PASS" : "FAIL";

    els.resultSummary.textContent = data.overall_summary || "No summary available.";

    els.specType.textContent = data.asset?.asset_type || "—";
    els.specMfr.textContent = data.asset?.manufacturer || "—";
    els.specModel.textContent = data.asset?.model_number || "—";
    els.specSerial.textContent = data.asset?.serial_or_tag_number || "—";
    els.specConfidence.textContent = data.asset?.confidence_score != null
      ? `${Math.round(data.asset.confidence_score * 100)}%`
      : "—";

    const severityColors = {
      Low: "bg-blue-100 text-blue-800",
      Medium: "bg-amber-100 text-amber-800",
      High: "bg-orange-100 text-orange-800",
      Critical: "bg-red-100 text-red-800",
    };
    els.defectList.innerHTML = "";
    if (!data.defects || data.defects.length === 0) {
      els.defectList.innerHTML = `<p class="text-sm text-green-700"><i class="fa-solid fa-circle-check mr-1"></i>No visual defects detected.</p>`;
    } else {
      for (const d of data.defects) {
        const div = document.createElement("div");
        div.className = "border border-gray-200 rounded-lg p-3";
        div.innerHTML = `
          <div class="flex items-center justify-between mb-1">
            <span class="font-medium text-sm">${escapeHtml(d.defect_type)}</span>
            <span class="text-xs font-semibold px-2 py-0.5 rounded-full ${severityColors[d.severity] || "bg-gray-100 text-gray-700"}">${escapeHtml(d.severity)}</span>
          </div>
          <p class="text-xs text-gray-500 mb-1">Location: ${escapeHtml(d.location_description || "—")}</p>
          <p class="text-xs text-gray-700"><span class="font-medium">Recommendation:</span> ${escapeHtml(d.recommendation || "—")}</p>
        `;
        els.defectList.appendChild(div);
      }
    }

    const compliant = data.is_compliant;
    const hazards = data.safety_hazards_detected || [];
    els.compliancePanel.innerHTML = `
      <div class="flex items-center gap-2">
        <span class="font-medium">Compliant:</span>
        <span class="${compliant ? "text-green-700" : "text-red-700"} font-semibold">${compliant === null || compliant === undefined ? "—" : compliant ? "Yes" : "No"}</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="font-medium">Immediate action required:</span>
        <span class="${data.immediate_action_required ? "text-red-700 font-semibold" : "text-gray-600"}">${data.immediate_action_required ? "YES — ESCALATE" : "No"}</span>
      </div>
      ${hazards.length ? `<ul class="list-disc list-inside text-red-700 text-xs mt-1">${hazards.map((h) => `<li>${escapeHtml(h)}</li>`).join("")}</ul>` : ""}
    `;

    els.viewReportBtn.href = `${API_V1}/inspections/${data.id}/report`;
  }

  els.newInspectionBtn.addEventListener("click", () => {
    els.resultsCard.classList.add("hidden");
    els.resultsEmpty.classList.remove("hidden");
    els.form.reset();
    selectedFile = null;
    els.dropzoneEmpty.classList.remove("hidden");
    els.dropzonePreview.classList.add("hidden");
    els.submitBtn.disabled = true;
  });

  // --- Recent inspections list ---------------------------------------------
  async function refreshInspectionList() {
    els.inspectionList.textContent = "Loading…";
    try {
      const res = await fetch(`${API_V1}/inspections?limit=10`);
      const items = await res.json();
      if (!items.length) {
        els.inspectionList.innerHTML = `<p class="text-gray-400 text-xs">No inspections yet.</p>`;
        return;
      }
      els.inspectionList.innerHTML = "";
      for (const item of items) {
        const row = document.createElement("button");
        row.className = "w-full text-left flex items-center justify-between gap-2 px-3 py-2 rounded-lg hover:bg-gray-50 border border-gray-100";
        const statusColor = {
          COMPLETED: "text-green-600",
          FAILED: "text-red-600",
          PENDING: "text-gray-400",
          PROCESSING: "text-blue-600",
        }[item.status] || "text-gray-400";
        row.innerHTML = `
          <span class="truncate">${escapeHtml(item.asset?.asset_type || item.original_filename)}</span>
          <span class="text-xs font-medium ${statusColor} whitespace-nowrap">${item.status}</span>
        `;
        row.addEventListener("click", async () => {
          if (item.status === "COMPLETED") {
            renderResult(item);
          } else {
            showProgress(statusMessage(item.status), 40);
            try {
              await pollForResult(item.id);
            } catch (err) {
              showError(err.message);
              hideProgress();
            }
          }
        });
        els.inspectionList.appendChild(row);
      }
    } catch {
      els.inspectionList.innerHTML = `<p class="text-red-400 text-xs">Could not load recent inspections.</p>`;
    }
  }
  els.refreshListBtn.addEventListener("click", refreshInspectionList);

  // --- Helpers -----------------------------------------------------------
  function showProgress(text, pct) {
    els.progressPanel.classList.remove("hidden");
    els.progressText.textContent = text;
    els.progressBar.style.width = `${pct}%`;
  }
  function hideProgress() {
    els.progressPanel.classList.add("hidden");
  }
  function showError(msg) {
    els.errorPanel.classList.remove("hidden");
    els.errorPanel.textContent = msg;
  }
  function hideError() {
    els.errorPanel.classList.add("hidden");
    els.errorPanel.textContent = "";
  }
  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }
  async function safeJson(res) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }
  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str ?? "";
    return div.innerHTML;
  }

  // Initial load
  refreshInspectionList();
})();
