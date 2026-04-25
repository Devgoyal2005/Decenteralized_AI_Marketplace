"""
Model CRUD routes — upload, list, status, update, delete.
"""
import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile

from backend.config import PINATA_API_KEY, PINATA_SECRET_KEY, TASK_IO_DEFAULTS
from backend.database import _db_available, _get_db_connection, _upsert_model_in_db
from backend.blockchain import verify_personal_signature
from backend.ipfs import jobs, process_upload, _verify_model_on_pinata
from backend.utils import (
    _find_model_by_id,
    _get_all_models,
    _parse_csv,
    _public_model_view,
    _read_registry,
    _write_registry,
)

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "pinata_configured": bool(PINATA_API_KEY and PINATA_SECRET_KEY),
    }


@router.post("/models/upload")
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
    sample_json: Optional[UploadFile] = File(None),
    thumbnail: Optional[UploadFile] = File(None),
) -> Dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Model file is required")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

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

    if sample_json and sample_json.filename:
        sample_bytes = await sample_json.read()
        if len(sample_bytes) > 102400:
            raise HTTPException(status_code=400, detail="Sample JSON must be under 100KB")
        try:
            metadata["sample_json"] = json.loads(sample_bytes.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="sample_json must be valid JSON")

    if thumbnail and thumbnail.filename:
        thumb_bytes = await thumbnail.read()
        if len(thumb_bytes) > 2_000_000:
            raise HTTPException(status_code=400, detail="Thumbnail must be under 2MB")
        metadata["thumbnail_bytes"] = thumb_bytes
        metadata["thumbnail_filename"] = thumbnail.filename

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
        metadata,
    )

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Upload started. Check status with GET /api/models/status/{job_id}",
    }


@router.get("/models/status/{job_id}")
def get_upload_status(job_id: str) -> Dict[str, Any]:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@router.get("/models")
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
        deduped_models.append(model)

    return {"models": [_public_model_view(model) for model in deduped_models]}


@router.get("/models/purchased")
def list_purchased_models() -> Dict[str, Any]:
    purchased = [_public_model_view(m) for m in _get_all_models() if m.get("purchased")]
    return {"models": purchased}


@router.patch("/models/{model_id}")
async def update_model(model_id: str, request: Request) -> Dict[str, Any]:
    """Update model details. Requires {"wallet": "0x..."} in body matching the creator."""
    body = await request.json()
    wallet = str(body.get("wallet", "")).strip().lower()
    if not wallet:
        raise HTTPException(status_code=400, detail="wallet is required in body")

    model = _find_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    creator = str(model.get("creator", "")).strip().lower()
    if wallet != creator:
        raise HTTPException(status_code=403, detail="Only the creator can edit this model")

    if "description" in body:
        model["description"] = body["description"]
    if "price_per_request" in body:
        if "pricing" not in model:
            model["pricing"] = {}
        model["pricing"]["per_request"] = float(body["price_per_request"])
    if "tags" in body:
        model["tags"] = _parse_csv(body["tags"]) if isinstance(body["tags"], str) else body["tags"]

    if _db_available():
        _upsert_model_in_db(model)
    else:
        registry = _read_registry()
        models = registry.setdefault("models", [])
        for idx, m in enumerate(models):
            if m.get("id") == model_id:
                models[idx] = model
                break
        _write_registry(registry)

    return {"success": True, "model": model}


@router.delete("/models/{model_id}")
async def delete_model(model_id: str, request: Request) -> Dict[str, Any]:
    """Requires {"wallet": "0x...", "signature": "0x...", "message": "..."} signed by creator."""
    body = await request.json()
    wallet = str(body.get("wallet", "")).strip().lower()
    signature = str(body.get("signature", "")).strip()
    message = str(body.get("message", "")).strip()

    if not wallet or not signature or not message:
        raise HTTPException(status_code=400, detail="wallet, signature, and message are required")

    model = _find_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    creator = str(model.get("creator", "")).strip().lower()
    if wallet != creator:
        raise HTTPException(status_code=403, detail="Only the creator can delete this model")

    verify_personal_signature(wallet, signature, message)

    if f"Delete model {model_id}" not in message:
        raise HTTPException(status_code=400, detail="Signed message intent does not match deletion request")

    if _db_available():
        conn = _get_db_connection()
        if conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM models_registry WHERE id = %s", (model_id,))
            conn.close()
    else:
        registry = _read_registry()
        registry["models"] = [m for m in registry.get("models", []) if m.get("id") != model_id]
        _write_registry(registry)

    return {"success": True, "message": f"Model {model_id} deleted successfully"}
