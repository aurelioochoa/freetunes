"""Device service tests (TDD): real usbmuxd listing with graceful fallback.

The runner is injectable so tests never need a physical iPhone.
"""
import pytest

from app.services.devices import (
    PRODUCT_MODEL,
    DeviceService,
    FakeRunner,
    parse_udids,
)


def _ok_runner() -> FakeRunner:
    return FakeRunner({
        ("idevice_id", "-l"): (0, "00008110-0014158C0E9B601E\n", ""),
        ("idevicepair", "validate"): (0, "SUCCESS\n", ""),
        ("ideviceinfo", "-u", "00008110-0014158C0E9B601E",
         "-k", "DeviceName"): (0, "Aurelio's iPhone\n", ""),
        ("ideviceinfo", "-u", "00008110-0014158C0E9B601E",
         "-k", "ProductVersion"): (0, "26.0.1\n", ""),
        ("ideviceinfo", "-u", "00008110-0014158C0E9B601E",
         "-k", "ProductType"): (0, "iPhone14,5\n", ""),
    })


def test_parse_udids():
    assert parse_udids("AAA\nBBB\n") == ["AAA", "BBB"]
    assert parse_udids("") == []


def test_list_real_device():
    svc = DeviceService(runner=_ok_runner(), available=True)
    devices = svc.list_devices()
    assert len(devices) == 1
    d = devices[0]
    assert d.udid == "00008110-0014158C0E9B601E"
    assert d.name == "Aurelio's iPhone"
    assert d.ios_version == "26.0.1"
    assert d.trusted is True
    assert d.model_id == "iphone-13"


def test_no_device_gives_empty_list():
    svc = DeviceService(runner=FakeRunner({("idevice_id", "-l"): (0, "", "")}),
                        available=True)
    assert svc.list_devices() == []


def test_tools_missing_falls_back_to_empty():
    svc = DeviceService(runner=FakeRunner({}), available=False)
    assert svc.list_devices() == []


def test_unpaired_device_not_trusted():
    runner = _ok_runner()
    runner.outputs[("idevicepair", "validate")] = (1, "", "not paired")
    svc = DeviceService(runner=runner, available=True)
    assert svc.list_devices()[0].trusted is False


def test_pair_triggers_trust_prompt_and_reports_trust():
    runner = FakeRunner({
        ("idevicepair", "pair", "-u", "U1"): (0, "SUCCESS\n", ""),
        ("idevicepair", "validate", "-u", "U1"): (0, "SUCCESS\n", ""),
    })
    svc = DeviceService(runner=runner, available=True)
    res = svc.pair("U1")
    assert res["ok"] is True and res["trusted"] is True


def test_pair_failure_guides_user_to_tap_trust():
    runner = FakeRunner({("idevicepair", "pair", "-u", "U1"): (1, "", "User denied pairing")})
    # fallback legacy argv also fails
    svc = DeviceService(runner=runner, available=True)
    res = svc.pair("U1")
    assert res["ok"] is False
    assert "Trust" in res["message"]


def test_pair_unavailable_in_mock_mode():
    svc = DeviceService(runner=FakeRunner({}), available=False)
    res = svc.pair("U1")
    assert res["ok"] is False and "trusted" in res


@pytest.mark.parametrize("product,model", [
    ("iPhone14,5", "iphone-13"),   # 13 / 13 mini family
    ("iPhone14,2", "iphone-13"),   # 13 Pro (same picker art)
    ("iPhone13,2", "iphone-13"),   # 12 (notch+Lightning, same art)
    ("iPhone14,7", "iphone-14"),   # 14
    ("iPhone15,2", "iphone-15"),   # 15
    ("iPhone17,2", "iphone-16-pro"),
    ("iPhone99,9", "iphone-15"),   # unknown future → sensible default
])
def test_product_type_mapping(product: str, model: str):
    assert PRODUCT_MODEL.get(product, "iphone-15") == model
