"""Header design contract tests: status signal, matched action pair, live data.

Guards the redesign: the header must show connection state at a glance
(status dot + trust chip), keep Sync/Trust as one matched-height action
group, and prefer live device data over placeholder blurb.
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "frontend", "src")
CSS = os.path.join(SRC, "apple.css")
HEADER = os.path.join(SRC, "components", "DeviceHeader.tsx")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def test_status_dot_on_mockup():
    header = _read(HEADER)
    css = _read(CSS)
    assert "ft-status-dot" in header, "mockup needs a connection status dot"
    assert "ft-status-dot" in css
    for state in ("trusted", "untrusted"):
        assert state in header, f"dot must handle state: {state}"
    assert "ft-pulse" in css, "trusted dot wants a pulse cue"
    assert "prefers-reduced-motion" in css, "pulse must respect reduced motion"


def test_trust_chip_signals_pairing_state():
    header = _read(HEADER)
    assert "Trusted ✓" in header, "trusted phones need a visible trust chip"
    assert "Not trusted" in header, "untrusted phones need a visible warning chip"
    assert "is-trusted" in _read(CSS) and "is-untrusted" in _read(CSS)


def test_matched_action_group():
    header = _read(HEADER)
    css = _read(CSS)
    assert "ft-actions" in header and "ft-actions" in css, \
        "Sync + Trust belong in one action group, not loose buttons"
    assert "ft-trust-btn" in header and "ft-trust-btn" in css, \
        "Trust is a secondary pill matching Sync height, not a small icon button"
    assert re.search(r"\.ft-trust-btn:not\(:disabled\):hover", css), "trust needs a hover state"
    assert re.search(r"\.ft-trust-btn:not\(:disabled\):active", css), "trust needs pressed feedback"


def test_chips_use_meters_and_tabular_numbers():
    header = _read(HEADER)
    css = _read(CSS)
    assert "ft-meter" in header and "ft-meter" in css, "battery/storage chips need mini meters"
    assert "tabular-nums" in css, "data chips must use tabular figures"


def test_subtitle_prefers_live_device_data():
    header = _read(HEADER)
    assert "product_type" in header, "subtitle should show the live product type when connected"
    assert "CONTOUR_MINI" in header, "header mini must follow the live contour"
    assert "ft-device" in header


def test_header_keeps_accessible_names():
    header = _read(HEADER)
    assert 'aria-label="Ask iPhone to trust this computer"' in header
    assert "title=" in header, "status elements need tooltips"
