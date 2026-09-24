"""Real device discovery via libimobiledevice CLI (usbmuxd/lockdown).

Falls back to an empty list when tools are missing (CI) or when
FREETUNES_MOCK=1. The runner is injectable for tests.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field

from ..models import Device
from .battery import ChargeEstimator
from .device_colors import resolve_device_color

#: ProductType (e.g. iPhone14,5) -> freetunes model catalog id (devices.ts).
#: Unknown future hardware falls back to iphone-15 (generic island art).
PRODUCT_MODEL: dict[str, str] = {
    # Home button, 3.5" Retina era
    "iPhone3,1": "iphone-4",  # 4 (GSM)
    "iPhone3,2": "iphone-4",  # 4 (GSM rev A)
    "iPhone3,3": "iphone-4",  # 4 (CDMA)
    "iPhone4,1": "iphone-4",  # 4S -> closest art
    # Notch + Lightning, iPhone 11 family (own Wikimedia art)
    "iPhone12,1": "iphone-11",  # 11
    "iPhone12,3": "iphone-11-pro",  # 11 Pro
    "iPhone12,5": "iphone-11-pro-max",  # 11 Pro Max
    "iPhone12,8": "iphone-se",  # SE 2020 (home button)
    "iPhone13,1": "iphone-13",  # 12 mini
    "iPhone13,2": "iphone-13",  # 12
    "iPhone13,3": "iphone-13",  # 12 Pro
    "iPhone13,4": "iphone-13",  # 12 Pro Max
    "iPhone14,2": "iphone-13",  # 13 Pro
    "iPhone14,3": "iphone-13",  # 13 Pro Max
    "iPhone14,4": "iphone-se",  # 13 mini -> closest small art
    "iPhone14,5": "iphone-13",  # 13
    "iPhone14,6": "iphone-se",  # SE 2022 (home button)
    "iPhone14,7": "iphone-14",  # 14
    "iPhone14,8": "iphone-14",  # 14 Plus
    "iPhone15,2": "iphone-15",  # 14 Pro
    "iPhone15,3": "iphone-15",  # 14 Pro Max
    # Dynamic Island + USB-C
    "iPhone15,4": "iphone-15",  # 15
    "iPhone15,5": "iphone-15",  # 15 Plus
    "iPhone16,1": "iphone-16-pro",  # 15 Pro
    "iPhone16,2": "iphone-16-pro",  # 15 Pro Max
    "iPhone17,1": "iphone-16-pro",  # 16 Pro
    "iPhone17,2": "iphone-16-pro",  # 16 Pro Max
    "iPhone17,3": "iphone-15",  # 16
    "iPhone17,4": "iphone-15",  # 16 Plus
    "iPhone17,5": "iphone-16-pro",  # 16e -> pro art
}

DEFAULT_MODEL = "iphone-15"


def parse_udids(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


@dataclass
class Completed:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class SubprocessRunner:
    def run(self, *args: str, timeout: int = 15,
            stdin: str | None = None) -> Completed:
        try:
            p = subprocess.run(list(args), capture_output=True, text=True,
                               timeout=timeout,
                               input=stdin if stdin is not None else None)
            return Completed(p.returncode, p.stdout, p.stderr)
        except subprocess.TimeoutExpired as e:
            # Streaming tools (idevicesyslog) never exit on their own: the
            # timeout *is* the stop condition, so the partial output captured
            # so far is the result, not an error. Decode bytes defensively —
            # e.stdout may be bytes when text=True races the kill. Report
            # success only when something was actually captured, so hung
            # one-shot commands (pair, afcclient) still read as failures.
            out = e.stdout or ""
            err = e.stderr or ""
            if isinstance(out, bytes):
                out = out.decode(errors="replace")
            if isinstance(err, bytes):
                err = err.decode(errors="replace")
            return Completed(0 if out.strip() else 1, out, err)
        except OSError as e:
            return Completed(1, "", str(e))


class FakeRunner:
    """Test double keyed by exact argv tuple (stdin is accepted, not keyed)."""

    def __init__(self, outputs: dict[tuple[str, ...], tuple[int, str, str]]) -> None:
        self.outputs = dict(outputs)

    def run(self, *args: str, timeout: int = 15,
            stdin: str | None = None) -> Completed:
        code, out, err = self.outputs.get(tuple(args), (1, "", "no stub"))
        return Completed(code, out, err)


@dataclass
class DeviceService:
    runner: SubprocessRunner | FakeRunner = field(
        default_factory=SubprocessRunner)
    available: bool | None = None
    #: Seconds a listing stays valid. The UI polls every 5 s; without this a
    #: sleeping phone would collect one hung probe per poll.
    cache_ttl_seconds: float = 20.0
    _cached: tuple[float, list] | None = field(default=None, repr=False)
    #: Serializes full probes: a hard reload fires /devices + /diagnostics/*
    #: at once and each calls list_devices(); without this they all probe
    #: usbmuxd/lockdown concurrently and contend.
    _lock: threading.RLock = field(default_factory=threading.RLock,
                                   repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.available is None:
            self.available = shutil.which("idevice_id") is not None
        lock = getattr(self, "_lock", None)
        if lock is None or not (hasattr(lock, "acquire") and hasattr(lock, "release")):
            # Instances built before this field existed (or test doubles)
            # may carry no lock — always ensure a real one.
            self._lock = threading.RLock()

    def _key(self, udid: str, key: str) -> str:
        r = self.runner.run("ideviceinfo", "-u", udid, "-k", key)
        if r.returncode != 0:
            return ""
        return r.stdout.strip()

    def _domain(self, udid: str, domain: str) -> dict[str, str]:
        r = self.runner.run("ideviceinfo", "-u", udid, "-q", domain)
        out: dict[str, str] = {}
        if r.returncode != 0:
            return out
        for line in r.stdout.splitlines():
            if ": " in line:
                k, v = line.split(": ", 1)
                out[k.strip()] = v.strip()
        return out

    @staticmethod
    def _int(value: str, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def is_trusted(self, udid: str) -> bool:
        r = self.runner.run("idevicepair", "validate", "-u", udid)
        if r.returncode == 0:
            return True
        # Older CLI validates the default device without -u; retry that way.
        r2 = self.runner.run("idevicepair", "validate")
        return r2.returncode == 0

    def pair(self, udid: str) -> dict:
        """Trigger the iOS 'Trust This Computer?' prompt via `idevicepair pair`.

        iOS shows the dialog itself — no software can show or bypass it.
        This call blocks (up to ~90 s) while the user taps Trust on the
        phone and enters the device passcode. Returns ok + fresh trust state.
        """
        if not self.available:
            return {"ok": False, "udid": udid, "trusted": False,
                    "message": "Pairing tool unavailable (mock mode or idevicepair missing)."}
        r = self.runner.run("idevicepair", "pair", "-u", udid, timeout=90)
        if r.returncode != 0:
            r = self.runner.run("idevicepair", "pair", timeout=90)
        self._cached = None  # re-probe trust on next listing
        trusted = self.is_trusted(udid) if r.returncode == 0 else False
        if r.returncode == 0 and trusted:
            return {"ok": True, "udid": udid, "trusted": True,
                    "message": "Paired — this computer is now trusted."}
        detail = ((r.stdout or "") + " " + (r.stderr or "")).strip()[-500:]
        return {"ok": False, "udid": udid, "trusted": trusted,
                "message": ("Pairing did not complete. Unlock the iPhone, tap Trust, "
                            "enter its passcode, then try again." + (f" ({detail})" if detail else ""))}

    def list_devices(self) -> list[Device]:
        if not self.available:
            return []
        now = time.monotonic()
        if self._cached is not None and now - self._cached[0] < self.cache_ttl_seconds:
            return self._cached[1]
        with self._lock:
            now = time.monotonic()
            if self._cached is not None and now - self._cached[0] < self.cache_ttl_seconds:
                return self._cached[1]
            devices = self._list_uncached()
            self._cached = (time.monotonic(), devices)
            return devices

    def _list_uncached(self) -> list[Device]:
        r = self.runner.run("idevice_id", "-l")
        if r.returncode != 0:
            return []
        devices: list[Device] = []
        for udid in parse_udids(r.stdout):
            name = self._key(udid, "DeviceName") or "iPhone"
            ios = self._key(udid, "ProductVersion") or "unknown"
            product = self._key(udid, "ProductType")
            try:
                extras = self._extras(udid, product)
            except Exception:
                extras = {}
            devices.append(Device(
                udid=udid,
                name=name,
                ios_version=ios,
                trusted=self.is_trusted(udid),
                product_type=product,
                model_id=PRODUCT_MODEL.get(product, DEFAULT_MODEL),
                **extras,
            ))
            if devices[-1].trusted and devices[-1].battery_pct >= 0:
                devices[-1].battery_eta_min = _estimator.record(
                    udid, devices[-1].battery_pct,
                    devices[-1].battery_charging, time.monotonic())
        return devices

    def _extras(self, udid: str, product: str = "") -> dict:
        disk = self._domain(udid, "com.apple.disk_usage")
        batt = self._domain(udid, "com.apple.mobile.battery")
        afc = self._afc_info(udid)
        # Since iOS 17 lockdown TotalDataAvailable overshoots what Settings
        # shows (upstream libimobiledevice#1572). AFC FSFreeBytes matches
        # Settings; fall back to the lockdown value when AFC is unreachable.
        afc_free = self._int(afc.get("FSFreeBytes", ""), -1)
        # Hardware finish: four cheap root-key probes (cached 20 s with the
        # rest of the listing). Missing keys (untrusted/old iOS) resolve to
        # ("", "") and the header hides the chip — never a wrong guess.
        color_name, color_hex = resolve_device_color(
            product,
            self._key(udid, "DeviceColor"),
            self._key(udid, "DeviceEnclosureColor"),
            self._key(udid, "DeviceRGBColor"),
            self._key(udid, "DeviceEnclosureRGBColor"),
        )
        return {
            "model_number": self._key(udid, "ModelNumber"),
            "serial": self._key(udid, "SerialNumber"),
            "hardware": self._key(udid, "HardwareModel"),
            "build": self._key(udid, "BuildVersion"),
            "storage_total": self._int(disk.get("TotalDiskCapacity", "0")),
            "storage_available": (afc_free if afc_free >= 0
                                  else self._int(disk.get("TotalDataAvailable", "0"))),
            "battery_pct": self._int(batt.get("BatteryCurrentCapacity", "-1"), -1),
            "battery_charging": batt.get("BatteryIsCharging", "").lower() == "true",
            "device_color": color_name,
            "device_color_hex": color_hex,
        }

    def _afc_info(self, udid: str) -> dict[str, str]:
        """Parse `afcclient devinfo` (`"FSFreeBytes": 123, ...`).

        The explicit `quit` is load-bearing: afcclient idles on stdin EOF
        instead of exiting, leaking one hung process per call that wedges
        later probes. Short timeout keeps the lockdown fallback fast.
        """
        r = self.runner.run("afcclient", "-u", udid, stdin="devinfo\nquit\n", timeout=8)
        if r.returncode != 0:
            return {}
        return dict(re.findall(r'"([A-Za-z]+)"\s*:\s*(\d+)', r.stdout))


_service: DeviceService | None = None

#: Process-wide charge sampler: every /devices poll feeds it one sample per
#: phone, so the ETA sharpens the longer the UI stays open.
_estimator = ChargeEstimator()


def get_service() -> DeviceService:
    """Process-wide service; mock mode forces tools-unavailable."""
    global _service
    if _service is None:
        mock = os.environ.get("FREETUNES_MOCK", "0") == "1"
        _service = DeviceService(available=False) if mock else DeviceService()
    return _service
