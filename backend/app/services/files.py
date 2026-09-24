"""Generic AFC file browsing + Photos (DCIM) + storage breakdown.

Strict-FOSS: uses `afcclient` CLI when present, MockAFC sample data in
mock mode. Photo import-to-Camera-Roll over AFC is unreliable on modern
iOS — export (pull) is solid, import is best-effort with honest errors.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..models import FileEntry, PhotoItem, StorageBreakdown
from .devices import SubprocessRunner

try:
    from PIL import Image
except ImportError:  # pragma: no cover - pillow is a hard dep, guard anyway
    Image = None  # type: ignore[assignment]

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".mov", ".mp4", ".dng"}

#: Extensions browsers + Pillow decode directly (no HEIC without pillow-heif).
DECODEABLE_IMG = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
#: iPhone stills browsers cannot show; decoded server-side (pillow-heif,
#: heif-convert, or ffmpeg — first available wins) into JPEG thumbs/previews.
HEIC_EXTS = {".heic", ".heif"}
POSTER_VIDEO = {".mov", ".mp4", ".m4v"}

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".mov", ".mp4", ".dng"}

#: Refuse to pull previews bigger than this (phone stays responsive,
#: browser <video> can stream the temp file instead of buffering it all).
MAX_PREVIEW_BYTES = 100 * 1024 * 1024

#: Thumbnails only need one frame, but the whole video must still be pulled
#: over USB for ffmpeg to seek it. 100 MB covered stills but 404'd most
#: iPhone videos (106–200 MB clips are common; see grid 404s). 500 MB fixes
#: the common case; multi-GB videos still 404 honestly and the tile keeps
#: its placeholder instead of hanging the daemon.
MAX_THUMB_BYTES = 500 * 1024 * 1024
THUMB_PULL_TIMEOUT = 90

MOCK_TREE: dict[str, list[FileEntry]] = {
    "/": [
        FileEntry(name="DCIM", path="/DCIM", is_dir=True),
        FileEntry(name="Books", path="/Books", is_dir=True),
        FileEntry(name="Downloads", path="/Downloads", is_dir=True),
    ],
    "/DCIM": [
        FileEntry(name="IMG_0001.JPG", path="/DCIM/IMG_0001.JPG", size=2_400_000),
        FileEntry(name="IMG_0002.HEIC", path="/DCIM/IMG_0002.HEIC", size=1_800_000),
        FileEntry(name="VID_0003.MOV", path="/DCIM/VID_0003.MOV", size=48_000_000),
    ],
}


def _is_photo(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(e) for e in PHOTO_EXTS)


def decode_heic_to_jpeg(src: Path, dest: Path) -> bool:
    """Decode one HEIC/HEIF still into a JPEG for browser display.

    Tries pillow-heif, then the `heif-convert` CLI, then ffmpeg — returns
    True when ``dest`` is a readable image. Used by thumbnails, HEIC
    previews, and the heic-to-jpg toolbox op.
    """
    try:
        from pillow_heif import register_heif_opener  # type: ignore
        register_heif_opener()
        if Image is not None:
            with Image.open(src) as im:
                im.convert("RGB").save(dest, "JPEG", quality=90)
            if dest.is_file() and dest.stat().st_size > 0:
                return True
    except ImportError:
        pass
    except Exception:
        pass
    if shutil.which("heif-convert") is not None:
        try:
            r = subprocess.run(["heif-convert", str(src), str(dest)],
                               capture_output=True, timeout=120)
            if r.returncode == 0 and dest.is_file() and dest.stat().st_size > 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    if shutil.which("ffmpeg") is not None:
        try:
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                                "-y", "-i", str(src), "-q:v", "4", str(dest)],
                               capture_output=True, timeout=120)
            if r.returncode == 0 and dest.is_file() and dest.stat().st_size > 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    return False


@dataclass
class FileBrowser:
    runner: object = field(default_factory=SubprocessRunner)
    available: bool | None = None

    def __post_init__(self) -> None:
        if self.available is None:
            mock = os.environ.get("FREETUNES_MOCK", "0") == "1"
            self.available = (not mock) and shutil.which("afcclient") is not None

    def list_dir(self, udid: str, path: str = "/") -> list[FileEntry]:
        path = path or "/"
        if not self.available:
            return list(MOCK_TREE.get(path, MOCK_TREE["/"][:1]))
        try:
            safe = self.validate_remote_path(path)
        except ValueError:
            return []
        r = self.runner.run(  # type: ignore[union-attr]
            "afcclient", "-u", udid, stdin=f"ls -l {safe}\nquit\n", timeout=15)
        if r.returncode != 0:
            return []
        out: list[FileEntry] = []
        for line in (r.stdout or "").splitlines():
            parsed = self._parse_ls_line(line)
            if parsed is None:
                continue
            name, is_dir, size = parsed
            full = (safe.rstrip("/") + "/" + name) if safe != "/" else ("/" + name)
            out.append(FileEntry(name=name, path=full, is_dir=is_dir, size=size))
        return out[:2000]

    @staticmethod
    def _parse_ls_line(line: str) -> tuple[str, bool, int] | None:
        """Parse one `afcclient ls` output line (long `-l` or short format).

        Returns (name, is_dir, size) or None for prompt/junk lines.
        """
        s = line.strip()
        if not s or s in (".", ".."):
            return None
        if s.startswith(("afc:", "FS", "afc", "AFC", "Connected", "Device")):
            return None
        if s.startswith((">", "afc")):
            return None
        # Long format: "-rw-r--r-- 1 mobile mobile 2587780 28 Aug 2025 09:03:29 NAME"
        # or "drwxr-xr-x 2 mobile mobile 10464 17 Sep 2026 23:24:05 NAME".
        if s[0] in "-dl" and len(s) > 10 and s[10] in (" ", "\t"):
            parts = s.split(None, 9)
            if len(parts) == 10:
                perms = parts[0]
                try:
                    size = int(parts[4])
                except ValueError:
                    size = 0
                name = parts[9].strip().strip('"').strip("'")
                if not name or name in (".", ".."):
                    return None
                is_dir = perms.startswith("d")
                return (name, is_dir, 0 if is_dir else max(0, size))
        # Short format fallback (plain `ls`): bare filename per line.
        name = s.strip('"').strip("'")
        if not name or name in (".", "..") or ":" in name:
            return None
        if " " in name and len(name) > 80:
            return None
        if name.startswith(("FS", "afc", "AFC", "Connected", "Device")):
            return None
        return (name, "." not in name, 0)

    def list_photos(self, udid: str) -> list[PhotoItem]:
        if not self.available:
            return [PhotoItem(filename=f.name, path=f.path, size=f.size)
                    for f in MOCK_TREE["/DCIM"]]
        entries = self.list_dir(udid, "/DCIM")
        # Also scan one level of APPLE subfolders (100APPLE, 101APPLE…).
        extra: list[FileEntry] = []
        for e in list(entries):
            if e.is_dir:
                extra.extend(self.list_dir(udid, e.path))
        photos = [e for e in (entries + extra) if not e.is_dir and _is_photo(e.name)]
        return [PhotoItem(filename=e.name, path=e.path, size=e.size) for e in photos[:2000]]

    @staticmethod
    def validate_remote_path(path: str) -> str:
        """Normalize an AFC path or raise ValueError (traversal/malformed)."""
        p = (path or "").strip()
        if not p.startswith("/"):
            raise ValueError("path must be absolute (start with /)")
        if "\x00" in p or "\n" in p or '"' in p:
            raise ValueError("path contains illegal characters")
        parts = [seg for seg in p.split("/") if seg not in ("", ".")]
        if ".." in parts:
            raise ValueError(".. is not allowed in preview paths")
        return "/" + "/".join(parts)

    def pull_file(self, udid: str, remote_path: str,
                  max_bytes: int | None = None, timeout: int = 30) -> Path | None:
        """Pull one file from the device into a temp dir (`afcclient get`).

        Returns the local Path, or None when unavailable (mock mode),
        the pull fails, or the file exceeds ``max_bytes`` (defaults to
        MAX_PREVIEW_BYTES). Thumbnails pass a larger cap + timeout since
        one ffmpeg frame still needs the whole video locally.
        Callers own cleanup of ``path.parent``.
        """
        remote = self.validate_remote_path(remote_path)
        if not self.available:
            return None
        cap = MAX_PREVIEW_BYTES if max_bytes is None else max_bytes
        tmpdir = Path(tempfile.mkdtemp(prefix="freetunes-afc-"))
        local = tmpdir / Path(remote).name
        r = self.runner.run(  # type: ignore[union-attr]
            "afcclient", "-u", udid,
            stdin=f'get "{remote}" "{local}"\nquit\n', timeout=timeout)
        if r.returncode != 0 or not local.is_file() or local.stat().st_size == 0:
            shutil.rmtree(tmpdir, ignore_errors=True)
            return None
        if local.stat().st_size > cap:
            shutil.rmtree(tmpdir, ignore_errors=True)
            return None
        return local

    def delete_file(self, udid: str, remote_path: str) -> bool:
        """Best-effort delete of one file via `afcclient rm`.

        Returns True when the device confirmed the removal. False in mock
        mode, on traversal errors (raises ValueError instead), or when the
        device refuses — DCIM is read-only on some iOS versions, in which
        case callers must surface an honest "delete on the iPhone itself"
        message instead of pretending it worked.
        """
        remote = self.validate_remote_path(remote_path)
        if not self.available:
            return False
        r = self.runner.run(  # type: ignore[union-attr]
            "afcclient", "-u", udid,
            stdin=f'rm "{remote}"\nquit\n', timeout=15)
        if r.returncode != 0:
            return False
        self.purge_thumbs(udid, remote)
        return True

    @staticmethod
    def purge_thumbs(udid: str, remote_path: str) -> None:
        """Drop cached thumbnails for a deleted photo (all common sizes)."""
        for size in (64, 128, 256, 384, 512, 640, 1024):
            try:
                cand = FileBrowser.thumb_key(udid, remote_path, size)
                if cand.is_file():
                    cand.unlink()
            except OSError:
                continue

    def find_photo_duplicates(self, udid: str, max_hash_files: int = 200) -> dict:
        """Group byte-identical photos on the iPhone (DCIM) by content hash.

        Size pre-filter first (like the local toolbox), then pull + SHA-256
        only the candidates. Pulls are capped at ``max_hash_files`` so a
        10k-photo library can't hang the daemon; the response reports
        ``scanned``/``hashed``/``skipped`` so the UI can say what it did.
        Temp dirs are removed after each hash. Unpullable files (mock mode,
        oversize video, transient AFC error) are counted in ``skipped``.
        """
        photos = self.list_photos(udid)
        scanned = len(photos)
        if not self.available:
            return {"ok": True, "udid": udid, "groups": [], "count": 0,
                    "scanned": scanned, "hashed": 0, "skipped": 0,
                    "note": ("Sample data has no bytes to compare — "
                             "plug in a trusted iPhone to scan real photos.")}
        by_size: dict[int, list] = {}
        for p in photos:
            by_size.setdefault(p.size or 0, []).append(p)
        candidates: list = []
        for size, items in by_size.items():
            if len(items) < 2:
                continue
            # Unknown sizes (short `ls` fallback reports 0): still comparable,
            # but bound the work — hash at most max_hash_files of them.
            candidates.extend(sorted(items, key=lambda e: e.path))
        candidates = candidates[:max(1, max_hash_files)]
        by_hash: dict[str, list[dict]] = {}
        hashed = 0
        skipped = 0
        for item in candidates:
            local = self.pull_file(udid, item.path)
            if local is None:
                skipped += 1
                continue
            try:
                h = hashlib.sha256()
                with open(local, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
                digest = h.hexdigest()
                hashed += 1
            except OSError:
                skipped += 1
                continue
            finally:
                shutil.rmtree(local.parent, ignore_errors=True)
            by_hash.setdefault(digest, []).append(
                {"filename": item.filename, "path": item.path, "size": item.size})
        groups = [sorted(m, key=lambda m: m["path"])
                  for m in by_hash.values() if len(m) > 1]
        groups = sorted(groups, key=lambda g: g[0]["path"])[:200]
        # Files that shared a size but were never pulled (over the cap) count
        # as skipped so the UI doesn't claim a full-library scan it didn't do.
        size_sharing = sum(len(v) for v in by_size.values() if len(v) > 1)
        skipped += max(0, size_sharing - len(candidates))
        return {"ok": True, "udid": udid, "groups": groups, "count": len(groups),
                "scanned": scanned, "hashed": hashed, "skipped": skipped}

    @staticmethod
    def thumb_key(udid: str, remote_path: str, size: int) -> Path:
        digest = hashlib.sha1(f"{udid}\n{remote_path}\n{size}".encode()).hexdigest()
        root = Path(os.environ.get("FREETUNES_CACHE",
                                   str(Path.home() / ".cache" / "freetunes"))) / "thumbs"
        root.mkdir(parents=True, exist_ok=True)
        return root / f"{digest}.jpg"

    def remote_size(self, udid: str, remote_path: str) -> int | None:
        """Fast `afcclient info` size probe (None when unknown).

        Lets thumbnails fail fast on multi-GB videos instead of hanging a
        90 s pull that can never succeed. Fail-open: callers pull anyway
        when the probe is inconclusive.
        """
        if not self.available:
            return None
        try:
            remote = self.validate_remote_path(remote_path)
        except ValueError:
            return None
        try:
            import json
            import re
            r = self.runner.run(  # type: ignore[union-attr]
                "afcclient", "-u", udid,
                stdin=f'info "{remote}"\nquit\n', timeout=8)
            if r.returncode != 0 or not r.stdout:
                return None
            m = re.search(r"\{[^}]*\}", r.stdout, re.DOTALL)
            if not m:
                return None
            info = json.loads(m.group(0))
            size = int(info.get("st_size", -1))
            return size if size >= 0 else None
        except Exception:
            return None

    def make_thumb(self, udid: str, remote_path: str, size: int = 512) -> Path | None:
        """Small cached JPEG for grid tiles (real pixels, fast second time).

        Photos decode via Pillow; videos via one ffmpeg frame; HEIC via
        pillow-heif/heif-convert/ffmpeg. Unknown types return None — tiles
        keep their placeholder and the inspector explains why. Videos use a
        larger pull cap (MAX_THUMB_BYTES) since clips over 100 MB are common;
        files still over the cap return None (honest placeholder, no hang).
        """
        remote = self.validate_remote_path(remote_path)
        if not self.available or Image is None:
            return None
        size = max(64, min(size, 1024))
        ext = Path(remote).suffix.lower()
        if ext not in DECODEABLE_IMG and ext not in POSTER_VIDEO and ext not in HEIC_EXTS:
            return None
        if ext in POSTER_VIDEO and shutil.which("ffmpeg") is None:
            return None
        if (ext in HEIC_EXTS and shutil.which("heif-convert") is None
                and shutil.which("ffmpeg") is None):
            try:
                import pillow_heif  # noqa: F401  # type: ignore
            except ImportError:
                return None
        dest = self.thumb_key(udid, remote, size)
        if dest.is_file() and dest.stat().st_size > 0:
            return dest
        if ext in POSTER_VIDEO:
            # Fail fast on multi-GB videos: no 90 s pull that can't succeed.
            probe = self.remote_size(udid, remote)
            if probe is not None and probe > MAX_THUMB_BYTES:
                return None
            local = self.pull_file(udid, remote,
                                   max_bytes=MAX_THUMB_BYTES,
                                   timeout=THUMB_PULL_TIMEOUT)
        else:
            local = self.pull_file(udid, remote)
        if local is None:
            return None
        try:
            if ext in POSTER_VIDEO:
                frame = local.parent / "frame.jpg"
                r = subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error",
                     "-ss", "0.5", "-i", str(local),
                     "-vframes", "1", "-q:v", "4", str(frame)],
                    capture_output=True, timeout=30)
                if r.returncode != 0 or not frame.is_file():
                    return None
                local = frame
            elif ext in HEIC_EXTS:
                decoded = local.parent / "decoded.jpg"
                if not decode_heic_to_jpeg(local, decoded):
                    return None
                local = decoded
            with Image.open(local) as im:
                im.draft("RGB", (size, size))
                rgb = im.convert("RGB")
                rgb.thumbnail((size, size))
                tmp = dest.with_suffix(".tmp.jpg")
                rgb.save(tmp, "JPEG", quality=72)
                os.replace(tmp, dest)
            return dest
        except Exception:
            return None
        finally:
            shutil.rmtree(local.parent, ignore_errors=True)


def storage_breakdown(total: int, available: int) -> StorageBreakdown:
    used = max(0, total - available) if total else 0
    return StorageBreakdown(total=total, available=available, used=used,
                            source="live" if total else "sample")


_browser: FileBrowser | None = None


def get_browser() -> FileBrowser:
    global _browser
    if _browser is None:
        mock = os.environ.get("FREETUNES_MOCK", "0") == "1"
        _browser = FileBrowser(available=False) if mock else FileBrowser()
    return _browser
