"""Contract tests (TDD): Documentation tab + Settings tab.

- Documentation shows the user guide (plain language + glossary), bundled
  as a static view — no backend endpoint.
- Settings consolidates every preference (theme, accent, iPhone model,
  library folders, backend status, sync defaults, reset) and persists
  them; the sidebar no longer carries Display pickers.
"""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "frontend", "src")
APP = os.path.join(SRC, "App.tsx")
SIDEBAR = os.path.join(SRC, "components", "Sidebar.tsx")
DOCS_VIEW = os.path.join(SRC, "components", "DocsView.tsx")
SETTINGS_VIEW = os.path.join(SRC, "components", "SettingsView.tsx")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


# --- Documentation tab ---
def test_docs_view_exists_and_covers_user_guide():
    assert os.path.isfile(DOCS_VIEW), "missing src/components/DocsView.tsx"
    view = _read(DOCS_VIEW)
    for token in ("Preview", "Sync", "Trust", "Glossary", "bundle", "afc", "usbmuxd"):
        assert token.lower() in view.lower(), f"DocsView missing user-guide content: {token}"


def test_docs_view_has_search_and_sources():
    view = _read(DOCS_VIEW)
    assert 'type="search"' in view, "DocsView needs a search field"
    assert "SOURCES" in view or "sources" in view.lower(), \
        "DocsView must list the open-source building blocks"


def test_docs_search_indexes_every_section():
    """Each SECTIONS entry needs search keywords, or search can't find it."""
    view = _read(DOCS_VIEW)
    for section in ("diagnostics", "backup", "firmware", "toolbox",
                    "files", "device"):
        assert f"'{section}'" in view or f'"{section}"' in view, \
            f"DocsView search index missing section: {section}"
    # Photos rides with the Files section but must still be searchable.
    assert "photos" in view.lower(), "DocsView search must find 'photos'"


def test_docs_glossary_covers_diagnostics_terms():
    view = _read(DOCS_VIEW)
    for token in ("syslog", "crash report", "backup"):
        assert token in view.lower(), f"DocsView glossary missing: {token}"


def test_docs_nav_is_grouped_knowledge_base():
    """The guide index stays compact as sections grow: grouped, not a tall
    wall of big buttons — and notes link to each other wiki-style."""
    view = _read(DOCS_VIEW)
    for token in ("Guide", "Reference"):
        assert token in view, f"DocsView index missing group: {token}"
    assert "Related" in view, "DocsView notes must link to related notes"
    for token in ("Prev", "Next"):
        assert token in view, "DocsView needs prev/next note traversal"


# --- Settings tab ---
def test_settings_view_exists_and_consolidates_prefs():
    assert os.path.isfile(SETTINGS_VIEW), "missing src/components/SettingsView.tsx"
    view = _read(SETTINGS_VIEW)
    for token in ("Theme", "Accent", "Model", "Library", "mirror", "Reset"):
        assert token.lower() in view.lower(), f"SettingsView missing preference: {token}"
    assert "localStorage" in view or "freetunes-" in view, \
        "SettingsView must persist preferences"


def test_sidebar_display_pickers_moved_to_settings():
    sidebar = _read(SIDEBAR)
    assert "ft-theme" not in sidebar and "ft-accent" not in sidebar, \
        "Theme/Accent pickers must live in Settings, not the sidebar"
