const API_BASE_URLS = ["http://127.0.0.1:8001", "http://127.0.0.1:8000"];
let activeApiBaseUrl = API_BASE_URLS[0];

const form = document.getElementById("uploadForm");
const result = document.getElementById("result");
const metricsContainer = document.getElementById("metricsContainer");
const addMetricBtn = document.getElementById("addMetricBtn");

async function apiFetch(path, options = undefined) {
  const orderedBases = [
    activeApiBaseUrl,
    ...API_BASE_URLS.filter((base) => base !== activeApiBaseUrl),
  ];

  let lastError = null;
  for (const base of orderedBases) {
    try {
      const response = await fetch(`${base}${path}`, options);
      activeApiBaseUrl = base;
      return response;
    } catch (err) {
      lastError = err;
    }
  }

  throw lastError || new Error("Backend is not reachable");
}

const METRIC_TYPES = [
  "Accuracy",
  "Precision",
  "Recall",
  "F1 Score",
  "mAP",
  "IoU",
  "Dice Score",
  "BLEU",
  "ROUGE",
  "Perplexity",
  "WER",
  "MSE",
  "MAE",
  "RMSE",
  "R²",
];

function createMetricRow(defaultType = "Accuracy", defaultValue = "") {
  const row = document.createElement("div");
  row.className = "metric-row";

  const options = METRIC_TYPES
    .map((metric) => `<option ${metric === defaultType ? "selected" : ""}>${metric}</option>`)
    .join("");

  row.innerHTML = `
    <select class="metric-type">${options}</select>
    <input class="metric-value" type="number" step="0.0001" placeholder="Metric value" value="${defaultValue}" />
    <button type="button" class="danger-btn">Remove</button>
  `;

  row.querySelector(".danger-btn").addEventListener("click", () => row.remove());
  metricsContainer.appendChild(row);
}

addMetricBtn.addEventListener("click", () => createMetricRow());

function collectMetrics() {
  const rows = [...metricsContainer.querySelectorAll(".metric-row")];
  return rows
    .map((row) => {
      const metricType = row.querySelector(".metric-type")?.value?.trim() || "";
      const metricValue = row.querySelector(".metric-value")?.value;
      return {
        metric_type: metricType,
        metric_value: metricValue === "" ? "" : Number(metricValue),
      };
    })
    .filter((m) => m.metric_type && m.metric_value !== "" && !Number.isNaN(m.metric_value));
}

createMetricRow("Accuracy", "");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  result.textContent = "Starting upload...";

  try {
    const formData = new FormData(form);
    const evaluationMetrics = collectMetrics();

    // Remove optional numeric fields if left empty, otherwise FastAPI returns 422
    const optionalNumericFields = [
      "price_per_request",
      "model_size_mb",
      "estimated_latency_ms",
    ];

    optionalNumericFields.forEach((field) => {
      const raw = formData.get(field);
      if (raw === null || String(raw).trim() === "") {
        formData.delete(field);
      }
    });

    if (evaluationMetrics.length > 0) {
      formData.append("evaluation_metrics", JSON.stringify(evaluationMetrics));
    }

    // Checkbox handling: ensure explicit boolean string is sent
    const gpuRequired = form.querySelector("input[name='gpu_required']")?.checked || false;
    formData.set("gpu_required", String(gpuRequired));

    const response = await apiFetch(`/api/models/upload`, {
      method: "POST",
      body: formData,
    });

    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || "Upload failed");
    }

    const jobId = payload.job_id;
    result.textContent = `Upload started. Job ID: ${jobId}. Checking status...`;

    // Poll for status
    const pollStatus = async () => {
      try {
        const statusResponse = await apiFetch(`/api/models/status/${jobId}`);
        const statusPayload = await statusResponse.json();

        if (!statusResponse.ok) {
          throw new Error(statusPayload.detail || "Status check failed");
        }

        if (statusPayload.status === "completed") {
          result.textContent = `Upload completed! Model ID: ${statusPayload.model_id}\nIPFS Hash: ${statusPayload.ipfs_hash}\nGateway: ${statusPayload.gateway_url}`;
          form.reset();
          metricsContainer.innerHTML = "";
          createMetricRow("Accuracy", "");
        } else if (statusPayload.status === "failed") {
          result.textContent = `Upload failed: ${statusPayload.error}`;
        } else {
          result.textContent = `Status: ${statusPayload.status} - ${statusPayload.message || ""}`;
          setTimeout(pollStatus, 2000); // Poll every 2 seconds
        }
      } catch (err) {
        result.textContent = `Error checking status: ${err.message}`;
      }
    };

    pollStatus();
  } catch (err) {
    result.textContent = `Error: ${err.message}`;
  }
});
