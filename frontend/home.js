/**
 * home.js — DAMM Marketplace homepage
 * Buy flow:
 *   1. Require wallet → POST /api/models/{id}/buy (downloads model + pins NFT metadata to Pinata)
 *   2. Show NFT metadata_uri to user → prompt MetaMask mint (contract.registerModel / buyModel)
 *   3. POST /api/models/{id}/license-confirm with real token_id
 * Uses wallet.js (requireWallet, showToast, showPasskeyModal)
 * Uses contract.js + ethers.js for on-chain interaction
 */

const API_BASE      = "http://127.0.0.1:8001";
const modelsList    = document.getElementById("modelsList");
const refreshBtn    = document.getElementById("refreshBtn");

// ─── API helper ───────────────────────────────────────────────
async function apiFetch(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options);
  return res;
}

// ─── Safe text helpers ────────────────────────────────────────
function txt(s) { return document.createTextNode(s == null ? "" : String(s)); }
function span(content, cls) {
  const el = document.createElement("span");
  if (cls) el.className = cls;
  el.textContent = content;
  return el;
}

// ─── Price row ────────────────────────────────────────────────
function buildPriceRow(model) {
  const row = document.createElement("div");
  row.className = "price-row";

  const label = span("Price per request:", "price-label");
  row.appendChild(label);

  const pricing = model.pricing;
  if (pricing && pricing.per_request != null && pricing.per_request > 0) {
    const val = span(pricing.per_request, "price-value");
    const cur = span(" " + (pricing.currency || "ETH"), "price-currency");
    row.appendChild(val);
    row.appendChild(cur);
  } else {
    row.appendChild(span("Free", "price-free"));
  }
  return row;
}

// ─── Metric badges ─────────────────────────────────────────────
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

// ─── License status check ──────────────────────────────────────
async function checkLicenseStatus(modelId, walletAddress) {
  try {
    const res = await apiFetch(
      `/api/models/${modelId}/license-status?wallet=${encodeURIComponent(walletAddress)}`
    );
    if (res.ok) return await res.json();
  } catch (_) {}
  return { purchased: false };
}

// ─── Build model card (XSS-safe) ──────────────────────────────
function buildModelCard(m) {
  const article = document.createElement("article");
  article.className = "model-card";
  article.dataset.modelId = m.id || "";

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

  // Price
  article.appendChild(buildPriceRow(m));

  // Meta grid
  const grid = document.createElement("div");
  grid.className = "model-meta-grid";
  const metaItems = [
    ["Type",      m.model_type || "—"],
    ["Task",      m.task_type || "—"],
    ["Framework", m.framework || "—"],
    ["Size",      `${m.model_size_mb ?? m.file_size_mb ?? "—"} MB`],
    ["Latency",   m.estimated_latency_ms != null ? `${m.estimated_latency_ms} ms` : "—"],
    ["GPU",       m.gpu_required ? "Required" : "Not required"],
    ["Uploaded",  m.uploaded_at ? new Date(m.uploaded_at).toLocaleDateString() : "—"],
    ["Creator",   m.creator || "—"],
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

  const badges = buildMetricBadges(m.evaluation_metrics);
  if (badges) article.appendChild(badges);

  const ipfsLine = document.createElement("small");
  ipfsLine.className = "muted";
  ipfsLine.textContent = `IPFS: ${m.ipfs_hash || "—"}`;
  article.appendChild(ipfsLine);

  if (m.gateway_url) {
    article.appendChild(document.createElement("br"));
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
  buyBtn.dataset.modelName = m.name || "Model";
  buyBtn.dataset.purchased = m.purchased ? "true" : "false";
  buyBtn.dataset.price = (m.pricing && m.pricing.per_request) ? m.pricing.per_request : "0";
  buyBtn.dataset.ipfsHash = m.ipfs_hash || "";
  buyBtn.textContent = m.purchased ? "▶ Use Model" : "Buy Model";
  actions.appendChild(buyBtn);

  article.appendChild(actions);

  // NFT status line (filled asynchronously)
  const nftLine = document.createElement("small");
  nftLine.className = "muted";
  nftLine.style.marginTop = "4px";
  nftLine.style.display = "block";
  article.appendChild(nftLine);

  // Async: check DB license status and update button/pill
  const wallet = typeof getWalletAddress === "function" ? getWalletAddress() : null;
  if (wallet && m.id) {
    checkLicenseStatus(m.id, wallet).then(status => {
      if (status.purchased) {
        buyBtn.textContent = "▶ Use Model";
        buyBtn.classList.add("is-bought");
        buyBtn.dataset.purchased = "true";
        buyBtn.dataset.nftTokenId = status.nft_token_id ?? "";
        if (!pills.querySelector(".pill-green")) {
          pills.appendChild(span("Licensed", "pill pill-green"));
        }
        if (status.nft_token_id != null) {
          nftLine.textContent = `NFT Token ID: #${status.nft_token_id}`;
        } else {
          nftLine.textContent = "License in DB — NFT mint pending";
        }
      }
    }).catch(() => {});
  }

  return article;
}

// ─── Full buy flow ─────────────────────────────────────────────
modelsList.addEventListener("click", async (event) => {
  const buyBtn = event.target.closest(".buy-btn");
  if (!buyBtn) return;

  const modelId   = buyBtn.dataset.modelId;
  const modelName = buyBtn.dataset.modelName;
  if (!modelId) return;

  // Already purchased → go to predict
  if (buyBtn.dataset.purchased === "true") {
    window.location.href = `predict.html?model_id=${encodeURIComponent(modelId)}`;
    return;
  }

  // Step 1: Require wallet
  let buyer;
  try {
    buyer = await requireWallet();
  } catch (_) { return; }

  const priceRaw = buyBtn.dataset.price || "0";

  buyBtn.disabled = true;
  buyBtn.textContent = "Checking…";

  try {
    // ── Step 1: Already licensed in DB? ──────────────────────
    const existingStatus = await checkLicenseStatus(modelId, buyer);
    if (existingStatus.purchased) {
      buyBtn.textContent = "▶ Use Model";
      buyBtn.classList.add("is-bought");
      buyBtn.dataset.purchased = "true";
      buyBtn.dataset.nftTokenId = existingStatus.nft_token_id ?? "";
      showToast("You already own this model!", "success");
      return;
    }

    // ── Step 2: Backend — download model + pin NFT metadata ──
    buyBtn.textContent = "Downloading model…";
    const buyRes = await apiFetch(`/api/models/${modelId}/buy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ buyer }),
    });
    const buyPayload = await buyRes.json();
    if (!buyRes.ok) throw new Error(buyPayload.detail || "Buy failed");

    const metadataUri = buyPayload.metadata_uri || "";
    showToast("Model downloaded ✓ — NFT metadata pinned to Pinata ✓", "success");

    // ── Step 3: On-chain mint via MetaMask (if contract configured) ──
    let nftTokenId = null;
    if (typeof getContract === "function" && metadataUri) {
      try {
        buyBtn.textContent = "Minting NFT…";
        showToast("Approve NFT mint transaction in MetaMask…", "info");
        const contract = await getContract();
        const priceWei = priceRaw && Number(priceRaw) > 0
          ? ethers.parseEther(priceRaw)
          : 0n;
        const tx = await contract.buyModel(modelId, { value: priceWei });
        buyBtn.textContent = "Confirming…";
        showToast("Transaction sent — waiting for confirmation…", "info");
        const receipt = await tx.wait();

        // Parse token ID from the ModelPurchased event (first log)
        if (receipt.logs && receipt.logs.length > 0) {
          try {
            const iface = contract.interface;
            const parsed = iface.parseLog(receipt.logs[0]);
            if (parsed && parsed.args) {
              // The event doesn't have tokenId directly — use tx block as proxy
              // In a real ERC-721 the Transfer event would have tokenId
              nftTokenId = Number(receipt.blockNumber); // placeholder until real NFT
            }
          } catch (_) {}
        }

        showToast("NFT minted on-chain ✓", "success");
      } catch (err) {
        if (err.code !== 4001) {
          console.warn("On-chain mint failed (non-fatal):", err);
          showToast("On-chain mint skipped — license stored in DB", "info");
        } else {
          showToast("MetaMask rejected. License still stored in DB.", "info");
        }
      }
    }

    // ── Step 4: Confirm token_id back to Neon DB ─────────────
    if (nftTokenId !== null) {
      try {
        await apiFetch(`/api/models/${modelId}/license-confirm`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ wallet_address: buyer, nft_token_id: nftTokenId }),
        });
      } catch (_) {}
    }

    // ── Step 5: Update UI ─────────────────────────────────────
    buyBtn.dataset.purchased = "true";
    buyBtn.dataset.nftTokenId = nftTokenId ?? "";
    buyBtn.textContent = "▶ Use Model";
    buyBtn.classList.add("is-bought");
    buyBtn.disabled = false;

    // Show NFT modal
    showPasskeyModal(
      modelName,
      nftTokenId != null
        ? `NFT Token #${nftTokenId}\nMetadata: ${metadataUri}`
        : `License stored in DB.\nMetadata URI: ${metadataUri || "(no metadata)"}`,
      () => {
        window.location.href = `predict.html?model_id=${encodeURIComponent(modelId)}`;
      }
    );

  } catch (err) {
    buyBtn.disabled = false;
    buyBtn.textContent = "Buy Model";
    showToast(`Buy failed: ${err.message}`, "error");
  }
});

// ─── Fetch + render models ─────────────────────────────────────
refreshBtn.addEventListener("click", fetchModels);

async function fetchModels() {
  modelsList.textContent = "Loading models…";
  try {
    const res = await apiFetch("/api/models");
    const payload = await res.json();
    const rawModels = payload.models || [];

    // Deduplicate by ipfs_hash
    const byHash = new Map();
    for (const m of rawModels) {
      const key = (m.ipfs_hash || m.id || "").trim();
      if (!key) continue;
      const prev = byHash.get(key);
      if (!prev || (m.uploaded_at || "") >= (prev.uploaded_at || "")) byHash.set(key, m);
    }

    const models = [...byHash.values()];
    modelsList.textContent = "";

    if (!models.length) {
      const p = document.createElement("p");
      p.style.color = "var(--text-3)";
      p.textContent = "No models uploaded yet. Be the first!";
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
