# Decentralized AI Marketplace (DAMM)

Decentralized AI marketplace with:
- Modular FastAPI backend for IPFS uploads, prediction, and proposal flows.
- Solidity smart contracts (`ModelRegistry` + `ModelLicense`) for registration, NFT licensing, and usage metering.
- Vanilla frontend (HTML/CSS/JS) with MetaMask + ethers.js integration.

## Architecture
- **Backend:** Modularized Python application under `backend/`.
- **Contracts:** Ethereum smart contracts using Hardhat under `contracts/`.
- **Frontend:** Modular static website under `frontend/` containing `pages/`, `css/` and `js/`.

## Project Structure
- `backend/`
  - `main.py` - Thin FastAPI initialization and route registration.
  - `config.py` - Environment definitions, config constants and smart contract ABIs.
  - `database.py` - PostgreSQL logic and CRUD operations for models, proposals, licenses.
  - `blockchain.py` - Web3 interaction and EIP-191 signature validations.
  - `ipfs.py` - Pinata integration and background model upload pipelines.
  - `utils.py` - Core utilities handling data parsing, lookups and JSON storage fallbacks.
  - `routes/` - Individual modules for API routing.
- `contracts/` 
  - `contracts/ModelLicense.sol` & `ModelRegistry.sol`.
  - Deployment scripts and configurations.
- `frontend/`
  - `index.html` - Hub page showing available marketplace models.
  - `pages/` - Inner dashboards/views (Upload, My Space, Predict, Contribute, etc.).
  - `css/` & `js/` - Minimized styles and dedicated logic controllers mapping to views.

## 1) Backend Setup
```powershell
cd D:\Decenteralized_AI_Marketplace
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Run backend:
```powershell
uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
```
Next, create `.env` under `backend/` with configurations for IPFS matching `.env.example`.

## 2) Frontend Setup
```powershell
cd D:\Decenteralized_AI_Marketplace\frontend
python -m http.server 8080
```

Open: [http://127.0.0.1:8080/index.html](http://127.0.0.1:8080/index.html).
Alternatively, connect it using a live server proxy extension.

## 3) Smart Contract configuration

### Prerequisites
- MetaMask test wallet with Sepolia ETH
- Configured Sepolia RPC URL (Infura/Alchemy/etc)

Configure `contracts/.env`:
```env
SEPOLIA_RPC_URL=https://sepolia.infura.io/v3/YOUR_PROJECT_ID
DEPLOYER_PRIVATE_KEY=YOUR_64_HEX_PRIVATE_KEY
```

Configure `backend/.env` for usage metering:
```env
WEB3_RPC_URL=https://sepolia.infura.io/v3/YOUR_PROJECT_ID
MODEL_LICENSE_ADDRESS=0xYOUR_MODEL_LICENSE_CONTRACT
BACKEND_SIGNER_PRIVATE_KEY=YOUR_64_HEX_PRIVATE_KEY
MODEL_LICENSE_MAX_USE_GAS=250000
MODEL_LICENSE_TX_TIMEOUT=180
```

Compile and Deploy:
```powershell
cd contracts
npm install
npx hardhat run scripts/deploy.js --network sepolia
```
Deployed configuration output gets automatically populated to `frontend/js/contract-config.js` logic mappings and `deployment.json`. 

## Market Runtime Flow
1. **Upload:** Creator uploads model file, thumbnail & metadata from `upload.html`.
2. **IPFS Pin:** Backend securely propagates file assets and model binary to Pinata nodes.
3. **Registry:** Meta is stored within backend JSON/DB nodes, syncing visible states to `index.html`.
4. **License (NFT):** Buyers connect wallets and trigger `ModelLicense` mints tied uniquely to model IPFS signatures and token constraints.
5. **Inference Execution:** Users run predictions. Backend filters out invalid signers lacking minted NFT IDs.
6. **Billing Updates:** A successful AI generation records network consumption on-chain preventing overuse via `usedCount >= maxUses`.

## Key API Features
- **Creator Endpoints:** `PATCH /api/models/{model_id}` & `DELETE /api/models/{model_id}` (Using Wallet Signatures) via the dashboard My Space.
- **Inference Checkpoints:** `POST /api/models/{model_id}/predict` and the vision variant `/predict-image`.
- **Licensing Routes:** Standardized `/license-status` parsing mapped properly to wallets mappings internally.
