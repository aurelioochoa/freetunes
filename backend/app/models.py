from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class Device(BaseModel):
    udid: str
    name: str = "iPhone"
    ios_version: str = "unknown"
    trusted: bool = False
    product_type: str = ""
    model_id: str = ""
    model_number: str = ""
    serial: str = ""
    hardware: str = ""
    build: str = ""
    storage_total: int = 0
    storage_available: int = 0
    battery_pct: int = -1
    battery_charging: bool = False
    battery_eta_min: int | None = None
    # Hardware finish from lockdownd color keys (see services/device_colors).
    # "" means unknown/unreported — the UI hides the color chip entirely.
    device_color: str = ""
    device_color_hex: str = ""


class AppInfo(BaseModel):
    bundle_id: str = Field(description="CFBundleIdentifier, e.g. org.videolan.vlc-ios")
    name: str
    file_sharing: bool = True
    installed: bool = True


class Track(BaseModel):
    path: str
    filename: str
    title: str = ""
    artist: str = ""
    album: str = ""
    size: int = 0
    sha256: str = ""


class SyncAction(str, Enum):
    push = "push"
    skip = "skip"
    delete = "delete"


class SyncItem(BaseModel):
    filename: str
    action: SyncAction
    reason: str = ""
    size: int = 0


class SyncPreview(BaseModel):
    app_bundle_id: str
    to_push: list[SyncItem] = []
    to_skip: list[SyncItem] = []
    to_delete: list[SyncItem] = []


class SyncRunRequest(BaseModel):
    app_bundle_id: str
    music_dir: str
    mirror_delete: bool = False
    dry_run: bool = False


class BackupInfo(BaseModel):
    udid: str
    last_backup: str | None = None
    encrypted: bool = False
    backup_dir: str | None = None
    available: bool = False
    size_bytes: int = 0
    file_count: int = 0
    has_manifest: bool = False


class BackupRecord(BaseModel):
    name: str = ""
    path: str = ""
    size_bytes: int = 0
    mtime: str | None = None
    is_key_file: bool = False


class FileEntry(BaseModel):
    name: str
    path: str = ""
    is_dir: bool = False
    size: int = 0


class PhotoItem(BaseModel):
    filename: str
    path: str = ""
    size: int = 0


class StorageBreakdown(BaseModel):
    total: int = 0
    available: int = 0
    used: int = 0
    source: str = "unknown"


class CrashItem(BaseModel):
    filename: str
    size: int = 0
    app: str = ""
    date: str = ""
    # File mtime as ISO-8601 (fallback sort/display when filename has no date).
    mtime: str = ""
    # panic | jetsam | crash | unknown — classified from the filename.
    kind: str = "crash"
    # Parsed locally from the .ips JSON header ("" when unreadable).
    exception: str = ""
    reason: str = ""
    os_version: str = ""


class VerificationCheck(BaseModel):
    label: str = ""
    status: str = "info"  # pass | warn | info
    detail: str = ""


class VerificationReport(BaseModel):
    udid: str
    model_number: str = ""
    kind: str = "unknown"
    refurbished_suspect: bool = False
    details: list[str] = []
    checks: list[VerificationCheck] = []
    summary: str = ""


class FirmwareBuild(BaseModel):
    version: str = ""
    buildid: str = ""
    signed: bool = False
    url: str = ""
    filesize: int = 0


class FlashDryRunRequest(BaseModel):
    udid: str
    ipsw: str = ""
    mode: str = "quick"
    confirm: bool = False


class TagEditRequest(BaseModel):
    path: str
    title: str | None = None
    artist: str | None = None
    album: str | None = None


class RingtoneRequest(BaseModel):
    src: str
    dest: str
    start_s: float = 0
    end_s: float = 30


class DeviceOpRequest(BaseModel):
    """Run one toolbox op on an iPhone file: pull → process → download."""
    udid: str = ""
    remote_path: str = ""
    op: str = ""  # compress-photo | heic-to-jpg | convert | ringtone | set-tags
    dest_ext: str | None = None  # convert target container, e.g. mp3
    start_s: float = 0
    end_s: float = 30
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    max_dim: int = 1920
    quality: int = 80