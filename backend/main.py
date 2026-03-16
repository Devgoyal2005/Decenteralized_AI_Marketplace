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
import requests
from requests import RequestException

BASE_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = BASE_DIR / "models_registry.json"
DOWNLOADED_MODELS_DIR = BASE_DIR / "downloaded_models"

load_dotenv(BASE_DIR / ".env")

PINATA_API_KEY = os.getenv("PINATA_API_KEY", "").strip()
PINATA_SECRET_KEY = os.getenv("PINATA_SECRET_KEY", "").strip()
IPFS_GATEWAY = os.getenv("IPFS_GATEWAY", "https://gateway.pinata.cloud/ipfs/").strip()

PINATA_FILE_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
PINATA_JSON_URL = "https://api.pinata.cloud/pinning/pinJSONToIPFS"

PINATA_CONNECT_TIMEOUT = int(os.getenv("PINATA_CONNECT_TIMEOUT", "30"))
PINATA_READ_TIMEOUT = int(os.getenv("PINATA_READ_TIMEOUT", "600"))
PINATA_UPLOAD_RETRIES = int(os.getenv("PINATA_UPLOAD_RETRIES", "2"))

app = FastAPI(title="Model Upload API", version="1.0.0")

jobs: Dict[str, Dict[str, Any]] = {}

app.add_middleware(
    CORSMiddleware,
    # Explicit origins for local frontend servers
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def _find_model_index(models: List[Dict[str, Any]], model_id: str) -> int:
    for idx, model in enumerate(models):
        if str(model.get("id", "")) == model_id:
            return idx
    return -1


def _model_extension(file_name: str) -> str:
    suffix = Path(file_name).suffix.strip()
    return suffix if suffix else ".bin"


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
        jobs[job_id] = {"status": "failed", "error": str(e)}


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
def buy_model(model_id: str) -> Dict[str, Any]:
    registry = _read_registry()
    models = registry.get("models", [])
    model_idx = _find_model_index(models, model_id)
    if model_idx < 0:
        raise HTTPException(status_code=404, detail="Model not found")

    model = models[model_idx]
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

    model["purchased"] = True
    model["downloaded_at"] = datetime.utcnow().isoformat() + "Z"
    model["local_model_path"] = str(local_path)
    models[model_idx] = model
    registry["models"] = models
    _write_registry(registry)

    return {
        "success": True,
        "message": "Model purchased and downloaded locally",
        "model_id": model_id,
        "ipfs_hash": ipfs_hash,
        "local_model_path": str(local_path),
    }


@app.get("/api/models/purchased")
def list_purchased_models() -> Dict[str, Any]:
    registry = _read_registry()
    purchased = [m for m in registry.get("models", []) if m.get("purchased")]
    return {"models": purchased}


@app.post("/api/models/{model_id}/predict")
def predict_with_model(model_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    registry = _read_registry()
    models = registry.get("models", [])
    model_idx = _find_model_index(models, model_id)
    if model_idx < 0:
        raise HTTPException(status_code=404, detail="Model not found")

    model = models[model_idx]
    local_model_path = str(model.get("local_model_path", "")).strip()
    if not model.get("purchased") or not local_model_path:
        raise HTTPException(status_code=400, detail="Model must be bought first")
    if not Path(local_model_path).exists():
        raise HTTPException(status_code=400, detail="Local model file missing. Buy again to download it")

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
        return {
            "model_id": model_id,
            "input_shape": expected_shape,
            "local_model_path": local_model_path,
            "output_labels": output_labels,
            "prediction": {
                "predicted_label": predicted_label,
                "probabilities": probabilities,
            },
        }

    digest = hashlib.sha256(f"{ipfs_hash}:{sum(input_vector):.8f}".encode("utf-8")).hexdigest()
    scalar = round((int(digest[:8], 16) / 0xFFFFFFFF), 6)
    return {
        "model_id": model_id,
        "input_shape": expected_shape,
        "local_model_path": local_model_path,
        "prediction": {
            "value": scalar,
        },
    }


@app.post("/api/models/{model_id}/predict-image")
async def predict_with_image(model_id: str, image: UploadFile = File(...)) -> Dict[str, Any]:
    registry = _read_registry()
    models = registry.get("models", [])
    model_idx = _find_model_index(models, model_id)
    if model_idx < 0:
        raise HTTPException(status_code=404, detail="Model not found")

    model = models[model_idx]
    local_model_path = str(model.get("local_model_path", "")).strip()
    if not model.get("purchased") or not local_model_path:
        raise HTTPException(status_code=400, detail="Model must be bought first")
    if not Path(local_model_path).exists():
        raise HTTPException(status_code=400, detail="Local model file missing. Buy again to download it")

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
        return {
            "model_id": model_id,
            "mode": "image",
            "file_name": image.filename,
            "local_model_path": local_model_path,
            "output_labels": output_labels,
            "prediction": {
                "predicted_label": predicted_label,
                "probabilities": probabilities,
            },
        }

    digest = hashlib.sha256(f"{ipfs_hash}:{sum(input_vector):.8f}".encode("utf-8")).hexdigest()
    scalar = round((int(digest[:8], 16) / 0xFFFFFFFF), 6)
    return {
        "model_id": model_id,
        "mode": "image",
        "file_name": image.filename,
        "local_model_path": local_model_path,
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
    registry = _read_registry()
    all_models = registry.get("models", [])

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

    verified_models = []
    for model in all_models:
        if model.get("verified"):
            verified_models.append(model)
        elif _verify_model_on_pinata(model["gateway_url"]):
            model["verified"] = True
            verified_models.append(model)

    # Update registry with deduplicated verified models
    registry["models"] = verified_models
    _write_registry(registry)
    return {"models": verified_models}


