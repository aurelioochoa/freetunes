import mimetypes
import shutil

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse

from ..services.files import get_browser, storage_breakdown, MAX_THUMB_BYTES, THUMB_PULL_TIMEOUT
from ..services.media_metadata import extract_metadata
from ..services.devices import get_service

router = APIRouter(tags=["files-photos"])


@router.get("/files/browse")
def browse(udid: str = Query(""), path: str = Query("/")) -> list[dict]:
    udid = udid or _first_udid()
    return [e.model_dump() for e in get_browser().list_dir(udid, path)]


@router.get("/photos")
def photos(udid: str = Query("")) -> list[dict]:
    udid = udid or _first_udid()
    return [p.model_dump() for p in get_browser().list_photos(udid)]


@router.get("/files/content")
def content(
    background: BackgroundTasks,
    udid: str = Query(""),
    path: str = Query(..., description="Absolute AFC path, e.g. /DCIM/IMG_0001.JPG"),
) -> FileResponse:
    """Stream one file's real bytes for image/video preview.

    Pulls via `afcclient get` into a temp dir (deleted after the
    response finishes). 404 in mock mode, when the pull fails, or past
    the preview size cap; 400 for malformed paths.
    """
    udid = udid or _first_udid()
    browser = get_browser()
    try:
        remote = browser.validate_remote_path(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    local = browser.pull_file(udid, remote)
    if local is None:
        raise HTTPException(
            status_code=404,
            detail=("No bytes available — mock mode has sample names only. "
                    "Plug in a trusted iPhone to preview the real file."))
    media, _ = mimetypes.guess_type(local.name)
    background.add_task(shutil.rmtree, str(local.parent), True)
    return FileResponse(
        path=str(local),
        media_type=media or "application/octet-stream",
        filename=local.name,
        content_disposition_type="inline",
        background=background,
    )


@router.get("/files/metadata")
def metadata(udid: str = Query(""), path: str = Query(...)) -> dict:
    """Extract embedded metadata only for the selected original file."""
    browser = get_browser()
    try:
        remote = browser.validate_remote_path(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    udid = udid or _first_udid()
    size = browser.remote_size(udid, remote) if browser.available else None
    if size is not None and size > MAX_THUMB_BYTES:
        raise HTTPException(status_code=413, detail="This file exceeds the 500 MB metadata limit. Export the original to inspect its metadata locally.")
    local = browser.pull_file(udid, remote, max_bytes=MAX_THUMB_BYTES, timeout=THUMB_PULL_TIMEOUT)
    if local is None:
        raise HTTPException(status_code=404, detail="Metadata is unavailable: the original could not be read from the iPhone, is over 500 MB, or is sample data.")
    try:
        return extract_metadata(local)
    finally:
        shutil.rmtree(local.parent, ignore_errors=True)


@router.get("/files/thumb")
def thumb(
    udid: str = Query(""),
    path: str = Query(..., description="Absolute AFC path, e.g. /DCIM/IMG_0001.JPG"),
    size: int = Query(512, ge=64, le=1024, description="Max thumbnail dimension in px"),
) -> FileResponse:
    """Small cached JPEG thumbnail for grid tiles.

    404 when there is nothing decodable to show (mock mode, HEIC without
    decoder, no ffmpeg for video, pull failed, or video over ~500 MB) —
    tiles keep their placeholder instead of breaking.
    """
    udid = udid or _first_udid()
    browser = get_browser()
    try:
        remote = browser.validate_remote_path(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    local = browser.make_thumb(udid, remote, size)
    if local is None:
        raise HTTPException(
            status_code=404,
            detail=("No thumbnail available (unsupported type, unreachable, "
                    "or video over ~500 MB — export it to view)."))
    return FileResponse(
        path=str(local),
        media_type="image/jpeg",
        filename=f"{local.stem}.jpg",
        content_disposition_type="inline",
    )


@router.get("/photos/duplicates")
def photo_duplicates(udid: str = Query("")) -> dict:
    """Byte-identical duplicate groups straight from the iPhone's DCIM.

    Size pre-filter + pull-and-hash of candidates only (capped), so it is
    the Photos equivalent of GET /tools/duplicates without exporting first.
    In mock mode returns an honest empty result (sample names carry no bytes).
    """
    udid = udid or _first_udid()
    return get_browser().find_photo_duplicates(udid)


@router.delete("/photos")
def delete_photo(udid: str = Query(""), path: str = Query(...,
                 description="Absolute AFC path, e.g. /DCIM/IMG_0001.JPG")) -> dict:
    """Delete one photo on the iPhone (best-effort via `afcclient rm`).

    DCIM is read-only on some iOS versions — then ok=False with guidance to
    delete on the phone itself. Never pretends success.
    """
    udid = udid or _first_udid()
    browser = get_browser()
    try:
        remote = browser.validate_remote_path(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not remote.lower().startswith("/dcim/"):
        raise HTTPException(status_code=400, detail="only /DCIM photos can be deleted here")
    if browser.delete_file(udid, remote):
        return {"ok": True, "udid": udid, "path": remote}
    raise HTTPException(
        status_code=409,
        detail=("Could not delete that photo — mock mode has sample names only, "
                "or this iOS version keeps DCIM read-only over USB. "
                "Delete it on the iPhone itself (Photos app)."))


@router.get("/storage/breakdown")
def breakdown(udid: str = Query("")) -> dict:
    devs = get_service().list_devices()
    dev = next((d for d in devs if not udid or d.udid == udid), devs[0] if devs else None)
    if dev is None:
        return storage_breakdown(0, 0).model_dump()
    return storage_breakdown(dev.storage_total, dev.storage_available).model_dump()


def _first_udid() -> str:
    devs = get_service().list_devices()
    return devs[0].udid if devs else "mock-udid"
