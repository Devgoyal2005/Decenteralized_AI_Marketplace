/**
 * wallet.js — Shared MetaMask auth + UI module for DAMM
 * Replaces window.prompt() buyer identity across all pages.
 */

const DAMM_WALLET_KEY = "damm-wallet-address";

// ─── Toast ────────────────────────────────────────────────────
function _ensureToastContainer() {
  let tc = document.getElementById("dammToastContainer");
  if (!tc) {
    tc = document.createElement("div");
    tc.id = "dammToastContainer";
    tc.className = "toast-container";
    document.body.appendChild(tc);
  }
  return tc;
}

function showToast(message, type = "info", duration = 4000) {
  const tc = _ensureToastContainer();
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  const icon = { success: "✓", error: "✕", info: "ℹ" }[type] || "ℹ";
  const iconSpan = document.createElement("span");
  iconSpan.textContent = icon;
  iconSpan.style.fontWeight = "700";

  const msg = document.createElement("span");
  msg.textContent = message;

  toast.appendChild(iconSpan);
  toast.appendChild(msg);
  tc.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = "toastOut 0.25s ease forwards";
    setTimeout(() => toast.remove(), 260);
  }, duration);
}

// ─── Wallet state ─────────────────────────────────────────────
function getWalletAddress() {
  return localStorage.getItem(DAMM_WALLET_KEY) || null;
}

function _saveWalletAddress(addr) {
  localStorage.setItem(DAMM_WALLET_KEY, addr);
}

function _clearWalletAddress() {
  localStorage.removeItem(DAMM_WALLET_KEY);
}

function _truncateAddress(addr) {
  if (!addr || addr.length < 10) return addr;
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

// ─── Connect ──────────────────────────────────────────────────
async function connectWallet() {
  if (!window.ethereum) {
    showToast("MetaMask not detected. Please install it to continue.", "error", 6000);
    throw new Error("MetaMask not installed");
  }

  try {
    const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
    const addr = accounts[0];
    if (!addr) throw new Error("No account returned");
    _saveWalletAddress(addr);
    return addr;
  } catch (err) {
    if (err.code === 4001) {
      showToast("Connection rejected. Please approve MetaMask to continue.", "error");
    } else {
      showToast(`Wallet error: ${err.message}`, "error");
    }
    throw err;
  }
}

// ─── Require wallet (blocks until connected) ──────────────────
async function requireWallet() {
  const existing = getWalletAddress();
  if (existing) return existing;
  return await connectWallet();
}

// ─── Wallet button renderer ───────────────────────────────────
function renderWalletBtn(navEl) {
  const btn = document.createElement("button");
  btn.id = "walletBtn";

  const dot = document.createElement("span");
  dot.className = "wallet-dot";

  const label = document.createElement("span");
  btn.appendChild(dot);
  btn.appendChild(label);

  function updateBtn(addr) {
    if (addr) {
      btn.classList.add("connected");
      label.textContent = _truncateAddress(addr);
      btn.title = addr;
    } else {
      btn.classList.remove("connected");
      label.textContent = "Connect Wallet";
      btn.title = "";
    }
  }

  updateBtn(getWalletAddress());

  btn.addEventListener("click", async () => {
    const addr = getWalletAddress();
    if (addr) {
      // Already connected — clicking shows address copied toast
      await navigator.clipboard.writeText(addr).catch(() => {});
      showToast(`Address copied: ${_truncateAddress(addr)}`, "success", 2500);
      return;
    }
    try {
      const newAddr = await connectWallet();
      updateBtn(newAddr);
      showToast(`Wallet connected: ${_truncateAddress(newAddr)}`, "success");
      // Dispatch event so pages can react
      window.dispatchEvent(new CustomEvent("walletConnected", { detail: { address: newAddr } }));
    } catch (_) {
      // Error already toasted inside connectWallet
    }
  });

  navEl.appendChild(btn);

  // React to account changes in MetaMask
  if (window.ethereum) {
    window.ethereum.on("accountsChanged", (accounts) => {
      if (accounts.length === 0) {
        _clearWalletAddress();
        updateBtn(null);
        showToast("Wallet disconnected.", "info");
      } else {
        _saveWalletAddress(accounts[0]);
        updateBtn(accounts[0]);
        showToast(`Switched to ${_truncateAddress(accounts[0])}`, "info");
      }
    });
  }
}

// ─── Passkey modal ────────────────────────────────────────────
function showPasskeyModal(modelName, passkey, onClose) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";

  const box = document.createElement("div");
  box.className = "modal-box";

  const title = document.createElement("h3");
  title.textContent = `🎉 Model purchased!`;

  const sub = document.createElement("p");
  sub.style.cssText = "font-size:13px;color:var(--text-2);margin-bottom:0;";
  sub.textContent = `"${modelName}" is ready to use. Save your runtime passkey:`;

  const passkeyEl = document.createElement("div");
  passkeyEl.className = "modal-passkey";
  passkeyEl.textContent = passkey;
  passkeyEl.title = "Click to select all";

  const note = document.createElement("p");
  note.className = "modal-note";
  note.textContent = "⚠ This passkey is required for every prediction call. It is also saved in your session so you don't need to re-enter it now.";

  const actions = document.createElement("div");
  actions.className = "modal-actions";

  const copyBtn = document.createElement("button");
  copyBtn.className = "secondary-btn";
  copyBtn.textContent = "Copy Passkey";
  copyBtn.addEventListener("click", async () => {
    await navigator.clipboard.writeText(passkey).catch(() => {});
    copyBtn.textContent = "Copied!";
    setTimeout(() => { copyBtn.textContent = "Copy Passkey"; }, 1800);
  });

  const closeBtn = document.createElement("button");
  closeBtn.textContent = "Go to Predict";
  closeBtn.addEventListener("click", () => {
    overlay.remove();
    if (typeof onClose === "function") onClose();
  });

  actions.appendChild(copyBtn);
  actions.appendChild(closeBtn);

  box.appendChild(title);
  box.appendChild(sub);
  box.appendChild(passkeyEl);
  box.appendChild(note);
  box.appendChild(actions);
  overlay.appendChild(box);
  document.body.appendChild(overlay);

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      overlay.remove();
      if (typeof onClose === "function") onClose();
    }
  });
}

// ─── Auto-init wallet button on DOM ready ─────────────────────
document.addEventListener("DOMContentLoaded", () => {
  const nav = document.querySelector(".site-actions");
  if (nav) renderWalletBtn(nav);
});
