"""Apple HIG contract tests (TDD): Liquid Glass floating chrome, sidebar
patterns, unified toolbar, inset table selection, accessibility.

Sources: Apple HIG Sidebars / Dark Mode; WWDC25 'Build an AppKit app with
the new design' (Liquid Glass: floating glass toolbar + sidebar,
concentricity, inset selection, badges, collapsible sidebar).
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "frontend", "src")
CSS = os.path.join(SRC, "apple.css")
APP = os.path.join(SRC, "App.tsx")
SIDEBAR = os.path.join(SRC, "components", "Sidebar.tsx")
TABLE = os.path.join(SRC, "components", "SyncTable.tsx")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def test_concentric_radius_tokens():
    css = _read(CSS)
    assert "--radius" in css, "expected concentric --radius-* tokens"


def test_floating_sidebar_and_toolbar():
    css = _read(CSS)
    sidebar = re.search(r"(?m)^\.ft-sidebar\s*\{([^}]*)\}", css)
    assert sidebar and "border-radius" in sidebar.group(1), \
        "HIG: sidebar floats as glass pane"
    header = re.search(r"(?m)^\.ft-header\s*\{([^}]*)\}", css)
    assert header and "border-radius" in header.group(1), \
        "HIG: toolbar floats above content"


def test_collapsible_sidebar():
    app = _read(APP)
    assert re.search(r"[Ss]idebar.*[Cc]ollaps|showSidebar|sidebarOpen", app), \
        "HIG: let people hide the sidebar"
    assert "aria-expanded={sidebarOpen}" in app, \
        "the sidebar toggle must announce its state"


def test_sidebar_badges():
    sidebar = _read(SIDEBAR)
    css = _read(CSS)
    assert "badge" in sidebar.lower(), "HIG: badge pending/new counts"
    assert "ft-badge" in css


def test_unified_toolbar_search():
    app = _read(APP)
    assert 'type="search"' in app, "HIG unified toolbar: inline search field"


def test_inset_table_selection():
    css = _read(CSS)
    assert ".ft-row.selected" in css, "HIG: inset selection style"
    sel = css.split(".ft-row.selected")[1].split("}")[0]
    assert "border-radius" in sel


def test_keyboard_focus_visible():
    css = _read(CSS)
    assert ":focus-visible" in css, "HIG/accessibility: visible keyboard focus"


def test_empty_state():
    table = _read(TABLE)
    css = _read(CSS)
    assert "ft-empty" in table, "HIG: friendly empty state, not a blank table"
    assert "ft-empty" in css
