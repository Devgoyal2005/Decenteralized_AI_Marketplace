"""
IPFS / Pinata helpers — uploading files, pinning JSON, and the background process_upload task.
"""
import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from requests import RequestException
from fastapi import HTTPException

from backend.config import (
    PINATA_API_KEY,
    PINATA_SECRET_KEY,
    PINATA_FILE_URL,
    PINATA_JSON_URL,
    PINATA_CONNECT_TIMEOUT,
    PINATA_READ_TIMEOUT,
    PINATA_UPLOAD_RETRIES,
    IPFS_GATEWAY,
)
from backend.database import (
    _db_available,
    _upsert_model_in_db,
    _find_model_by_ipfs_from_db,
)
from backend.utils import _read_registry, _write_registry


# ── Shared in-memory job store (referenced by routes) ─────────
jobs: Dict[str, Dict[str, Any]] = {}


def _pinata_headers() -> Dict[str, str]:
    if not PINATA_API_KEY or not PINATA_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Pinata credentials are missing in backend/.env")
    return {
        "pinata_api_key": PINATA_API_KEY,
        "pinata_secret_api_key": PINATA_SECRET_KEY,
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


def _verify_model_on_pinata(gateway_url: str) -> bool:
    try:
        response = requests.head(gateway_url, timeout=10)
        return response.status_code == 200
    except RequestException:
        return False


def process_upload(
    job_id: str,
    file_bytes: bytes,
    file_filename: str,
    file_content_type: str,
    metadata: Dict[str, Any],
) -> None:
    """Background task: pin model file + metadata to IPFS via Pinata, store record in DB."""
    try:
        headers = _pinata_headers()

        # 0) Pin thumbnail if present
        thumbnail_ipfs_hash = ""
        thumbnail_bytes = metadata.get("thumbnail_bytes")
        if thumbnail_bytes:
            thumb_files = {
                "file": (metadata.get("thumbnail_filename", "thumbnail.png"), thumbnail_bytes, "application/octet-stream")
            }
            thumb_meta = {"name": f"thumb-{metadata['name']}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"}
            thumb_res = _post_with_retries(
                PINATA_FILE_URL,
                headers=headers,
                retries=PINATA_UPLOAD_RETRIES,
                files=thumb_files,
                data={"pinataMetadata": json.dumps(thumb_meta)}
            )
            if thumb_res.status_code < 300:
                thumbnail_ipfs_hash = thumb_res.json().get("IpfsHash", "")

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
            "thumbnail_ipfs_hash": thumbnail_ipfs_hash,
            "thumbnail_gateway_url": f"{IPFS_GATEWAY.rstrip('/')}/{thumbnail_ipfs_hash}" if thumbnail_ipfs_hash else "",
        }

        if metadata.get("sample_json") is not None:
            record["sample_json"] = metadata["sample_json"]
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

        record["verified"] = True

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
