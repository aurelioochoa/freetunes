from fastapi import APIRouter, Query

from ..models import AppInfo
from ..services.afc import RemoteFile, get_afc
from ..services.app_presence import KNOWN_APPS, get_presence

router = APIRouter(prefix="/apps", tags=["apps"])


@router.get("", response_model=list[AppInfo])
def list_apps() -> list[AppInfo]:
    presence = get_presence()
    return [AppInfo(bundle_id=bid, name=name, file_sharing=True,
                    installed=presence.is_installed(bid))
            for bid, name in KNOWN_APPS]


@router.get("/{bundle_id}/files")
def list_files(bundle_id: str) -> list[dict]:
    afc = get_afc()
    files: list[RemoteFile] = afc.list_docs(bundle_id)
    return [{"filename": f.filename, "size": f.size, "sha256": f.sha256} for f in files]


@router.delete("/{bundle_id}/files")
def delete_file(bundle_id: str, filename: str = Query(...)) -> dict:
    afc = get_afc()
    afc.delete(bundle_id, filename)
    return {"ok": True, "filename": filename}
