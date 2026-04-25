const activeApiBaseUrl = (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost" || window.location.hostname === "[::1]")
  ? "http://127.0.0.1:8001"
  : "";

const licensesTabContainer = document.getElementById("licensesTab");
const uploadsTabContainer = document.getElementById("uploadsTab");
const loadingIndicator = document.getElementById("loadingIndicator");
const warning = document.getElementById("connectionWarning");
const section = document.getElementById("mySpaceSection");
const refreshBtn = document.getElementById("refreshMySpaceBtn");

const tabs = document.querySelectorAll('.dashboard-tab');
const tabContents = document.querySelectorAll('.dashboard-section');

// Edit Modal elements
const editModal = document.getElementById("editModal");
const closeEditModal = document.getElementById("closeEditModal");
const editForm = document.getElementById("editForm");
const saveEditBtn = document.getElementById("saveEditBtn");

// ─── TAB LOGIC ─────────────────────────────────────
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    tabs.forEach(t => t.classList.remove('active'));
    tabContents.forEach(c => c.classList.remove('active'));
    
    tab.classList.add('active');
    document.getElementById(tab.dataset.target).classList.add('active');
  });
});

// ─── RENDERING ─────────────────────────────────────

function renderLicenses(licenses) {
  licensesTabContainer.innerHTML = "";
  if (!licenses || licenses.length === 0) {
    licensesTabContainer.innerHTML = `<p style="color: var(--muted);">You haven't purchased any models yet.</p>`;
    return;
  }

  licenses.forEach(lic => {
    const card = document.createElement("div");
    card.className = "my-license-card";
    
    const maxUses = (lic.max_uses === null || lic.max_uses === undefined || lic.max_uses === "Unknown") ? 1000 : lic.max_uses;
    const usedCount = (lic.used_count === null || lic.used_count === undefined || lic.used_count === "Unknown") ? 0 : lic.used_count;
    const remaining = Math.max(0, maxUses - usedCount);

    const tokenDisplay = lic.nft_token_id !== null ? `#${lic.nft_token_id}` : "Legacy Key";
    const dateDisplay = lic.purchased_at ? new Date(lic.purchased_at).toLocaleString() : "Unknown date";
    
    card.innerHTML = `
      <div class="my-license-info">
        <h3>${lic.model_name || lic.model_id}</h3>
        <p>Purchased: ${dateDisplay}</p>
        <div style="margin-top:10px;">
           <a href="predict.html?model_id=${lic.model_id}" class="primary-btn" style="text-decoration:none; display:inline-block; font-size:0.9rem; padding: 6px 14px; border-radius:4px;">Go to Prediction</a>
        </div>
      </div>
      <div class="my-license-stats">
        <div class="nft-badge">NFT ${tokenDisplay}</div>
        <div class="usage-ring">
          <strong>${remaining}</strong> out of ${maxUses} uses left
        </div>
      </div>
    `;
    licensesTabContainer.appendChild(card);
  });
}

function renderUploads(uploads) {
  uploadsTabContainer.innerHTML = "";
  if (!uploads || uploads.length === 0) {
    uploadsTabContainer.innerHTML = `<p style="color: var(--muted);">You haven't uploaded any models yet.</p>`;
    return;
  }

  uploads.forEach(up => {
    const card = document.createElement("div");
    card.className = "my-license-card";
    
    const priceStr = (up.pricing && up.pricing.per_request) ? up.pricing.per_request : "0";
    const dateDisplay = up.uploaded_at ? new Date(up.uploaded_at).toLocaleDateString() : "Unknown date";

    // Cache exact data so we can edit it later
    const tagsStr = (up.tags || []).join(", ");
    const descStr = up.description || "";

    card.innerHTML = `
      <div class="my-license-info">
        <h3>${up.name || up.id}</h3>
        <p>Uploaded: ${dateDisplay} &bull; Price: ${priceStr} ETH</p>
        <div style="margin-top:10px; display:flex; gap: 8px;">
           <button class="model-edit-btn" 
              data-id="${up.id}" 
              data-desc="${encodeURIComponent(descStr)}"
              data-price="${priceStr}"
              data-tags="${tagsStr}"
            >Edit Details</button>
           <button class="model-delete-btn" data-id="${up.id}">Delete Model</button>
        </div>
      </div>
      <div class="my-license-stats">
        <div class="nft-badge" style="background:rgba(16,185,129,0.1); color:#10b981;">Total Sales: ${up.sales_count || 0}</div>
      </div>
    `;
    uploadsTabContainer.appendChild(card);
  });
}

// ─── DATA FETCHING ─────────────────────────────────

async function loadDashboardData() {
  const wallet = typeof getWalletAddress === 'function' ? getWalletAddress() : null;
  if (!wallet) {
    warning.style.display = "block";
    section.style.display = "none";
    return;
  }

  warning.style.display = "none";
  section.style.display = "block";
  loadingIndicator.style.display = "block";
  licensesTabContainer.innerHTML = "";
  uploadsTabContainer.innerHTML = "";

  try {
    // Fetch both simultaneously
    const [resLic, resUp] = await Promise.all([
      fetch(`${activeApiBaseUrl}/api/models/my-licenses?wallet=${wallet}`),
      fetch(`${activeApiBaseUrl}/api/models/my-uploads?wallet=${wallet}`)
    ]);
    
    if (!resLic.ok || !resUp.ok) throw new Error("Failed to load dashboard data");
    
    const dataLic = await resLic.json();
    const dataUp = await resUp.json();
    
    loadingIndicator.style.display = "none";
    renderLicenses(dataLic.licenses || []);
    renderUploads(dataUp.uploads || []);
  } catch (err) {
    console.error(err);
    loadingIndicator.style.display = "none";
    licensesTabContainer.innerHTML = `<p style="color:var(--error);">Error loading dashboard. Make sure your local server is running.</p>`;
  }
}

// ─── EVENT DELEGATION FOR EDIT & DELETE ───────────

uploadsTabContainer.addEventListener("click", async (e) => {
  const editBtn = e.target.closest('.model-edit-btn');
  const delBtn = e.target.closest('.model-delete-btn');

  // EDIT
  if (editBtn) {
    document.getElementById("editModelId").value = editBtn.dataset.id;
    document.getElementById("editDescription").value = decodeURIComponent(editBtn.dataset.desc);
    document.getElementById("editPrice").value = editBtn.dataset.price;
    document.getElementById("editTags").value = editBtn.dataset.tags;
    editModal.style.display = "block";
  }

  // DELETE
  if (delBtn) {
    const modelId = delBtn.dataset.id;
    const wallet = typeof getWalletAddress === 'function' ? getWalletAddress() : null;
    if (!wallet) return alert("Connect wallet first!");

    if (!confirm(`Are you sure you want to permanently delete model ${modelId}?`)) return;

    try {
      const message = `Delete model ${modelId} from DAMM Marketplace`;
      // Request MetaMask personal signature
      delBtn.disabled = true;
      delBtn.textContent = "Signing...";
      
      const signature = await window.ethereum.request({
        method: 'personal_sign',
        params: [message, wallet]
      });

      delBtn.textContent = "Deleting...";

      const res = await fetch(`${activeApiBaseUrl}/api/models/${modelId}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wallet, signature, message })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Delete failed");

      alert("Model deleted successfully!");
      loadDashboardData();
    } catch (err) {
      console.error(err);
      alert(`Deletion failed: ${err.message}`);
      delBtn.disabled = false;
      delBtn.textContent = "Delete Model";
    }
  }
});

// ─── EDIT MODAL HANDLERS ──────────────────────────

if (closeEditModal) {
  closeEditModal.onclick = () => editModal.style.display = "none";
}

editForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const wallet = typeof getWalletAddress === 'function' ? getWalletAddress() : null;
  if (!wallet) return alert("Wallet not connected");

  const modelId = document.getElementById("editModelId").value;
  const body = {
    wallet: wallet,
    description: document.getElementById("editDescription").value,
    price_per_request: document.getElementById("editPrice").value,
    tags: document.getElementById("editTags").value
  };

  saveEditBtn.disabled = true;
  saveEditBtn.textContent = "Saving...";

  try {
    const res = await fetch(`${activeApiBaseUrl}/api/models/${modelId}`, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Update failed");
    
    editModal.style.display = "none";
    loadDashboardData(); // Refresh UI
  } catch (err) {
    console.error(err);
    alert(`Update failed: ${err.message}`);
  } finally {
    saveEditBtn.disabled = false;
    saveEditBtn.textContent = "Save Changes";
  }
});

// ─── INITIALIZATION ───────────────────────────────

setInterval(() => {
  const wallet = typeof getWalletAddress === 'function' ? getWalletAddress() : null;
  const isConnected = !!wallet;
  const isSectionVisible = section.style.display !== "none";

  if (isConnected && !isSectionVisible) {
    loadDashboardData();
  } else if (!isConnected && isSectionVisible) {
    warning.style.display = "block";
    section.style.display = "none";
  }
}, 1000);

if (refreshBtn) refreshBtn.addEventListener("click", loadDashboardData);

setTimeout(loadDashboardData, 500);
