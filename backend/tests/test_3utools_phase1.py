"""Phase 1/2 3uTools-parity tests: backup, files/photos, diagnostics, toolbox, firmware.

Hermetic (FREETUNES_MOCK=1): CLI tools are stubbed via FakeRunner and
service `available=False` paths; toolbox pure functions use tmp dirs.
"""
import json
import os
import tempfile

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import toolbox as tb
from app.services.backup_service import BackupService
from app.services.devices import FakeRunner
from app.services.diagnostics import verification_for
from app.services.files import FileBrowser
from app.services.firmware import flash_dry_run

app = create_app()
client = TestClient(app)


def test_backup_info_mock_shape():
    r = client.get("/backup/some-udid").json()
    assert r["udid"] == "some-udid"
    assert "encrypted" in r


def test_backup_files_mock_empty_list():
    assert client.get("/backup/some-udid/files").json() == []


def test_backup_service_info_parses_cli():
    import pathlib
    root = pathlib.Path(tempfile.mkdtemp())
    svc = BackupService(runner=FakeRunner({}), backup_root=root, available=True)
    target_dir = str(svc._dir("U1"))
    svc.runner = FakeRunner({("idevicebackup2", "-u", "U1", "info", target_dir): (
        0, "Last backup: 2026-09-18\nEncrypted: True\n", "")})
    info = svc.info("U1")
    assert info.encrypted is True
    assert "2026" in (info.last_backup or "")


def test_files_browse_mock():
    rows = client.get("/files/browse", params={"path": "/"}).json()
    assert any(r["name"] == "DCIM" for r in rows)


def test_photos_mock():
    photos = client.get("/photos").json()
    assert len(photos) >= 2
    assert photos[0]["filename"].lower().endswith((".jpg", ".heic", ".mov"))


def test_file_browser_lists_via_runner():
    fb = FileBrowser(runner=FakeRunner({
        ("afcclient", "-u", "U1"): (0, "DCIM\nBooks\n", "")}), available=True)
    # list_dir sends stdin; FakeRunner ignores stdin and keys on argv.
    rows = fb.list_dir("U1", "/")
    assert {r.name for r in rows} >= {"DCIM", "Books"}


def test_storage_breakdown_shape():
    body = client.get("/storage/breakdown").json()
    assert {"total", "available", "used", "source"} <= set(body)


def test_verification_retail_vs_refurb():
    assert verification_for("U", "M1234LL/A").kind == "retail-new"
    rep = verification_for("U", "F1234LL/A")
    assert rep.kind == "refurbished" and rep.refurbished_suspect is True
    api = client.get("/diagnostics/verification").json()
    assert "kind" in api and "details" in api


def test_crashes_and_syslog_mock():
    assert isinstance(client.get("/diagnostics/crashes").json(), list)
    body = client.get("/diagnostics/syslog", params={"lines": 5}).json()
    assert "lines" in body and body["live"] is False


def test_crash_list_has_enriched_fields():
    rows = client.get("/diagnostics/crashes").json()
    assert len(rows) >= 1
    assert all(set(r) >= {"filename", "size", "app", "date", "mtime", "kind",
                          "exception", "reason", "os_version"} for r in rows)
    assert any(r["exception"] for r in rows)


def test_crash_kind_and_header_helpers():
    from app.services import diagnostics as diag

    assert diag.classify_crash_kind("panic-2026-09-10.ips") == "panic"
    assert diag.classify_crash_kind("JetsamEvent-2026-09-10.ips") == "jetsam"
    assert diag.classify_crash_kind("SpringBoard-2026-09-10.ips") == "crash"
    assert diag.sanitize_crash_filename("a.ips") == "a.ips"
    assert diag.sanitize_crash_filename("../etc/passwd") == ""
    assert diag.sanitize_crash_filename("evil.sh") == ""
    parsed = diag.parse_crash_header_text(json.dumps({
        "exception": {"type": "EXC_CRASH"},
        "termination": {"reason": "abort() called"},
        "os_version": "iOS 26.0.1"}))
    assert parsed["exception"] == "EXC_CRASH"
    assert "abort" in parsed["reason"]
    assert "26" in parsed["os_version"]


def test_crash_detail_mock_and_traversal_guard():
    rows = client.get("/diagnostics/crashes").json()
    name = rows[0]["filename"]
    detail = client.get(f"/diagnostics/crashes/{name}").json()
    assert detail["item"]["filename"] == name
    assert "preview" in detail and isinstance(detail["preview"], str)
    # Unknown names and wrong extensions are 404, never a file read.
    assert client.get("/diagnostics/crashes/nope.ips").status_code == 404
    assert client.get("/diagnostics/crashes/evil.sh").status_code == 404


def test_crash_summary_has_kinds():
    body = client.get("/diagnostics/summary").json()
    assert "crash_kinds" in body and isinstance(body["crash_kinds"], dict)


def test_syslog_relay_banners_never_surface():
    from app.services import diagnostics as diag

    banner = "[connected:00008110-0014158C0E9B601E]"
    assert diag.is_relay_banner(banner) is True
    assert diag.is_relay_banner("Sep 18 12:00:00 iPhone backupd[42]: ok") is False
    # The banner must not count, filter through, or parse as a process.
    assert banner not in diag.strip_relay_banners(f"{banner}\nreal line")
    assert diag.parse_log_process(banner) == ""
    assert diag.parse_log_process(
        "Sep 23 13:17:12.467 wifid(WiFiPolicy)[54] <Notice>: hi") == "wifid"


def test_syslog_snapshot_shape_has_entries():
    body = client.get("/diagnostics/syslog", params={"lines": 5}).json()
    assert isinstance(body.get("entries"), list)
    assert all(set(e) >= {"text", "level", "proc"} for e in body["entries"])
    assert "cached" in body and "capture_ms" in body and "window" in body


def test_syslog_stream_endpoint_streams_sse():
    # `limit` makes the mock ticker finite (a live TestClient would buffer
    # an infinite SSE body forever); a real phone ignores it.
    r = client.get("/diagnostics/syslog/stream",
                   params={"level": "all", "limit": 3})
    assert "text/event-stream" in r.headers["content-type"]
    assert "event: hello" in r.text
    rows = [json.loads(ev.split("data:", 1)[1])
            for ev in r.text.split("\n\n") if ev.startswith("data:")]
    assert len(rows) == 3
    assert all(set(row) >= {"text", "level", "proc"} for row in rows)
    assert not any(row["text"].startswith("[connected") for row in rows)


def test_toolbox_duplicates_and_tags(tmp_path=None):
    d = tempfile.mkdtemp()
    a = os.path.join(d, "a.mp3")
    b = os.path.join(d, "b.mp3")
    for p in (a, b):
        with open(p, "wb") as f:
            f.write(b"same-bytes")
    res = tb.find_duplicates(d)
    assert res["ok"] is True and res["count"] == 1
    api = client.get("/tools/duplicates", params={"path": d}).json()
    assert api["count"] == 1

    # Tag edit on non-audio returns honest failure, never crash.
    bad = client.post("/tools/tags", json={"path": os.path.join(d, "nope.mp3")}).json()
    assert bad["ok"] is False


def test_ringtone_validates_40s_limit():
    d = tempfile.mkdtemp()
    src = os.path.join(d, "s.mp3")
    with open(src, "wb") as f:
        f.write(b"x")
    res = client.post("/tools/ringtone", json={
        "src": src, "dest": os.path.join(d, "r.m4r"),
        "start_s": 0, "end_s": 99}).json()
    assert res["ok"] is False and "40" in res["reason"]


def test_flash_dry_run_requires_confirm():
    first = client.post("/flash/dry-run", json={
        "udid": "U1", "ipsw": "/tmp/x.ipsw", "mode": "quick", "confirm": False}).json()
    assert first["ok"] is False and "gates" in first
    second = flash_dry_run("U1", "/tmp/x.ipsw", "retain", True)
    assert second["ok"] is True and "--keep-data" in second["command"]
    bad = flash_dry_run("U1", "/tmp/x.ipsw", "nope", True)
    assert bad["ok"] is False
