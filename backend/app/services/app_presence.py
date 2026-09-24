"""Target-app presence via HouseArrest: is VLC/Readest/BookPlayer installed?

Probes `afcclient --documents <bundle>`; success means the app exists,
`ApplicationLookupFailed` means it doesn't. Results are cached (default
60 s) because each probe spawns a usbmuxd round-trip.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field

#: bundle id -> display name for freetunes sync targets.
KNOWN_APPS: list[tuple[str, str]] = [
    ("org.videolan.vlc-ios", "VLC"),
    ("com.readest.readest", "Readest"),
    ("com.tortugapower.BookPlayer", "BookPlayer"),
]


class CliProbe:
    def probe(self, bundle_id: str) -> bool:
        try:
            p = subprocess.run(
                ["afcclient", "--documents", bundle_id],
                input="ls /\n", capture_output=True, text=True, timeout=12)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return p.returncode == 0 and "ApplicationLookupFailed" not in (
            p.stdout + p.stderr)


@dataclass
class AppPresence:
    runner: object = None
    ttl_seconds: int = 60
    _cache: dict = field(default_factory=dict, repr=False)

    def _probe(self, bundle_id: str) -> bool:
        if self.runner is not None:
            return bool(self.runner.probe(bundle_id))  # type: ignore[union-attr]
        return CliProbe().probe(bundle_id)

    def is_installed(self, bundle_id: str) -> bool:
        now = time.monotonic()
        hit = self._cache.get(bundle_id)
        if hit is not None and now - hit[1] < self.ttl_seconds:
            return hit[0]
        value = self._probe(bundle_id)
        self._cache[bundle_id] = (value, now)
        return value


_presence: AppPresence | None = None


def get_presence() -> AppPresence:
    global _presence
    if _presence is None:
        mock = os.environ.get("FREETUNES_MOCK", "0") == "1"
        if mock or shutil.which("afcclient") is None:
            _presence = _MockPresence()
        else:
            _presence = AppPresence()
    return _presence


class _MockPresence(AppPresence):
    def is_installed(self, bundle_id: str) -> bool:
        return True
