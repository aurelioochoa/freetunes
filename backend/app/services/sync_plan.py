"""Local library scanning + sync-plan diff (pure functions, fully tested)."""
from __future__ import annotations

import hashlib
import os

from ..models import SyncAction, SyncItem, SyncPreview, Track

MUSIC_EXTS = {".mp3", ".m4a", ".m4b", ".flac", ".opus", ".ogg", ".wav", ".aac"}
BOOK_EXTS = {".epub", ".pdf", ".mobi", ".azw3", ".fb2", ".txt", ".cbz"}


def sha256_file(path: str, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _tag(track_path: str) -> dict:
    """Best-effort metadata via mutagen; falls back to filename."""
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(track_path, easy=True)
        if audio is not None:
            def first(key: str) -> str:
                v = audio.get(key)
                return str(v[0]) if v else ""

            return {
                "title": first("title"),
                "artist": first("artist"),
                "album": first("album"),
            }
    except Exception:
        pass
    base = os.path.splitext(os.path.basename(track_path))[0]
    return {"title": base, "artist": "", "album": ""}


def scan_dir(root: str, exts: set[str]) -> list[Track]:
    tracks: list[Track] = []
    if not os.path.isdir(root):
        return tracks
    for dirpath, _, filenames in os.walk(root):
        for fn in sorted(filenames):
            if os.path.splitext(fn)[1].lower() not in exts:
                continue
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            meta = _tag(full) if exts is MUSIC_EXTS else {
                "title": os.path.splitext(fn)[0], "artist": "", "album": ""
            }
            tracks.append(
                Track(
                    path=full,
                    filename=fn,
                    title=meta["title"] or os.path.splitext(fn)[0],
                    artist=meta["artist"],
                    album=meta["album"],
                    size=size,
                    sha256=sha256_file(full),
                )
            )
    return tracks


def scan_music(root: str) -> list[Track]:
    return scan_dir(root, MUSIC_EXTS)


def scan_books(root: str) -> list[Track]:
    return scan_dir(root, BOOK_EXTS)


def plan_sync(
    local: list[Track],
    remote: dict[str, str],
    bundle_id: str,
    mirror_delete: bool = False,
) -> SyncPreview:
    """Compare local sha256 vs remote {filename: sha256}.

    - push: new or changed content
    - skip: identical sha
    - delete (only if mirror_delete): remote file absent locally
    """
    preview = SyncPreview(app_bundle_id=bundle_id)
    local_by_name = {t.filename: t for t in local}
    for name, track in sorted(local_by_name.items()):
        if remote.get(name) == track.sha256:
            preview.to_skip.append(
                SyncItem(filename=name, action=SyncAction.skip,
                         reason="identical", size=track.size)
            )
        elif name in remote:
            preview.to_push.append(
                SyncItem(filename=name, action=SyncAction.push,
                         reason="changed", size=track.size)
            )
        else:
            preview.to_push.append(
                SyncItem(filename=name, action=SyncAction.push,
                         reason="new", size=track.size)
            )
    if mirror_delete:
        for name in sorted(remote):
            if name not in local_by_name:
                preview.to_delete.append(
                    SyncItem(filename=name, action=SyncAction.delete,
                             reason="absent locally")
                )
    return preview
