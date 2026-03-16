# Decentralized AI Marketplace (FastAPI + HTML/CSS/JS)

Simple local marketplace to upload AI models to Pinata/IPFS, buy (download) models locally, and run prediction flow from web UI.

## Project structure
- backend/
  - .env (Pinata credentials, ignored by git)
  - main.py
  - requirements.txt
  - models_registry.json
  - downloaded_models/ (created after buy)
- frontend/
  - index.html (home/marketplace)
  - upload.html (upload model + metadata)
  - predict.html (run predictions)
  - home.js
  - upload.js
  - predict.js
  - styles.css

## Backend setup
```powershell
cd D:\Decenteralized_AI_Marketplace
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Run backend:
```powershell
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

## Frontend setup
```powershell
cd D:\Decenteralized_AI_Marketplace\frontend
python -m http.server 5500
```

Open:
- http://127.0.0.1:5500/index.html
- http://127.0.0.1:5500/upload.html
- http://127.0.0.1:5500/predict.html

## Main API endpoints
- GET /api/health
- GET /api/models
- POST /api/models/upload
- GET /api/models/status/{job_id}
- POST /api/models/{model_id}/buy
- GET /api/models/purchased
- POST /api/models/{model_id}/predict
- POST /api/models/{model_id}/predict-image

## Notes
- Buying a model downloads it to backend/downloaded_models.
- For meaningful classification output, upload model metadata with correct `input_shape` and `output_labels`.
