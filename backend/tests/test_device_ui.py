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


def test_app_polls_devices():
    app = _read(APP)
    assert re.search(r"setInterval\(\s*refresh\s*,", app), \
        "the device list must refresh live, not only on mount"


def test_status_banner_states():
    app = _read(APP)
    assert "ft-devbanner" in app, "connection status banner"
    assert "ft-devbanner" in _read(CSS)
    for text in ("Trust", "plug"):
        assert text.lower() in app.lower(), f"banner must guide: {text}"
