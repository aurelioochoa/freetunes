"""Every tab is reachable end to end: sidebar entry -> App route -> label
-> Documentation section.

Replaces a dozen per-tab "does App.tsx mention FooView" greps with one
table-driven check that fails for the tab that is actually missing a
piece (a routed view with no sidebar entry is unreachable; a sidebar
entry with no route renders the sync table instead of its view).
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "frontend", "src")


def _read(*parts: str) -> str:
    with open(os.path.join(SRC, *parts)) as f:
        return f.read()


APP = _read("App.tsx")
SIDEBAR = _read("components", "Sidebar.tsx")
DOCS = _read("components", "DocsView.tsx")

#: Sync views share the SyncTable fallback branch instead of a route.
SYNC_VIEWS = {"music", "books", "audiobooks"}


def _sidebar_views() -> set[str]:
    items = set(re.findall(r"\['([a-z]+)', '[^']+', '[^']*'\]", SIDEBAR))
    items |= set(re.findall(r"setView\('([a-z]+)'\)", SIDEBAR))
    general = re.search(r"\(\[([^\]]+)\] as const\)\.map", SIDEBAR)
    items |= set(re.findall(r"'([a-z]+)'", general.group(1)))
    return items


def _record_keys(name: str) -> set[str]:
    block = APP.split(f"const {name}: Record<string, string> = {{")[1]
    return set(re.findall(r"^\s*([a-z]+):", block.split("};")[0], re.M))


def test_sidebar_lists_every_view_including_general():
    views = _sidebar_views()
    assert {"device", "screen", "docs", "settings"} <= views, views
    assert views == _record_keys("VIEW_LABEL"), \
        "every sidebar entry needs a toolbar label and vice versa"
    assert views == _record_keys("VIEW_APP")


def test_every_non_sync_view_has_its_own_route():
    routed = dict(re.findall(r"view === '([a-z]+)' \? \(\s*<(\w+)", APP))
    for view in _sidebar_views() - SYNC_VIEWS:
        assert view in routed, f"'{view}' has no route in App.tsx"
    # Each routed component is its own view, never a copy-paste twin.
    assert len(set(routed.values())) == len(routed), routed


def test_documentation_covers_every_tab():
    ids = set(re.findall(r"\{ id: '([a-z-]+)'", DOCS))
    # The three sync views share the "copy" guide, Photos rides with Files.
    shared = {"music": "copy", "books": "copy", "audiobooks": "copy",
              "photos": "files", "docs": "start"}
    for view in _sidebar_views():
        assert shared.get(view, view) in ids, \
            f"DocsView has no section for the '{view}' tab"
