"""
Prediction routes — tabular and image-based inference.
"""
import hashlib
import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.config import WEB3_RPC_URL, MODEL_LICENSE_ADDRESS
from backend.database import _resolve_license
from backend.blockchain import _verify_license_for_model, _record_license_use_on_chain
from backend.utils import (
    _find_model_by_id,
    _ensure_model_downloaded,
    _flatten_to_floats,
    _parse_shape_to_ints,
    _predict_labels,
)

router = APIRouter(prefix="/api", tags=["predict"])


@router.post("/models/{model_id}/predict")
def predict_with_model(model_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    model = _find_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    wallet_address = str(body.get("wallet_address", "")).strip()
    if not wallet_address:
        raise HTTPException(status_code=400, detail="wallet_address is required")

    # DB license check
    license_record = _resolve_license(wallet_address, model_id)
    if not license_record:
        raise HTTPException(
            status_code=403,
            detail="No license found for this wallet and model. Purchase the model first.",
        )

    token_id_from_db = license_record.get("nft_token_id")
    token_id_raw = body.get("license_token_id", token_id_from_db)
    try:
        token_id = int(token_id_raw) if token_id_raw is not None else None
    except (TypeError, ValueError):
        token_id = None

    # Optionally verify on-chain
    license_status_before = None
    if token_id is not None and WEB3_RPC_URL and MODEL_LICENSE_ADDRESS:
        try:
            license_status_before = _verify_license_for_model(model_id, wallet_address, token_id)
        except HTTPException as exc:
            print(f"[WARN] On-chain check failed but DB record is valid: {exc.detail}")
        except Exception:
            pass

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

        return _build_predict_response(
            model_id, token_id, wallet_address, expected_shape, local_model_path,
            output_labels, license_status_before, updated_status, usage_tx,
            prediction={"predicted_label": predicted_label, "probabilities": probabilities},
        )

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

    return _build_predict_response(
        model_id, token_id, wallet_address, expected_shape, local_model_path,
        output_labels, license_status_before, updated_status, usage_tx,
        prediction={"value": scalar},
    )


@router.post("/models/{model_id}/predict-image", tags=["models"])
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

    license_record = _resolve_license(wallet_address, model_id)
    if not license_record:
        raise HTTPException(
            status_code=403,
            detail="No license found for this wallet. Purchase the model first.",
        )

    resolved_token_id = token_id if token_id is not None else license_record.get("nft_token_id")

    license_info = None
    if resolved_token_id is not None and WEB3_RPC_URL and MODEL_LICENSE_ADDRESS:
        try:
            license_info = _verify_license_for_model(
                model_id=model_id, wallet_address=wallet_address, token_id=resolved_token_id,
            )
        except HTTPException as exc:
            print(f"[WARN] On-chain check failed but DB record is valid: {exc.detail}")
        except Exception:
            pass

    local_model_path = _ensure_model_downloaded(model)

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")

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

        return _build_predict_response(
            model_id, resolved_token_id, wallet_address, [], local_model_path,
            output_labels, license_info, updated_status, usage_tx,
            prediction={"predicted_label": predicted_label, "probabilities": probabilities},
            mode="image", file_name=image.filename,
        )

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

    return _build_predict_response(
        model_id, resolved_token_id, wallet_address, [], local_model_path,
        output_labels, license_info, updated_status, usage_tx,
        prediction={"value": scalar},
        mode="image", file_name=image.filename,
    )


# ── Helper ─────────────────────────────────────────────────────


def _build_predict_response(
    model_id, token_id, wallet_address, input_shape, local_model_path,
    output_labels, license_before, updated_status, usage_tx,
    prediction, mode=None, file_name=None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "model_id": model_id,
        "license_token_id": token_id,
        "wallet_address": wallet_address,
        "local_model_path": local_model_path,
        "license": {
            "nft_token_id": token_id,
            "owner": (license_before or {}).get("owner", wallet_address),
            "max_uses": (updated_status or {}).get("max_uses"),
            "used_count": (updated_status or {}).get("used_count"),
            "remaining_uses": (
                max((updated_status or {}).get("max_uses", 0) - (updated_status or {}).get("used_count", 0), 0)
                if updated_status else None
            ),
            "record_use_tx": usage_tx,
            "verified_via": "on-chain" if updated_status else "neon-db",
        },
        "prediction": prediction,
    }
    if input_shape:
        result["input_shape"] = input_shape
    if output_labels:
        result["output_labels"] = output_labels
    if mode:
        result["mode"] = mode
    if file_name:
        result["file_name"] = file_name
    return result
