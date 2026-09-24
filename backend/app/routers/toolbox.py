import mimetypes
import shutil

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from ..models import DeviceOpRequest, RingtoneRequest, TagEditRequest
from ..services import toolbox as tb
from ..services.files import get_browser

router = APIRouter(prefix="/tools", tags=["toolbox"])

DEVICE_OPS = ("compress-photo", "heic-to-jpg", "convert", "ringtone", "set-tags")


def _with_download(result: dict, dest: str, auto: bool) -> dict:
    if result.get("ok") and auto:
        from pathlib import Path
        result["download"] = f"/tools/file?name={Path(dest).name}"
        result["filename"] = Path(dest).name
    return result


def _resolve_dest(src: str, dest: str, op: str, ext: str) -> tuple[str, bool]:
    if dest.strip():
        return dest.strip(), False
    auto = tb.auto_dest_for(src, op, ext)
    return str(auto), True


@router.post("/tags")
def edit_tags(req: TagEditRequest) -> dict:
    return tb.edit_audio_tags(req.path, req.title, req.artist, req.album)


@router.get("/duplicates")
def duplicates(path: str = Query(...), min_size: int = Query(1)) -> dict:
    return tb.find_duplicates(path, min_size)


@router.post("/ringtone")
def ringtone(req: RingtoneRequest) -> dict:
    dest, auto = _resolve_dest(req.src, req.dest, "ringtone", "m4r")
    return _with_download(tb.make_ringtone(req.src, dest, req.start_s, req.end_s), dest, auto)


@router.post("/convert")
def convert(src: str = Query(...), dest: str = Query("")) -> dict:
    from pathlib import Path
    want = Path(dest).suffix[1:] if dest.strip() else Path(src).suffix[1:] or "mp3"
    real_dest, auto = _resolve_dest(src, dest, "convert", want or "mp3")
    return _with_download(tb.convert_media(src, real_dest), real_dest, auto)


@router.post("/compress-photo")
def compress(src: str = Query(...), dest: str = Query(""),
             max_dim: int = Query(1920), quality: int = Query(80)) -> dict:
    from pathlib import Path
    want = Path(dest).suffix[1:] if dest.strip() else Path(src).suffix[1:] or "jpg"
    real_dest, auto = _resolve_dest(src, dest, "small", want)
    return _with_download(tb.compress_photo(src, real_dest, max_dim, quality), real_dest, auto)


@router.post("/heic-to-jpg")
def heic2jpg(src: str = Query(...), dest: str = Query("")) -> dict:
    real_dest, auto = _resolve_dest(src, dest, "converted", "jpg")
    return _with_download(tb.heic_to_jpg(src, real_dest), real_dest, auto)


@router.post("/upload")
def upload(file: UploadFile = File(...)) -> dict:
    """Accept a browser drag-drop/browse upload for toolbox inputs."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="no filename in upload")
    result = tb.save_upload_stream(file.filename, file.file)
    if not result.get("ok"):
        status = 413 if "cap" in (result.get("reason") or "") else 400
        raise HTTPException(status_code=status, detail=result.get("reason"))
    return result


@router.get("/file")
def tool_file(name: str = Query(..., description="Upload basename, e.g. tone-2.m4r")) -> FileResponse:
    """Download a toolbox result. Scoped to the uploads dir — nothing else."""
    local = tb.scoped_upload(name)
    if local is None:
        raise HTTPException(status_code=404, detail="no such toolbox file")
    media, _ = mimetypes.guess_type(local.name)
    return FileResponse(path=str(local), media_type=media or "application/octet-stream",
                        filename=local.name, content_disposition_type="inline")


@router.post("/from-device")
def from_device(req: DeviceOpRequest) -> dict:
    """Pull one iPhone file, run a toolbox op, return a download link."""
    if req.op not in DEVICE_OPS:
        return {"ok": False, "reason": f"op must be one of {list(DEVICE_OPS)}"}
    browser = get_browser()
    try:
        remote = browser.validate_remote_path(req.remote_path)
    except ValueError as e:
        return {"ok": False, "reason": str(e)}
    udid = req.udid or _first_udid()
    local = browser.pull_file(udid, remote)
    if local is None:
        return {"ok": False,
                "reason": ("Could not pull that file — plug in a trusted iPhone and retry. "
                           "Mock mode has sample names only.")}
    from pathlib import Path
    src_ext = Path(remote).suffix[1:].lower() or "bin"
    try:
        if req.op == "compress-photo":
            dest = tb.auto_dest_for(remote, "small", src_ext or "jpg")
            result = tb.compress_photo(str(local), str(dest), req.max_dim, req.quality)
        elif req.op == "heic-to-jpg":
            dest = tb.auto_dest_for(remote, "converted", "jpg")
            result = tb.heic_to_jpg(str(local), str(dest), req.quality)
        elif req.op == "convert":
            want = (req.dest_ext or "mp3").lower().strip(".")[:8] or "mp3"
            dest = tb.auto_dest_for(remote, "convert", want)
            result = tb.convert_media(str(local), str(dest))
        elif req.op == "ringtone":
            dest = tb.auto_dest_for(remote, "ringtone", "m4r")
            result = tb.make_ringtone(str(local), str(dest), req.start_s, req.end_s)
        else:  # set-tags: tag a device-side copy, hand it back for download
            dest = tb.auto_dest_for(remote, "tagged", src_ext)
            shutil.copy2(local, dest)
            result = tb.edit_audio_tags(str(dest), req.title, req.artist, req.album)
        if result.get("ok"):
            result["download"] = f"/tools/file?name={dest.name}"
            result["filename"] = dest.name
            result["source"] = remote
        return result
    finally:
        shutil.rmtree(local.parent, ignore_errors=True)


def _first_udid() -> str:
    from ..services.devices import get_service
    devs = get_service().list_devices()
    return devs[0].udid if devs else "mock-udid"
