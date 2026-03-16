const API_BASE_URLS = ["http://127.0.0.1:8001", "http://127.0.0.1:8000"];
let activeApiBaseUrl = API_BASE_URLS[0];

const modelSelect = document.getElementById("modelSelect");
const buySelectedBtn = document.getElementById("buySelectedBtn");
const modelInfo = document.getElementById("modelInfo");
const predictForm = document.getElementById("predictForm");
const predictInput = document.getElementById("predictInput");
const predictImage = document.getElementById("predictImage");
const jsonInputLabel = document.getElementById("jsonInputLabel");
const imageInputLabel = document.getElementById("imageInputLabel");
const predictResult = document.getElementById("predictResult");

let models = [];

async function apiFetch(path, options = undefined) {
  const orderedBases = [
    activeApiBaseUrl,
    ...API_BASE_URLS.filter((base) => base !== activeApiBaseUrl),
  ];

  let lastError = null;
  for (const base of orderedBases) {
    try {
      const response = await fetch(`${base}${path}`, options);
      if (response.status === 404) {
        continue;
      }
      activeApiBaseUrl = base;
      return response;
    } catch (err) {
      lastError = err;
    }
  }

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

function selectedModel() {
  const modelId = modelSelect.value;
  return models.find((m) => m.id === modelId) || null;
}

function renderModelInfo() {
  const model = selectedModel();
  if (!model) {
    modelInfo.textContent = "No model selected.";
    return;
  }

  const inputShape = Array.isArray(model.input_shape) && model.input_shape.length
    ? model.input_shape.join(", ")
    : "Any numeric array";
  const labels = Array.isArray(model.output_labels) && model.output_labels.length
    ? model.output_labels.join(", ")
    : "No labels";

  const localPath = model.local_model_path || "Not downloaded yet";
  const isCnn = String(model.model_type || "").toUpperCase().includes("CNN");

  jsonInputLabel.style.display = isCnn ? "none" : "grid";
  imageInputLabel.style.display = isCnn ? "grid" : "none";
  predictInput.required = !isCnn;
  predictImage.required = isCnn;

  modelInfo.textContent = `Model: ${model.name} | Type: ${model.model_type || "-"} | Bought: ${model.purchased ? "Yes" : "No"} | Input shape: ${inputShape} | Output labels: ${labels} | Local path: ${localPath}`;
}

function renderModelOptions() {
  if (!models.length) {
    modelSelect.innerHTML = "<option value=''>No models available</option>";
    renderModelInfo();
    return;
  }

  modelSelect.innerHTML = models
    .map((m) => `<option value="${m.id}">${m.name} (${m.id})</option>`)
    .join("");

  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("model_id");
  if (fromQuery && models.some((m) => m.id === fromQuery)) {
    modelSelect.value = fromQuery;
  }

  renderModelInfo();
}

async function fetchModels() {
  const response = await apiFetch("/api/models");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load models");
  }
  models = payload.models || [];
  renderModelOptions();
}

async function buySelectedModel() {
  const model = selectedModel();
  if (!model) return;

  buySelectedBtn.disabled = true;
  buySelectedBtn.textContent = "Buying...";
  try {
    const response = await apiFetch(`/api/models/${model.id}/buy`, { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Buy failed");
    }

    predictResult.textContent = `Bought model ${model.id}. Local path: ${payload.local_model_path}`;
    await fetchModels();
  } catch (err) {
    predictResult.textContent = `Buy failed: ${err.message}`;
  } finally {
    buySelectedBtn.disabled = false;
    buySelectedBtn.textContent = "Buy Selected Model";
  }
}

buySelectedBtn.addEventListener("click", buySelectedModel);
modelSelect.addEventListener("change", renderModelInfo);

predictForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const model = selectedModel();
  if (!model) {
    predictResult.textContent = "Select a model first.";
    return;
  }

  const isCnn = String(model.model_type || "").toUpperCase().includes("CNN");
  if (!model.purchased) {
    predictResult.textContent = "Buy the model first."
    return;
  }

  predictResult.textContent = "Predicting...";
  try {
    let response;
    if (isCnn) {
      const file = predictImage.files && predictImage.files[0];
      if (!file) {
        predictResult.textContent = "Please upload an image for CNN prediction.";
        return;
      }

      const formData = new FormData();
      formData.append("image", file);
      response = await apiFetch(`/api/models/${model.id}/predict-image`, {
        method: "POST",
        body: formData,
      });
    } else {
      let parsedInput;
      try {
        parsedInput = JSON.parse(predictInput.value);
      } catch {
        predictResult.textContent = "Input must be valid JSON array.";
        return;
      }

      response = await apiFetch(`/api/models/${model.id}/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: parsedInput }),
      });
    }

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Prediction failed");
    }

    predictResult.textContent = JSON.stringify(payload, null, 2);
  } catch (err) {
    predictResult.textContent = `Prediction failed: ${err.message}`;
  }
});

fetchModels().catch((err) => {
  predictResult.textContent = `Failed to load models: ${err.message}`;
});
