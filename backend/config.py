"""
Centralized configuration — environment variables, paths, and constants.
"""
from pathlib import Path
from dotenv import load_dotenv
import os
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = BASE_DIR / "models_registry.json"
DOWNLOADED_MODELS_DIR = BASE_DIR / "downloaded_models"
PROPOSALS_PATH = BASE_DIR / "proposals_registry.json"

load_dotenv(BASE_DIR / ".env")

# ── Pinata / IPFS ──────────────────────────────────────────────
PINATA_API_KEY = os.getenv("PINATA_API_KEY", "").strip()
PINATA_SECRET_KEY = os.getenv("PINATA_SECRET_KEY", "").strip()
IPFS_GATEWAY = os.getenv("IPFS_GATEWAY", "https://gateway.pinata.cloud/ipfs/").strip()
PINATA_FILE_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
PINATA_JSON_URL = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
PINATA_CONNECT_TIMEOUT = int(os.getenv("PINATA_CONNECT_TIMEOUT", "30"))
PINATA_READ_TIMEOUT = int(os.getenv("PINATA_READ_TIMEOUT", "600"))
PINATA_UPLOAD_RETRIES = int(os.getenv("PINATA_UPLOAD_RETRIES", "2"))

# ── Database ───────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# ── Web3 / Blockchain ─────────────────────────────────────────
WEB3_RPC_URL = os.getenv("WEB3_RPC_URL", "").strip()
MODEL_LICENSE_ADDRESS = os.getenv("MODEL_LICENSE_ADDRESS", "").strip()
MODEL_LICENSE_MAX_USE_GAS = int(os.getenv("MODEL_LICENSE_MAX_USE_GAS", "250000"))
MODEL_LICENSE_TX_TIMEOUT = int(os.getenv("MODEL_LICENSE_TX_TIMEOUT", "180"))
BACKEND_SIGNER_PRIVATE_KEY = os.getenv("BACKEND_SIGNER_PRIVATE_KEY", "").strip()

# ── CORS ───────────────────────────────────────────────────────
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:8001,http://localhost:8001,http://127.0.0.1:8080,http://localhost:8080,http://[::1]:8080",
    ).split(",")
    if origin.strip()
]

# ── Smart-contract ABI (minimal subset) ───────────────────────
MODEL_LICENSE_ABI_MIN = [
    {
        "inputs": [{"internalType": "uint256", "name": "_tokenId", "type": "uint256"}],
        "name": "getLicenseStatus",
        "outputs": [
            {"internalType": "string", "name": "modelId", "type": "string"},
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "uint256", "name": "maxUses", "type": "uint256"},
            {"internalType": "uint256", "name": "usedCount", "type": "uint256"},
            {"internalType": "bool", "name": "expired", "type": "bool"},
            {"internalType": "string", "name": "metadataUri", "type": "string"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "_tokenId", "type": "uint256"},
            {"internalType": "address", "name": "_wallet", "type": "address"},
            {"internalType": "string", "name": "_modelId", "type": "string"},
        ],
        "name": "isLicenseUsable",
        "outputs": [
            {"internalType": "bool", "name": "usable", "type": "bool"},
            {"internalType": "string", "name": "reason", "type": "string"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "_tokenId", "type": "uint256"}],
        "name": "recordUse",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# ── Task I/O defaults ─────────────────────────────────────────
TASK_IO_DEFAULTS: Dict[str, Dict[str, str]] = {
    "Classification": {"input_type": "Image tensor", "output_type": "Class probabilities"},
    "Regression": {"input_type": "Tabular features (numeric/text)", "output_type": "Single continuous numeric value"},
    "Object Detection": {"input_type": "Image tensor", "output_type": "Bounding boxes + class scores"},
    "Segmentation": {"input_type": "Image tensor", "output_type": "Pixel-wise mask"},
    "Text Generation": {"input_type": "Prompt text", "output_type": "Generated text"},
    "Text Classification": {"input_type": "Text string", "output_type": "Class probabilities"},
    "Machine Translation": {"input_type": "Source text", "output_type": "Translated text"},
    "Speech Recognition": {"input_type": "Audio waveform/features", "output_type": "Transcribed text"},
    "Image Generation": {"input_type": "Noise vector / condition", "output_type": "Generated image"},
    "Text-to-Image": {"input_type": "Prompt text", "output_type": "Generated image"},
    "Question Answering": {"input_type": "Question + context text", "output_type": "Answer span/text"},
    "Recommendation": {"input_type": "User/item features", "output_type": "Ranked item scores"},
    "Forecasting": {"input_type": "Time-series window", "output_type": "Future value(s)"},
}
