"""
Proposal routes — list, submit, upvote.
"""
import uuid
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.database import (
    _db_available,
    _insert_proposal_in_db,
    _read_proposals_from_db,
    _upvote_proposal_in_db,
)
from backend.utils import (
    _read_proposals_registry,
    _write_proposals_registry,
    _recompute_proposal_acceptance,
)

router = APIRouter(prefix="/api", tags=["proposals"])


@router.get("/proposals")
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


@router.post("/proposals")
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


@router.post("/proposals/{proposal_id}/upvote")
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
