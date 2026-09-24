"""Firmware info (signed-only) + guarded flash dry-run.

Strict-FOSS: firmware metadata comes from the public ipsw.me API;
flashing itself would shell out to `idevicerestore` (FOSS) but is
**never executed** here. `POST /flash/dry-run` only validates and
returns the exact command + safety gates. A real `/flash/run`
endpoint is intentionally deferred to Phase 5 behind
FREETUNES_ALLOW_FLASH=1 + explicit confirm + mandatory backup.
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.request

from ..models import FirmwareBuild

MODES = ("quick", "retain", "anti-recovery")


def signed_firmwares(product_type: str, timeout: int = 10) -> list[FirmwareBuild]:
    product_type = (product_type or "").strip()
    if not product_type:
        return []
    url = f"https://api.ipsw.me/v4/device/{product_type}?type=ipsw"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "freetunes/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return []
    out: list[FirmwareBuild] = []
    for fw in data.get("firmwares", []):
        try:
            out.append(FirmwareBuild(
                version=str(fw.get("version", "")),
                buildid=str(fw.get("buildid", "")),
                signed=bool(fw.get("signed", False)),
                url=str(fw.get("url", "")),
                filesize=int(fw.get("filesize", 0) or 0),
            ))
        except Exception:
            continue
    return [b for b in out if b.signed]


def flash_dry_run(udid: str, ipsw: str, mode: str, confirm: bool) -> dict:
    if mode not in MODES:
        return {"ok": False, "reason": f"mode must be one of {list(MODES)}"}
    if not ipsw:
        return {"ok": False, "reason": "ipsw path/URL required"}
    gates = [
        "Back up first (Backup view → full backup) — flash can wipe the phone.",
        "Signed firmware only — unsigned restores fail and can strand the device.",
        "Know your Apple ID password — activation lock survives flashing.",
        "Keep the cable plugged in and the screen on; never unplug mid-flash.",
    ]
    if not confirm:
        return {"ok": False, "confirmed": False, "gates": gates,
                "reason": "re-run with confirm=true after reading the safety gates"}
    tool = shutil.which("idevicerestore")
    cmd = ["idevicerestore", "-u", udid]
    if mode == "retain":
        cmd.append("--keep-data")
    if mode == "anti-recovery":
        cmd.append("--erase")
    cmd.append(ipsw)
    return {
        "ok": True,
        "confirmed": True,
        "udid": udid,
        "mode": mode,
        "command": cmd,
        "idevicerestore_found": tool is not None,
        "gates": gates,
        "note": ("DRY RUN only — nothing was flashed. Real execution lands in "
                 "Phase 5 behind FREETUNES_ALLOW_FLASH=1."),
        "allow_flash_env": os.environ.get("FREETUNES_ALLOW_FLASH", "0"),
    }
