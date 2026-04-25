"""
License routes — buy, confirm, status, my-licenses, license-metadata.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from psycopg2.extras import RealDictCursor
from web3 import Web3
from requests import RequestException

from backend.config import (
    IPFS_GATEWAY,
    PINATA_JSON_URL,
    PINATA_UPLOAD_RETRIES,
    WEB3_RPC_URL,
    MODEL_LICENSE_ADDRESS,
)
from backend.database import (
    _get_db_connection,
    _get_nft_license_from_db,
    _store_nft_license_in_db,
)
from backend.blockchain import _verify_license_for_model
from backend.ipfs import _pinata_headers, _post_with_retries
from backend.utils import _find_model_by_id, _ensure_model_downloaded

router = APIRouter(prefix="/api", tags=["licenses"])


@router.post("/models/{model_id}/buy")
def buy_model(model_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full buy flow:
    1. Validate model exists
    2. Download model file from IPFS/Pinata into local cache
    3. Pin ERC-721 NFT metadata JSON to Pinata
    4. Store wallet → model_id → nft metadata in Neon DB
    5. Return metadata_uri so frontend can call mintLicense on-chain
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

    # Check if already purchased
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

    # Download model file
    local_model_path = _ensure_model_downloaded(model)

    # Pin NFT metadata JSON to Pinata
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

    # Store in Neon DB
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


@router.post("/models/{model_id}/license-confirm")
def confirm_license_token(model_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Called after on-chain mint confirms. Writes the real nft_token_id to DB."""
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
        raise HTTPException(status_code=404, detail="No license record found. Call /buy first.")

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


@router.get("/models/{model_id}/license-status")
def get_license_status(model_id: str, wallet: str) -> Dict[str, Any]:
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


@router.get("/models/my-licenses")
def get_my_licenses(wallet: str) -> Dict[str, Any]:
    if not wallet:
        raise HTTPException(status_code=400, detail="wallet query param is required")

    conn = _get_db_connection()
    if conn is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    licenses = []
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT model_id, model_name, nft_token_id, metadata_uri, purchased_at, local_model_path
                    FROM nft_licenses
                    WHERE LOWER(wallet_address) = LOWER(%s)
                    ORDER BY purchased_at DESC;
                    """,
                    (wallet,),
                )
                rows = cur.fetchall()

                cur.execute(
                    """
                    SELECT model_id, model_name, NULL as nft_token_id, '' as metadata_uri, purchased_at, '' as local_model_path
                    FROM model_passkeys
                    WHERE LOWER(buyer) = LOWER(%s)
                      AND model_id NOT IN (SELECT model_id FROM nft_licenses WHERE LOWER(wallet_address) = LOWER(%s));
                    """,
                    (wallet, wallet),
                )
                legacy_rows = cur.fetchall()

        conn.close()

        for row in list(rows) + list(legacy_rows):
            mid = row["model_id"]
            nft_token_id = row.get("nft_token_id")

            usage_info = {"max_uses": "Unknown", "used_count": "Unknown"}
            if nft_token_id is not None and WEB3_RPC_URL and MODEL_LICENSE_ADDRESS:
                try:
                    chain_status = _verify_license_for_model(mid, wallet, nft_token_id)
                    usage_info["max_uses"] = chain_status["max_uses"]
                    usage_info["used_count"] = chain_status["used_count"]
                except Exception:
                    pass

            licenses.append({
                "model_id": mid,
                "model_name": row["model_name"],
                "nft_token_id": nft_token_id,
                "metadata_uri": row.get("metadata_uri"),
                "purchased_at": str(row["purchased_at"]),
                "local_model_path": row.get("local_model_path"),
                "max_uses": usage_info["max_uses"],
                "used_count": usage_info["used_count"],
            })

        return {"licenses": licenses}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.post("/models/{model_id}/license-metadata")
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
