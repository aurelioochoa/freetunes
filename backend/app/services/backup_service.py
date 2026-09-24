"""Real backup/restore wiring around `idevicebackup2` (strict-FOSS path).

Mock mode (FREETUNES_MOCK=1 or tool missing) returns safe stubs so the
API stays stable and tests stay hermetic. Passwords are never taken on
the CLI — callers pass them via the BACKUP_PASSWORD env var, matching
upstream guidance.
"""
from __future__ import annotations

import datetime
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..models import BackupInfo, BackupRecord
from .devices import Completed, SubprocessRunner


def default_backup_root() -> Path:
    return Path.home() / "freetunes-backups"


def _parse_info(stdout: str) -> dict:
    out: dict[str, str] = {}
    for line in stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


KEY_FILES = {"Info.plist", "Manifest.db", "Manifest.plist", "Status.plist", "Manifest.mbdb"}


def _iso_from_mtime(ts: float) -> str:
    try:
        return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()
    except (OSError, ValueError, OverflowError):
        return ""


@dataclass
class BackupService:
    runner: SubprocessRunner | object = field(default_factory=SubprocessRunner)
    backup_root: Path = field(default_factory=default_backup_root)
    available: bool | None = None

    def __post_init__(self) -> None:
        if self.available is None:
            mock = os.environ.get("FREETUNES_MOCK", "0") == "1"
            self.available = (not mock) and shutil.which("idevicebackup2") is not None

    def _dir(self, udid: str) -> Path:
        safe = "".join(c for c in (udid or "unknown") if c.isalnum() or c in ("-", "_")).strip() or "unknown"
        d = Path(self.backup_root) / safe
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _scan(self, d: Path) -> dict:
        size = 0
        count = 0
        latest: float | None = None
        has_manifest = False
        try:
            entries = list(d.iterdir())
        except OSError:
            return {"size_bytes": 0, "file_count": 0, "last": None, "has_manifest": False}
        for p in entries:
            try:
                if p.is_file(follow_symlinks=False):
                    st = p.stat()
                    size += st.st_size
                    count += 1
                    if p.name in KEY_FILES:
                        has_manifest = True
                    if latest is None or st.st_mtime > latest:
                        latest = st.st_mtime
                elif p.is_dir():
                    # Shallow walk: one level is enough for idevicebackup2 layouts
                    # without risking a multi-GB recursive stat on every poll.
                    for sub in p.iterdir():
                        try:
                            if sub.is_file(follow_symlinks=False):
                                st = sub.stat()
                                size += st.st_size
                                count += 1
                        except OSError:
                            continue
            except OSError:
                continue
        last = _iso_from_mtime(latest) if latest else None
        # A directory with only stray files but no manifest is not a backup.
        return {"size_bytes": size, "file_count": count, "last": last,
                "has_manifest": has_manifest}

    def info(self, udid: str) -> BackupInfo:
        d = self._dir(udid)
        disk = self._scan(d)
        if not self.available:
            return BackupInfo(udid=udid, last_backup=disk["last"], encrypted=False,
                              backup_dir=str(d), available=False,
                              size_bytes=disk["size_bytes"], file_count=disk["file_count"],
                              has_manifest=disk["has_manifest"])
        r: Completed = self.runner.run(  # type: ignore[union-attr]
            "idevicebackup2", "-u", udid, "info", str(d), timeout=30)
        parsed = _parse_info(r.stdout or "")
        last = parsed.get("last backup") or parsed.get("last_backup") or disk["last"]
        enc_raw = (parsed.get("encrypted") or parsed.get("encryption") or "").lower()
        encrypted = enc_raw in ("true", "yes", "on", "1")
        # Manifest on disk corroborates encryption only via tool output; keep tool as source.
        return BackupInfo(
            udid=udid,
            last_backup=last,
            encrypted=encrypted,
            backup_dir=str(d),
            available=True,
            size_bytes=disk["size_bytes"],
            file_count=disk["file_count"],
            has_manifest=disk["has_manifest"],
        )

    def history(self, udid: str) -> list[dict]:
        """Local backup inventory: key files + sizes, newest first."""
        d = self._dir(udid)
        rows: list[BackupRecord] = []
        try:
            entries = sorted(d.iterdir(), key=lambda p: p.name)
        except OSError:
            return []
        for p in entries:
            try:
                if not p.is_file(follow_symlinks=False):
                    continue
                st = p.stat()
                rows.append(BackupRecord(
                    name=p.name, path=str(p), size_bytes=st.st_size,
                    mtime=_iso_from_mtime(st.st_mtime),
                    is_key_file=p.name in KEY_FILES,
                ))
            except OSError:
                continue
        rows.sort(key=lambda r: (r.is_key_file, r.mtime or ""), reverse=True)
        return [r.model_dump() for r in rows[:200]]

    def list_files(self, udid: str) -> list[dict]:
        if self.available:
            d = self._dir(udid)
            r: Completed = self.runner.run(  # type: ignore[union-attr]
                "idevicebackup2", "-u", udid, "list", str(d), timeout=60)
            if r.returncode == 0:
                rows: list[dict] = []
                for line in (r.stdout or "").splitlines():
                    line = line.strip()
                    if not line or line.lower().startswith("filename"):
                        continue
                    parts = [p.strip() for p in line.split(",")]
                    rows.append({"filename": parts[0], "size": parts[1] if len(parts) > 1 else ""})
                return rows[:2000]
            # Tool failed (no backup yet?) — fall through to disk listing.
        d = self._dir(udid)
        disk_rows: list[dict] = []
        try:
            for p in sorted(d.iterdir(), key=lambda p: p.name):
                try:
                    if p.is_file(follow_symlinks=False):
                        disk_rows.append({"filename": p.name, "size": str(p.stat().st_size)})
                except OSError:
                    continue
        except OSError:
            return []
        return disk_rows[:2000]

    def verify(self, udid: str) -> dict:
        d = self._dir(udid)
        disk = self._scan(d)
        problems: list[str] = []
        if not disk["has_manifest"]:
            problems.append("No backup manifest on disk (Info.plist / Manifest.db missing) — run a backup first.")
        if disk["file_count"] == 0:
            problems.append("Backup folder is empty.")
        tool_ok: bool | None = None
        tool_out = ""
        if self.available:
            r: Completed = self.runner.run(  # type: ignore[union-attr]
                "idevicebackup2", "-u", udid, "info", str(d), timeout=30)
            tool_ok = r.returncode == 0
            tool_out = (r.stdout or "")[-2000:]
            if not tool_ok:
                problems.append("idevicebackup2 info refused the folder — it may belong to another device or need BACKUP_PASSWORD.")
        ok = not problems
        return {"ok": ok, "udid": udid, "backup_dir": str(d),
                "size_bytes": disk["size_bytes"], "file_count": disk["file_count"],
                "has_manifest": disk["has_manifest"], "tool_ok": tool_ok,
                "problems": problems, "output": tool_out,
                "message": "Backup looks complete." if ok else "; ".join(problems)}

    def delete(self, udid: str) -> dict:
        d = self._dir(udid)
        try:
            count = sum(1 for _ in d.iterdir())
        except OSError:
            count = 0
        try:
            shutil.rmtree(d)
            d.mkdir(parents=True, exist_ok=True)
            return {"ok": True, "udid": udid, "removed_entries": count,
                    "backup_dir": str(d), "message": f"Deleted local backup ({count} entries)."}
        except OSError as e:
            return {"ok": False, "udid": udid, "message": f"Delete failed: {e}"}

    def backup(self, udid: str, full: bool = True) -> dict:
        if not self.available:
            return {"ok": False, "udid": udid, "full": full,
                    "message": "Backup tool unavailable (mock mode or idevicebackup2 missing)."}
        d = self._dir(udid)
        # Pre-flight: need a reachable device folder, not just the tool.
        try:
            free = shutil.disk_usage(d).free
        except OSError:
            free = -1
        args = ["idevicebackup2", "-u", udid, "backup"]
        if full:
            args.append("--full")
        args.append(str(d))
        started = time.monotonic()
        r: Completed = self.runner.run(*args, timeout=3600)  # type: ignore[union-attr]
        elapsed = time.monotonic() - started
        disk = self._scan(d)
        base: dict = {"ok": r.returncode == 0, "udid": udid, "full": full,
                      "output": (r.stdout or "")[-4000:], "error": (r.stderr or "")[-2000:],
                      "elapsed_s": round(elapsed, 1),
                      "size_bytes": disk["size_bytes"], "file_count": disk["file_count"],
                      "free_bytes": free}
        if r.returncode != 0 and not base["error"] and not base["output"]:
            base["hint"] = "No output — unlock the iPhone, tap Trust, and keep the cable in."
        return base

    def restore(self, udid: str, system: bool = False, settings: bool = False,
                skip_apps: bool = False, copy: bool = True) -> dict:
        if not self.available:
            return {"ok": False, "udid": udid,
                    "message": "Restore unavailable (mock mode or idevicebackup2 missing)."}
        d = self._dir(udid)
        disk = self._scan(d)
        if not disk["has_manifest"]:
            return {"ok": False, "udid": udid,
                    "message": "Nothing to restore — no backup manifest in " + str(d) + ". Back up first."}
        args = ["idevicebackup2", "-u", udid, "restore"]
        if system:
            args.append("--system")
        if settings:
            args.append("--settings")
        if skip_apps:
            args.append("--skip-apps")
        if copy:
            args.append("--copy")
        args.append(str(d))
        r: Completed = self.runner.run(*args, timeout=3600)  # type: ignore[union-attr]
        return {"ok": r.returncode == 0, "udid": udid,
                "output": (r.stdout or "")[-4000:], "error": (r.stderr or "")[-2000:]}

    def set_encryption(self, udid: str, enabled: bool) -> dict:
        if not self.available:
            return {"ok": False, "udid": udid,
                    "message": "Encryption toggle unavailable (mock mode)."}
        d = self._dir(udid)
        cmd = "on" if enabled else "off"
        # Password comes from BACKUP_PASSWORD env, never CLI args.
        r: Completed = self.runner.run(  # type: ignore[union-attr]
            "idevicebackup2", "-u", udid, "encryption", cmd, str(d), timeout=120)
        ok = r.returncode == 0
        hint = "" if ok else " Set BACKUP_PASSWORD env if the backup needs a password."
        return {"ok": ok, "udid": udid, "encrypted": enabled,
                "output": (r.stdout or "")[-2000:], "hint": hint.strip()}


_service: BackupService | None = None


def get_backup_service() -> BackupService:
    global _service
    if _service is None:
        mock = os.environ.get("FREETUNES_MOCK", "0") == "1"
        _service = BackupService(available=False) if mock else BackupService()
    return _service


def _reset_for_tests() -> None:
    global _service
    _service = None
