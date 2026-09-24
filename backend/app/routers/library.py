from fastapi import APIRouter, Query

from ..models import Track
from ..services.sync_plan import scan_books, scan_music

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/music", response_model=list[Track])
def music(path: str = Query(..., description="Local music dir")) -> list[Track]:
    return scan_music(path)


@router.get("/books", response_model=list[Track])
def books(path: str = Query(..., description="Local books dir")) -> list[Track]:
    return scan_books(path)
