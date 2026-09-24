"""Tests for toolbox uploads, auto-dest downloads, and from-device ops."""
import io

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import toolbox as tb

client = TestClient(create_app())


def _tiny_jpg() -> bytes:
    from io import BytesIO
    from PIL import Image as PILImage
    buf = BytesIO()
    PILImage.new("RGB", (64, 48), (10, 120, 200)).save(buf, "JPEG")
    return buf.getvalue()


def test_upload_roundtrip_and_scoped_download(tmp_path, monkeypatch):
    monkeypatch.setenv("FREETUNES_CACHE", str(tmp_path))
    r = client.post("/tools/upload", files={"file": ("my pic.jpg", io.BytesIO(_tiny_jpg()), "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["path"].endswith(".jpg")
    assert body["size"] > 0 and body["download"].startswith("/tools/file?name=")
    dl = client.get(body["download"])
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "image/jpeg"
    assert dl.content[:2] == b"\xff\xd8"


def test_upload_rejects_empty_and_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("FREETUNES_CACHE", str(tmp_path))
    r = client.post("/tools/upload", files={"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")})
    assert r.status_code == 400
    assert client.get("/tools/file", params={"name": "../thumb.jpg"}).status_code == 404
    assert client.get("/tools/file", params={"name": ".hidden"}).status_code == 404
    assert client.get("/tools/file", params={"name": "nope.jpg"}).status_code == 404


def test_tool_endpoints_auto_dest_return_download(tmp_path, monkeypatch):
    monkeypatch.setenv("FREETUNES_CACHE", str(tmp_path))
    src = tmp_path / "in.jpg"
    src.write_bytes(_tiny_jpg())
    r = client.post("/tools/compress-photo", params={"src": str(src), "dest": ""}).json()
    assert r["ok"], r
    assert r["download"].startswith("/tools/file?name=")
    assert client.get(r["download"]).status_code == 200


def test_from_device_validates_and_needs_real_pull():
    bad = client.post("/tools/from-device", json={"op": "nope", "remote_path": "/x.jpg"}).json()
    assert bad["ok"] is False and "op must be" in bad["reason"]
    trav = client.post("/tools/from-device", json={"op": "convert", "remote_path": "/a/../b"}).json()
    assert trav["ok"] is False
    # mock mode: pull unavailable -> honest failure, never a crash
    mock = client.post("/tools/from-device",
                       json={"udid": "mock-udid", "remote_path": "/DCIM/X.JPG", "op": "compress-photo"}).json()
    assert mock["ok"] is False and "trusted iPhone" in mock["reason"]


def test_from_device_success_with_stub_runner(tmp_path, monkeypatch):
    from app.services.files import FileBrowser
    import app.routers.toolbox as router_mod
    monkeypatch.setenv("FREETUNES_CACHE", str(tmp_path))
    payload = _tiny_jpg()

    class Runner:
        def run(self, *args: str, timeout: int = 15, stdin: str | None = None):
            from app.services.devices import Completed
            from pathlib import Path as P
            dest = (stdin or "").split('"')[-2]
            P(dest).write_bytes(payload)
            return Completed(0, "", "")

    monkeypatch.setattr(router_mod, "get_browser",
                        lambda: FileBrowser(runner=Runner(), available=True))  # type: ignore[arg-type]
    body = client.post("/tools/from-device",
                       json={"udid": "U", "remote_path": "/DCIM/IMG_1.JPG",
                             "op": "compress-photo"}).json()
    assert body["ok"], body
    assert body["download"].startswith("/tools/file?name=")
    assert client.get(body["download"]).status_code == 200
