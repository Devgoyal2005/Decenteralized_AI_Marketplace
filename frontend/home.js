/**
 * home.js — DAMM Marketplace homepage
 * - Uses wallet.js for MetaMask identity (no more window.prompt)
 * - Builds model cards via createElement (XSS-safe, no innerHTML for user data)
 * - Shows price on each card
 * - Uses showPasskeyModal from wallet.js instead of alert()
 */

const API_BASE_URLS = ["http://127.0.0.1:8001"];
let activeApiBaseUrl = API_BASE_URLS[0];

const modelsList = document.getElementById("modelsList");
const refreshBtn = document.getElementById("refreshBtn");

// ─── API fetch with fallback ───────────────────────────────────
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
  // Final fallback
  for (const base of ordered) {
    try {
      const res = await fetch(`${base}${path}`, options);
      activeApiBaseUrl = base;
      return res;
    } catch (e) { lastErr = e; }
  }
  throw lastErr || new Error("Backend is not reachable");
}

// ─── Safe text helper ─────────────────────────────────────────
function txt(str) {
  const el = document.createTextNode(str == null ? "" : String(str));
  return el;
}

function span(content, className) {
  const el = document.createElement("span");
  if (className) el.className = className;
  el.textContent = content;
  return el;
}

// ─── Price display ────────────────────────────────────────────
function buildPriceRow(model) {
  const row = document.createElement("div");
  row.className = "price-row";

  const label = document.createElement("span");
  label.className = "price-label";
  label.textContent = "Price per request:";

  row.appendChild(label);

  const pricing = model.pricing;
  if (pricing && pricing.per_request != null && pricing.per_request > 0) {
    const val = document.createElement("span");
    val.className = "price-value";
    val.textContent = pricing.per_request;

    const cur = document.createElement("span");
    cur.className = "price-currency";
    cur.textContent = pricing.currency || "ETH";

    row.appendChild(val);
    row.appendChild(cur);
  } else {
    const free = document.createElement("span");
    free.className = "price-free";
    free.textContent = "Free";
    row.appendChild(free);
  }

  return row;
}

// ─── Metric badges ────────────────────────────────────────────
function buildMetricBadges(metrics) {
  if (!Array.isArray(metrics) || !metrics.length) return null;
  const wrap = document.createElement("div");
  wrap.className = "metrics-badges";
  metrics.forEach(m => {
    const b = document.createElement("span");
    b.className = "badge";
    b.textContent = `${m.metric_type}: ${m.metric_value}`;
    wrap.appendChild(b);
  });
  return wrap;
}

// ─── Build a single model card (XSS-safe) ─────────────────────
function buildModelCard(m) {
  const article = document.createElement("article");
  article.className = "model-card";

  // Title row
  const titleRow = document.createElement("div");
  titleRow.className = "model-title-row";

  const strong = document.createElement("strong");
  strong.textContent = m.name || "Unnamed Model";
  titleRow.appendChild(strong);

  const pills = document.createElement("div");
  pills.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;";
  pills.appendChild(span(m.category || "General", "pill"));
  if (m.purchased) pills.appendChild(span("Owned", "pill pill-green"));
  titleRow.appendChild(pills);
  article.appendChild(titleRow);

  // Description
  const desc = document.createElement("p");
  desc.className = "model-desc";
  desc.textContent = m.description || "No description provided.";
  article.appendChild(desc);

  // Price row
  article.appendChild(buildPriceRow(m));

  // Meta grid
  const grid = document.createElement("div");
  grid.className = "model-meta-grid";

  const metaItems = [
    ["Type", m.model_type || "—"],
    ["Task", m.task_type || "—"],
    ["Framework", m.framework || "—"],
    ["Size", `${m.model_size_mb ?? m.file_size_mb ?? "—"} MB`],
    ["Latency", m.estimated_latency_ms != null ? `${m.estimated_latency_ms} ms` : "—"],
    ["GPU", m.gpu_required ? "Required" : "Not required"],
    ["Uploaded", m.uploaded_at ? new Date(m.uploaded_at).toLocaleDateString() : "—"],
    ["Creator", m.creator || "—"],
  ];

  metaItems.forEach(([key, val]) => {
    const small = document.createElement("small");
    const b = document.createElement("b");
    b.textContent = `${key}: `;
    small.appendChild(b);
    small.appendChild(document.createTextNode(val));
    grid.appendChild(small);
  });
  article.appendChild(grid);

  // Metric badges
  const badges = buildMetricBadges(m.evaluation_metrics);
  if (badges) article.appendChild(badges);

  // IPFS info
  const ipfsLine = document.createElement("small");
  ipfsLine.className = "muted";
  ipfsLine.textContent = `IPFS: ${m.ipfs_hash || "—"}`;
  article.appendChild(ipfsLine);

  if (m.gateway_url) {
    const br = document.createElement("br");
    article.appendChild(br);
    const link = document.createElement("a");
    link.className = "primary-link";
    link.href = m.gateway_url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "↗ View file on IPFS";
    article.appendChild(link);
  }

  // Actions
  const actions = document.createElement("div");
  actions.className = "model-actions";

  const buyBtn = document.createElement("button");
  buyBtn.className = `buy-btn${m.purchased ? " is-bought" : ""}`;
  buyBtn.dataset.modelId = m.id || "";
  buyBtn.dataset.purchased = m.purchased ? "true" : "false";
  buyBtn.dataset.modelName = m.name || "Model";
  buyBtn.dataset.price = (m.pricing && m.pricing.per_request) ? m.pricing.per_request : "0";
  buyBtn.textContent = m.purchased ? "▶ Use Model" : "Buy Model";
  actions.appendChild(buyBtn);

  article.appendChild(actions);
  return article;
}

// ─── Buy handler ──────────────────────────────────────────────
modelsList.addEventListener("click", async (event) => {
  const buyBtn = event.target.closest(".buy-btn");
  if (!buyBtn) return;

  const modelId = buyBtn.dataset.modelId;
  if (!modelId) return;

  // Already purchased → go straight to predict
  if (buyBtn.dataset.purchased === "true") {
    window.location.href = `predict.html?model_id=${encodeURIComponent(modelId)}`;
    return;
  }

  // Need wallet to buy
  let buyer;
  try {
    buyer = await requireWallet();
  } catch (_) {
    return; // wallet.js already showed the error toast
  }

  const modelPriceRaw = buyBtn.dataset.price || "0";
  const modelName = buyBtn.dataset.modelName;

  const originalText = buyBtn.textContent;
  buyBtn.disabled = true;
  buyBtn.textContent = "Buying…";

  try {
    if (typeof getContract === "function") {
       const contract = await getContract();
       showToast("Checking on-chain purchase status...", "info");
       const isPurchasedOnChain = await contract.checkPurchase(modelId, buyer);
       if (!isPurchasedOnChain) {
           const priceWei = modelPriceRaw && Number(modelPriceRaw) > 0 ? ethers.parseEther(modelPriceRaw) : 0n;
           showToast("Please approve the purchase transaction in MetaMask...", "info");
           const tx = await contract.buyModel(modelId, { value: priceWei });
           showToast(`Transaction sent! Waiting for confirmation...`, "info");
           await tx.wait();
           showToast("On-chain purchase confirmed! Generating runtime passkey...", "success");
       } else {
           showToast("Model already purchased on-chain. Generating backend passkey...", "info");
       }
    }

    const res = await apiFetch(`/api/models/${modelId}/buy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ buyer }),
    });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || "Buy failed");

    if (payload.passkey) {
      sessionStorage.setItem(`damm-passkey-${modelId}`, payload.passkey);
    }

    buyBtn.textContent = "▶ Use Model";
    buyBtn.classList.add("is-bought");
    buyBtn.dataset.purchased = "true";

    const modelName = buyBtn.dataset.modelName;
    showPasskeyModal(modelName, payload.passkey || "(no passkey returned)", () => {
      window.location.href = `predict.html?model_id=${encodeURIComponent(modelId)}`;
    });

  } catch (err) {
    buyBtn.textContent = originalText;
    buyBtn.disabled = false;
    showToast(`Buy failed: ${err.message}`, "error");
  }
});

// ─── Fetch + render models ────────────────────────────────────
refreshBtn.addEventListener("click", fetchModels);

async function fetchModels() {
  modelsList.textContent = "Loading models…";

  try {
    const res = await apiFetch("/api/models");
    const payload = await res.json();

    const rawModels = payload.models || [];

    // Deduplicate by IPFS hash (keep most recent)
    const byHash = new Map();
    for (const m of rawModels) {
      const key = (m.ipfs_hash || m.id || "").trim();
      if (!key) continue;
      const prev = byHash.get(key);
      if (!prev || (m.uploaded_at || "") >= (prev.uploaded_at || "")) {
        byHash.set(key, m);
      }
    }

    const models = [...byHash.values()];
    modelsList.textContent = "";

    if (!models.length) {
      const p = document.createElement("p");
      p.style.color = "var(--text-3)";
      p.textContent = "No models uploaded yet. Be the first to upload one!";
      modelsList.appendChild(p);
      return;
    }

    const frag = document.createDocumentFragment();
    models.forEach(m => frag.appendChild(buildModelCard(m)));
    modelsList.appendChild(frag);

  } catch (err) {
    modelsList.textContent = "";
    const p = document.createElement("p");
    p.style.color = "var(--red)";
    p.textContent = `Failed to load models: ${err.message}`;
    modelsList.appendChild(p);
  }
}

fetchModels();
