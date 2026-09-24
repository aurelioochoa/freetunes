"""Proxy + header regression tests.

Root cause of 'no photos or files': the Vite dev proxy only forwarded
the original six prefixes, so every newer tab (/photos, /files,
/diagnostics, /tools, /firmware, /flash, /storage) got a 404 from the
dev server and rendered empty. This test fails if any backend route is
not reachable through vite.config.ts.
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VITE = os.path.join(ROOT, "frontend", "vite.config.ts")
HEADER = os.path.join(ROOT, "frontend", "src", "components", "DeviceHeader.tsx")
APP = os.path.join(ROOT, "frontend", "src", "App.tsx")


def _proxied_prefixes() -> set[str]:
    with open(VITE) as f:
        cfg = f.read()
    return set(re.findall(r"'(/[a-z-]+)'\s*:", cfg))


def test_vite_proxy_covers_every_backend_route():
    from app.main import create_app
    proxied = _proxied_prefixes()
    # Exact first-segment match: '/screen' must not be covered by '/s'.
    missing = [path for path in create_app().openapi()["paths"]
               if "/" + path.strip("/").split("/")[0] not in proxied]
    assert not missing, f"backend routes unreachable via vite proxy (tab renders empty): {missing}"


def test_header_has_trust_button():
    with open(HEADER) as f:
        header = f.read()
    assert "Ask iPhone to Trust" in header, "DeviceHeader must expose the Trust button"
    assert "onPair" in header and "showTrust" in header
    assert re.search(r"!absent\s*&&", header), \
        "header Sync + Trust actions must be hidden (not just disabled) with no iPhone"
    assert "ft-actions" in header, "Sync + Trust belong in one action group"
    with open(APP) as f:
        app = f.read()
    assert "onPair={doPair}" in app, "App must wire doPair into the header"
    assert re.search(r"showTrust(?!\s*=\s*\{)", app), \
        "Trust button must render unconditionally (plain showTrust, never gated on trusted state)"
