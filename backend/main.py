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
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:8001,http://localhost:8001",
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
        _init_passkeys_table()
    except Exception as exc:
        print(f"[WARN] Failed to initialize DB table model_passkeys: {exc}")
    try:
        _init_models_table()
    except Exception as exc:
        print(f"[WARN] Failed to initialize DB table models_registry: {exc}")
    try:
        _init_proposals_table()
    except Exception as exc:
        print(f"[WARN] Failed to initialize DB table proposals_registry: {exc}")
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
def buy_model(model_id: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    models = _get_all_models()
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

    runtime_passkey = _generate_runtime_passkey()
    buyer = str((body or {}).get("buyer", "")).strip() or "Anonymous Buyer"
    owner_name = str(model.get("creator", "")).strip() or "Unknown Owner"
    model_name = str(model.get("name", "")).strip() or "Unnamed Model"

    try:
        _store_passkey_in_db(
            model_id=model_id,
            model_name=model_name,
            model_owner=owner_name,
            buyer=buyer,
            passkey=runtime_passkey,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to store passkey in DB: {exc}")

    model["purchased"] = True
    model["downloaded_at"] = datetime.utcnow().isoformat() + "Z"
    model["local_model_path"] = str(local_path)
    model["runtime_passkey"] = runtime_passkey
    model["passkey_generated_at"] = datetime.utcnow().isoformat() + "Z"
    try:
        _save_model_record(model)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update model purchase status: {exc}")

    return {
        "success": True,
        "message": "Model purchased and downloaded locally",
        "model_id": model_id,
        "model_name": model_name,
        "owner": owner_name,
        "buyer": buyer,
        "ipfs_hash": ipfs_hash,
        "local_model_path": str(local_path),
        "passkey": runtime_passkey,
    }


@app.get("/api/models/purchased")
def list_purchased_models() -> Dict[str, Any]:
    purchased = [_public_model_view(m) for m in _get_all_models() if m.get("purchased")]
    return {"models": purchased}


@app.post("/api/models/{model_id}/predict")
def predict_with_model(model_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    models = _get_all_models()
    model_idx = _find_model_index(models, model_id)
    if model_idx < 0:
        raise HTTPException(status_code=404, detail="Model not found")

    model = models[model_idx]
    local_model_path = str(model.get("local_model_path", "")).strip()
    if not model.get("purchased") or not local_model_path:
        raise HTTPException(status_code=400, detail="Model must be bought first")
    if not Path(local_model_path).exists():
        raise HTTPException(status_code=400, detail="Local model file missing. Buy again to download it")

    provided_passkey = str(body.get("passkey", "")).strip()
    if not provided_passkey:
        raise HTTPException(status_code=400, detail="Passkey is required to run this model")

    db_url = _normalized_database_url()
    if db_url:
        try:
            if not _is_passkey_valid_in_db(model_id, provided_passkey):
                raise HTTPException(status_code=403, detail="Invalid passkey")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Passkey verification failed: {exc}")
    else:
        expected_passkey = str(model.get("runtime_passkey", "")).strip()
        if not expected_passkey:
            raise HTTPException(status_code=400, detail="Passkey missing for this model. Buy again to generate one")
        if provided_passkey != expected_passkey:
            raise HTTPException(status_code=403, detail="Invalid passkey")

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
async def predict_with_image(
    model_id: str,
    image: UploadFile = File(...),
    passkey: str = Form(...),
) -> Dict[str, Any]:
    models = _get_all_models()
    model_idx = _find_model_index(models, model_id)
    if model_idx < 0:
        raise HTTPException(status_code=404, detail="Model not found")

    model = models[model_idx]
    local_model_path = str(model.get("local_model_path", "")).strip()
    if not model.get("purchased") or not local_model_path:
        raise HTTPException(status_code=400, detail="Model must be bought first")
    if not Path(local_model_path).exists():
        raise HTTPException(status_code=400, detail="Local model file missing. Buy again to download it")

    provided_passkey = str(passkey or "").strip()
    if not provided_passkey:
        raise HTTPException(status_code=400, detail="Passkey is required to run this model")

    db_url = _normalized_database_url()
    if db_url:
        try:
            if not _is_passkey_valid_in_db(model_id, provided_passkey):
                raise HTTPException(status_code=403, detail="Invalid passkey")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Passkey verification failed: {exc}")
    else:
        expected_passkey = str(model.get("runtime_passkey", "")).strip()
        if not expected_passkey:
            raise HTTPException(status_code=400, detail="Passkey missing for this model. Buy again to generate one")
        if provided_passkey != expected_passkey:
            raise HTTPException(status_code=403, detail="Invalid passkey")

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