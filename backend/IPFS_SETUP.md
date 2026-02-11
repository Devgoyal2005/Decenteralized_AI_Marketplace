# IPFS Integration Setup Guide

## Quick Start

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Get Pinata API Credentials

1. Go to https://app.pinata.cloud
2. Create account (free tier: 1GB)
3. Navigate to **API Keys** section
4. Click **New Key**
5. Enable:
   - ✅ `pinFileToIPFS`
   - ✅ `pinJSONToIPFS`
6. Copy your **API Key** and **API Secret**

### 3. Configure Environment

```bash
# Copy the example env file
cp .env.example .env

# Edit .env and add your Pinata credentials
# PINATA_API_KEY=your_actual_api_key_here
# PINATA_SECRET_KEY=your_actual_secret_key_here
```

### 4. Upload Brain Tumor Model to IPFS

```bash
# Make sure unet_brain_tumor_final.keras exists in backend/
python upload_to_ipfs.py
```

This will:
- Upload the model to IPFS via Pinata
- Get back an IPFS hash (CID)
- Update `models_registry.json` with the hash
- Save hash to `ipfs_hash.txt`

### 5. Test Download from IPFS

```bash
python test_download_ipfs.py
```

This will:
- Download model from IPFS to `model_cache/`
- Load the model into memory
- Run a test prediction
- Verify everything works

### 6. Start Backend with IPFS Support

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## How It Works

### Model Upload Flow

```
1. User uploads .keras file via API
2. Backend uploads to Pinata IPFS
3. Get IPFS hash (e.g., QmXx...abc)
4. Store in models_registry.json:
   {
     "id": "brain-tumor-unet",
     "ipfs_hash": "QmXx...abc",
     "creator": "0x123...",
     ...
   }
```

### Model Usage Flow

```
1. User sends prediction request with model_id
2. Backend checks if model in memory cache
3. If not, checks local disk cache
4. If not, downloads from IPFS
5. Loads model and makes prediction
```

---

## File Structure

```
backend/
├── ipfs_service.py          # IPFS upload/download via Pinata
├── model_manager.py          # Dynamic model loading & caching
├── models_registry.json      # Model metadata storage
├── .env                      # Pinata API credentials (create this)
├── .env.example              # Template for .env
├── upload_to_ipfs.py         # Script to upload model to IPFS
├── test_download_ipfs.py     # Script to test IPFS download
├── model_cache/              # Local cache for downloaded models
│   └── brain-tumor-unet.keras
└── main.py                   # FastAPI app (will be updated next)
```

---

## API Endpoints (Coming Next)

### Upload Model
```bash
POST /api/models/upload
Content-Type: multipart/form-data

{
  "file": <model_file>,
  "name": "My Model",
  "creator": "0x123...",
  "description": "...",
  "model_type": "keras",
  "price_monthly": 49.99
}

Response:
{
  "success": true,
  "model_id": "my-model-uuid",
  "ipfs_hash": "QmXx...abc",
  "message": "Model uploaded to IPFS"
}
```

### List Models
```bash
GET /api/models

Response:
{
  "models": [
    {
      "id": "brain-tumor-unet",
      "name": "Brain Tumor Segmentation",
      "ipfs_hash": "QmXx...abc",
      "creator": "0x123...",
      ...
    }
  ]
}
```

### Get Model Info
```bash
GET /api/models/brain-tumor-unet

Response:
{
  "id": "brain-tumor-unet",
  "name": "Brain Tumor Segmentation",
  "ipfs_hash": "QmXx...abc",
  "creator": "0x123...",
  "gateway_url": "https://gateway.pinata.cloud/ipfs/QmXx...abc",
  ...
}
```

### Make Prediction
```bash
POST /api/predict
Content-Type: multipart/form-data

{
  "model_id": "brain-tumor-unet",  # <-- Now required!
  "file": <mri_image>
}

Response:
{
  "success": true,
  "prediction": {
    "mask": [...],
    "tumor_percentage": 14.45,
    ...
  },
  "model_loaded_from": "ipfs"  # or "cache" or "memory"
}
```

---

## Testing Commands

```bash
# 1. Upload model to IPFS
python upload_to_ipfs.py

# 2. Download and test model
python test_download_ipfs.py

# 3. Test full prediction flow
python test_api.py

# 4. Clear model cache
rm -rf model_cache/*
```

---

## Troubleshooting

### "Pinata credentials not configured"
- Make sure you created `.env` file (not `.env.example`)
- Check that `PINATA_API_KEY` and `PINATA_SECRET_KEY` are set
- No quotes needed: `PINATA_API_KEY=abc123`

### "Upload failed"
- Check your Pinata API key permissions
- Verify you have free space (free tier: 1GB)
- Check internet connection

### "Download failed"
- Try waiting a few minutes (IPFS propagation)
- Model will try multiple gateways automatically
- Check the IPFS hash is correct in `models_registry.json`

### "Model not found in registry"
- Check `models_registry.json` exists
- Verify model ID matches exactly
- Run `python upload_to_ipfs.py` to add brain tumor model

---

## Next Steps

1. ✅ Upload brain tumor model to IPFS
2. ✅ Test download and loading
3. 🔄 Update main.py with new endpoints (coming next)
4. 🔄 Create frontend upload page
5. 🔄 Add MetaMask wallet integration

---

## Security Notes

- ⚠️ Never commit `.env` file to git (already in .gitignore)
- ⚠️ IPFS files are **public** - anyone with the hash can download
- ⚠️ For private models, encrypt before uploading
- ⚠️ Validate all user uploads before processing

---

## Cost Considerations

**Pinata Free Tier:**
- 1GB storage
- Unlimited requests
- 3 gateways

**Upgrade if needed:**
- Picnic Plan: $20/month (100GB)
- Enterprise: Custom pricing

**Alternative gateways:**
- IPFS.io (free but slower)
- Cloudflare (free)
- Self-hosted IPFS node (free but complex)
