"""Polish contract tests (TDD): themes, animation, iPhone model catalog,
plain-language copy, app icons, GitHub sources, docs.
"""
import os
import re

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "frontend", "src")
PUBLIC = os.path.join(ROOT, "frontend", "public")
CSS = os.path.join(SRC, "apple.css")
APP = os.path.join(SRC, "App.tsx")
TABLE = os.path.join(SRC, "components", "SyncTable.tsx")
HEADER = os.path.join(SRC, "components", "DeviceHeader.tsx")
SIDEBAR = os.path.join(SRC, "components", "Sidebar.tsx")
DEVICES = os.path.join(SRC, "devices.ts")
SOURCES = os.path.join(SRC, "sources.ts")
DOCS = os.path.join(ROOT, "docs")
README = os.path.join(ROOT, "README.md")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


# --- Themes ---
def test_theme_overrides():
    css = _read(CSS)
    assert '[data-theme="light"]' in css, "explicit light theme override"
    assert '[data-theme="dark"]' in css, "explicit dark theme override"


def test_accent_themes():
    css = _read(CSS)
    assert re.search(r'\[data-accent="[a-z]+"\][^}]*--accent', css), \
        "accent themes must set --accent"


def test_theme_picker_in_ui():
    app = _read(APP)
    assert re.search(r"[Tt]heme", app), "UI needs a theme picker"
    assert "localStorage" in app, "persist theme choice"


# --- Animation ---
def test_animations_with_reduced_motion_guard():
    css = _read(CSS)
    assert "@keyframes" in css, "expected UI animations"
    assert "prefers-reduced-motion" in css, "animations must respect reduced motion"
    assert "transition" in css


# --- iPhone models ---
def test_device_catalog():
    assert os.path.isfile(DEVICES), "missing src/devices.ts model catalog"
    catalog = _read(DEVICES)
    assert len(re.findall(r"id:\s*['\"]", catalog)) >= 3, "at least 3 iPhone models"


def test_device_art_per_model():
    catalog = _read(DEVICES)
    art = set(re.findall(r"/([\w-]+\.(?:svg|png))", catalog))
    assert len(art) >= 3, "each model needs its own device render"
    for name in art:
        path = os.path.join(PUBLIC, name)
        assert os.path.isfile(path), f"missing public/{name}"
        with open(path, "rb") as f:
            head = f.read(600)
        if name.endswith(".svg"):
            assert b"<svg" in head, f"public/{name} is not an SVG"
        else:
            assert head[:8] == b"\x89PNG\r\n\x1a\n", f"public/{name} is not a PNG"
    for fake in ("iphone.svg", "iphone-13.svg", "iphone-14.svg",
                 "iphone-16-pro.svg", "iphone-se.svg"):
        assert fake not in catalog, f"fake gradient {fake} must be gone from the catalog"
        assert not os.path.isfile(os.path.join(PUBLIC, fake)), \
            f"fake gradient public/{fake} must be deleted"


def test_model_picker_wired():
    ui = _read(APP) + _read(HEADER)
    assert re.search(r"[Mm]odel", ui), "UI must let users pick their iPhone model"
    assert "iphone" in ui.lower() and (".svg" in ui or "-mini.png" in ui or "CONTOUR_MINI" in ui)


# --- Plain-language copy + technical data ---
def test_friendly_action_labels():
    table = _read(TABLE)
    assert "Copy to iPhone" in table, "push needs a plain-language label"
    assert "Already" in table or "up to date" in table.lower(), \
        "skip needs a plain-language label"


def test_technical_data_preserved():
    table = _read(TABLE)
    assert "<details" in table or "title=" in table, \
        "technical data (codes/hashes) must stay inspectable"


# --- App icons ---
def _svg_shapes(path: str) -> str:
    with open(path) as f:
        return f.read()


def test_music_icon_geometry():
    """The sidebar music (VLC) icon must stay a symmetric cone on brand orange."""
    svg = _svg_shapes(os.path.join(PUBLIC, "app-vlc.svg"))
    assert 'viewBox="0 0 64 64"' in svg
    assert "#ff8800" in svg, "VLC brand orange background"
    assert svg.count("<polygon") >= 4, "cone body + shade + stripe-cut segments"
    for m in re.finditer(r"<polygon points=\"([^\"]+)\"", svg):
        xs = [float(p.split(",")[0]) for p in m.group(1).strip().split()]
        if min(xs) < 32:  # full-width cone segments (half-width ones are shading)
            assert min(xs) + max(xs) == pytest.approx(64.0), \
                "every cone segment must be symmetric around x=32"
def test_app_icons_exist_and_used():
    for icon in ("app-vlc.svg", "app-readest.svg", "app-bookplayer.svg"):
        path = os.path.join(PUBLIC, icon)
        assert os.path.isfile(path), f"missing public/{icon}"
        with open(path) as f:
            assert "<svg" in f.read(600)
    ui = _read(SIDEBAR) + _read(APP)
    assert "app-vlc.svg" in ui and "app-readest.svg" in ui, \
        "sidebar must show VLC/Readest icons"


# --- Real device renders ---
def test_device_renders_are_portrait_pngs():
    """Header + carousel art must be real portrait PNG renders, not gradients."""
    catalog = _read(DEVICES)
    art = set(re.findall(r"/([\w-]+\.png)", catalog))
    assert len(art) >= 3, "catalog must reference real PNG renders"
    for name in art:
        path = os.path.join(PUBLIC, name)
        assert os.path.isfile(path), f"missing public/{name}"
        assert os.path.getsize(path) > 5000, f"public/{name} looks empty"
        with open(path, "rb") as f:
            head = f.read(32)
        assert head[:8] == b"\x89PNG\r\n\x1a\n", f"public/{name} is not a PNG"
        # IHDR: width/height are bytes 16..24 (big-endian); renders are portrait.
        width = int.from_bytes(head[16:20], "big")
        height = int.from_bytes(head[20:24], "big")
        assert height > width, f"public/{name} must be a portrait render"


# --- GitHub sources ---
def test_sources_catalog_and_footer():
    assert os.path.isfile(SOURCES), "missing src/sources.ts"
    sources = _read(SOURCES)
    for repo in ("videolan/vlc-ios", "readest/readest", "TortugaPower/BookPlayer",
                 "libimobiledevice/libimobiledevice"):
        assert repo in sources, f"sources must link {repo}"
    assert "https://github.com/" in sources
    app = _read(APP)
    assert "github" in app.lower(), "footer must link GitHub sources"


# --- Docs ---
def test_docs_exist_and_linked():
    for doc in ("USER_GUIDE.md", "DEVELOPER.md", "SYNC_MODEL.md"):
        assert os.path.isfile(os.path.join(DOCS, doc)), f"missing docs/{doc}"
    readme = _read(README)
    assert "docs/USER_GUIDE.md" in readme, "README must link the user guide"


def test_user_guide_plain_language():
    guide = _read(os.path.join(DOCS, "USER_GUIDE.md")).lower()
    assert "glossary" in guide, "user guide needs a jargon glossary"
    for term in ("bundle", "afc", "usbmuxd"):
        assert term in guide, f"glossary must explain '{term}'"
