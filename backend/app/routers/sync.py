from fastapi import APIRouter

from ..models import SyncPreview, SyncRunRequest
from ..services.afc import get_afc
from ..services.sync_plan import plan_sync, scan_books, scan_music

router = APIRouter(prefix="/sync", tags=["sync"])

BOOK_BUNDLES = ("readest", "bookplayer", "books")


def _scan(music_dir: str, bundle_id: str):
    if any(k in bundle_id.lower() for k in BOOK_BUNDLES):
        return scan_books(music_dir)
    return scan_music(music_dir)


@router.post("/preview", response_model=SyncPreview)
def preview(req: SyncRunRequest) -> SyncPreview:
    afc = get_afc()
    local = _scan(req.music_dir, req.app_bundle_id)
    remote = {f.filename: f.sha256 for f in afc.list_docs(req.app_bundle_id)}
    return plan_sync(local, remote, req.app_bundle_id, req.mirror_delete)


@router.post("/run")
def run(req: SyncRunRequest) -> dict:
    afc = get_afc()
    local = _scan(req.music_dir, req.app_bundle_id)
    by_name = {t.filename: t for t in local}
    prev = preview(req)
    if req.dry_run:
        return {"dry_run": True, "pushed": [], "deleted": [],
                "preview": prev.model_dump()}
    pushed: list[str] = []
    for item in prev.to_push:
        track = by_name.get(item.filename)
        if track is None:
            continue
        afc.push(req.app_bundle_id, track.path, track.filename)
        pushed.append(item.filename)
    deleted: list[str] = []
    if req.mirror_delete:
        for item in prev.to_delete:
            afc.delete(req.app_bundle_id, item.filename)
            deleted.append(item.filename)
    return {"dry_run": False, "pushed": pushed, "deleted": deleted,
            "skipped": [i.filename for i in prev.to_skip]}
