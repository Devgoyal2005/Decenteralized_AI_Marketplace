"""
Database layer — connection management, table initialization, and all CRUD operations.
"""
import json
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.config import DATABASE_URL, REGISTRY_PATH, PROPOSALS_PATH


# ── Connection helpers ─────────────────────────────────────────


def _normalized_database_url() -> str:
    if not DATABASE_URL:
        return ""
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


# ── Table initialization ──────────────────────────────────────


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


# ── NFT License CRUD ──────────────────────────────────────────


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


# ── Model Registry CRUD ──────────────────────────────────────


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


# ── Passkey CRUD ──────────────────────────────────────────────


def _store_passkey_in_db(
    *, model_id: str, model_name: str, model_owner: str, buyer: str, passkey: str
) -> None:
    conn = _get_db_connection()
    if conn is None:
        return
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_passkeys (model_id, model_name, model_owner, buyer, passkey, purchased_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT DO NOTHING;
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


# ── Proposals CRUD ────────────────────────────────────────────


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
                    SET data = %s, upvotes = %s, updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (json.dumps(proposal), proposal["upvotes"], proposal_id),
                )
        conn.close()
        return proposal
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return None


# ── Bootstrap JSON → DB ──────────────────────────────────────


def _bootstrap_json_registries_to_db() -> None:
    """Copy local JSON registries into DB on first run so nothing is lost."""
    if not _db_available():
        return

    # Models
    if REGISTRY_PATH.exists():
        try:
            registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
            for model in registry.get("models", []):
                if str(model.get("id", "")).strip():
                    _upsert_model_in_db(model)
        except Exception as exc:
            print(f"[WARN] Failed to bootstrap models JSON into DB: {exc}")

    # Proposals
    if PROPOSALS_PATH.exists():
        try:
            proposals_reg = json.loads(PROPOSALS_PATH.read_text(encoding="utf-8"))
            for proposal in proposals_reg.get("proposals", []):
                if str(proposal.get("id", "")).strip():
                    _insert_proposal_in_db(proposal)
        except Exception as exc:
            print(f"[WARN] Failed to bootstrap proposals JSON into DB: {exc}")
