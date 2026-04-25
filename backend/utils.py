"""
Shared utilities — JSON registry I/O, model lookups, data parsing, and helper functions.
"""
import hashlib
import json
import secrets
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from requests import RequestException
from fastapi import HTTPException

from backend.config import REGISTRY_PATH, PROPOSALS_PATH, DOWNLOADED_MODELS_DIR


# ── JSON Registry I/O ─────────────────────────────────────────


def _ensure_registry() -> None:
    if not REGISTRY_PATH.exists():
        REGISTRY_PATH.write_text(json.dumps({"models": []}, indent=2), encoding="utf-8")


def _read_registry() -> Dict[str, Any]:
    _ensure_registry()
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _write_registry(registry: Dict[str, Any]) -> None:
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def _ensure_proposals_registry() -> None:
    if not PROPOSALS_PATH.exists():
        PROPOSALS_PATH.write_text(json.dumps({"proposals": []}, indent=2), encoding="utf-8")


def _read_proposals_registry() -> Dict[str, Any]:
    _ensure_proposals_registry()
    return json.loads(PROPOSALS_PATH.read_text(encoding="utf-8"))


def _write_proposals_registry(registry: Dict[str, Any]) -> None:
    PROPOSALS_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")


# ── Model Lookup Helpers ──────────────────────────────────────


def _find_model_index(models: List[Dict[str, Any]], model_id: str) -> int:
    for idx, model in enumerate(models):
        if str(model.get("id", "")) == model_id:
            return idx
    return -1


def _get_all_models() -> List[Dict[str, Any]]:
    from backend.database import _db_available, _read_models_from_db
    if _db_available():
        db_models = _read_models_from_db()
        if db_models is not None:
            return db_models
    registry = _read_registry()
    return registry.get("models", [])


def _find_model_by_id(model_id: str) -> Optional[Dict[str, Any]]:
    models = _get_all_models()
    idx = _find_model_index(models, model_id)
    if idx < 0:
        return None
    return models[idx]


def _save_model_record(model: Dict[str, Any]) -> None:
    from backend.database import _db_available, _upsert_model_in_db
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


def _ensure_downloads_dir() -> None:
    DOWNLOADED_MODELS_DIR.mkdir(parents=True, exist_ok=True)


def _model_extension(file_name: str) -> str:
    suffix = Path(file_name).suffix.strip()
    return suffix if suffix else ".bin"


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


# ── Data Parsing / Inference Utilities ─────────────────────────


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


def _parse_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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
