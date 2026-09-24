"""Hardware finish (iPhone color) tests: lockdown keys -> header chip.

Backend resolves lockdownd color keys to (name, hex); the header shows a
chip + subtle tint only when a hex is known, otherwise today's header.
"""
import os
import re

os.environ["FREETUNES_MOCK"] = "1"

from app.services.device_colors import normalize_hex_color, resolve_device_color
from app.services.devices import DeviceService, FakeRunner

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "frontend", "src")
HEADER = os.path.join(SRC, "components", "DeviceHeader.tsx")
CSS = os.path.join(SRC, "apple.css")
API = os.path.join(SRC, "api.ts")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _runner_with_colors(colors: dict[str, str]) -> FakeRunner:
    outputs = {
        ("idevice_id", "-l"): (0, "UDID-1\n", ""),
        ("idevicepair", "validate"): (0, "SUCCESS\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "DeviceName"): (0, "Phone\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "ProductVersion"): (0, "26.0.1\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "ProductType"): (0, "iPhone11,8\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "ModelNumber"): (0, "MLPF3\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "SerialNumber"): (0, "SER123\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-k", "BuildVersion"): (0, "23A355\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-q", "com.apple.disk_usage"): (
            0, "TotalDiskCapacity: 128000000000\nTotalDataAvailable: 107542908928\n", ""),
        ("ideviceinfo", "-u", "UDID-1", "-q", "com.apple.mobile.battery"): (
            0, "BatteryCurrentCapacity: 52\nBatteryIsCharging: true\n", ""),
        ("afcclient", "-u", "UDID-1"): (1, "", "locked"),
    }
    for key, value in colors.items():
        outputs[("ideviceinfo", "-u", "UDID-1", "-k", key)] = (0, value + "\n", "")
    return FakeRunner(outputs)


# ---- Normalization ----

def test_hex_passthrough():
    assert normalize_hex_color("#3b3b3c") == "#3b3b3c"
    assert normalize_hex_color("#ABC") == "#aabbcc"


def test_named_color():
    assert normalize_hex_color("black") == "#1d1d1f"
    assert normalize_hex_color("Midnight") == "#1e2a38"


def test_rgb_integer():
    assert normalize_hex_color("16711680") == "#ff0000"
    assert normalize_hex_color("0x00FF00") == "#00ff00"


def test_small_int_is_not_rgb():
    # Per-model color ids (1..9) would render near-black — never guess.
    assert normalize_hex_color("1") == ""
    assert normalize_hex_color("8") == ""


# ---- Resolution ----

def test_enclosure_rgb_wins_without_table():
    name, hexval = resolve_device_color("iPhone99,9", enclosure_rgb="11223344")
    assert hexval == "#ab4130"


def test_enclosure_rgb_exact():
    name, hexval = resolve_device_color("iPhone14,5", enclosure_rgb="16711680")
    assert hexval == "#ff0000"


def test_xr_coral_via_table():
    name, hexval = resolve_device_color("iPhone11,8", enclosure="8")
    assert name == "Coral"
    assert hexval == "#ff7f6b"


def test_iphone13_midnight_via_table():
    # Live unit: iPhone14,5 (iPhone 13) Midnight, MLPF3, reports id 1.
    name, hexval = resolve_device_color("iPhone14,5", front="1", enclosure="1")
    assert name == "Midnight"
    assert hexval == "#1e2a38"


def test_unknown_combo_hides():
    assert resolve_device_color("iPhone99,9", enclosure="8") == ("", "")
    assert resolve_device_color("", "", "", "", "") == ("", "")


# ---- Service wiring ----

def test_list_devices_exposes_color():
    runner = _runner_with_colors({
        "DeviceColor": "1",
        "DeviceEnclosureColor": "8",
    })
    (d,) = DeviceService(runner=runner, available=True).list_devices()
    assert d.product_type == "iPhone11,8"
    assert d.device_color == "Coral"
    assert d.device_color_hex == "#ff7f6b"


def test_missing_keys_hide_gracefully():
    runner = _runner_with_colors({})
    (d,) = DeviceService(runner=runner, available=True).list_devices()
    assert d.device_color == ""
    assert d.device_color_hex == ""


def test_api_contract_carries_color():
    from fastapi.testclient import TestClient
    from app.main import create_app
    import app.services.devices as devices_mod

    svc = DeviceService(runner=_runner_with_colors({
        "DeviceColor": "1",
        "DeviceEnclosureColor": "8",
    }), available=True)
    devices_mod._service = svc
    try:
        client = TestClient(create_app())
        (d,) = client.get("/devices").json()
        assert d["device_color"] == "Coral"
        assert d["device_color_hex"] == "#ff7f6b"
    finally:
        devices_mod._service = None


# ---- Frontend contract ----

def test_header_renders_color_chip_and_tint():
    header = _read(HEADER)
    assert "device_color_hex" in header, "header must read the live finish hex"
    assert "is-color" in header, "finish needs its own chip"
    assert "ft-color-dot" in header, "chip needs a color dot"
    assert "--device-color" in header, "header tints via a CSS variable"
    assert "data-color" in header, "tint must be scoped so unknown colors change nothing"


def test_header_validates_hex_before_css():
    header = _read(HEADER)
    assert re.search(r"#\[0-9a-f\]", header, re.IGNORECASE), \
        "raw lockdown strings must be validated before becoming CSS"


def test_header_css_has_finish_styles():
    css = _read(CSS)
    assert ".ft-chip.is-color" in css
    assert ".ft-color-dot" in css
    assert ".ft-header[data-color]" in css


def test_api_types_carry_color():
    api = _read(API)
    assert "device_color" in api and "device_color_hex" in api
