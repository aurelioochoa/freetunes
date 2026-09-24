"""Regression tests for the fixed Firmware/Toolbox/Files tabs.

Guards the exact bugs reported: Firmware stale-state message, Toolbox
with only duplicates, Files without photos.
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "frontend", "src")
API = os.path.join(SRC, "api.ts")
FW = os.path.join(SRC, "components", "FirmwareView.tsx")
TB = os.path.join(SRC, "components", "ToolboxView.tsx")
MEDIA = os.path.join(SRC, "components", "MediaViews.tsx")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def test_api_clients_cover_all_toolbox_tools():
    api = _read(API)
    for fn in ("editTags", "makeRingtone", "convertMedia", "compressPhoto", "heicToJpg",
               "photos", "browse", "firmwareSigned", "flashDryRun", "duplicates",
               "upload", "toolFileUrl", "fromDevice", "fileContentUrl", "thumbUrl"):
        assert fn in api, f"api.ts missing {fn}() client"


def test_firmware_no_stale_rows_message():
    fw = _read(FW)
    # The reported bug: setRows(...) then read rows.length in the same
    # handler (stale closure) — message must derive from the fresh result.
    assert "setMsg(rows.length" not in fw, "stale-closure message bug is back"
    assert "useEffect" in fw, "firmware list should auto-load"
    assert "quick" in fw and "retain" in fw, "flash mode selector missing"
    assert "command" in fw and "gates" in fw, "dry-run result must show command + gates"


def test_toolbox_covers_all_six_tools():
    tb = _read(TB)
    for label in ("Duplicate", "Audio tags", "Ringtone", "Format conversion",
                  "Compress photo", "HEIC"):
        assert label.lower() in tb.lower(), f"Toolbox missing section: {label}"
    for fn in ("api.duplicates", "api.editTags", "api.makeRingtone",
               "api.convertMedia", "api.compressPhoto", "api.heicToJpg"):
        assert fn in tb, f"Toolbox never calls {fn}"


def test_files_view_shows_files_and_photos():
    media = _read(MEDIA)
    assert "api.browse" in media and "api.photos" in media, \
        "Files tab must load both file browser and DCIM photos"
    assert "Photos on this iPhone" in media, "Files tab missing embedded photos section"
    assert "Go up" in media or "parentOf" in media, "Files needs an Up/back affordance"
    assert "Refresh" in media, "Files/Photos need a refresh action"


def test_photos_view_has_loading_and_error_states():
    media = _read(MEDIA)
    assert "Loading photos" in media, "Photos needs a loading state"
    assert "Could not load photos" in media, "Photos needs an error state"
    assert re.search(r"useEffect", media), "views must load on mount"


def test_files_contextual_tool_actions():
    media = _read(MEDIA)
    assert "api.fromDevice" in media, "Files rows need contextual toolbox actions"
    assert "Actions for" in media, "file menu needs accessible labels"
    assert "Export original" in media, "file menu needs a direct export"


def test_toolbox_offers_developer_mode_controls():
    # Both Developer Mode actions must be reachable from the Toolbox, not
    # only from the device page and the Screen tab.
    tb = _read(TB)
    assert "DevModeControls" in tb, "Toolbox missing the Developer Mode tool"
    assert "Developer Mode" in tb, "Developer Mode card needs a visible title"
    assert "udid" in tb, "Developer Mode needs the connected udid to act on"
    dev = _read(os.path.join(SRC, "components", "DevModeControls.tsx"))
    assert "api.screenRevealDevMode" in dev, "no way to show the Settings row"
    assert "api.screenEnableDevMode" in dev, "no way to turn Developer Mode on"
    # Enabling reboots the phone, so it must never fire on a single click.
    assert "armReboot" in dev, "enable must be a two-step confirm, not one click"


def test_toolbox_receives_udid_from_app():
    app = _read(os.path.join(SRC, "App.tsx"))
    m = re.search(r"<ToolboxView[^>]*>", app)
    assert m, "ToolboxView is not mounted"
    assert "udid" in m.group(0), \
        "ToolboxView must get the udid or Developer Mode can never act"


def test_developer_mode_card_never_renders_empty():
    # The card has a title and a footer; with no phone or no backend the
    # body must still say something instead of sitting blank.
    tb = _read(TB)
    assert "Connect and trust an iPhone" in tb, \
        "Developer Mode card needs a no-device empty state"
    assert "fallback" in tb, \
        "Developer Mode card needs a fallback when pymobiledevice3 is absent"
    dev = _read(os.path.join(SRC, "components", "DevModeControls.tsx"))
    assert "fallback" in dev, "DevModeControls must accept a fallback"
    # A null status means "still loading", not "unsupported" — showing the
    # fallback then would flash a wrong message on every mount.
    assert "if (!udid || !status) return null;" in dev, \
        "loading state must collapse, not fall back"


def test_toolbox_devmode_card_has_grid_area():
    css = _read(os.path.join(SRC, "apple.css"))
    assert ".bento-devmode" in css, "Developer Mode card has no grid placement"


def test_toolbox_drag_drop_upload():
    tb = _read(TB)
    assert "api.upload" in tb, "Toolbox sources need browse/upload"
    assert "onDrop" in tb, "Toolbox sources need drag-drop"
    assert "Download" in tb, "tool results need a download path"


def test_file_menu_solid_and_clickable():
    css = _read(os.path.join(SRC, "apple.css"))
    m = re.search(r"\.ft-menu\s*\{([^}]*)\}", css)
    assert m and "var(--menu)" in m.group(1), \
        "file menu needs a solid per-theme background, not translucent glass"
    # Fill-mode entrance animations on rows leave a permanent stacking
    # context per row that buries the ⋯ popover beneath later siblings
    # (both paint and hit-testing). Table-level fade only.
    assert ".ft-table .ft-row:not(.head)" not in css, \
        "row-level persisted animations trap the file menu"


def test_pair_endpoint_shape_in_mock_mode():
    from fastapi.testclient import TestClient

    from app.main import create_app
    client = TestClient(create_app())
    body = client.post("/devices/some-udid/pair").json()
    assert body["ok"] is False and body["trusted"] is False
    assert "udid" in body and "message" in body


def test_trust_button_always_visible():
    app = _read(os.path.join(SRC, "App.tsx"))
    header = _read(os.path.join(SRC, "components", "DeviceHeader.tsx"))
    assert "api.pair" in app, "UI needs a Trust-request action calling the pair endpoint"
    # Single home for the button is the header (next to Sync), hidden once
    # trusted — the banner stays status text only.
    assert "Ask iPhone to Trust" in header, "header needs the Trust button"
    assert "Waiting for Trust" in header, "button needs a waiting state while iOS shows the prompt"
    assert "showTrust" in app, "App must wire the header Trust button"
    assert "Ask iPhone to Trust" not in app, "banner must not duplicate the header Trust button"
