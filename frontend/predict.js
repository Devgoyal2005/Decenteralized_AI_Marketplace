/**
 * predict.js — DAMM Predict page
 * - wallet.js provides requireWallet() and showToast()
 * - No more window.prompt() for buyer identity
 */

const API_BASE_URLS = ["http://127.0.0.1:8001"];
let activeApiBaseUrl = API_BASE_URLS[0];

const modelSelect    = document.getElementById("modelSelect");
const buySelectedBtn = document.getElementById("buySelectedBtn");
const modelInfo      = document.getElementById("modelInfo");
const predictForm    = document.getElementById("predictForm");
const predictInput   = document.getElementById("predictInput");
const predictImage   = document.getElementById("predictImage");
const passkeyInput   = document.getElementById("passkeyInput");
const jsonInputLabel = document.getElementById("jsonInputLabel");
const imageInputLabel= document.getElementById("imageInputLabel");
const predictResult  = document.getElementById("predictResult");
const predictVisual  = document.getElementById("predictVisual");

let models = [];

// ─── Passkey session helpers ──────────────────────────────────
function getStoredPasskey(modelId) {
  return modelId ? (sessionStorage.getItem(`damm-passkey-${modelId}`) || "") : "";
}

function setStoredPasskey(modelId, passkey) {
  if (modelId && passkey) sessionStorage.setItem(`damm-passkey-${modelId}`, passkey);
}

// ─── API fetch ────────────────────────────────────────────────
async function apiFetch(path, options) {
  const ordered = [activeApiBaseUrl, ...API_BASE_URLS.filter(b => b !== activeApiBaseUrl)];
  let lastErr = null;

  for (const base of ordered) {
    try {
      const res = await fetch(`${base}${path}`, options);
      if (res.status === 404) continue;
      activeApiBaseUrl = base;
      return res;
    } catch (e) { lastErr = e; }
  }
  for (const base of ordered) {
    try {
      const res = await fetch(`${base}${path}`, options);
      activeApiBaseUrl = base;
      return res;
    } catch (e) { lastErr = e; }
  }
  throw lastErr || new Error("Backend is not reachable");
}

// ─── Model selection helpers ──────────────────────────────────
function selectedModel() {
  return models.find(m => m.id === modelSelect.value) || null;
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

  const isCnn = String(model.model_type || "").toUpperCase().includes("CNN");
  const storedPasskey = getStoredPasskey(model.id);
  if (storedPasskey && passkeyInput) passkeyInput.value = storedPasskey;

  jsonInputLabel.style.display  = isCnn ? "none" : "grid";
  imageInputLabel.style.display = isCnn ? "grid" : "none";
  predictInput.required  = !isCnn;
  predictImage.required  = isCnn;

  // Safe text assignment — no innerHTML
  modelInfo.textContent = [
    `Model: ${model.name}`,
    `Type: ${model.model_type || "—"}`,
    `Purchased: ${model.purchased ? "Yes" : "No"}`,
    `Input shape: ${inputShape}`,
    `Labels: ${labels}`,
  ].join("  |  ");
}

function renderModelOptions() {
  if (!models.length) {
    modelSelect.textContent = "";
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No models available";
    modelSelect.appendChild(option);
    renderModelInfo();
    return;
  }

  modelSelect.textContent = "";
  models.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = `${m.name} (${m.id})`;
    modelSelect.appendChild(opt);
  });

  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("model_id");
  if (fromQuery && models.some(m => m.id === fromQuery)) {
    modelSelect.value = fromQuery;
  }

  renderModelInfo();
}

async function fetchModels() {
  const res = await apiFetch("/api/models");
  const payload = await res.json();
  if (!res.ok) throw new Error(payload.detail || "Failed to load models");
  models = payload.models || [];
  renderModelOptions();
}

// ─── Prediction result renderer ───────────────────────────────
function renderClearPrediction(payload, model) {
  const prediction = payload?.prediction || {};
  const lines = [];

  if (payload?.local_model_path) {
    lines.push(`Using local model: ${payload.local_model_path}`);
  }

  if (prediction?.predicted_label) {
    const probs = prediction?.probabilities || {};
    const conf = typeof probs[prediction.predicted_label] === "number"
      ? `${(probs[prediction.predicted_label] * 100).toFixed(2)}%`
      : "N/A";
    lines.push(`Predicted class: ${prediction.predicted_label}`);
    lines.push(`Confidence: ${conf}`);
    if (Object.keys(probs).length > 1) {
      lines.push("All probabilities:");
      Object.entries(probs)
        .sort(([,a],[,b]) => b - a)
        .forEach(([label, prob]) => {
          lines.push(`  ${label}: ${(prob * 100).toFixed(2)}%`);
        });
    }
  } else if (typeof prediction?.value === "number") {
    lines.push(`Predicted value: ${prediction.value}`);
  } else if (typeof prediction?.text === "string" && prediction.text.trim()) {
    lines.push(`Predicted text: ${prediction.text}`);
  } else if (typeof prediction?.generated_text === "string" && prediction.generated_text.trim()) {
    lines.push(`Generated text: ${prediction.generated_text}`);
  } else if (typeof prediction?.answer === "string" && prediction.answer.trim()) {
    lines.push(`Answer: ${prediction.answer}`);
  } else {
    lines.push(`Prediction completed for: ${model?.name || payload?.model_id || "Unknown"}`);
  }

  const imageUrl = prediction?.image_url || payload?.image_url;
  if (imageUrl && predictVisual) {
    predictVisual.textContent = "";
    const caption = document.createElement("p");
    caption.textContent = "Generated image output:";
    caption.style.fontWeight = "600";
    const img = document.createElement("img");
    img.src = imageUrl;
    img.alt = "Prediction output";
    img.style.cssText = "max-width:100%;border-radius:8px;border:1px solid var(--border);margin-top:8px;";
    predictVisual.appendChild(caption);
    predictVisual.appendChild(img);
  } else if (predictVisual) {
    predictVisual.textContent = "";
  }

  predictResult.textContent = lines.join("\n");
}

// ─── Buy selected model ───────────────────────────────────────
async function buySelectedModel() {
  const model = selectedModel();
  if (!model) return;

  // Require wallet — no more window.prompt
  let buyer;
  try {
    buyer = await requireWallet();
  } catch (_) {
    return; // error already toasted
  }

  buySelectedBtn.disabled = true;
  buySelectedBtn.textContent = "Buying…";

  try {
    const res = await apiFetch(`/api/models/${model.id}/buy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ buyer }),
    });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || "Buy failed");

    if (payload.passkey) {
      setStoredPasskey(model.id, payload.passkey);
      if (passkeyInput) passkeyInput.value = payload.passkey;
    }

    showToast(`"${model.name}" purchased successfully!`, "success");
    predictResult.textContent = [
      `Model purchased: ${payload.model_name}`,
      `Local path: ${payload.local_model_path}`,
      `Passkey saved to session automatically.`,
    ].join("\n");

    if (predictVisual) predictVisual.textContent = "";
    await fetchModels();
  } catch (err) {
    showToast(`Buy failed: ${err.message}`, "error");
    predictResult.textContent = `Buy failed: ${err.message}`;
    if (predictVisual) predictVisual.textContent = "";
  } finally {
    buySelectedBtn.disabled = false;
    buySelectedBtn.textContent = "Buy Selected Model";
  }
}

buySelectedBtn.addEventListener("click", buySelectedModel);
modelSelect.addEventListener("change", renderModelInfo);

// ─── Predict submit ───────────────────────────────────────────
predictForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const model = selectedModel();
  if (!model) {
    predictResult.textContent = "Select a model first.";
    if (predictVisual) predictVisual.textContent = "";
    return;
  }

  const isCnn = String(model.model_type || "").toUpperCase().includes("CNN");
  const passkey = (passkeyInput?.value || "").trim();

  if (!model.purchased) {
    predictResult.textContent = "Buy the model first.";
    if (predictVisual) predictVisual.textContent = "";
    return;
  }

  if (!passkey) {
    predictResult.textContent = "Passkey is required. Buy the model to generate one.";
    if (predictVisual) predictVisual.textContent = "";
    return;
  }

  const submitBtn = document.getElementById("predictSubmitBtn");
  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "Verifying…"; }
  predictResult.textContent = "Verifying on-chain purchase…";

  try {
     if (typeof getContract === "function") {
         const contract = await getContract();
         const buyer = typeof getWalletAddress === "function" ? getWalletAddress() : null;
         if (buyer) {
             const isPurchasedOnChain = await contract.checkPurchase(model.id, buyer);
             if (!isPurchasedOnChain) {
                 predictResult.textContent = "On-chain verification failed. You must securely buy this model on-chain first.";
                 if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "Run Prediction"; }
                 return;
             }
         }
     }
  } catch(err) {
     console.warn("On-chain check failed or skipped: ", err);
  }

  predictResult.textContent = "Running prediction…";

  try {
    let res;

    if (isCnn) {
      const file = predictImage.files && predictImage.files[0];
      if (!file) {
        predictResult.textContent = "Please upload an image for CNN prediction.";
        if (predictVisual) predictVisual.textContent = "";
        return;
      }
      const formData = new FormData();
      formData.append("image", file);
      formData.append("passkey", passkey);
      res = await apiFetch(`/api/models/${model.id}/predict-image`, {
        method: "POST",
        body: formData,
      });
    } else {
      let parsedInput;
      try {
        parsedInput = JSON.parse(predictInput.value);
      } catch {
        predictResult.textContent = "Input must be valid JSON (e.g. [0.2, 0.7, 0.1]).";
        if (predictVisual) predictVisual.textContent = "";
        return;
      }
      res = await apiFetch(`/api/models/${model.id}/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: parsedInput, passkey }),
      });
    }

    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || "Prediction failed");
    renderClearPrediction(payload, model);

  } catch (err) {
    predictResult.textContent = `Prediction failed: ${err.message}`;
    if (predictVisual) predictVisual.textContent = "";
  } finally {
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "Run Prediction"; }
  }
});

fetchModels().catch(err => {
  predictResult.textContent = `Failed to load models: ${err.message}`;
});
