"""Device UI contract tests: live device polling, status banner, model auto-match."""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "frontend", "src")
APP = os.path.join(SRC, "App.tsx")
API = os.path.join(SRC, "api.ts")
CSS = os.path.join(SRC, "apple.css")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def test_api_has_devices_call():
    api = _read(API)
    assert re.search(r"devices:\s*\(\)", api), "api needs a devices() call"
    assert "model_id" in api and "product_type" in api


def test_app_polls_devices():
    app = _read(APP)
    assert "api.devices()" in app or "devices()" in app
    assert "setInterval" in app, "device list must refresh live"


def test_status_banner_states():
    app = _read(APP)
    assert "ft-devbanner" in app, "connection status banner"
    assert "ft-devbanner" in _read(CSS)
    for text in ("Trust", "plug"):
        assert text.lower() in app.lower(), f"banner must guide: {text}"


def test_model_auto_match():
    app = _read(APP)
    assert "model_id" in app, "auto-select placeholder art from real ProductType"
