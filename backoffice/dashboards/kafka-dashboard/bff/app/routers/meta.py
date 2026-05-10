"""Read-only metadata endpoints for the FE (owners list, etc)."""

from fastapi import APIRouter, Depends

from ..deps import require_reader
from ..owners import load_owners

router = APIRouter(tags=["meta"])


@router.get("/_owners", dependencies=[Depends(require_reader)])
def list_owners() -> dict:
    """Return owners loaded from owners.yaml for FE dropdown."""
    owners = load_owners()
    return {
        "items": [o.model_dump() for o in owners],
        "total": len(owners),
    }
