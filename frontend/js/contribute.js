/**
 * contribute.js — DAMM Contribute page
 * XSS fix: all user-generated content (title, summary, details, proposer)
 * now set via textContent, never innerHTML.
 */

const API_BASE_URLS = ["http://127.0.0.1:8001"];
let activeApiBaseUrl = API_BASE_URLS[0];

const proposalForm         = document.getElementById("proposalForm");
const proposalTitle        = document.getElementById("proposalTitle");
const proposalProposer     = document.getElementById("proposalProposer");
const proposalSummary      = document.getElementById("proposalSummary");
const proposalDetails      = document.getElementById("proposalDetails");
const proposalList         = document.getElementById("proposalList");
const refreshProposalsBtn  = document.getElementById("refreshProposalsBtn");

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
  throw lastErr || new Error("Backend is not reachable");
}

// ─── Build a proposal card (XSS-safe, no innerHTML for user data) ──
function buildProposalCard(proposal) {
  const article = document.createElement("article");
  article.className = "proposal-card";
  article.dataset.proposalId = proposal.id;

  // Head row
  const head = document.createElement("div");
  head.className = "proposal-head";

  const title = document.createElement("strong");
  title.textContent = proposal.title || "Untitled";
  head.appendChild(title);

  const statusEl = document.createElement("span");
  statusEl.className = `proposal-status ${proposal.accepted ? "accepted" : "pending"}`;
  statusEl.textContent = proposal.accepted ? "Accepted" : "Pending";
  head.appendChild(statusEl);
  article.appendChild(head);

  // Meta line
  const meta = document.createElement("p");
  meta.className = "proposal-meta";
  const byText = proposal.proposer || "Anonymous";
  const dateText = proposal.created_at
    ? new Date(proposal.created_at).toLocaleString()
    : "Unknown date";
  meta.textContent = `By ${byText} · ${dateText}`;
  article.appendChild(meta);

  // Summary
  if (proposal.summary) {
    const sumP = document.createElement("p");
    sumP.textContent = proposal.summary;
    article.appendChild(sumP);
  }

  // Implementation details
  if (proposal.details) {
    const detP = document.createElement("p");
    detP.className = "proposal-details";
    const b = document.createElement("b");
    b.textContent = "Implementation: ";
    detP.appendChild(b);
    detP.appendChild(document.createTextNode(proposal.details));
    article.appendChild(detP);
  }

  // Actions row
  const actions = document.createElement("div");
  actions.className = "proposal-actions";

  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = `▲ ${proposal.upvotes || 0} upvotes`;
  actions.appendChild(badge);

  const upvoteBtn = document.createElement("button");
  upvoteBtn.type = "button";
  upvoteBtn.className = "upvote-btn";
  upvoteBtn.dataset.proposalId = proposal.id;
  upvoteBtn.textContent = "Upvote ▲";
  actions.appendChild(upvoteBtn);

  article.appendChild(actions);
  return article;
}

// ─── Render proposals list ────────────────────────────────────
function renderProposals(items) {
  proposalList.textContent = "";

  if (!Array.isArray(items) || !items.length) {
    const p = document.createElement("p");
    p.style.color = "var(--text-3)";
    p.textContent = "No proposals submitted yet. Be the first!";
    proposalList.appendChild(p);
    return;
  }

  const frag = document.createDocumentFragment();
  items.forEach(proposal => frag.appendChild(buildProposalCard(proposal)));
  proposalList.appendChild(frag);
}

async function fetchProposals() {
  proposalList.textContent = "Loading proposals…";
  const res = await apiFetch("/api/proposals");
  const payload = await res.json();
  if (!res.ok) throw new Error(payload.detail || "Failed to load proposals");
  renderProposals(payload.proposals || []);
}

// ─── Submit proposal ──────────────────────────────────────────
proposalForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const body = {
    title:    proposalTitle.value.trim(),
    proposer: proposalProposer.value.trim() || getWalletAddress() || "Anonymous",
    summary:  proposalSummary.value.trim(),
    details:  proposalDetails.value.trim(),
  };

  if (!body.title || !body.summary) {
    showToast("Proposal title and summary are required.", "error");
    return;
  }

  const submitBtn = proposalForm.querySelector("button[type=submit]");
  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "Submitting…"; }

  try {
    const res = await apiFetch("/api/proposals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || "Failed to submit proposal");

    showToast("Proposal submitted!", "success");
    proposalForm.reset();
    await fetchProposals();
  } catch (err) {
    showToast(`Failed to submit: ${err.message}`, "error");
  } finally {
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "Submit Proposal"; }
  }
});

// ─── Upvote handler ───────────────────────────────────────────
proposalList.addEventListener("click", async (event) => {
  const upvoteBtn = event.target.closest(".upvote-btn");
  if (!upvoteBtn) return;

  const proposalId = upvoteBtn.dataset.proposalId;
  if (!proposalId) return;

  upvoteBtn.disabled = true;
  upvoteBtn.textContent = "Voting…";

  try {
    const res = await apiFetch(`/api/proposals/${proposalId}/upvote`, { method: "POST" });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || "Failed to upvote");
    showToast("Upvote recorded!", "success", 2000);
    await fetchProposals();
  } catch (err) {
    showToast(`Upvote failed: ${err.message}`, "error");
    upvoteBtn.disabled = false;
    upvoteBtn.textContent = "Upvote ▲";
  }
});

// ─── Refresh button ───────────────────────────────────────────
refreshProposalsBtn.addEventListener("click", () => {
  fetchProposals().catch(err => {
    proposalList.textContent = "";
    const p = document.createElement("p");
    p.style.color = "var(--red)";
    p.textContent = `Failed: ${err.message}`;
    proposalList.appendChild(p);
  });
});

fetchProposals().catch(err => {
  proposalList.textContent = "";
  const p = document.createElement("p");
  p.style.color = "var(--red)";
  p.textContent = `Failed to load: ${err.message}`;
  proposalList.appendChild(p);
});
