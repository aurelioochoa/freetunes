"""Local toolbox: audio tags, duplicates, ringtone/convert helpers.

All local-CPU, no device private APIs. External binaries (ffmpeg, PIL,
pillow-heif) are optional — endpoints return HTTP 501-style dicts with
`{"ok": False, "reason": ...}` instead of crashing when missing.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
from pathlib import Path


def edit_audio_tags(path: str, title: str | None = None,
                    artist: str | None = None, album: str | None = None) -> dict:
    if not os.path.isfile(path):
        return {"ok": False, "reason": f"not found: {path}"}
    try:
        from mutagen import File as MutagenFile
    except Exception as e:  # pragma: no cover
        return {"ok": False, "reason": f"mutagen missing: {e}"}
    try:
        audio = MutagenFile(path, easy=True)
        if audio is None:
            return {"ok": False, "reason": "unsupported audio type for tagging"}
        if title is not None:
            audio["title"] = [title]
        if artist is not None:
            audio["artist"] = [artist]
        if album is not None:
            audio["album"] = [album]
        audio.save()
        return {"ok": True, "path": path, "title": title, "artist": artist, "album": album}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_duplicates(root: str, min_size: int = 1) -> dict:
    """Group files by content hash (size pre-filter). Pure stdlib."""
    by_size: dict[int, list[str]] = {}
    if not os.path.isdir(root):
        return {"ok": False, "reason": f"not a directory: {root}"}
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if size < min_size:
                continue
            by_size.setdefault(size, []).append(full)
    groups: list[list[str]] = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_hash: dict[str, list[str]] = {}
        for p in paths:
            try:
                by_hash.setdefault(_sha256(p), []).append(p)
            except OSError:
                continue
        for members in by_hash.values():
            if len(members) > 1:
                groups.append(sorted(members))
    return {"ok": True, "root": root, "groups": sorted(groups)[:200], "count": len(groups)}


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def make_ringtone(src: str, dest: str, start_s: float = 0, end_s: float = 30) -> dict:
    if not os.path.isfile(src):
        return {"ok": False, "reason": f"not found: {src}"}
    if not (0 <= start_s < end_s <= 40):
        return {"ok": False,
                "reason": "ringtone must satisfy 0 <= start < end <= 40s (iOS limit)"}
    if not _have("ffmpeg"):
        return {"ok": False, "reason": "ffmpeg not installed — install ffmpeg for ringtone creation"}
    dur = end_s - start_s
    cmd = ["ffmpeg", "-y", "-ss", str(start_s), "-t", str(dur),
           "-i", src, "-c:a", "aac", "-b:a", "128k", dest]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "reason": str(e)}
    if p.returncode != 0:
        return {"ok": False, "reason": (p.stderr or "")[-1500:]}
    # iOS ringtone container is .m4r (AAC). If caller asked .m4r we are done;
    # otherwise note the rename hint.
    return {"ok": True, "src": src, "dest": dest, "duration_s": dur,
            "hint": "Rename to .m4r and import via GarageBand/Files on modern iOS."}


def convert_media(src: str, dest: str) -> dict:
    if not os.path.isfile(src):
        return {"ok": False, "reason": f"not found: {src}"}
    if not _have("ffmpeg"):
        return {"ok": False, "reason": "ffmpeg not installed"}
    try:
        p = subprocess.run(["ffmpeg", "-y", "-i", src, dest],
                           capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "reason": str(e)}
    if p.returncode != 0:
        return {"ok": False, "reason": (p.stderr or "")[-1500:]}
    return {"ok": True, "src": src, "dest": dest}


def compress_photo(src: str, dest: str, max_dim: int = 1920, quality: int = 80) -> dict:
    try:
        from PIL import Image
    except Exception:
        return {"ok": False, "reason": "Pillow not installed — pip install Pillow for photo compression"}
    try:
        im = Image.open(src)
        im.thumbnail((max_dim, max_dim))
        im.save(dest, quality=quality, optimize=True)
        return {"ok": True, "src": src, "dest": dest}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def heic_to_jpg(src: str, dest: str, quality: int = 90) -> dict:
    try:
        from pillow_heif import register_heif_opener  # type: ignore
        from PIL import Image
        register_heif_opener()
        im = Image.open(src)
        im.save(dest, "JPEG", quality=quality)
        return {"ok": True, "src": src, "dest": dest}
    except ImportError:
        pass
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    # No pillow-heif: same server-side decoders the preview path uses.
    try:
        from .files import decode_heic_to_jpeg
        if decode_heic_to_jpeg(Path(src), Path(dest)):
            return {"ok": True, "src": src, "dest": dest}
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    return {"ok": False, "reason": "no HEIC decoder found — pip install pillow-heif, or install heif-convert / ffmpeg"}


#: Browser uploads land here (drag-drop / browse). Served back only via
#: GET /tools/file?name=<basename> — never as raw server paths.
UPLOAD_MAX_BYTES = 500 * 1024 * 1024
UPLOAD_TTL_S = 24 * 3600


def uploads_dir() -> Path:
    root = Path(os.environ.get("FREETUNES_CACHE",
                               str(Path.home() / ".cache" / "freetunes"))) / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def sweep_uploads(max_age_s: int = UPLOAD_TTL_S) -> None:
    try:
        now = time.time()
        root = uploads_dir()
        for child in root.iterdir():
            try:
                if now - child.stat().st_mtime > max_age_s:
                    if child.is_file() or child.is_symlink():
                        child.unlink()
            except OSError:
                continue
    except OSError:
        pass


def safe_upload_name(filename: str) -> str:
    base = os.path.basename(filename or "upload").strip() or "upload"
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "upload"
    stem, dot, ext = base.partition(".")
    return f"{stem[:80]}{dot}{ext[:16]}" if dot else stem[:80]


def unique_upload_path(wanted: str) -> Path:
    """Collision-free path inside the uploads dir (no traversal possible)."""
    name = safe_upload_name(wanted)
    dest = uploads_dir() / name
    if not dest.exists():
        return dest
    stem, dot, ext = name.partition(".")
    for i in range(2, 1000):
        cand = uploads_dir() / f"{stem}-{i}{dot}{ext}" if dot else uploads_dir() / f"{stem}-{i}"
        if not cand.exists():
            return cand
    raise OSError("upload dir is full of collisions")


def save_upload_stream(filename: str, stream, chunk_size: int = 1024 * 1024) -> dict:
    """Persist an uploaded file in chunks; 413 past UPLOAD_MAX_BYTES."""
    sweep_uploads()
    dest = unique_upload_path(filename)
    written = 0
    try:
        with open(dest, "wb") as f:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > UPLOAD_MAX_BYTES:
                    f.close()
                    dest.unlink(missing_ok=True)
                    return {"ok": False, "reason": "file exceeds the 500 MB upload cap"}
                f.write(chunk)
    except OSError as e:
        return {"ok": False, "reason": str(e)}
    if written == 0:
        dest.unlink(missing_ok=True)
        return {"ok": False, "reason": "empty file — nothing uploaded"}
    return {"ok": True, "path": str(dest), "filename": dest.name,
            "size": written, "download": f"/tools/file?name={dest.name}"}


def scoped_upload(name: str) -> Path | None:
    """Resolve a download key to a file, or None (never escapes uploads)."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    cand = uploads_dir() / name
    try:
        if not cand.is_file() or cand.parent != uploads_dir():
            return None
    except OSError:
        return None
    return cand


def auto_dest_for(src: str, op: str, ext: str) -> Path:
    """Output path next to nothing — always inside uploads when auto."""
    stem = Path(src).stem[:80] or op
    return unique_upload_path(f"{stem}-{op}.{ext.lstrip('.').lower()[:8] or 'bin'}")
