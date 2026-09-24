"""Device extras + app presence tests (TDD)."""
import os

os.environ["FREETUNES_MOCK"] = "1"

from app.services import app_presence as presence_mod
from app.services.app_presence import KNOWN_APPS, AppPresence
from app.services.devices import Completed, DeviceService, FakeRunner


class FakeRunnerP:
    """Presence probe double: bundle id -> installed, counts real probes."""

    def __init__(self, mapping: dict[str, bool]) -> None:
        self.mapping = mapping
        self.calls = 0

    def probe(self, bundle_id: str) -> bool:
        self.calls += 1
        return self.mapping.get(bundle_id, False)


def _device_runner() -> FakeRunner:
    return FakeRunner({
        ("idevice_id", "-l"): (0, "UDID-1\n", ""),
        ("idevicepair", "validate"): (0, "SUCCESS\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "DeviceName"): (0, "Phone\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "ProductVersion"): (0, "26.0.1\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "ProductType"): (0, "iPhone14,5\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "ModelNumber"): (0, "MLPF3\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "SerialNumber"): (0, "SER123\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "BuildVersion"): (0, "23A355\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-q", "com.apple.disk_usage"): (
            0, "TotalDiskCapacity: 128000000000\nTotalDataAvailable: 107542908928\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-q", "com.apple.mobile.battery"): (
            0, "BatteryCurrentCapacity: 52\nBatteryIsCharging: true\n", ""),
    })


def test_extras_filled():
    svc = DeviceService(runner=_device_runner(), available=True)
    (d,) = svc.list_devices()
    assert d.model_number == "MLPF3"
    assert d.serial == "SER123"
    assert d.build == "23A355"
    assert d.storage_total == 128000000000
    assert d.storage_available == 107542908928
    assert d.battery_pct == 52
    assert d.battery_charging is True


def test_extras_failure_does_not_kill_listing():
    runner = FakeRunner({("idevice_id", "-l"): (0, "UDID-9\n", "")})
    svc = DeviceService(runner=runner, available=True)
    (d,) = svc.list_devices()
    assert d.udid == "UDID-9"
    assert d.battery_pct == -1
    assert d.storage_total == 0


# Real fixture: iPhone 13, iOS 26.0.1 — lockdown overshoots (107 GB),
# AFC FSFreeBytes matches Settings (~1.06 GB). Serial anonymized.
AFC_DEVINFO = '"FSTotalBytes": 127866785792,\n"FSFreeBytes": 1059487744,\n"FSBlockSize": 4096\n'


def _storage_runner(afc_stdout: str = AFC_DEVINFO, afc_rc: int = 0) -> FakeRunner:
    outputs = {
        ("idevice_id", "-l"): (0, "UDID-1\n", ""),
        ("idevicepair", "validate"): (0, "SUCCESS\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "DeviceName"): (0, "Phone\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "ProductVersion"): (0, "26.0.1\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "ProductType"): (0, "iPhone14,5\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "ModelNumber"): (0, "MLPF3\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "SerialNumber"): (0, "SER123\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "BuildVersion"): (0, "23A355\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-q", "com.apple.disk_usage"): (
            0, "TotalDiskCapacity: 128000000000\nTotalDataAvailable: 107495641088\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-q", "com.apple.mobile.battery"): (
            0, "BatteryCurrentCapacity: 52\nBatteryIsCharging: true\n", ""),
        ("afcclient", "-u", "UDID-1"): (afc_rc, afc_stdout, ""),
    }
    return FakeRunner(outputs)


def test_storage_prefers_afc_free_over_lockdown():
    svc = DeviceService(runner=_storage_runner(), available=True)
    (d,) = svc.list_devices()
    assert d.storage_available == 1059487744, \
        "must match Settings (~1.06 GB), not lockdown TotalDataAvailable (107 GB)"
    assert d.storage_total == 128000000000


def test_storage_falls_back_to_lockdown_when_afc_fails():
    svc = DeviceService(runner=_storage_runner(afc_stdout="", afc_rc=1),
                        available=True)
    (d,) = svc.list_devices()
    assert d.storage_available == 107495641088


def test_storage_falls_back_on_garbage_afc_output():
    svc = DeviceService(runner=_storage_runner(afc_stdout="ERROR: nope\n"),
                        available=True)
    (d,) = svc.list_devices()
    assert d.storage_available == 107495641088


class CountingRunner(FakeRunner):
    def __init__(self, outputs) -> None:
        super().__init__(outputs)
        self.calls: list = []

    def run(self, *args, timeout=15, stdin=None):
        self.calls.append(args[0])
        return super().run(*args, timeout=timeout, stdin=stdin)


def test_device_list_is_cached_briefly():
    runner = CountingRunner({("idevice_id", "-l"): (0, "U\n", "")})
    svc = DeviceService(runner=runner, available=True)
    svc.list_devices()
    svc.list_devices()
    assert runner.calls.count("idevice_id") == 1, \
        "a sleeping phone must not be hammered on every UI poll"


class TimeoutRecordingRunner(FakeRunner):
    def __init__(self) -> None:
        super().__init__({("idevice_id", "-l"): (0, "U\n", "")})
        self.timeouts: dict = {}

    def run(self, *args, timeout=15, stdin=None):
        self.timeouts[args] = timeout
        if args[0] == "afcclient":
            return Completed(1, "", "locked?")
        return super().run(*args, timeout=timeout, stdin=stdin)


def test_afc_probe_times_out_fast():
    runner = TimeoutRecordingRunner()
    DeviceService(runner=runner, available=True).list_devices()
    key = ("afcclient", "-u", "U")
    assert key in runner.timeouts, "AFC must be probed for Settings-grade numbers"
    assert runner.timeouts[key] <= 10, \
        "a locked phone hangs AFC — fail fast back to lockdown values"


class StdinRecordingRunner(FakeRunner):
    def __init__(self) -> None:
        super().__init__({("idevice_id", "-l"): (0, "U\n", "")})
        self.stdins: dict = {}

    def run(self, *args, timeout=15, stdin=None):
        self.stdins[args] = stdin
        if args[0] == "afcclient":
            return Completed(0, '"FSFreeBytes": 42,\n', "")
        return super().run(*args, timeout=timeout, stdin=stdin)


def test_afc_session_quits_cleanly():
    """afcclient idles forever on EOF — it must be told `quit`, else every
    poll leaks a hung process that wedges later probes."""
    runner = StdinRecordingRunner()
    DeviceService(runner=runner, available=True).list_devices()
    stdin = runner.stdins.get(("afcclient", "-u", "U"), "")
    assert "devinfo" in stdin and "quit" in stdin


def test_presence_installed_and_missing():
    runner = FakeRunnerP({
        "org.videolan.vlc-ios": True,
        "com.readest.readest": False,
    })
    p = AppPresence(runner=runner, ttl_seconds=60)
    assert p.is_installed("org.videolan.vlc-ios") is True
    assert p.is_installed("com.readest.readest") is False


def test_presence_caches_within_ttl():
    runner = FakeRunnerP({"org.videolan.vlc-ios": True})
    p = AppPresence(runner=runner, ttl_seconds=60)
    assert p.is_installed("org.videolan.vlc-ios") is True
    assert runner.calls == 1
    assert p.is_installed("org.videolan.vlc-ios") is True
    assert runner.calls == 1, "second check must come from cache"


def test_known_apps_targets():
    ids = {b for b, _ in KNOWN_APPS}
    assert ids == {"org.videolan.vlc-ios", "com.readest.readest",
                   "com.tortugapower.BookPlayer"}


def test_apps_endpoint_reports_installed_flag():
    presence_mod._presence = AppPresence(
        runner=FakeRunnerP({"org.videolan.vlc-ios": True}), ttl_seconds=60)
    try:
        from fastapi.testclient import TestClient
        from app.main import create_app
        client = TestClient(create_app())
        apps = {a["bundle_id"]: a for a in client.get("/apps").json()}
        assert apps["org.videolan.vlc-ios"]["installed"] is True
        assert apps["com.readest.readest"]["installed"] is False
    finally:
        presence_mod._presence = None
