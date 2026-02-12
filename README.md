# 🧠 DAMM - Decentralized AI Model Marketplace

A decentralized marketplace for AI models with IPFS storage, enabling creators to upload, share, and monetize their trained models.

## 🌟 Features

### Phase 1: Core Functionality ✅
- ✅ FastAPI backend with TensorFlow model serving
- ✅ Next.js frontend marketplace with TypeScript
- ✅ Brain tumor segmentation using U-Net (BraTS 2020 dataset)
- ✅ Real-time prediction with MRI image upload
- ✅ Model performance statistics and visualization

### Phase 2: IPFS Integration ✅
- ✅ Upload models to IPFS via Pinata
- ✅ Decentralized model storage with content addressing
- ✅ Dynamic model loading from IPFS
- ✅ Local model caching system
- ✅ Multiple IPFS gateway fallback
- ✅ MetaMask wallet integration
- ✅ Model registry (JSON-based)

### Phase 3: Coming Soon 🚧
- ⏳ Smart contracts for ownership
- ⏳ Subscription/pay-per-use payments
- ⏳ Model reputation system

## 🏗️ Architecture

```
DAMM
├── backend/                 # FastAPI Python backend
│   ├── main.py             # API endpoints (IPFS-enabled)
│   ├── ipfs_service.py     # IPFS upload/download via Pinata
│   ├── model_manager.py    # Dynamic model loading & caching
│   ├── models_registry.json # Model metadata registry
│   ├── model_cache/        # Local cache for IPFS models
│   ├── .env                # Pinata credentials (create from .env.example)
│   └── unet_brain_tumor_final.keras # Brain tumor model
│
└── frontend/               # Next.js React frontend
    ├── pages/
    │   ├── index.tsx       # Marketplace (dynamic from IPFS)
    │   ├── upload.tsx      # Model upload page (NEW)
    │   └── models/[id].tsx # Model details
    └── components/         # React components
```

## Tech Stack## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- **Pinata account** ([Sign up free](https://app.pinata.cloud))
- MetaMask browser extension

### 1. Backend Setup

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Configure Pinata credentials
cp .env.example .env
# Edit .env and add your PINATA_API_KEY and PINATA_SECRET_KEY
```

**Get Pinata API Keys:**
1. Go to https://app.pinata.cloud
2. Navigate to **API Keys** → **New Key**
3. Enable `pinFileToIPFS` and `pinJSONToIPFS`
4. Copy API Key & Secret to `.env`

### 2. Upload Brain Tumor Model to IPFS

```bash
python upload_to_ipfs.py
```

This uploads the model and updates the registry with its IPFS hash.

### 3. Start Backend

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Backend at: http://localhost:8000  
API docs: http://localhost:8000/docs

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend at: http://localhost:3000

## 📡 API Endpoints

### IPFS-Enabled Endpoints

#### List Models (from registry)
```http
GET /api/models
```

Returns all models with IPFS hashes and gateway URLs.

#### Upload New Model to IPFS
```http
POST /api/models/upload
Content-Type: multipart/form-data

{
  "file": <model_file>,
  "name": "My Model",
  "description": "...",
  "creator": "0x123...",      # Your wallet address
  "model_type": "keras",
  "category": "Medical Imaging",
  "price_monthly": 49.99
}
```

Response:
```json
{
  "success": true,
  "model_id": "my-model-abc123",
  "ipfs_hash": "QmXx...xyz",
  "gateway_url": "https://gateway.pinata.cloud/ipfs/QmXx...xyz"
}
```

#### Make Prediction (auto-downloads from IPFS if needed)
```http
POST /api/predict

{
  "file": <image_file>,
  "model_id": "brain-tumor-unet"
}
```

Response includes `model_source`: `"ipfs"`, `"cache"`, or `"memory"`

## 🎨 Frontend Features

### Marketplace (`/`)
- Dynamic model list from registry
- IPFS hash display
- Creator wallet addresses
- "View on IPFS" button (📡)

### Upload Page (`/upload`)
- MetaMask wallet connection
- Model file upload (.keras, .h5, .pkl, .pt)
- Metadata form (name, description, pricing)
- Upload to IPFS via Pinata
- View IPFS hash & gateway URL

### Model Details (`/models/[id]`)
- Upload MRI for prediction
- View segmentation results
- IPFS gateway links
- Performance charts

## 🧪 Testing

```bash
cd backend

# Test IPFS upload
python upload_to_ipfs.py

# Test IPFS download & model loading
python test_download_ipfs.py

# Test prediction
python test_predict.py

# Clear model cache
rm -rf model_cache/
```

## 🛠️ Tech Stack

### Backend
- **FastAPI** - API framework
- **TensorFlow 2.15** - Model serving
- **Pinata SDK** - IPFS uploads
- **python-dotenv** - Environment variables
- **requests** - IPFS gateway downloads

### Frontend
- **Next.js 14** - React framework
- **TypeScript 5** - Type safety
- **Tailwind CSS 3** - Styling
- **Recharts** - Visualizations
- **MetaMask** - Wallet integration

### IPFS
- **Pinata** - IPFS pinning service
- **Multiple gateways** - Pinata, ipfs.io, Cloudflare

## 📊 Brain Tumor Model Details

- **Architecture**: U-Net 2D
- **Dataset**: BraTS 2020 (368 patients, 57,040 slices)
- **Performance**: 99.77% validation accuracy, 94.27% Dice coefficient
- **Input**: 128x128 grayscale MRI
- **Parameters**: 7.7M
- **IPFS Hash**: Check `models_registry.json` after upload

## 🔧 Configuration

### Backend `.env`
```bash
PINATA_API_KEY=your_api_key
PINATA_SECRET_KEY=your_secret_key
IPFS_GATEWAY=https://gateway.pinata.cloud
MODEL_CACHE_DIR=./model_cache
```

## 🐛 Troubleshooting

**"Pinata credentials not configured"**
- Create `.env` file from `.env.example`
- Add valid Pinata API keys

**"Upload failed"**
- Check Pinata API key permissions
- Verify free space (free tier: 1GB)

**"Download failed from IPFS"**
- Wait a few minutes (IPFS propagation)
- System tries multiple gateways automatically

**MetaMask not detected**
- Install MetaMask extension
- Refresh page

## 🗺️ Roadmap

✅ **Phase 1**: Core marketplace  
✅ **Phase 2**: IPFS integration  
🚧 **Phase 3**: Smart contracts & payments  
📅 **Phase 4**: Advanced features (versioning, ratings)

## 📄 License

MIT License

---

**For detailed IPFS setup instructions, see [backend/IPFS_SETUP.md](backend/IPFS_SETUP.md)**

## Future Enhancements

- [ ] Blockchain integration for subscriptions
- [ ] User authentication and authorization
- [ ] Model versioning and A/B testing
- [ ] Batch prediction API
- [ ] Model performance monitoring
- [ ] Support for multiple AI models
- [ ] Payment gateway integration

## License

MIT

## Contributing

Pull requests are welcome. For major changes, please open an issue first.
```
