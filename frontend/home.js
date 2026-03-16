const API_BASE_URLS = ["http://127.0.0.1:8001", "http://127.0.0.1:8000"];
let activeApiBaseUrl = API_BASE_URLS[0];

const modelsList = document.getElementById("modelsList");
const refreshBtn = document.getElementById("refreshBtn");

refreshBtn.addEventListener("click", fetchModels);

modelsList.addEventListener("click", async (event) => {
  const buyBtn = event.target.closest(".buy-btn");
  if (!buyBtn) return;

  const modelId = buyBtn.dataset.modelId;
  if (!modelId) return;

  const isPurchased = buyBtn.dataset.purchased === "true";
  if (isPurchased) {
    window.location.href = `predict.html?model_id=${encodeURIComponent(modelId)}`;
    return;
  }

  const originalText = buyBtn.textContent;
  buyBtn.disabled = true;
  buyBtn.textContent = "Buying...";

  try {
    const response = await apiFetch(`/api/models/${modelId}/buy`, { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Buy failed");
    }

    buyBtn.textContent = "Bought";
    buyBtn.classList.add("is-bought");
    // Immediately move user to prediction flow for this model.
    window.location.href = `predict.html?model_id=${encodeURIComponent(modelId)}`;
  } catch (err) {
    buyBtn.textContent = originalText;
    buyBtn.disabled = false;
    alert(`Buy failed: ${err.message}`);
  }
});

async function apiFetch(path, options = undefined) {
  const orderedBases = [
    activeApiBaseUrl,
    ...API_BASE_URLS.filter((base) => base !== activeApiBaseUrl),
  ];

  let lastError = null;
  for (const base of orderedBases) {
    try {
      const response = await fetch(`${base}${path}`, options);
      // If this backend doesn't have the route (404), try next base URL.
      if (response.status === 404) {
        continue;
      }
      activeApiBaseUrl = base;
      return response;
    } catch (err) {
      lastError = err;
    }
  }

  // Final fallback: return last 404 response if no base had the route.
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

function renderMetricBadges(metrics) {
  if (!Array.isArray(metrics) || metrics.length === 0) return "";
  return `
    <div class="metrics-badges">
      ${metrics
        .map((m) => `<span class="badge">${m.metric_type}: ${m.metric_value}</span>`)
        .join("")}
    </div>
  `;
}

async function fetchModels() {
  modelsList.innerHTML = "Loading...";
  try {
    const response = await apiFetch("/api/models");
    const payload = await response.json();

    const rawModels = payload.models || [];
    const byHash = new Map();
    for (const model of rawModels) {
      const key = (model.ipfs_hash || model.id || "").trim();
      if (!key) continue;

      const previous = byHash.get(key);
      if (!previous) {
        byHash.set(key, model);
        continue;
      }

      const prevUploaded = previous.uploaded_at || "";
      const currUploaded = model.uploaded_at || "";
      if (currUploaded >= prevUploaded) {
        byHash.set(key, model);
      }
    }

    const models = [...byHash.values()];
    if (!models.length) {
      modelsList.innerHTML = "<p>No models uploaded yet.</p>";
      return;
    }

    modelsList.innerHTML = models
      .map((m) => `
        <article class="model-card">
          <div class="model-title-row">
            <strong>${m.name || "Unnamed Model"}</strong>
            <span class="pill">${m.category || "General"}</span>
          </div>
          <p class="model-desc">${m.description || "No description"}</p>
          <div class="model-meta-grid">
            <small><b>ID:</b> ${m.id || "-"}</small>
            <small><b>Type:</b> ${m.model_type || "-"}</small>
            <small><b>Task:</b> ${m.task_type || "-"}</small>
            <small><b>Framework:</b> ${m.framework || "-"}</small>
            <small><b>Size:</b> ${m.model_size_mb ?? m.file_size_mb ?? "-"} MB</small>
            <small><b>Latency:</b> ${m.estimated_latency_ms ?? "-"} ms</small>
            <small><b>GPU:</b> ${m.gpu_required ? "Yes" : "No"}</small>
            <small><b>Uploaded:</b> ${m.uploaded_at ? new Date(m.uploaded_at).toLocaleString() : "-"}</small>
          </div>

          ${renderMetricBadges(m.evaluation_metrics)}

          <small class="muted"><b>IPFS:</b> ${m.ipfs_hash || "-"}</small><br/>
          ${m.gateway_url ? `<a class="primary-link" href="${m.gateway_url}" target="_blank" rel="noreferrer">Open file on IPFS</a>` : ""}
          <div class="model-actions">
            <button
              type="button"
              class="buy-btn ${m.purchased ? "is-bought" : ""}"
              data-model-id="${m.id || ""}"
              data-purchased="${m.purchased ? "true" : "false"}"
            >
              ${m.purchased ? "Bought" : "Buy"}
            </button>
          </div>
        </article>
      `)
      .join("");
  } catch (err) {
    modelsList.innerHTML = `<p style="color:red">Failed: ${err.message}</p>`;
  }
}

fetchModels();
