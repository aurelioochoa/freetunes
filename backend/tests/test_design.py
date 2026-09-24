"""Design contract tests (TDD): glassmorphism theme + iPhone device render.

These guard the Finder+Music look: frosted-glass surfaces, gradient backdrop,
and a real device render wired into the UI.
"""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CSS = os.path.join(ROOT, "frontend", "src", "apple.css")
APP = os.path.join(ROOT, "frontend", "src", "App.tsx")
HEADER = os.path.join(ROOT, "frontend", "src", "components", "DeviceHeader.tsx")
PUBLIC = os.path.join(ROOT, "frontend", "public")
DEVICES = os.path.join(ROOT, "frontend", "src", "devices.ts")
# Header mini per contour — the render shown when no iPhone is connected.
PHONE = os.path.join(PUBLIC, "iphone-se-mini.png")
REMOVED_FAKES = (
    "iphone.svg",
    "iphone-13.svg",
    "iphone-14.svg",
    "iphone-16-pro.svg",
    "iphone-se.svg",
)


def _css() -> str:
    with open(CSS) as f:
        return f.read()


def test_glassmorphism_backdrop_blur():
    css = _css()
    assert css.count("backdrop-filter") >= 3, "glass surfaces need backdrop-filter blur"
    assert "blur(" in css


def test_glassmorphism_translucent_surfaces():
    css = _css()
    assert "rgba(" in css, "glass needs translucent rgba surfaces"
    assert "--glass" in css, "expected --glass design tokens"


def test_glassmorphism_gradient_backdrop():
    css = _css().lower()
    assert "gradient" in css, "expected gradient backdrop for glass depth"


def test_glass_card_class_exists():
    css = _css()
    assert ".glass" in css, "expected reusable .glass card class"


def test_iphone_render_asset_exists_and_is_png():
    assert os.path.isfile(PHONE), "missing frontend/public/iphone-se-mini.png"
    with open(PHONE, "rb") as f:
        head = f.read(32)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", "device render must be a PNG"
    assert os.path.getsize(PHONE) > 5000, "device render looks empty"
    for fake in REMOVED_FAKES:
        assert not os.path.isfile(os.path.join(PUBLIC, fake)), \
            f"fake gradient {fake} must be deleted"
    with open(DEVICES) as f:
        catalog = f.read()
    for fake in REMOVED_FAKES:
        assert fake not in catalog, f"fake gradient {fake} must be gone from the catalog"


def test_iphone_render_wired_into_ui():
    with open(APP) as f:
        app = f.read()
    with open(HEADER) as f:
        header = f.read()
    assert "CONTOUR_MINI" in header or "iphone-se-mini.png" in header or \
        "model.svg" in header, \
        "UI must render the iPhone contour art (mini live contour)"
    assert "ft-device" in (app + header), "expected ft-device mockup class in UI"
