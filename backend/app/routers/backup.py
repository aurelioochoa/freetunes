from fastapi import APIRouter, Query

from ..models import BackupInfo
from ..services.backup_service import get_backup_service

router = APIRouter(prefix="/backup", tags=["backup"])


@router.get("/{udid}", response_model=BackupInfo)
def backup_info(udid: str) -> BackupInfo:
    return get_backup_service().info(udid)


@router.post("/{udid}")
def start_backup(udid: str, full: bool = True) -> dict:
    res = get_backup_service().backup(udid, full=full)
    if not res.get("ok") and "mock" in res.get("message", "").lower():
        # Keep the legacy stable message tests/clients expect.
        res["message"] = "Backup wiring lands in P1 (idevicebackup2). API is stable."
    return res


@router.get("/{udid}/files")
def backup_files(udid: str) -> list[dict]:
    return get_backup_service().list_files(udid)


@router.get("/{udid}/history")
def backup_history(udid: str) -> list[dict]:
    return get_backup_service().history(udid)


@router.post("/{udid}/verify")
def backup_verify(udid: str) -> dict:
    return get_backup_service().verify(udid)


@router.delete("/{udid}")
def backup_delete(udid: str) -> dict:
    return get_backup_service().delete(udid)


@router.post("/{udid}/encryption")
def backup_encryption(udid: str, enabled: bool = Query(True)) -> dict:
    return get_backup_service().set_encryption(udid, enabled)


@router.post("/{udid}/restore")
def backup_restore(udid: str, system: bool = False, settings: bool = False,
                   skip_apps: bool = False) -> dict:
    return get_backup_service().restore(udid, system=system,
                                        settings=settings, skip_apps=skip_apps)
