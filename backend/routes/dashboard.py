"""
Dashboard routes — my-uploads for creator management.
"""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from psycopg2.extras import RealDictCursor

from backend.database import _get_db_connection

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/models/my-uploads")
def get_my_uploads(wallet: str) -> Dict[str, Any]:
    """
    GET /api/models/my-uploads?wallet=0x...
    Returns a list of all models uploaded by this wallet, including sales stats.
    """
    if not wallet:
        raise HTTPException(status_code=400, detail="wallet query param is required")

    conn = _get_db_connection()
    if conn is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, data
                    FROM models_registry
                    ORDER BY updated_at DESC;
                    """
                )
                rows = cur.fetchall()

                uploads = []
                import json
                for row in rows:
                    data = row["data"]
                    if isinstance(data, str):
                        data = json.loads(data)

                    creator = str(data.get("creator", "")).strip().lower()
                    if creator != wallet.strip().lower():
                        continue

                    model_id = data.get("id", row["id"])

                    # Count sales from both tables
                    cur.execute(
                        "SELECT COUNT(*) as cnt FROM nft_licenses WHERE model_id = %s",
                        (model_id,),
                    )
                    nft_count = cur.fetchone()["cnt"]

                    cur.execute(
                        "SELECT COUNT(*) as cnt FROM model_passkeys WHERE model_id = %s",
                        (model_id,),
                    )
                    passkey_count = cur.fetchone()["cnt"]

                    sales_count = nft_count + passkey_count

                    upload_obj = dict(data)
                    upload_obj["sales_count"] = sales_count
                    uploads.append(upload_obj)

        conn.close()
        return {"uploads": uploads}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
