const API_BASE_URL = "http://127.0.0.1:8000";

const form = document.getElementById("uploadForm");
const result = document.getElementById("result");
const modelsList = document.getElementById("modelsList");
const refreshBtn = document.getElementById("refreshBtn");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  result.textContent = "Uploading...";

  try {
    const formData = new FormData(form);

    const response = await fetch(`${API_BASE_URL}/api/models/upload`, {
      method: "POST",
      body: formData,
    });

    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || "Upload failed");
    }

    result.textContent = JSON.stringify(payload, null, 2);
    form.reset();
    await fetchModels();
  } catch (err) {
    result.textContent = `Error: ${err.message}`;
  }
});

refreshBtn.addEventListener("click", fetchModels);

async function fetchModels() {
  modelsList.textContent = "Loading...";
  try {
    const response = await fetch(`${API_BASE_URL}/api/models`);
    const payload = await response.json();

    const models = payload.models || [];
    if (!models.length) {
      modelsList.textContent = "";
      const empty = document.createElement("p");
      empty.textContent = "No models uploaded yet.";
      modelsList.appendChild(empty);
      return;
    }

    modelsList.textContent = "";
    const frag = document.createDocumentFragment();

    models.forEach((m) => {
      const card = document.createElement("article");
      card.className = "model-card";

      const title = document.createElement("strong");
      title.textContent = m.name || "Unnamed model";
      card.appendChild(title);
      card.appendChild(document.createElement("br"));

      const id = document.createElement("small");
      id.textContent = `ID: ${m.id || "N/A"}`;
      card.appendChild(id);
      card.appendChild(document.createElement("br"));

      const ipfs = document.createElement("small");
      ipfs.textContent = `IPFS: ${m.ipfs_hash || "N/A"}`;
      card.appendChild(ipfs);
      card.appendChild(document.createElement("br"));

      if (m.gateway_url) {
        const link = document.createElement("a");
        link.href = m.gateway_url;
        link.target = "_blank";
        link.rel = "noreferrer";
        link.textContent = "Open file on IPFS";
        card.appendChild(link);
      }

      frag.appendChild(card);
    });

    modelsList.appendChild(frag);
  } catch (err) {
    modelsList.textContent = "";
    const failure = document.createElement("p");
    failure.style.color = "red";
    failure.textContent = `Failed: ${err.message}`;
    modelsList.appendChild(failure);
  }
}

fetchModels();
