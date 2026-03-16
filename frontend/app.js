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
  modelsList.innerHTML = "Loading...";
  try {
    const response = await fetch(`${API_BASE_URL}/api/models`);
    const payload = await response.json();

    const models = payload.models || [];
    if (!models.length) {
      modelsList.innerHTML = "<p>No models uploaded yet.</p>";
      return;
    }

    modelsList.innerHTML = models
      .map((m) => `
        <article class="model-card">
          <strong>${m.name}</strong><br/>
          <small>ID: ${m.id}</small><br/>
          <small>IPFS: ${m.ipfs_hash}</small><br/>
          <a href="${m.gateway_url}" target="_blank" rel="noreferrer">Open file on IPFS</a>
        </article>
      `)
      .join("");
  } catch (err) {
    modelsList.innerHTML = `<p style="color:red">Failed: ${err.message}</p>`;
  }
}

fetchModels();
