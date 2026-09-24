"""Tests for photo deduplication directly on DCIM (no export first).

Hermetic: stub runner materializes pulls; mock mode asserts honest empties.
"""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.files import FileBrowser

client = TestClient(create_app())

PAYLOAD_A = b"same-bytes-123"
PAYLOAD_B = b"different!!"


class _DupRunner:
    """Fake afcclient: ls lists 3 photos, get materializes bytes, rm ok."""

    def __init__(self, fail_rm: bool = False):
        self.fail_rm = fail_rm
        self.files = {
            "/DCIM/IMG_1.JPG": PAYLOAD_A,
            "/DCIM/IMG_2.JPG": PAYLOAD_A,
            "/DCIM/IMG_3.JPG": PAYLOAD_B,
        }
        self.rms: list[str] = []

    def run(self, *args: str, timeout: int = 15, stdin: str | None = None):
        from app.services.devices import Completed
        s = stdin or ""
        if s.startswith("ls"):
            out = "\n".join([
                f"-rw-r--r-- 1 mobile mobile {len(PAYLOAD_A)} 28 Aug 2025 09:03:29 IMG_1.JPG",
                f"-rw-r--r-- 1 mobile mobile {len(PAYLOAD_A)} 28 Aug 2025 09:03:30 IMG_2.JPG",
                f"-rw-r--r-- 1 mobile mobile {len(PAYLOAD_B)} 28 Aug 2025 09:03:31 IMG_3.JPG",
            ])
            return Completed(0, out, "")
        if s.startswith("get"):
            parts = s.split('"')
            remote = parts[1]
            dest = parts[-2]
            Path(dest).write_bytes(self.files[remote])
            return Completed(0, "", "")
        if s.startswith("rm"):
            self.rms.append(s)
            return Completed(1 if self.fail_rm else 0, "", "denied" if self.fail_rm else "")
        return Completed(1, "", "huh")


def _browser(**kw) -> FileBrowser:
    return FileBrowser(runner=_DupRunner(**kw), available=True)  # type: ignore[arg-type]


def test_find_photo_duplicates_groups_identical():
    fb = _browser()
    res = fb.find_photo_duplicates("U")
    assert res["ok"] is True
    assert res["count"] == 1
    assert res["scanned"] == 3 and res["hashed"] == 2
    group = res["groups"][0]
    assert {m["path"] for m in group} == {"/DCIM/IMG_1.JPG", "/DCIM/IMG_2.JPG"}


def test_find_photo_duplicates_mock_is_honest_empty():
    res = FileBrowser(available=False).find_photo_duplicates("mock-udid")
    assert res["ok"] is True and res["groups"] == [] and res["count"] == 0
    assert "no bytes" in res["note"]


def test_delete_file_sends_rm_and_validates():
    fb = _browser()
    assert fb.delete_file("U", "/DCIM/IMG_1.JPG") is True
    assert 'rm "/DCIM/IMG_1.JPG"' in fb.runner.rms[0]  # type: ignore[attr-defined]
    assert _browser(fail_rm=True).delete_file("U", "/DCIM/IMG_1.JPG") is False
    assert FileBrowser(available=False).delete_file("U", "/DCIM/X.JPG") is False
    try:
        fb.delete_file("U", "/a/../b")
    except ValueError:
        pass
    else:
        raise AssertionError("traversal accepted")


def test_photo_duplicates_endpoint_mock_shape():
    body = client.get("/photos/duplicates").json()
    assert body["ok"] is True and body["groups"] == [] and body["count"] == 0
    assert body["scanned"] >= 2


def test_photo_delete_endpoint_guards_and_mock_409():
    assert client.delete("/photos", params={"path": "../etc/passwd"}).status_code == 400
    assert client.delete("/photos", params={"path": "/Books/x.pdf"}).status_code == 400
    r = client.delete("/photos", params={"path": "/DCIM/IMG_0001.JPG"})
    assert r.status_code == 409
    assert "DCIM" in r.json()["detail"] or "mock" in r.json()["detail"].lower()


def test_photo_duplicates_and_delete_endpoints_with_stub(monkeypatch):
    import app.routers.files as router_mod
    runner = _DupRunner()
    monkeypatch.setattr(router_mod, "get_browser",
                        lambda: FileBrowser(runner=runner, available=True))  # type: ignore[arg-type]
    body = client.get("/photos/duplicates", params={"udid": "U"}).json()
    assert body["ok"] is True and body["count"] == 1
    assert body["groups"][0][0]["filename"] == "IMG_1.JPG"
    gone = client.delete("/photos", params={"udid": "U", "path": "/DCIM/IMG_1.JPG"}).json()
    assert gone["ok"] is True and gone["path"] == "/DCIM/IMG_1.JPG"


def test_frontend_photos_view_wires_dedup():
    import os
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    with open(os.path.join(root, "frontend", "src", "api.ts")) as f:
        api = f.read()
    assert "photoDuplicates" in api and "deletePhoto" in api
    with open(os.path.join(root, "frontend", "src", "components", "MediaViews.tsx")) as f:
        media = f.read()
    assert "Find duplicates" in media
    assert "Keep first" in media
