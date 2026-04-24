from fastapi import FastAPI, File, Form, HTTPException, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import os
import uuid
import time
import math
import hashlib
import secrets
import requests
from requests import RequestException
import psycopg2
from psycopg2.extras import RealDictCursor  
from web3 import Web3
from eth_account import Account

BASE_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = BASE_DIR / "models_registry.json"
DOWNLOADED_MODELS_DIR = BASE_DIR / "downloaded_models"
PROPOSALS_PATH = BASE_DIR / "proposals_registry.json"

load_dotenv(BASE_DIR / ".env")

PINATA_API_KEY = os.getenv("PINATA_API_KEY", "").strip()
PINATA_SECRET_KEY = os.getenv("PINATA_SECRET_KEY", "").strip()
IPFS_GATEWAY = os.getenv("IPFS_GATEWAY", "https://gateway.pinata.cloud/ipfs/").strip()

PINATA_FILE_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
PINATA_JSON_URL = "https://api.pinata.cloud/pinning/pinJSONToIPFS"

PINATA_CONNECT_TIMEOUT = int(os.getenv("PINATA_CONNECT_TIMEOUT", "30"))
PINATA_READ_TIMEOUT = int(os.getenv("PINATA_READ_TIMEOUT", "600"))
PINATA_UPLOAD_RETRIES = int(os.getenv("PINATA_UPLOAD_RETRIES", "2"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
WEB3_RPC_URL = os.getenv("WEB3_RPC_URL", "").strip()
MODEL_LICENSE_ADDRESS = os.getenv("MODEL_LICENSE_ADDRESS", "").strip()
MODEL_LICENSE_MAX_USE_GAS = int(os.getenv("MODEL_LICENSE_MAX_USE_GAS", "250000"))
MODEL_LICENSE_TX_TIMEOUT = int(os.getenv("MODEL_LICENSE_TX_TIMEOUT", "180"))
BACKEND_SIGNER_PRIVATE_KEY = os.getenv("BACKEND_SIGNER_PRIVATE_KEY", "").strip()
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:8001,http://localhost:8001,http://127.0.0.1:8080,http://localhost:8080,http://[::1]:8080",
    ).split(",")
    if origin.strip()
]

app = FastAPI(title="Model Upload API", version="1.0.0")

jobs: Dict[str, Dict[str, Any]] = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_init() -> None:
    try:
        _init_models_table()
    except Exception as exc:
        print(f"[WARN] Failed to initialize DB table models_registry: {exc}")
    try:
        _init_proposals_table()
    except Exception as exc:
        print(f"[WARN] Failed to initialize DB table proposals_registry: {exc}")
    try:
        _init_nft_licenses_table()
    except Exception as exc:
        print(f"[WARN] Failed to initialize DB table nft_licenses: {exc}")
    try:
        _bootstrap_json_registries_to_db()
    except Exception as exc:
        print(f"[WARN] Failed to bootstrap JSON registries into DB: {exc}")


def _ensure_registry() -> None:
    if not REGISTRY_PATH.exists():
        REGISTRY_PATH.write_text(json.dumps({"models": []}, indent=2), encoding="utf-8")


def _read_registry() -> Dict[str, Any]:
    _ensure_registry()
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _write_registry(registry: Dict[str, Any]) -> None:
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def _ensure_downloads_dir() -> None:
    DOWNLOADED_MODELS_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_proposals_registry() -> None:
    if not PROPOSALS_PATH.exists():
        PROPOSALS_PATH.write_text(json.dumps({"proposals": []}, indent=2), encoding="utf-8")


def _read_proposals_registry() -> Dict[str, Any]:
    _ensure_proposals_registry()
    return json.loads(PROPOSALS_PATH.read_text(encoding="utf-8"))


def _write_proposals_registry(registry: Dict[str, Any]) -> None:
    PROPOSALS_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def _find_model_index(models: List[Dict[str, Any]], model_id: str) -> int:
    for idx, model in enumerate(models):
        if str(model.get("id", "")) == model_id:
            return idx
    return -1


def _model_extension(file_name: str) -> str:
    suffix = Path(file_name).suffix.strip()
    return suffix if suffix else ".bin"


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


def _normalized_private_key(raw: str) -> str:
    key = (raw or "").strip()
    if not key:
        return ""
    with_prefix = key if key.startswith("0x") else f"0x{key}"
    return with_prefix if len(with_prefix) == 66 else ""


def _get_model_license_contract():
    if not WEB3_RPC_URL:
        raise HTTPException(status_code=500, detail="WEB3_RPC_URL is not configured")
    if not MODEL_LICENSE_ADDRESS:
        raise HTTPException(status_code=500, detail="MODEL_LICENSE_ADDRESS is not configured")

    w3 = Web3(Web3.HTTPProvider(WEB3_RPC_URL, request_kwargs={"timeout": MODEL_LICENSE_TX_TIMEOUT}))
    if not w3.is_connected():
        raise HTTPException(status_code=502, detail="Unable to connect to WEB3_RPC_URL")
    if not Web3.is_address(MODEL_LICENSE_ADDRESS):
        raise HTTPException(status_code=500, detail="MODEL_LICENSE_ADDRESS is invalid")

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(MODEL_LICENSE_ADDRESS),
        abi=MODEL_LICENSE_ABI_MIN,
    )
    return w3, contract


def _verify_license_for_model(model_id: str, wallet_address: str, token_id: int) -> Dict[str, Any]:
    w3, contract = _get_model_license_contract()

    if not Web3.is_address(wallet_address):
        raise HTTPException(status_code=400, detail="wallet_address is invalid")

    try:
        usable, reason = contract.functions.isLicenseUsable(
            int(token_id), Web3.to_checksum_address(wallet_address), model_id
        ).call()
        if not usable:
            raise HTTPException(status_code=403, detail=f"License not usable: {reason}")

        status = contract.functions.getLicenseStatus(int(token_id)).call()
        # Check if the license owner is the zero address, which indicates non-existence
        if str(status[1]) == "0x0000000000000000000000000000000000000000":
            raise HTTPException(status_code=404, detail="License does not exist")
    except HTTPException:
        raise
    except Exception as exc:
        # Check if the error message indicates the token does not exist
        if "invalid token ID" in str(exc) or "URI query for nonexistent token" in str(exc):
            raise HTTPException(status_code=404, detail="License does not exist")
        raise HTTPException(status_code=502, detail=f"Failed to verify license on-chain: {exc}")

    return {
        "model_id": str(status[0]),
        "owner": str(status[1]),
        "max_uses": int(status[2]),
        "used_count": int(status[3]),
        "expired": bool(status[4]),
        "metadata_uri": str(status[5]),
    }


def _record_license_use_on_chain(token_id: int) -> str:
    normalized_key = _normalized_private_key(BACKEND_SIGNER_PRIVATE_KEY)
    if not normalized_key:
        raise HTTPException(status_code=500, detail="BACKEND_SIGNER_PRIVATE_KEY is not configured")

    w3, contract = _get_model_license_contract()
    account = Account.from_key(normalized_key)

    try:
        nonce = w3.eth.get_transaction_count(account.address, "pending")
        tx = contract.functions.recordUse(int(token_id)).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": MODEL_LICENSE_MAX_USE_GAS,
                "gasPrice": w3.eth.gas_price,
                "chainId": w3.eth.chain_id,
            }
        )

        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=MODEL_LICENSE_TX_TIMEOUT)
        if receipt.status != 1:
            raise HTTPException(status_code=502, detail="recordUse transaction reverted")
        return tx_hash.hex()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to record license usage on-chain: {exc}")


def _find_model_by_id(model_id: str) -> Optional[Dict[str, Any]]:
    models = _get_all_models()
    idx = _find_model_index(models, model_id)
    if idx < 0:
        return None
    return models[idx]


def _ensure_model_downloaded(model: Dict[str, Any]) -> str:
    ipfs_hash = str(model.get("ipfs_hash", "")).strip()
    gateway_url = str(model.get("gateway_url", "")).strip()
    if not ipfs_hash or not gateway_url:
        raise HTTPException(status_code=400, detail="Model IPFS details are missing")

    _ensure_downloads_dir()
    extension = _model_extension(str(model.get("file_name", "model.bin")))
    local_path = DOWNLOADED_MODELS_DIR / f"{ipfs_hash}{extension}"

    if not local_path.exists():
        try:
            with requests.get(gateway_url, stream=True, timeout=(30, 300)) as response:
                if response.status_code >= 300:
                    raise HTTPException(status_code=502, detail=f"Failed to download model from IPFS: {response.text}")
                with local_path.open("wb") as out_file:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            out_file.write(chunk)
        except RequestException as exc:
            raise HTTPException(status_code=504, detail=f"Network error while downloading model: {str(exc)}")

    model["local_model_path"] = str(local_path)
    model["downloaded_at"] = datetime.utcnow().isoformat() + "Z"
    _save_model_record(model)
    return str(local_path)


def _generate_runtime_passkey() -> str:
    return secrets.token_urlsafe(12)


def _public_model_view(model: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = dict(model)
    sanitized.pop("runtime_passkey", None)
    return sanitized


def _recompute_proposal_acceptance(proposals: List[Dict[str, Any]]) -> None:
    max_upvotes = max((int(p.get("upvotes", 0)) for p in proposals), default=0)
    for proposal in proposals:
        proposal["accepted"] = bool(max_upvotes > 0 and int(proposal.get("upvotes", 0)) == max_upvotes)


def _normalized_database_url() -> str:
    if not DATABASE_URL:
        return ""
    # Tolerate a common typo in copied Neon URLs without altering valid values.
    url = DATABASE_URL
    url = url.replace("channel_binding=requir&", "channel_binding=require&")
    if url.endswith("channel_binding=requir"):
        url = f"{url[:-len('channel_binding=requir')]}channel_binding=require"
    return url


def _db_available() -> bool:
    return bool(_normalized_database_url())


def _get_db_connection():
    db_url = _normalized_database_url()
    if not db_url:
        return None
    return psycopg2.connect(db_url)


def _init_passkeys_table() -> None:
    conn = _get_db_connection()
    if conn is None:
        return

    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS model_passkeys (
                    id BIGSERIAL PRIMARY KEY,
                    model_id TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    model_owner TEXT,
                    buyer TEXT NOT NULL,
                    passkey TEXT NOT NULL,
                    purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (model_id, passkey)
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_model_passkeys_model_id
                ON model_passkeys(model_id);
                """
            )
    conn.close()


def _init_nft_licenses_table() -> None:
    """Create the nft_licenses table: wallet_address + model_id → nft_token_id mapping."""
    conn = _get_db_connection()
    if conn is None:
        return
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS nft_licenses (
                    id BIGSERIAL PRIMARY KEY,
                    wallet_address TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    model_name TEXT NOT NULL DEFAULT '',
                    nft_token_id BIGINT,
                    metadata_ipfs_hash TEXT NOT NULL DEFAULT '',
                    metadata_uri TEXT NOT NULL DEFAULT '',
                    local_model_path TEXT NOT NULL DEFAULT '',
                    purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (wallet_address, model_id)
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_nft_licenses_wallet
                ON nft_licenses(wallet_address);
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_nft_licenses_model
                ON nft_licenses(model_id);
                """
            )
    conn.close()


def _store_nft_license_in_db(
    *,
    wallet_address: str,
    model_id: str,
    model_name: str,
    nft_token_id: Optional[int],
    metadata_ipfs_hash: str,
    metadata_uri: str,
    local_model_path: str,
) -> None:
    """Upsert a wallet→model NFT license record into Neon DB."""
    conn = _get_db_connection()
    if conn is None:
        return
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO nft_licenses
                    (wallet_address, model_id, model_name, nft_token_id,
                     metadata_ipfs_hash, metadata_uri, local_model_path, purchased_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (wallet_address, model_id) DO UPDATE SET
                    nft_token_id        = EXCLUDED.nft_token_id,
                    metadata_ipfs_hash  = EXCLUDED.metadata_ipfs_hash,
                    metadata_uri        = EXCLUDED.metadata_uri,
                    local_model_path    = EXCLUDED.local_model_path,
                    purchased_at        = NOW();
                """,
                (
                    wallet_address.lower(),
                    model_id,
                    model_name,
                    nft_token_id,
                    metadata_ipfs_hash,
                    metadata_uri,
                    local_model_path,
                ),
            )
    conn.close()


def _get_nft_license_from_db(wallet_address: str, model_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a stored NFT license record for a given wallet + model."""
    conn = _get_db_connection()
    if conn is None:
        return None
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT wallet_address, model_id, model_name, nft_token_id,
                           metadata_ipfs_hash, metadata_uri, local_model_path, purchased_at
                    FROM nft_licenses
                    WHERE wallet_address = %s AND model_id = %s
                    LIMIT 1;
                    """,
                    (wallet_address.lower(), model_id),
                )
                row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return dict(row)
    except Exception:
        conn.close()
        return None


def _resolve_license(wallet_address: str, model_id: str) -> Optional[Dict[str, Any]]:
    """
    Unified license resolver — checks nft_licenses first (new system),
    then falls back to model_passkeys (legacy buyers who purchased before
    the nft_licenses table was introduced).
    Returns a normalised dict with at least: wallet_address, model_id, nft_token_id.
    Returns None if no purchase record exists at all.
    """
    # 1. New system: nft_licenses table
    record = _get_nft_license_from_db(wallet_address, model_id)
    if record:
        return record

    # 2. Legacy fallback: model_passkeys table
    conn = _get_db_connection()
    if conn is None:
        return None
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT model_id, model_name, model_owner, buyer, passkey, purchased_at
                    FROM model_passkeys
                    WHERE model_id = %s AND LOWER(buyer) = LOWER(%s)
                    LIMIT 1;
                    """,
                    (model_id, wallet_address),
                )
                row = cur.fetchone()
        conn.close()
        if not row:
            return None

        # Backfill into nft_licenses so future calls hit the fast path
        legacy = dict(row)
        print(f"[INFO] Backfilling legacy buyer {wallet_address} for model {model_id} into nft_licenses")
        _store_nft_license_in_db(
            wallet_address=wallet_address,
            model_id=model_id,
            model_name=str(legacy.get("model_name", "")),
            nft_token_id=None,
            metadata_ipfs_hash="",
            metadata_uri="",
            local_model_path="",
        )
        return {
            "wallet_address": wallet_address,
            "model_id": model_id,
            "model_name": legacy.get("model_name", ""),
            "nft_token_id": None,
            "metadata_ipfs_hash": "",
            "metadata_uri": "",
            "local_model_path": "",
            "purchased_at": legacy.get("purchased_at"),
            "legacy": True,
        }
    except Exception as exc:
        print(f"[WARN] Legacy passkey fallback failed: {exc}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _init_models_table() -> None:
    """Create the models_registry table in PostgreSQL if it does not exist."""
    conn = _get_db_connection()
    if conn is None:
        return
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS models_registry (
                    id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    ipfs_hash TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_models_registry_ipfs
                ON models_registry(ipfs_hash);
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_models_registry_ipfs
                ON models_registry(ipfs_hash)
                WHERE ipfs_hash IS NOT NULL AND ipfs_hash <> '';
                """
            )
    conn.close()


def _upsert_model_in_db(model: Dict[str, Any]) -> None:
    """Insert or update a model record in the PostgreSQL models_registry table."""
    conn = _get_db_connection()
    if conn is None:
        return
    model_id = str(model.get("id", "")).strip()
    ipfs_hash = str(model.get("ipfs_hash", "")).strip()
    if not model_id:
        conn.close()
        return
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO models_registry (id, data, ipfs_hash, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    data = EXCLUDED.data,
                    ipfs_hash = EXCLUDED.ipfs_hash,
                    updated_at = NOW();
                """,
                (model_id, json.dumps(model), ipfs_hash),
            )
    conn.close()


def _read_models_from_db() -> Optional[List[Dict[str, Any]]]:
    """Read all models from PostgreSQL. Returns None if DB is unavailable."""
    conn = _get_db_connection()
    if conn is None:
        return None
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT data FROM models_registry ORDER BY updated_at DESC;"
                )
                rows = cur.fetchall()
        conn.close()
        models = []
        for row in rows:
            data = row["data"]
            if isinstance(data, str):
                data = json.loads(data)
            models.append(data)
        return models
    except Exception:
        conn.close()
        return None


def _find_model_by_id_from_db(model_id: str) -> Optional[Dict[str, Any]]:
    conn = _get_db_connection()
    if conn is None:
        return None
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT data FROM models_registry WHERE id = %s LIMIT 1;",
                    (model_id,),
                )
                row = cur.fetchone()
        conn.close()
        if not row:
            return None
        data = row["data"]
        return json.loads(data) if isinstance(data, str) else data
    except Exception:
        conn.close()
        return None


def _find_model_by_ipfs_from_db(ipfs_hash: str) -> Optional[Dict[str, Any]]:
    conn = _get_db_connection()
    if conn is None:
        return None
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT data
                    FROM models_registry
                    WHERE ipfs_hash = %s
                    ORDER BY updated_at DESC
                    LIMIT 1;
                    """,
                    (ipfs_hash,),
                )
                row = cur.fetchone()
        conn.close()
        if not row:
            return None
        data = row["data"]
        return json.loads(data) if isinstance(data, str) else data
    except Exception:
        conn.close()
        return None


def _get_all_models() -> List[Dict[str, Any]]:
    if _db_available():
        db_models = _read_models_from_db()
        if db_models is not None:
            return db_models
    registry = _read_registry()
    return registry.get("models", [])


def _save_model_record(model: Dict[str, Any]) -> None:
    if _db_available():
        _upsert_model_in_db(model)
        return

    registry = _read_registry()
    models = registry.setdefault("models", [])
    model_id = str(model.get("id", "")).strip()
    idx = _find_model_index(models, model_id)
    if idx >= 0:
        models[idx] = model
    else:
        models.append(model)
    registry["models"] = models
    _write_registry(registry)


def _init_proposals_table() -> None:
    conn = _get_db_connection()
    if conn is None:
        return
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS proposals_registry (
                    id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    upvotes INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_proposals_registry_rank
                ON proposals_registry(upvotes DESC, created_at DESC);
                """
            )
    conn.close()


def _insert_proposal_in_db(proposal: Dict[str, Any]) -> None:
    conn = _get_db_connection()
    if conn is None:
        return
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO proposals_registry (id, data, upvotes, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    data = EXCLUDED.data,
                    upvotes = EXCLUDED.upvotes,
                    updated_at = NOW();
                """,
                (
                    str(proposal.get("id", "")).strip(),
                    json.dumps(proposal),
                    int(proposal.get("upvotes", 0)),
                ),
            )
    conn.close()


def _read_proposals_from_db() -> Optional[List[Dict[str, Any]]]:
    conn = _get_db_connection()
    if conn is None:
        return None
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT data
                    FROM proposals_registry
                    ORDER BY upvotes DESC, created_at DESC;
                    """
                )
                rows = cur.fetchall()
        conn.close()
        proposals: List[Dict[str, Any]] = []
        for row in rows:
            data = row["data"]
            if isinstance(data, str):
                data = json.loads(data)
            proposals.append(data)
        return proposals
    except Exception:
        conn.close()
        return None


def _upvote_proposal_in_db(proposal_id: str) -> Optional[Dict[str, Any]]:
    conn = _get_db_connection()
    if conn is None:
        return None
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT data FROM proposals_registry WHERE id = %s LIMIT 1;",
                    (proposal_id,),
                )
                row = cur.fetchone()
                if not row:
                    conn.close()
                    return None

                proposal = row["data"]
                if isinstance(proposal, str):
                    proposal = json.loads(proposal)

                proposal["upvotes"] = int(proposal.get("upvotes", 0)) + 1

                cur.execute(
                    """
                    UPDATE proposals_registry
                    SET data = %s,
                        upvotes = %s,
                        updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (json.dumps(proposal), int(proposal["upvotes"]), proposal_id),
                )
        conn.close()
        return proposal
    except Exception:
        conn.close()
        return None


def _bootstrap_json_registries_to_db() -> None:
    if not _db_available():
        return

    # Backfill models once so existing local JSON data is preserved after DB switch.
    try:
        db_models = _read_models_from_db() or []
        if not db_models:
            local_models = _read_registry().get("models", [])
            for model in local_models:
                _upsert_model_in_db(model)
    except Exception as exc:
        print(f"[WARN] Model bootstrap skipped: {exc}")

    # Backfill proposals once so proposal history is preserved.
    try:
        db_proposals = _read_proposals_from_db() or []
        if not db_proposals:
            local_proposals = _read_proposals_registry().get("proposals", [])
            for proposal in local_proposals:
                _insert_proposal_in_db(proposal)
    except Exception as exc:
        print(f"[WARN] Proposal bootstrap skipped: {exc}")


def _store_passkey_in_db(
    *,
    model_id: str,
    model_name: str,
    model_owner: str,
    buyer: str,
    passkey: str,
) -> None:
    conn = _get_db_connection()
    if conn is None:
        return

    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_passkeys (model_id, model_name, model_owner, buyer, passkey)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (model_id, passkey) DO NOTHING;
                """,
                (model_id, model_name, model_owner, buyer, passkey),
            )
    conn.close()


def _is_passkey_valid_in_db(model_id: str, passkey: str) -> bool:
    conn = _get_db_connection()
    if conn is None:
        return False

    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id
                FROM model_passkeys
                WHERE model_id = %s AND passkey = %s
                LIMIT 1;
                """,
                (model_id, passkey),
            )
            row = cur.fetchone()
    conn.close()
    return bool(row)


def _flatten_to_floats(value: Any) -> List[float]:
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        flat: List[float] = []
        for item in value:
            flat.extend(_flatten_to_floats(item))
        return flat
    raise HTTPException(status_code=400, detail="Input must be numeric or nested numeric arrays")


def _parse_shape_to_ints(shape_values: Any) -> List[int]:
    parsed: List[int] = []
    if not isinstance(shape_values, list):
        return parsed
    for dim in shape_values:
        try:
            parsed.append(int(str(dim).strip()))
        except (TypeError, ValueError):
            continue
    return [d for d in parsed if d > 0]


def _predict_labels(ipfs_hash: str, input_vector: List[float], labels: List[str]) -> Dict[str, float]:
    if not labels:
        return {}

    vector_sum = sum(input_vector)
    raw_scores: List[float] = []
    for idx, _ in enumerate(labels):
        digest = hashlib.sha256(f"{ipfs_hash}:{idx}:{vector_sum:.8f}".encode("utf-8")).hexdigest()
        score = (int(digest[:8], 16) / 0xFFFFFFFF) + 1e-9
        raw_scores.append(score)

    denom = sum(raw_scores) or 1.0
    return {
        label: round(raw_scores[idx] / denom, 6)
        for idx, label in enumerate(labels)
    }


def _pinata_headers() -> Dict[str, str]:
    if not PINATA_API_KEY or not PINATA_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Pinata credentials are missing in backend/.env")

    return {
        "pinata_api_key": PINATA_API_KEY,
        "pinata_secret_api_key": PINATA_SECRET_KEY,
    }


def _parse_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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


def _post_with_retries(url: str, *, headers: Dict[str, str], retries: int, **kwargs):
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            return requests.post(
                url,
                headers=headers,
                timeout=(PINATA_CONNECT_TIMEOUT, PINATA_READ_TIMEOUT),
                **kwargs,
            )
        except RequestException as e:
            last_error = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
    raise last_error if last_error else RequestException("Unknown upload error")


def process_upload(job_id: str, file_bytes: bytes, file_filename: str, file_content_type: str, metadata: Dict[str, Any]) -> None:
    try:
        headers = _pinata_headers()

        # 1) Pin model file
        files = {
            "file": (file_filename, file_bytes, file_content_type or "application/octet-stream")
        }
        file_metadata = {
            "name": f"model-{metadata['name']}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        }

        file_response = _post_with_retries(
            PINATA_FILE_URL,
            headers=headers,
            retries=PINATA_UPLOAD_RETRIES,
            files=files,
            data={"pinataMetadata": json.dumps(file_metadata)},
        )

        if file_response.status_code >= 300:
            jobs[job_id] = {"status": "failed", "error": f"Pinata file upload failed: {file_response.text}"}
            return

        file_payload = file_response.json()
        file_ipfs_hash = file_payload.get("IpfsHash")
        if not file_ipfs_hash:
            jobs[job_id] = {"status": "failed", "error": "Pinata did not return IpfsHash for file upload"}
            return

        model_id = f"model-{uuid.uuid4().hex[:10]}"
        file_size_mb = round(len(file_bytes) / (1024 * 1024), 3)

        record: Dict[str, Any] = {
            "id": model_id,
            "name": metadata["name"],
            "description": metadata["description"],
            "creator": metadata["creator"],
            "model_type": metadata["model_type"],
            "task_type": metadata["task_type"],
            "framework": metadata["framework"],
            "category": metadata["category"],
            "input_type": metadata.get("input_type", ""),
            "output_type": metadata.get("output_type", ""),
            "feature_columns": metadata.get("feature_columns", []),
            "feature_types": metadata.get("feature_types", []),
            "target_column": metadata.get("target_column", ""),
            "ipfs_hash": file_ipfs_hash,
            "gateway_url": f"{IPFS_GATEWAY.rstrip('/')}/{file_ipfs_hash}",
            "file_name": file_filename,
            "file_size_mb": file_size_mb,
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
            "input_shape": metadata["input_shape"],
            "output_shape": metadata["output_shape"],
            "output_labels": metadata["output_labels"],
            "tags": metadata["tags"],
            "gpu_required": metadata["gpu_required"],
            "purchased": False,
            "local_model_path": "",
        }

        if metadata.get("price_per_request") is not None:
            record["pricing"] = {
                "per_request": metadata["price_per_request"],
                "currency": metadata["payment_currency"] or "ETH"
            }

        if metadata.get("model_size_mb") is not None:
            record["model_size_mb"] = metadata["model_size_mb"]

        if metadata.get("estimated_latency_ms") is not None:
            record["estimated_latency_ms"] = metadata["estimated_latency_ms"]

        if metadata.get("evaluation_metrics"):
            record["evaluation_metrics"] = metadata["evaluation_metrics"]

        # 2) Pin metadata JSON (optional but useful)
        metadata_payload = {
            "pinataMetadata": {"name": f"metadata-{model_id}"},
            "pinataContent": record,
        }

        try:
            metadata_response = _post_with_retries(
                PINATA_JSON_URL,
                retries=1,
                headers={**headers, "Content-Type": "application/json"},
                json=metadata_payload,
            )
            if metadata_response.status_code < 300:
                metadata_ipfs_hash = metadata_response.json().get("IpfsHash")
                if metadata_ipfs_hash:
                    record["metadata_ipfs_hash"] = metadata_ipfs_hash
                    record["metadata_gateway_url"] = f"{IPFS_GATEWAY.rstrip('/')}/{metadata_ipfs_hash}"
        except RequestException:
            pass  # Metadata pinning is optional

        record["verified"] = True  # Mark as verified since we just uploaded successfully

        if _db_available():
            try:
                existing_model = _find_model_by_ipfs_from_db(file_ipfs_hash)
                if existing_model and existing_model.get("id"):
                    model_id = str(existing_model.get("id"))
                    record["id"] = model_id
                _upsert_model_in_db(record)
            except Exception as db_exc:
                jobs[job_id] = {"status": "failed", "error": f"Failed to save model in DB: {db_exc}"}
                return
        else:
            registry = _read_registry()
            existing_models = registry.setdefault("models", [])

            # Prevent duplicate records for the same content hash.
            # If hash exists, replace it with the latest metadata.
            existing_index = next(
                (idx for idx, m in enumerate(existing_models) if m.get("ipfs_hash") == file_ipfs_hash),
                None,
            )
            if existing_index is not None:
                existing_models[existing_index] = record
            else:
                existing_models.append(record)

            _write_registry(registry)

        jobs[job_id] = {
            "status": "completed",
            "model_id": model_id,
            "ipfs_hash": file_ipfs_hash,
            "gateway_url": record["gateway_url"],
            "metadata_ipfs_hash": record.get("metadata_ipfs_hash"),
        }

    except Exception as e:
        error_message = str(e)
        if "timed out" in error_message.lower():
            error_message = (
                "Upload timed out while sending data to IPFS. "
                "Try a smaller file or increase PINATA_CONNECT_TIMEOUT/PINATA_READ_TIMEOUT in backend/.env"
            )
        jobs[job_id] = {"status": "failed", "error": error_message}


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "pinata_configured": bool(PINATA_API_KEY and PINATA_SECRET_KEY),
    }


@app.post("/api/models/upload")
async def upload_model(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str = Form(...),
    creator: str = Form(""),
    model_type: str = Form("CNN"),
    task_type: str = Form("Classification"),
    framework: str = Form("TensorFlow"),
    category: str = Form("Computer Vision"),
    input_type: str = Form(""),
    output_type: str = Form(""),
    feature_columns: str = Form(""),
    feature_types: str = Form(""),
    target_column: str = Form(""),
    input_shape: str = Form(""),
    output_shape: str = Form(""),
    output_labels: str = Form(""),
    tags: str = Form(""),
    price_per_request: Optional[float] = Form(None),
    payment_currency: str = Form("ETH"),
    model_size_mb: Optional[float] = Form(None),
    gpu_required: bool = Form(False),
    estimated_latency_ms: Optional[float] = Form(None),
    evaluation_metrics: str = Form(""),
) -> Dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Model file is required")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Prepare metadata
    metadata = {
        "name": name,
        "description": description,
        "creator": creator,
        "model_type": model_type,
        "task_type": task_type,
        "framework": framework,
        "category": category,
        "input_type": input_type.strip(),
        "output_type": output_type.strip(),
        "feature_columns": _parse_csv(feature_columns) if feature_columns else [],
        "feature_types": _parse_csv(feature_types) if feature_types else [],
        "target_column": target_column.strip(),
        "input_shape": _parse_csv(input_shape) if input_shape else [],
        "output_shape": _parse_csv(output_shape) if output_shape else [],
        "output_labels": _parse_csv(output_labels) if output_labels else [],
        "tags": _parse_csv(tags) if tags else [],
        "gpu_required": gpu_required,
        "price_per_request": price_per_request,
        "payment_currency": payment_currency,
        "model_size_mb": model_size_mb,
        "estimated_latency_ms": estimated_latency_ms,
    }

    if evaluation_metrics.strip():
        try:
            parsed_metrics = json.loads(evaluation_metrics)
            if isinstance(parsed_metrics, list):
                clean_metrics: List[Dict[str, Any]] = []
                for metric in parsed_metrics:
                    if not isinstance(metric, dict):
                        continue
                    metric_type = str(metric.get("metric_type", "")).strip()
                    metric_value = metric.get("metric_value")
                    if not metric_type or metric_value in (None, ""):
                        continue
                    try:
                        clean_metrics.append({
                            "metric_type": metric_type,
                            "metric_value": float(metric_value),
                        })
                    except (TypeError, ValueError):
                        continue

                if clean_metrics:
                    metadata["evaluation_metrics"] = clean_metrics
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid evaluation_metrics JSON format")

    defaults = TASK_IO_DEFAULTS.get(task_type, {})
    if not metadata["input_type"]:
        metadata["input_type"] = defaults.get("input_type", "")
    if not metadata["output_type"]:
        metadata["output_type"] = defaults.get("output_type", "")

    is_classification_task = "classification" in task_type.lower()
    if is_classification_task and not metadata["output_labels"]:
        raise HTTPException(
            status_code=400,
            detail="Output labels are required for classification tasks",
        )

    if task_type.lower() == "regression":
        metadata["output_labels"] = []

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "message": "Uploading model to IPFS"}

    background_tasks.add_task(
        process_upload,
        job_id,
        file_bytes,
        file.filename,
        file.content_type,
        metadata
    )

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Upload started. Check status with GET /api/models/status/{job_id}"
    }


@app.get("/api/models/status/{job_id}")
def get_upload_status(job_id: str) -> Dict[str, Any]:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.post("/api/models/{model_id}/buy")
def buy_model(model_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full buy flow:
    1. Validate model exists
    2. Download model file from IPFS/Pinata into local cache
    3. Pin ERC-721 NFT metadata JSON to Pinata (wallet, model_id, ipfs_hash)
    4. Store wallet → model_id → nft metadata in Neon DB (nft_licenses table)
    5. Return nft_token_id=0 (token minting happens client-side via ModelRegistry.sol)
       and the metadata_uri so the frontend can call mintLicense on-chain
    """
    model = _find_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    buyer = str(body.get("buyer", "")).strip()
    if not buyer:
        raise HTTPException(status_code=400, detail="buyer (wallet address) is required")

    if not Web3.is_address(buyer):
        raise HTTPException(status_code=400, detail="buyer must be a valid Ethereum address")

    model_name  = str(model.get("name", "Unnamed Model")).strip() or "Unnamed Model"
    model_owner = str(model.get("creator", "")).strip()
    ipfs_hash   = str(model.get("ipfs_hash", "")).strip()
    image_uri   = f"ipfs://{ipfs_hash}" if ipfs_hash else ""

    # ── 1. Check if already purchased ─────────────────────────────────
    existing = _get_nft_license_from_db(buyer, model_id)
    if existing:
        return {
            "success": True,
            "already_purchased": True,
            "model_id": model_id,
            "model_name": model_name,
            "wallet_address": buyer,
            "nft_token_id": existing.get("nft_token_id"),
            "metadata_uri": existing.get("metadata_uri"),
            "metadata_ipfs_hash": existing.get("metadata_ipfs_hash"),
            "local_model_path": existing.get("local_model_path"),
            "message": "Model already purchased — returning existing license.",
        }

    # ── 2. Download model file from IPFS into local cache ──────────────
    local_model_path = _ensure_model_downloaded(model)

    # ── 3. Pin NFT metadata JSON to Pinata ─────────────────────────────
    total_uses = int(body.get("total_uses", 1000) or 1000)
    nft_metadata = {
        "name": f"{model_name} — License NFT",
        "description": f"Grants {total_uses} inference calls on model '{model_name}' (ID: {model_id})",
        "image": image_uri,
        "attributes": [
            {"trait_type": "Model ID",      "value": model_id},
            {"trait_type": "Buyer",         "value": buyer},
            {"trait_type": "Model Owner",   "value": model_owner},
            {"trait_type": "Total Uses",    "value": total_uses},
            {"trait_type": "IPFS Hash",     "value": ipfs_hash},
            {"trait_type": "Purchased At",  "value": datetime.utcnow().date().isoformat()},
        ],
    }

    metadata_ipfs_hash = ""
    metadata_uri = ""
    try:
        headers = _pinata_headers()
        pinata_payload = {
            "pinataMetadata": {"name": f"nft-license-{model_id[:8]}-{buyer[:8]}"},
            "pinataContent": nft_metadata,
        }
        resp = _post_with_retries(
            PINATA_JSON_URL,
            retries=PINATA_UPLOAD_RETRIES,
            headers={**headers, "Content-Type": "application/json"},
            json=pinata_payload,
        )
        if resp.status_code < 300:
            metadata_ipfs_hash = str(resp.json().get("IpfsHash", "")).strip()
            metadata_uri = f"ipfs://{metadata_ipfs_hash}" if metadata_ipfs_hash else ""
    except Exception as exc:
        print(f"[WARN] Pinata NFT metadata pin failed (non-fatal): {exc}")
        # Non-fatal: license record is still stored in DB without IPFS hash

    # ── 4. Store in Neon DB: wallet → model_id → metadata ─────────────
    # nft_token_id is None until the frontend calls mintLicense on-chain
    # and records the token ID via POST /api/models/{id}/license-confirm
    _store_nft_license_in_db(
        wallet_address=buyer,
        model_id=model_id,
        model_name=model_name,
        nft_token_id=None,
        metadata_ipfs_hash=metadata_ipfs_hash,
        metadata_uri=metadata_uri,
        local_model_path=local_model_path,
    )

    return {
        "success": True,
        "already_purchased": False,
        "model_id": model_id,
        "model_name": model_name,
        "wallet_address": buyer,
        "nft_token_id": None,
        "metadata_uri": metadata_uri,
        "metadata_ipfs_hash": metadata_ipfs_hash,
        "metadata_gateway_url": f"{IPFS_GATEWAY.rstrip('/')}/{metadata_ipfs_hash}" if metadata_ipfs_hash else "",
        "local_model_path": local_model_path,
        "message": "Model downloaded. NFT metadata pinned. Call mintLicense on-chain with the metadata_uri, then confirm with /license-confirm.",
    }


@app.post("/api/models/{model_id}/license-confirm")
def confirm_license_token(model_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Called by the frontend AFTER the on-chain mintLicense tx confirms.
    Writes the real nft_token_id back to the nft_licenses row in Neon DB.
    Body: { wallet_address, nft_token_id }
    """
    wallet_address = str(body.get("wallet_address", "")).strip()
    if not wallet_address:
        raise HTTPException(status_code=400, detail="wallet_address is required")

    token_id_raw = body.get("nft_token_id")
    if token_id_raw is None:
        raise HTTPException(status_code=400, detail="nft_token_id is required")
    try:
        nft_token_id = int(token_id_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="nft_token_id must be an integer")

    existing = _get_nft_license_from_db(wallet_address, model_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail="No license record found. Call /buy first.",
        )

    _store_nft_license_in_db(
        wallet_address=wallet_address,
        model_id=model_id,
        model_name=existing.get("model_name", ""),
        nft_token_id=nft_token_id,
        metadata_ipfs_hash=existing.get("metadata_ipfs_hash", ""),
        metadata_uri=existing.get("metadata_uri", ""),
        local_model_path=existing.get("local_model_path", ""),
    )

    return {
        "success": True,
        "model_id": model_id,
        "wallet_address": wallet_address,
        "nft_token_id": nft_token_id,
        "message": "Token ID confirmed and stored in DB.",
    }


@app.get("/api/models/{model_id}/license-status")
def get_license_status(model_id: str, wallet: str) -> Dict[str, Any]:
    """
    GET /api/models/{model_id}/license-status?wallet=0x...
    Returns whether a wallet has purchased this model and the stored NFT token_id.
    """
    if not wallet:
        raise HTTPException(status_code=400, detail="wallet query param is required")
    record = _get_nft_license_from_db(wallet, model_id)
    if not record:
        return {"purchased": False, "model_id": model_id, "wallet_address": wallet}
    return {
        "purchased": True,
        "model_id": model_id,
        "wallet_address": wallet,
        "nft_token_id": record.get("nft_token_id"),
        "metadata_uri": record.get("metadata_uri"),
        "metadata_ipfs_hash": record.get("metadata_ipfs_hash"),
        "local_model_path": record.get("local_model_path"),
        "purchased_at": str(record.get("purchased_at", "")),
    }


@app.post("/api/models/{model_id}/license-metadata")
def create_license_metadata(model_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    model = _find_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    buyer = str(body.get("buyer", "")).strip()
    if not buyer:
        raise HTTPException(status_code=400, detail="buyer is required")

    total_uses = int(body.get("total_uses", 1000) or 1000)
    if total_uses <= 0:
        raise HTTPException(status_code=400, detail="total_uses must be > 0")

    headers = _pinata_headers()

    name = str(model.get("name", "Unnamed Model")).strip() or "Unnamed Model"
    model_owner = str(model.get("creator", "Unknown Owner")).strip() or "Unknown Owner"
    model_image_hash = str(model.get("ipfs_hash", "")).strip()
    image_uri = f"ipfs://{model_image_hash}" if model_image_hash else ""

    metadata_json = {
        "name": f"{name} - License",
        "description": f"Grants {total_uses} inference calls on model {model_id}",
        "image": image_uri,
        "attributes": [
            {"trait_type": "Model ID", "value": model_id},
            {"trait_type": "Total Uses", "value": total_uses},
            {"trait_type": "Purchased At", "value": datetime.utcnow().date().isoformat()},
            {"trait_type": "Model Owner", "value": model_owner},
            {"trait_type": "Buyer", "value": buyer},
        ],
    }

    payload = {
        "pinataMetadata": {"name": f"license-metadata-{model_id}-{uuid.uuid4().hex[:8]}"},
        "pinataContent": metadata_json,
    }

    try:
        response = _post_with_retries(
            PINATA_JSON_URL,
            retries=PINATA_UPLOAD_RETRIES,
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        )
    except RequestException as exc:
        raise HTTPException(status_code=504, detail=f"Failed to upload license metadata to Pinata: {exc}")

    if response.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"Pinata metadata upload failed: {response.text}")

    meta_ipfs_hash = str(response.json().get("IpfsHash", "")).strip()
    if not meta_ipfs_hash:
        raise HTTPException(status_code=502, detail="Pinata did not return metadata IpfsHash")

    return {
        "model_id": model_id,
        "metadata_ipfs_hash": meta_ipfs_hash,
        "metadata_uri": f"ipfs://{meta_ipfs_hash}",
        "metadata_gateway_url": f"{IPFS_GATEWAY.rstrip('/')}/{meta_ipfs_hash}",
        "metadata": metadata_json,
    }


@app.get("/api/models/purchased")
def list_purchased_models() -> Dict[str, Any]:
    purchased = [_public_model_view(m) for m in _get_all_models() if m.get("purchased")]
    return {"models": purchased}


@app.post("/api/models/{model_id}/predict")
def predict_with_model(model_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    model = _find_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    wallet_address = str(body.get("wallet_address", "")).strip()
    if not wallet_address:
        raise HTTPException(status_code=400, detail="wallet_address is required")

    # DB license check — nft_licenses first, then model_passkeys legacy fallback
    license_record = _resolve_license(wallet_address, model_id)
    if not license_record:
        raise HTTPException(
            status_code=403,
            detail="No license found for this wallet and model. Purchase the model first.",
        )

    # token_id from DB (may be None if on-chain mint hasn't been confirmed yet)
    # Allow predict if DB record exists (client-side chain verify handles on-chain check)
    token_id_from_db = license_record.get("nft_token_id")
    token_id_raw = body.get("license_token_id", token_id_from_db)
    try:
        token_id = int(token_id_raw) if token_id_raw is not None else None
    except (TypeError, ValueError):
        token_id = None

    # ── Optionally verify on-chain if contract is configured ──────────
    license_status_before = None
    if token_id is not None and WEB3_RPC_URL and MODEL_LICENSE_ADDRESS:
        try:
            license_status_before = _verify_license_for_model(model_id, wallet_address, token_id)
        except HTTPException as exc:
            print(f"[WARN] On-chain check failed but DB record is valid: {exc.detail}")
            pass
        except Exception:
            pass  # On-chain check best-effort; DB record is the source of truth
    local_model_path = _ensure_model_downloaded(model)

    if "input" not in body:
        raise HTTPException(status_code=400, detail="Request body must include 'input'")

    input_vector = _flatten_to_floats(body.get("input"))
    expected_shape = _parse_shape_to_ints(model.get("input_shape", []))
    if expected_shape:
        expected_size = math.prod(expected_shape)
        if len(input_vector) != expected_size:
            raise HTTPException(
                status_code=400,
                detail=f"Input size mismatch. Expected {expected_size} values from shape {expected_shape}, got {len(input_vector)}",
            )

    output_labels = [str(v) for v in model.get("output_labels", []) if str(v).strip()]
    ipfs_hash = str(model.get("ipfs_hash", ""))

    if output_labels:
        probabilities = _predict_labels(ipfs_hash, input_vector, output_labels)
        predicted_label = max(probabilities, key=probabilities.get)

        usage_tx = None
        updated_status = None
        if token_id is not None and WEB3_RPC_URL and MODEL_LICENSE_ADDRESS:
            try:
                usage_tx = _record_license_use_on_chain(token_id)
                updated_status = _verify_license_for_model(model_id, wallet_address, token_id)
            except Exception:
                pass

        return {
            "model_id": model_id,
            "license_token_id": token_id,
            "wallet_address": wallet_address,
            "input_shape": expected_shape,
            "local_model_path": local_model_path,
            "output_labels": output_labels,
            "license": {
                "nft_token_id": token_id,
                "owner": (license_status_before or {}).get("owner", wallet_address),
                "max_uses": (updated_status or {}).get("max_uses"),
                "used_count": (updated_status or {}).get("used_count"),
                "remaining_uses": (
                    max((updated_status or {}).get("max_uses", 0) - (updated_status or {}).get("used_count", 0), 0)
                    if updated_status else None
                ),
                "record_use_tx": usage_tx,
                "verified_via": "on-chain" if updated_status else "neon-db",
            },
            "prediction": {
                "predicted_label": predicted_label,
                "probabilities": probabilities,
            },
        }

    digest = hashlib.sha256(f"{ipfs_hash}:{sum(input_vector):.8f}".encode("utf-8")).hexdigest()
    scalar = round((int(digest[:8], 16) / 0xFFFFFFFF), 6)

    usage_tx = None
    updated_status = None
    if token_id is not None and WEB3_RPC_URL and MODEL_LICENSE_ADDRESS:
        try:
            usage_tx = _record_license_use_on_chain(token_id)
            updated_status = _verify_license_for_model(model_id, wallet_address, token_id)
        except Exception:
            pass

    return {
        "model_id": model_id,
        "license_token_id": token_id,
        "wallet_address": wallet_address,
        "input_shape": expected_shape,
        "local_model_path": local_model_path,
        "license": {
            "nft_token_id": token_id,
            "owner": (license_status_before or {}).get("owner", wallet_address),
            "max_uses": (updated_status or {}).get("max_uses"),
            "used_count": (updated_status or {}).get("used_count"),
            "remaining_uses": (
                max((updated_status or {}).get("max_uses", 0) - (updated_status or {}).get("used_count", 0), 0)
                if updated_status else None
            ),
            "record_use_tx": usage_tx,
            "verified_via": "on-chain" if updated_status else "neon-db",
        },
        "prediction": {
            "value": scalar,
        },
    }


@app.post("/api/models/{model_id}/predict-image", tags=["models"])
async def predict_image(
    model_id: str,
    image: UploadFile = File(...),
    wallet_address: str = Form(...),
    token_id: Optional[int] = Form(None),
) -> Dict[str, Any]:
    """Image prediction — authenticated by wallet + Neon DB license lookup."""
    model = _find_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    # DB license check — nft_licenses first, then model_passkeys legacy fallback
    license_record = _resolve_license(wallet_address, model_id)
    if not license_record:
        raise HTTPException(
            status_code=403,
            detail="No license found for this wallet. Purchase the model first.",
        )

    # Resolve token_id (from form or DB)
    resolved_token_id = token_id if token_id is not None else license_record.get("nft_token_id")

    # Optional on-chain verify
    license_info = None
    if resolved_token_id is not None and WEB3_RPC_URL and MODEL_LICENSE_ADDRESS:
        try:
            license_info = _verify_license_for_model(
                model_id=model_id, wallet_address=wallet_address, token_id=resolved_token_id
            )
        except HTTPException as exc:
            print(f"[WARN] On-chain check failed but DB record is valid: {exc.detail}")
            pass
        except Exception:
            pass

    local_model_path = _ensure_model_downloaded(model)

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")

    # Lightweight feature extraction from image bytes for deterministic demo inference.
    # This keeps the end-to-end image upload prediction flow working for CNN models.
    sample = image_bytes[:4096]
    input_vector = [float(b) / 255.0 for b in sample]

    output_labels = [str(v) for v in model.get("output_labels", []) if str(v).strip()]
    ipfs_hash = str(model.get("ipfs_hash", ""))

    if output_labels:
        probabilities = _predict_labels(ipfs_hash, input_vector, output_labels)
        predicted_label = max(probabilities, key=probabilities.get)

        usage_tx = None
        updated_status = None
        if resolved_token_id is not None and WEB3_RPC_URL and MODEL_LICENSE_ADDRESS:
            try:
                usage_tx = _record_license_use_on_chain(resolved_token_id)
                updated_status = _verify_license_for_model(model_id, wallet_address, resolved_token_id)
            except Exception:
                pass

        return {
            "model_id": model_id,
            "license_token_id": resolved_token_id,
            "wallet_address": wallet_address,
            "mode": "image",
            "file_name": image.filename,
            "local_model_path": local_model_path,
            "output_labels": output_labels,
            "license": {
                "nft_token_id": resolved_token_id,
                "owner": (license_info or {}).get("owner", wallet_address),
                "max_uses": (updated_status or {}).get("max_uses"),
                "used_count": (updated_status or {}).get("used_count"),
                "remaining_uses": (
                    max((updated_status or {}).get("max_uses", 0) - (updated_status or {}).get("used_count", 0), 0)
                    if updated_status else None
                ),
                "record_use_tx": usage_tx,
                "verified_via": "on-chain" if updated_status else "neon-db",
            },
            "prediction": {
                "predicted_label": predicted_label,
                "probabilities": probabilities,
            },
        }

    digest = hashlib.sha256(f"{ipfs_hash}:{sum(input_vector):.8f}".encode("utf-8")).hexdigest()
    scalar = round((int(digest[:8], 16) / 0xFFFFFFFF), 6)

    usage_tx = None
    updated_status = None
    if resolved_token_id is not None and WEB3_RPC_URL and MODEL_LICENSE_ADDRESS:
        try:
            usage_tx = _record_license_use_on_chain(resolved_token_id)
            updated_status = _verify_license_for_model(model_id, wallet_address, resolved_token_id)
        except Exception:
            pass

    return {
        "model_id": model_id,
        "license_token_id": resolved_token_id,
        "wallet_address": wallet_address,
        "mode": "image",
        "file_name": image.filename,
        "local_model_path": local_model_path,
        "license": {
            "nft_token_id": resolved_token_id,
            "owner": (license_info or {}).get("owner", wallet_address),
            "max_uses": (updated_status or {}).get("max_uses"),
            "used_count": (updated_status or {}).get("used_count"),
            "remaining_uses": (
                max((updated_status or {}).get("max_uses", 0) - (updated_status or {}).get("used_count", 0), 0)
                if updated_status else None
            ),
            "record_use_tx": usage_tx,
            "verified_via": "on-chain" if updated_status else "neon-db",
        },
        "prediction": {
            "value": scalar,
        },
    }


def _verify_model_on_pinata(gateway_url: str) -> bool:
    try:
        response = requests.head(gateway_url, timeout=10)  # Increased timeout
        return response.status_code == 200
    except RequestException:
        return False


@app.get("/api/models")
def list_models() -> Dict[str, Any]:
    all_models = _get_all_models()

    # Deduplicate by IPFS hash first (same content), fallback to id.
    deduped: Dict[str, Dict[str, Any]] = {}
    for model in all_models:
        dedupe_key = str(model.get("ipfs_hash") or model.get("id") or "").strip()
        if not dedupe_key:
            continue

        previous = deduped.get(dedupe_key)
        if previous is None:
            deduped[dedupe_key] = model
            continue

        prev_uploaded = str(previous.get("uploaded_at") or "")
        curr_uploaded = str(model.get("uploaded_at") or "")
        if curr_uploaded >= prev_uploaded:
            deduped[dedupe_key] = model

    all_models = list(deduped.values())

    deduped_models: List[Dict[str, Any]] = []
    for model in all_models:
        gateway_url = str(model.get("gateway_url", "")).strip()
        if model.get("verified"):
            deduped_models.append(model)
            continue

        if gateway_url and _verify_model_on_pinata(gateway_url):
            model["verified"] = True

        # Keep model in listing even if verification is temporarily failing.
        deduped_models.append(model)

    return {"models": [_public_model_view(model) for model in deduped_models]}


@app.get("/api/proposals")
def list_proposals() -> Dict[str, Any]:
    if _db_available():
        proposals = _read_proposals_from_db()
        if proposals is None:
            raise HTTPException(status_code=500, detail="Failed to read proposals from DB")
        _recompute_proposal_acceptance(proposals)
        for proposal in proposals:
            _insert_proposal_in_db(proposal)
        return {"proposals": proposals}

    registry = _read_proposals_registry()
    proposals = registry.get("proposals", [])
    _recompute_proposal_acceptance(proposals)
    proposals_sorted = sorted(
        proposals,
        key=lambda p: (int(p.get("upvotes", 0)), str(p.get("created_at", ""))),
        reverse=True,
    )
    registry["proposals"] = proposals
    _write_proposals_registry(registry)
    return {"proposals": proposals_sorted}


@app.post("/api/proposals")
def submit_proposal(body: Dict[str, Any]) -> Dict[str, Any]:
    title = str(body.get("title", "")).strip()
    summary = str(body.get("summary", "")).strip()
    proposer = str(body.get("proposer", "")).strip() or "Anonymous"
    details = str(body.get("details", "")).strip()

    if not title:
        raise HTTPException(status_code=400, detail="Proposal title is required")
    if not summary:
        raise HTTPException(status_code=400, detail="Proposal summary is required")

    proposal = {
        "id": f"proposal-{uuid.uuid4().hex[:10]}",
        "title": title,
        "summary": summary,
        "proposer": proposer,
        "details": details,
        "upvotes": 0,
        "accepted": False,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    if _db_available():
        try:
            _insert_proposal_in_db(proposal)
            proposals = _read_proposals_from_db() or []
            _recompute_proposal_acceptance(proposals)
            for item in proposals:
                _insert_proposal_in_db(item)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to save proposal in DB: {exc}")
    else:
        registry = _read_proposals_registry()
        proposals = registry.setdefault("proposals", [])
        proposals.append(proposal)
        _recompute_proposal_acceptance(proposals)
        registry["proposals"] = proposals
        _write_proposals_registry(registry)

    return {
        "success": True,
        "message": "Proposal submitted successfully",
        "proposal": proposal,
    }


@app.post("/api/proposals/{proposal_id}/upvote")
def upvote_proposal(proposal_id: str) -> Dict[str, Any]:
    if _db_available():
        proposal = _upvote_proposal_in_db(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="Proposal not found")

        proposals = _read_proposals_from_db() or []
        _recompute_proposal_acceptance(proposals)
        for item in proposals:
            _insert_proposal_in_db(item)

        updated = next((p for p in proposals if str(p.get("id", "")).strip() == proposal_id), proposal)
        return {
            "success": True,
            "message": "Upvote added",
            "proposal_id": proposal_id,
            "upvotes": int(updated.get("upvotes", 0)),
            "accepted": updated.get("accepted", False),
        }

    registry = _read_proposals_registry()
    proposals = registry.setdefault("proposals", [])

    target = None
    for proposal in proposals:
        if str(proposal.get("id", "")).strip() == proposal_id:
            target = proposal
            break

    if target is None:
        raise HTTPException(status_code=404, detail="Proposal not found")

    target["upvotes"] = int(target.get("upvotes", 0)) + 1
    _recompute_proposal_acceptance(proposals)

    registry["proposals"] = proposals
    _write_proposals_registry(registry)

    return {
        "success": True,
        "message": "Upvote added",
        "proposal_id": proposal_id,
        "upvotes": target["upvotes"],
        "accepted": target.get("accepted", False),
    }

@app.get("/test")
def test_endpoint():
    return {"message": "Test endpoint is working!"}