"""Tests for GET /files/content (real-byte previews via `afcclient get`).

Hermetic: mock mode returns 404 (sample names carry no bytes); pull
logic is exercised with a stub runner that materializes the dest file.
"""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.files import FileBrowser

client = TestClient(create_app())


class _StubRunner:
    """Mimics afcclient: writes payload bytes to the LOCALPATH of `get`."""

    def __init__(self, payload: bytes = b"\xff\xd8fake-jpeg", fail: bool = False):
        self.payload = payload
        self.fail = fail
        self.seen_stdin = ""

    def run(self, *args: str, timeout: int = 15, stdin: str | None = None):
        from app.services.devices import Completed
        self.seen_stdin = stdin or ""
        if self.fail:
            return Completed(1, "", "no device")
        # stdin looks like: get "/DCIM/X.JPG" "/tmp/xxx/X.JPG"\nquit\n
        dest = (stdin or "").split('"')[-2]
        Path(dest).write_bytes(self.payload)
        return Completed(0, "", "")


def _browser(payload: bytes = b"\xff\xd8fake-jpeg", fail: bool = False) -> FileBrowser:
    return FileBrowser(runner=_StubRunner(payload, fail), available=True)  # type: ignore[arg-type]


def test_content_rejects_traversal_and_relative():
    for bad in ("../etc/passwd", "DCIM/x.jpg", "/a/../b", "/x\x00y"):
        try:
            FileBrowser.validate_remote_path(bad)
        except ValueError:
            continue
        raise AssertionError(f"validate_remote_path accepted {bad!r}")


def test_pull_returns_none_when_unavailable_or_failed():
    assert FileBrowser(available=False).pull_file("U", "/DCIM/X.JPG") is None
    assert _browser(fail=True).pull_file("U", "/DCIM/X.JPG") is None


def test_pull_materializes_file_and_cleans_up():
    runner = _StubRunner(b"hello-bytes")
    fb = FileBrowser(runner=runner, available=True)  # type: ignore[arg-type]
    local = fb.pull_file("U", "/DCIM/IMG_0001.JPG")
    assert local is not None and local.read_bytes() == b"hello-bytes"
    assert 'get "/DCIM/IMG_0001.JPG"' in runner.seen_stdin
    # caller-owned cleanup (router does this via BackgroundTasks)
    import shutil
    shutil.rmtree(local.parent, ignore_errors=True)
    assert not local.parent.exists()


def test_pull_rejects_oversize():
    import app.services.files as files_mod
    fb = _browser(b"x" * 16)
    old = files_mod.MAX_PREVIEW_BYTES
    files_mod.MAX_PREVIEW_BYTES = 8
    try:
        assert fb.pull_file("U", "/DCIM/big.MOV") is None
    finally:
        files_mod.MAX_PREVIEW_BYTES = old


def test_content_endpoint_404_in_mock_mode():
    r = client.get("/files/content", params={"path": "/DCIM/IMG_0001.JPG"})
    assert r.status_code == 404
    assert "mock" in r.json()["detail"].lower()


def test_content_endpoint_400_on_bad_path():
    r = client.get("/files/content", params={"path": "../etc/passwd"})
    assert r.status_code == 400


def _tiny_png() -> bytes:
    from io import BytesIO
    from PIL import Image as PILImage
    buf = BytesIO()
    PILImage.new("RGB", (32, 24), (200, 30, 40)).save(buf, "PNG")
    return buf.getvalue()


def test_thumb_endpoint_404_in_mock_mode():
    r = client.get("/files/thumb", params={"path": "/DCIM/IMG_0001.JPG"})
    assert r.status_code == 404


def test_thumb_endpoint_400_on_bad_path():
    r = client.get("/files/thumb", params={"path": "/a/../b"})
    assert r.status_code == 400


def test_make_thumb_decodes_photo_to_jpeg(tmp_path, monkeypatch):
    from app.services.files import FileBrowser
    monkeypatch.setenv("FREETUNES_CACHE", str(tmp_path))
    png = _tiny_png()

    class Runner:
        def run(self, *args: str, timeout: int = 15, stdin: str | None = None):
            from app.services.devices import Completed
            dest = (stdin or "").split('"')[-2]
            with open(dest, "wb") as f:
                f.write(png)
            return Completed(0, "", "")

    fb = FileBrowser(runner=Runner(), available=True)  # type: ignore[arg-type]
    first = fb.make_thumb("U", "/DCIM/IMG_0001.JPG", 128)
    assert first is not None and first.read_bytes()[:2] == b"\xff\xd8"
    # second call is a cache hit (no pull needed even with a failing runner)
    fb.runner = _StubRunner(b"", fail=True)  # type: ignore[assignment]
    assert fb.make_thumb("U", "/DCIM/IMG_0001.JPG", 128) == first


def test_make_thumb_rejects_heic_without_decoder_and_unknown(monkeypatch):
    import shutil
    from app.services.files import FileBrowser
    real_which = shutil.which
    monkeypatch.setattr(shutil, "which",
                        lambda name: None if name in ("heif-convert", "ffmpeg") else real_which(name))
    fb = FileBrowser(runner=_StubRunner(_tiny_png()), available=True)  # type: ignore[arg-type]
    assert fb.make_thumb("U", "/DCIM/IMG_0002.HEIC") is None
    assert fb.make_thumb("U", "/DCIM/notes.txt") is None


def _tiny_heic(tmp_path) -> bytes | None:
    """Encode a real HEIC with heif-enc when available (else None → skip)."""
    import shutil
    import subprocess
    if shutil.which("heif-enc") is None:
        return None
    src = tmp_path / "src.png"
    dst = tmp_path / "src.heic"
    _tiny_png_bytes = _tiny_png()
    src.write_bytes(_tiny_png_bytes)
    r = subprocess.run(["heif-enc", "-o", str(dst), str(src)],
                       capture_output=True, timeout=60)
    if r.returncode != 0 or not dst.is_file():
        return None
    return dst.read_bytes()


def test_make_thumb_decodes_heic_to_jpeg(tmp_path, monkeypatch):
    import shutil
    if shutil.which("heif-convert") is None and shutil.which("ffmpeg") is None:
        import pytest
        pytest.skip("no HEIC decoder (heif-convert/ffmpeg) on PATH")
    heic = _tiny_heic(tmp_path)
    if heic is None:
        import pytest
        pytest.skip("heif-enc unavailable — cannot synthesize HEIC fixture")
    from app.services.files import FileBrowser
    monkeypatch.setenv("FREETUNES_CACHE", str(tmp_path / "cache"))

    class Runner:
        def run(self, *args: str, timeout: int = 15, stdin: str | None = None):
            from app.services.devices import Completed
            dest = (stdin or "").split('"')[-2]
            with open(dest, "wb") as f:
                f.write(heic)
            return Completed(0, "", "")

    fb = FileBrowser(runner=Runner(), available=True)  # type: ignore[arg-type]
    thumb = fb.make_thumb("U", "/DCIM/IMG_0002.HEIC", 128)
    assert thumb is not None and thumb.read_bytes()[:2] == b"\xff\xd8"


def test_heic_to_jpg_toolbox_falls_back_without_pillow_heif(tmp_path):
    import shutil
    import pytest
    if shutil.which("heif-convert") is None and shutil.which("ffmpeg") is None:
        pytest.skip("no HEIC decoder (heif-convert/ffmpeg) on PATH")
    try:
        import pillow_heif  # noqa: F401
        pytest.skip("pillow-heif installed — fallback path not exercised")
    except ImportError:
        pass
    heic = _tiny_heic(tmp_path)
    if heic is None:
        pytest.skip("heif-enc unavailable — cannot synthesize HEIC fixture")
    from app.services import toolbox as tb
    src = tmp_path / "in.heic"
    dest = tmp_path / "out.jpg"
    src.write_bytes(heic)
    res = tb.heic_to_jpg(str(src), str(dest))
    assert res["ok"] is True and dest.read_bytes()[:2] == b"\xff\xd8"
