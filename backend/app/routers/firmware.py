from fastapi import APIRouter, Query

from ..models import FirmwareBuild, FlashDryRunRequest
from ..services.firmware import flash_dry_run, signed_firmwares

router = APIRouter(tags=["firmware"])


@router.get("/firmware/signed", response_model=list[FirmwareBuild])
def signed(product: str = Query(..., description="ProductType e.g. iPhone14,5")) -> list[FirmwareBuild]:
    return signed_firmwares(product)


@router.post("/flash/dry-run")
def dry_run(req: FlashDryRunRequest) -> dict:
    return flash_dry_run(req.udid, req.ipsw, req.mode, req.confirm)
