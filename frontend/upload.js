const API_BASE_URLS = ["http://127.0.0.1:8001", "http://127.0.0.1:8000"];
let activeApiBaseUrl = API_BASE_URLS[0];

const form = document.getElementById("uploadForm");
const result = document.getElementById("result");
const metricsContainer = document.getElementById("metricsContainer");
const addMetricBtn = document.getElementById("addMetricBtn");
const modelTypeSelect = form.querySelector("select[name='model_type']");
const taskTypeSelect = form.querySelector("select[name='task_type']");
const inputTypeField = document.getElementById("inputType");
const outputTypeField = document.getElementById("outputType");
const inputShapeField = document.getElementById("inputShape");
const outputLabelsField = document.getElementById("outputLabels");
const featureColumnsField = document.getElementById("featureColumns");
const featureTypesField = document.getElementById("featureTypes");
const targetColumnField = document.getElementById("targetColumn");

const TASK_IO_PRESETS = {
  Classification: { input_type: "Image tensor", output_type: "Class probabilities (multi-class)" },
  Regression: { input_type: "Tabular mixed features (numeric/text)", output_type: "Single continuous numeric value" },
  "Object Detection": { input_type: "Image tensor", output_type: "Bounding boxes + class scores" },
  Segmentation: { input_type: "Image tensor", output_type: "Pixel-wise mask" },
  "Text Generation": { input_type: "Prompt text", output_type: "Generated text" },
  "Text Classification": { input_type: "Text string", output_type: "Class probabilities (multi-class)" },
  "Machine Translation": { input_type: "Text string", output_type: "Translated text" },
  "Speech Recognition": { input_type: "Audio waveform/features", output_type: "Generated text" },
  "Image Generation": { input_type: "Noise vector / condition", output_type: "Generated image" },
  "Text-to-Image": { input_type: "Prompt text", output_type: "Generated image" },
  "Question Answering": { input_type: "Question + context text", output_type: "Answer span/text" },
  Recommendation: { input_type: "Tabular mixed features (numeric/text)", output_type: "Ranked item scores" },
  Forecasting: { input_type: "Time-series window", output_type: "Future value(s)" },
};

const IO_AUTOFILL = {
  "Image tensor": { input_shape: "224,224,3", feature_columns: "", feature_types: "" },
  "Tabular numeric features": {
    input_shape: "8",
    feature_columns: "f1,f2,f3,f4,f5,f6,f7,f8",
    feature_types: "numeric,numeric,numeric,numeric,numeric,numeric,numeric,numeric",
  },
  "Tabular mixed features (numeric/text)": {
    input_shape: "6",
    feature_columns: "age,income,city,review_text,score,segment",
    feature_types: "numeric,numeric,categorical,text,numeric,categorical",
  },
  "Text string": { input_shape: "", feature_columns: "text", feature_types: "text" },
  "Prompt text": { input_shape: "", feature_columns: "prompt", feature_types: "text" },
  "Audio waveform/features": { input_shape: "16000", feature_columns: "audio", feature_types: "numeric" },
  "Time-series window": { input_shape: "24,5", feature_columns: "t-23...t0", feature_types: "numeric" },
  "Question + context text": { input_shape: "", feature_columns: "question,context", feature_types: "text,text" },
  "Noise vector / condition": { input_shape: "100", feature_columns: "z", feature_types: "numeric" },
};

const OUTPUT_LABELS_AUTOFILL = {
  "Class probabilities (binary)": "class_0,class_1",
  "Class probabilities (multi-class)": "class_0,class_1,class_2",
  "Bounding boxes + class scores": "object_0,object_1",
  "Pixel-wise mask": "background,foreground",
};

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

function applyTaskPreset(taskType) {
  const preset = TASK_IO_PRESETS[taskType] || TASK_IO_PRESETS.Classification;
  if (inputTypeField) inputTypeField.value = preset.input_type;
  if (outputTypeField) outputTypeField.value = preset.output_type;
  applyAutonomousIO();
}

function applyAutonomousIO() {
  const taskType = taskTypeSelect?.value || "Classification";
  const inputType = inputTypeField?.value || "Image tensor";
  const outputType = outputTypeField?.value || "Class probabilities (multi-class)";

  const inputPreset = IO_AUTOFILL[inputType] || IO_AUTOFILL["Image tensor"];

  if (inputShapeField) inputShapeField.value = inputPreset.input_shape || "";
  if (featureColumnsField) featureColumnsField.value = inputPreset.feature_columns || "";
  if (featureTypesField) featureTypesField.value = inputPreset.feature_types || "";

  if (targetColumnField) {
    targetColumnField.value = taskType === "Regression" ? "target_value" : "target_class";
  }

  const isRegression = taskType === "Regression" || outputType === "Single continuous numeric value" || outputType === "Future value(s)";
  if (outputLabelsField) {
    outputLabelsField.value = isRegression ? "" : (OUTPUT_LABELS_AUTOFILL[outputType] || "class_0,class_1,class_2");
  }
}

function applyModelTypeHints() {
  const modelType = modelTypeSelect?.value || "";
  if (modelType !== "Basic ML") return;

  if (taskTypeSelect && ["Object Detection", "Segmentation", "Image Generation", "Text-to-Image"].includes(taskTypeSelect.value)) {
    taskTypeSelect.value = "Regression";
  }

  if (inputTypeField && !inputTypeField.value) {
    inputTypeField.value = "Tabular mixed features (numeric/text)";
  }
  applyTaskPreset(taskTypeSelect?.value || "Regression");
}

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
taskTypeSelect?.addEventListener("change", (e) => applyTaskPreset(e.target.value));
modelTypeSelect?.addEventListener("change", () => applyModelTypeHints());
inputTypeField?.addEventListener("change", applyAutonomousIO);
outputTypeField?.addEventListener("change", applyAutonomousIO);

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
applyTaskPreset(taskTypeSelect?.value || "Classification");
applyModelTypeHints();
applyAutonomousIO();

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
