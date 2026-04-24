/**
 * predict.js — DAMM Predict page
 *
 * Auth flow (wallet-based, no passkey):
 *   1. User connects MetaMask wallet
 *   2. modelSelect onChange → hit /license-status?wallet=... → show NFT status in licenseInfo
 *   3. On submit → if licensed (DB record exists) → POST /predict with wallet_address + license_token_id
 *   4. Backend verifies license in Neon DB (+ optional on-chain check) → runs prediction
 */

const API_BASE = "http://127.0.0.1:8001";

const modelSelect       = document.getElementById("modelSelect");
const buySelectedBtn    = document.getElementById("buySelectedBtn");
const modelInfo         = document.getElementById("modelInfo");
const licenseInfo       = document.getElementById("licenseInfo");
const licenseTokenSelect = document.getElementById("licenseTokenSelect");
const predictForm       = document.getElementById("predictForm");
const predictInput      = document.getElementById("predictInput");
const predictImage      = document.getElementById("predictImage");
const jsonInputLabel    = document.getElementById("jsonInputLabel");
const imageInputLabel   = document.getElementById("imageInputLabel");
const predictResult     = document.getElementById("predictResult");
const predictVisual     = document.getElementById("predictVisual");

let models = [];
let currentLicense = null;

// ─── API helper ───────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  return fetch(`${API_BASE}${path}`, options);
}

// ─── License lookup ────────────────────────────────────────────
async function fetchLicenseStatus(modelId, walletAddress) {
  try {
    const res = await apiFetch(
      `/api/models/${modelId}/license-status?wallet=${encodeURIComponent(walletAddress)}`
    );
    if (res.ok) return await res.json();
  } catch (_) {}
  return { purchased: false };
}

// ─── Update license UI ─────────────────────────────────────────
async function updateLicenseForSelected() {
  currentLicense = null;
  if (licenseInfo) licenseInfo.textContent = "";
  if (licenseTokenSelect) {
    licenseTokenSelect.innerHTML = '<option value="">—</option>';
  }

  const model = models.find(m => m.id === modelSelect?.value);
  if (!model) return;

  // Update modelInfo
  if (modelInfo) {
    const inputShape = Array.isArray(model.input_shape) && model.input_shape.length
      ? model.input_shape.join(", ") : "Any";
    const labels = Array.isArray(model.output_labels) && model.output_labels.length
      ? model.output_labels.join(", ") : "None";
    modelInfo.textContent = `Type: ${model.model_type || "—"}  |  Input shape: ${inputShape}  |  Labels: ${labels}`;
  }

  // Toggle CNN image vs JSON input
  const isCnn = String(model.model_type || "").toUpperCase().includes("CNN");
  if (jsonInputLabel) jsonInputLabel.style.display = isCnn ? "none" : "";
  if (imageInputLabel) imageInputLabel.style.display = isCnn ? "" : "none";
  if (predictInput) predictInput.required = !isCnn;
  if (predictImage) predictImage.required = isCnn;

  const wallet = typeof getWalletAddress === "function" ? getWalletAddress() : null;
  if (!wallet) {
    if (licenseInfo) licenseInfo.textContent = "Connect wallet to check license.";
    return;
  }

  if (licenseInfo) licenseInfo.textContent = "Checking license…";
  currentLicense = await fetchLicenseStatus(model.id, wallet);

  if (licenseInfo) {
    if (currentLicense.purchased) {
      const tokenLabel = currentLicense.nft_token_id != null
        ? `NFT #${currentLicense.nft_token_id}`
        : "License in DB (NFT mint pending)";
      licenseInfo.textContent = `✅ Licensed — ${tokenLabel}`;
      licenseInfo.style.color = "var(--green, #4caf50)";

      // Populate the license token select with the token from DB
      if (licenseTokenSelect) {
        const opt = document.createElement("option");
        opt.value = currentLicense.nft_token_id ?? "db";
        opt.textContent = tokenLabel;
        opt.selected = true;
        licenseTokenSelect.innerHTML = "";
        licenseTokenSelect.appendChild(opt);
      }
    } else {
      licenseInfo.textContent = "❌ No license found — buy the model first.";
      licenseInfo.style.color = "var(--red, #f44336)";
    }
  }
}

// ─── Load models ───────────────────────────────────────────────
async function fetchModels() {
  const res = await apiFetch("/api/models");
  if (!res.ok) throw new Error("Failed to load models");
  const payload = await res.json();
  models = payload.models || [];

  if (modelSelect) {
    modelSelect.innerHTML = models.map(m => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `${m.name} (${m.id.slice(0, 8)}…)`;
      return opt.outerHTML;
    }).join("");
  }

  // Auto-select model from URL query string
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("model_id");
  if (fromQuery && models.some(m => m.id === fromQuery) && modelSelect) {
    modelSelect.value = fromQuery;
  }

  await updateLicenseForSelected();
}

// ─── Events ────────────────────────────────────────────────────
if (modelSelect) modelSelect.addEventListener("change", updateLicenseForSelected);
window.addEventListener("walletConnected", updateLicenseForSelected);

// ─── Buy selected model inline ─────────────────────────────────
if (buySelectedBtn) {
  buySelectedBtn.addEventListener("click", async () => {
    const model = models.find(m => m.id === modelSelect?.value);
    if (!model) { showToast("Select a model first", "error"); return; }

    let buyer;
    try { buyer = await requireWallet(); } catch (_) { return; }

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

      showToast(`"${model.name}" purchased — license stored in DB ✓`, "success");
      if (predictResult) {
        predictResult.textContent = [
          `✅ Model purchased: ${payload.model_name}`,
          `📁 Local path: ${payload.local_model_path}`,
          `🖼  NFT metadata: ${payload.metadata_uri || "(pinning pending)"}`,
          ``,
          `Your wallet is your license. Enter input below and click Run Prediction.`,
        ].join("\n");
      }
      await updateLicenseForSelected();
    } catch (err) {
      showToast(`Buy failed: ${err.message}`, "error");
    } finally {
      buySelectedBtn.disabled = false;
      buySelectedBtn.textContent = "Buy Selected Model";
    }
  });
}

// ─── Prediction result renderer ────────────────────────────────
function renderPrediction(payload, model) {
  const prediction = payload?.prediction || {};
  const lines = [];

  if (payload.local_model_path) lines.push(`📁 Model file: ${payload.local_model_path}`);

  const lic = payload.license || {};
  if (lic.nft_token_id != null)     lines.push(`🔑 NFT Token: #${lic.nft_token_id}`);
  if (lic.verified_via)             lines.push(`✅ Verified via: ${lic.verified_via}`);
  if (lic.remaining_uses != null)   lines.push(`🔄 Remaining uses: ${lic.remaining_uses}`);
  if (lic.record_use_tx)            lines.push(`⛓  Usage TX: ${lic.record_use_tx}`);

  lines.push("");

  if (prediction.predicted_label) {
    lines.push(`🎯 Predicted: ${prediction.predicted_label}`);
    const conf = (prediction.probabilities || {})[prediction.predicted_label];
    if (typeof conf === "number") lines.push(`📊 Confidence: ${(conf * 100).toFixed(2)}%`);

    const allProbs = Object.entries(prediction.probabilities || {})
      .sort(([, a], [, b]) => b - a);
    if (allProbs.length > 1) {
      lines.push("", "All probabilities:");
      allProbs.forEach(([lbl, p]) => lines.push(`  ${lbl}: ${(p * 100).toFixed(2)}%`));
    }
  } else if (typeof prediction.value === "number") {
    lines.push(`📈 Predicted value: ${prediction.value}`);
  }

  if (predictResult) predictResult.textContent = lines.join("\n");
  if (predictVisual) predictVisual.textContent = "";
}

// ─── Submit prediction ─────────────────────────────────────────
if (predictForm) {
  predictForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const model = models.find(m => m.id === modelSelect?.value);
    if (!model) { if (predictResult) predictResult.textContent = "Select a model first."; return; }

    const wallet = typeof getWalletAddress === "function" ? getWalletAddress() : null;
    if (!wallet) {
      if (predictResult) predictResult.textContent = "Connect your MetaMask wallet first.";
      showToast("Connect your wallet first", "error");
      return;
    }

    const submitBtn = document.getElementById("predictSubmitBtn");
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "Checking…"; }
    if (predictResult) predictResult.textContent = "Verifying license in Neon DB…";

    try {
      // ── Step 1: Verify license in DB ───────────────────────
      const license = await fetchLicenseStatus(model.id, wallet);
      if (!license.purchased) {
        if (predictResult) predictResult.textContent = "❌ No license found.\nBuy the model first using the 'Buy Selected Model' button.";
        showToast("You don't own this model", "error");
        return;
      }

      const tokenId = license.nft_token_id ?? null;

      // ── Step 2: Optional on-chain double-check ──────────────
      if (typeof getContract === "function" && tokenId != null) {
        try {
          const contract = await getContract();
          const onChain = await contract.checkPurchase(model.id, wallet);
          if (!onChain) showToast("On-chain check: not found (DB record used)", "info");
        } catch (_) {}
      }

      if (submitBtn) submitBtn.textContent = "Running…";
      if (predictResult) predictResult.textContent = "Running prediction…";

      const isCnn = String(model.model_type || "").toUpperCase().includes("CNN");
      let res;

      if (isCnn) {
        const file = predictImage?.files?.[0];
        if (!file) {
          if (predictResult) predictResult.textContent = "Please upload an image for CNN prediction.";
          return;
        }
        const formData = new FormData();
        formData.append("image", file);
        formData.append("wallet_address", wallet);
        if (tokenId != null) formData.append("token_id", tokenId);
        res = await apiFetch(`/api/models/${model.id}/predict-image`, {
          method: "POST",
          body: formData,
        });
      } else {
        let parsedInput;
        try { parsedInput = JSON.parse(predictInput?.value || ""); }
        catch {
          if (predictResult) predictResult.textContent = "Input must be valid JSON (e.g. [0.2, 0.7, 0.1]).";
          return;
        }
        res = await apiFetch(`/api/models/${model.id}/predict`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            wallet_address: wallet,
            license_token_id: tokenId,
            input: parsedInput,
          }),
        });
      }

      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Prediction failed");
      renderPrediction(payload, model);

    } catch (err) {
      if (predictResult) predictResult.textContent = `❌ Prediction failed: ${err.message}`;
      if (predictVisual) predictVisual.textContent = "";
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "Run Prediction"; }
    }
  });
}

// ─── Init ──────────────────────────────────────────────────────
fetchModels().catch(err => {
  if (predictResult) predictResult.textContent = `Failed to load models: ${err.message}`;
});
