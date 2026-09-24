from fastapi.testclient import TestClient

from app.main import create_app
from app.services.afc import reset_mock

app = create_app()
client = TestClient(app)


def test_health_and_apps():
    reset_mock()
    assert client.get("/health").json()["ok"] is True
    apps = client.get("/apps").json()
    ids = {a["bundle_id"] for a in apps}
    assert "org.videolan.vlc-ios" in ids


def test_sync_preview_and_run(tmp_path):
    reset_mock()
    (tmp_path / "song.mp3").write_bytes(b"hello-music")
    body = {"app_bundle_id": "org.videolan.vlc-ios",
            "music_dir": str(tmp_path), "mirror_delete": False}
    prev = client.post("/sync/preview", json=body).json()
    assert prev["to_push"][0]["filename"] == "song.mp3"
    run = client.post("/sync/run", json=body).json()
    assert run["pushed"] == ["song.mp3"]
    prev2 = client.post("/sync/preview", json=body).json()
    assert prev2["to_skip"][0]["filename"] == "song.mp3"
