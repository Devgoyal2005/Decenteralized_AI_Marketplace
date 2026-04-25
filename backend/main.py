"""
DAMM Backend — Decentralized AI Model Marketplace API.

This is the application entry point. All business logic lives in the
sub-modules (config, database, blockchain, ipfs, utils) and route files
under the routes/ package.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import CORS_ORIGINS
from backend.database import (
    _init_models_table,
    _init_proposals_table,
    _init_nft_licenses_table,
    _bootstrap_json_registries_to_db,
)

# ── Route routers ─────────────────────────────────────────────
from backend.routes.models import router as models_router
from backend.routes.licenses import router as licenses_router
from backend.routes.predict import router as predict_router
from backend.routes.dashboard import router as dashboard_router
from backend.routes.proposals import router as proposals_router

# ── App ───────────────────────────────────────────────────────

app = FastAPI(title="DAMM API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all route groups
app.include_router(models_router)
app.include_router(licenses_router)
app.include_router(predict_router)
app.include_router(dashboard_router)
app.include_router(proposals_router)


# ── Startup ───────────────────────────────────────────────────


@app.on_event("startup")
def _startup_init() -> None:
    for init_fn, label in [
        (_init_models_table, "models_registry"),
        (_init_proposals_table, "proposals_registry"),
        (_init_nft_licenses_table, "nft_licenses"),
        (_bootstrap_json_registries_to_db, "bootstrap_json"),
    ]:
        try:
            init_fn()
        except Exception as exc:
            print(f"[WARN] Startup init ({label}) failed: {exc}")


# ── Test / Debug ──────────────────────────────────────────────


@app.get("/test")
def test_endpoint():
    return {"message": "Test endpoint is working!"}