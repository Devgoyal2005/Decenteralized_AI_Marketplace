# 🚀 New API Endpoints Reference

## Model Management

### 📝 Edit Model (Owner Only)
```http
PUT /api/models/{model_id}
Content-Type: multipart/form-data

wallet_address: string (required)
name: string (optional)
description: string (optional)
category: string (optional)
price_per_hour: float (optional)
payment_currency: string (optional) [ETH, BTC, USDC, DAI, MATIC]
tags: string (optional, comma-separated)
accuracy: float (optional)
```

**Response:**
```json
{
  "success": true,
  "message": "Model updated successfully",
  "model": { /* updated model data */ }
}
```

**Errors:**
- 404: Model not found
- 403: Only the model owner can edit this model

---

### 🗑️ Delete Model (Owner Only)
```http
DELETE /api/models/{model_id}
Content-Type: multipart/form-data

wallet_address: string (required)
```

**Response:**
```json
{
  "success": true,
  "message": "Model 'Brain Tumor U-Net' deleted successfully"
}
```

**What it does:**
- Unpins from Pinata
- Removes from registry
- Deletes cached file
- Cannot be undone

**Errors:**
- 404: Model not found  
- 403: Only the model owner can delete this model

---

### 🛒 Purchase Model
```http
POST /api/models/{model_id}/purchase
Content-Type: multipart/form-data

wallet_address: string (required)
```

**Response:**
```json
{
  "success": true,
  "message": "Model 'Brain Tumor U-Net' purchased successfully",
  "model_id": "brain-tumor-unet",
  "cached": true,
  "pricing": {
    "per_hour": 0.005,
    "currency": "ETH"
  }
}
```

**What it does:**
- Downloads model from IPFS to local cache
- Increments download counter
- Model becomes available for predictions
- For now: FREE (payment integration later)

**Errors:**
- 404: Model not found
- 500: Failed to download model

---

### 📤 Upload Model (Updated)
```http
POST /api/models/upload
Content-Type: multipart/form-data

file: binary (required)
name: string (required)
description: string (required)
creator: string (required, wallet address)
model_type: string (optional) [keras, pytorch, sklearn]
category: string (optional)
price_per_hour: float (optional)  👈 NEW
payment_currency: string (optional)  👈 NEW [ETH, BTC, USDC, DAI, MATIC]
input_shape: string (optional, comma-separated)
output_shape: string (optional, comma-separated)
tags: string (optional, comma-separated)
accuracy: float (optional)
```

**Response:**
```json
{
  "success": true,
  "model_id": "brain-tumor-unet-a1b2c3d4",
  "ipfs_hash": "QmXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "gateway_url": "https://amethyst-sophisticated-macaw-961.mypinata.cloud/ipfs/QmXXXX...",
  "message": "Model 'Brain Tumor U-Net' uploaded successfully"
}
```

---

### 🔮 Predict (Enhanced)
```http
POST /api/predict
Content-Type: multipart/form-data

file: binary (required, image file)
model_id: string (optional, default: "brain-tumor-unet")
```

**Response:**
```json
{
  "success": true,
  "model_id": "brain-tumor-unet",
  "model_source": "cache",
  "prediction": {
    "mask": [[0, 0, 1, ...], ...],
    "mask_image": "data:image/png;base64,iVBORw0KGgo...",  👈 NEW
    "overlay_image": "data:image/png;base64,iVBORw0KGgo...",  👈 NEW
    "tumor_detected": true,
    "tumor_percentage": 12.45,
    "confidence": 0.9876,
    "image_size": [128, 128]
  }
}
```

**New Fields:**
- `mask_image`: Base64-encoded PNG of binary segmentation mask
- `overlay_image`: Base64-encoded PNG with red tumor overlay on original

**Display in HTML:**
```html
<img src="${prediction.mask_image}" alt="Segmentation Mask" />
<img src="${prediction.overlay_image}" alt="Tumor Overlay" />
```

---

### 🧹 Admin: Cleanup Pinata
```http
POST /api/admin/cleanup-pinata
Content-Type: multipart/form-data

confirm: boolean (required, must be true)
```

**Response:**
```json
{
  "success": true,
  "message": "Cleaned up Pinata storage",
  "unpinned_count": 5,
  "failed_count": 0,
  "failed_hashes": []
}
```

**What it does:**
- Lists all pinned files on Pinata
- Unpins each one
- Returns success/failure counts

**⚠️ WARNING:** This removes ALL files from Pinata. Cannot be undone.

---

## Model Pricing Structure (NEW)

### Old Format (Deprecated):
```json
{
  "pricing": {
    "monthly": 49.99,
    "yearly": 499.99
  }
}
```

### New Format:
```json
{
  "pricing": {
    "per_hour": 0.005,
    "currency": "ETH"
  }
}
```

### Supported Cryptocurrencies:
- `ETH` - Ethereum
- `BTC` - Bitcoin
- `USDC` - USD Coin (stablecoin)
- `DAI` - DAI (stablecoin)
- `MATIC` - Polygon

---

## Frontend Purchase Tracking

### Save Purchase (localStorage):
```javascript
localStorage.setItem(`purchased_${modelId}`, 'true')
```

### Check Purchase:
```javascript
const isPurchased = localStorage.getItem(`purchased_${modelId}`) === 'true'
```

### Future: Blockchain
Will be replaced with smart contract in Phase 3

---

## Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (missing required fields) |
| 403 | Forbidden (not the owner) |
| 404 | Model not found |
| 500 | Server error |
| 503 | Service unavailable (model not loaded) |

---

## Testing Workflow

### 1. Start Backend
```bash
cd backend
uvicorn main:app --reload
```

### 2. Start Frontend
```bash
cd frontend
npm run dev
```

### 3. Test Upload
- Go to http://localhost:3000/upload
- Connect MetaMask
- Fill form with per-hour pricing
- Select cryptocurrency
- Upload model

### 4. Test Buy
- Go to model details page
- Connect wallet (any address)
- Click "Buy Model"
- Verify localStorage has purchase record
- Try prediction (should work now)

### 5. Test Edit (Owner Only)
- Connect wallet that matches model creator
- Click "Edit" button
- Modify fields
- Click "Save"
- Verify changes

### 6. Test Delete (Owner Only)
- Connect owner wallet
- Click "Edit" → "Delete"
- Confirm deletion
- Verify model removed from:
  - Frontend marketplace
  - `models_registry.json`
  - Pinata (unpinned)
  - Local cache

---

## Example: Complete Purchase Flow

```javascript
// 1. User clicks "Buy Model"
const handleBuy = async () => {
  // Connect wallet
  const accounts = await window.ethereum.request({ 
    method: 'eth_requestAccounts' 
  })
  
  // Purchase
  const formData = new FormData()
  formData.append('wallet_address', accounts[0])
  
  const response = await fetch(
    `http://localhost:8000/api/models/brain-tumor-unet/purchase`,
    { method: 'POST', body: formData }
  )
  
  const result = await response.json()
  
  if (result.success) {
    // Save to localStorage
    localStorage.setItem('purchased_brain-tumor-unet', 'true')
    alert('Model purchased!')
  }
}

// 2. User uploads image for prediction
const handlePredict = async () => {
  // Check if purchased
  const isPurchased = localStorage.getItem('purchased_brain-tumor-unet')
  if (!isPurchased) {
    alert('Please purchase this model first!')
    return
  }
  
  // Make prediction
  const formData = new FormData()
  formData.append('file', imageFile)
  formData.append('model_id', 'brain-tumor-unet')
  
  const response = await fetch(
    'http://localhost:8000/api/predict',
    { method: 'POST', body: formData }
  )
  
  const result = await response.json()
  
  // Display segmentation images
  document.getElementById('mask').src = result.prediction.mask_image
  document.getElementById('overlay').src = result.prediction.overlay_image
}
```

---

**Last Updated:** February 13, 2026  
**Version:** 2.0 - IPFS Integration with Purchase System
