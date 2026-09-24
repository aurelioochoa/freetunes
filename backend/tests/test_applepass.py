"""Apple-design pass contract tests: favicon, responsive CSS, device panel,
app presence in sidebar, refresh + copy actions.
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "frontend", "src")
PUBLIC = os.path.join(ROOT, "frontend", "public")
CSS = os.path.join(SRC, "apple.css")
APP = os.path.join(SRC, "App.tsx")
HTML = os.path.join(ROOT, "frontend", "index.html")
SIDEBAR = os.path.join(SRC, "components", "Sidebar.tsx")
PANEL = os.path.join(SRC, "components", "DevicePanel.tsx")
API = os.path.join(SRC, "api.ts")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def test_favicon_exists_and_linked():
    fav = os.path.join(PUBLIC, "favicon.svg")
    assert os.path.isfile(fav), "missing public/favicon.svg"
    with open(fav) as f:
        assert "<svg" in f.read(600)
    html = _read(HTML).lower()
    assert "favicon.svg" in html, "index.html must link the favicon"
    assert "theme-color" in html


def test_responsive_drawer_and_table():
    css = _read(CSS)
    assert re.search(r"@media\s*\([^)]*max-width", css), "responsive breakpoints"
    assert "ft-backdrop" in css, "drawer needs a tap-to-close backdrop"
    assert re.search(r"\.ft-table\s*\{[^}]*overflow-x:\s*auto", css), \
        "wide tables must scroll, not squeeze"


def test_device_panel():
    assert os.path.isfile(PANEL), "missing DevicePanel component"
    panel = _read(PANEL)
    for field in ("battery", "serial", "storage", "UDID"):
        assert field.lower() in panel.lower(), f"panel must show {field}"
    assert "clipboard" in panel.lower(), "UDID needs a copy button"
    assert "DevicePanel" in _read(APP), "App must render the panel"


def test_sidebar_shows_app_presence():
    sidebar = _read(SIDEBAR)
    assert "installed" in sidebar.lower(), "sidebar must reflect installed state"
    assert "not-installed" in _read(CSS), "missing apps need a dimmed style"


def test_refresh_action():
    app = _read(APP)
    assert 'aria-label="Refresh' in app, "manual refresh button"


def test_banner_has_bottom_spacing():
    css = _read(CSS)
    banner = re.search(r"(?m)^\.ft-devbanner\s*\{([^}]*)\}", css)
    assert banner, "missing .ft-devbanner rule"
    body = banner.group(1)
    m = re.search(r"margin\s*:\s*([^;]+);", body)
    assert m, "banner needs an explicit margin"
    parts = m.group(1).split()
    bottom = parts[2] if len(parts) >= 3 else parts[0]
    assert bottom != "0", "banner needs breathing room above the header"


def test_deep_linkable_views():
    assert "location.hash" in _read(APP), "views must be deep-linkable (#/device)"
    assert "Pick a section" in _read(APP), "unknown hash must not render undefined"


def test_storage_human_units():
    # StorageBar.tsx is gone; the header's storage chip owns the label now.
    header = _read(os.path.join(SRC, "components", "DeviceHeader.tsx"))
    assert re.search(r"\(device\.storage_available / 1e9\)\.toFixed\(1\)\} GB free",
                     header), "1.04 GB free must not render as a bare byte count"


def test_header_shows_battery_status_and_eta():
    header = _read(os.path.join(SRC, "components", "DeviceHeader.tsx"))
    assert "battery" in header.lower(), "header needs a battery pill"
    assert "to full" in header.lower() or "eta" in header.lower(), \
        "header must show time until full charge"
    assert "battery_eta_min" in _read(API), "API must carry the estimate"
