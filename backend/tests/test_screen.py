"""Live-screen (3uTools-style realtime view) tests.

Hermetic: no device, no host tools. The autouse fixture below stubs every
host probe (subprocess, gio/systemctl, avahi, tunneld), so a test only
sees the tools it hands in through ``which``/``runner`` — results never
depend on what happens to be installed on the machine running the suite.
"""
import asyncio
import io
import json
import os
import re
import struct
import sys

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.services import screen as scr
from app.services.devices import FakeRunner
from app.services.screen import ScreenService

client = TestClient(create_app())

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "frontend", "src")
PUBLIC = os.path.join(ROOT, "frontend", "public")
PMD3 = "/usr/bin/pymobiledevice3"

# The real probes, captured before the fixture stubs them per test.
_real_avahi_state = scr.avahi_state
_real_tunneld_state = scr.tunneld_state
_real_capture_ok = scr._valeria_capture_ok


def _no_subprocess(*a, **k):
    raise OSError("hermetic test: no host tools")


@pytest.fixture(autouse=True)
def hermetic(monkeypatch):
    scr._help_cache.clear()
    scr._probe_cache.clear()
    monkeypatch.setattr(scr.subprocess, "run", _no_subprocess)
    monkeypatch.setattr(scr, "_run_capture", lambda argv, timeout=10: (1, ""))
    monkeypatch.setattr(scr, "avahi_state", lambda runner=None: "running")
    monkeypatch.setattr(scr, "tunneld_state", lambda udid: "unknown")
    monkeypatch.setattr(scr, "_first_device_is_ours",
                        lambda on_error=False: True)
    yield
    scr.hd_stop()
    scr.valeria_stop()
    scr.airplay_stop()
    scr._help_cache.clear()
    scr._probe_cache.clear()


class RecordingRunner:
    """FakeRunner that also remembers the argv of every call."""

    def __init__(self, outputs=None):
        self.calls: list[tuple[str, ...]] = []
        self.inner = FakeRunner(outputs or {})

    def run(self, *args: str, timeout: int = 15, stdin: str | None = None):
        self.calls.append(tuple(args))
        return self.inner.run(*args, timeout=timeout, stdin=stdin)


class _AliveProc:
    """Popen stand-in for a server that keeps running."""

    def __init__(self, log_text: str = "", fh=None):
        if fh is not None and log_text:
            fh.write(log_text)

    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, timeout=5):
        pass


class _DeadProc(_AliveProc):
    def poll(self):
        return 1


def _popen(cls=_AliveProc, log_text: str = "", seen: list | None = None):
    def fake(cmd, *a, **k):
        if seen is not None:
            seen.append((list(cmd), k))
        return cls(log_text, k.get("stdout"))
    return fake


def _svc(outputs: dict | None = None, **kw) -> ScreenService:
    return ScreenService(runner=FakeRunner(outputs or {}),
                         which=lambda name: f"/usr/bin/{name}", mock=False,
                         **kw)


def _probe_outputs(devmode: str | None = None, ddi: str | None = None):
    out = {}
    if devmode is not None:
        out[(PMD3, "amfi", "developer-mode-status", "--udid", "U1")] = (
            0, f"{devmode}\n", "")
    if ddi is not None:
        out[(PMD3, "mounter", "list", "--udid", "U1")] = (0, ddi, "")
    return out


MOUNTED = '[{"ImageType": "Personalized"}]'


# -- HTTP surface in mock mode: always up, never 500 ---------------------
def test_status_in_mock_is_honest():
    body = client.get("/screen/status").json()
    assert body["mode"] == "mock"
    assert body["available"] is False and body["live"] is False
    assert body["ddi"] == "unknown" and body["developer_mode"] == "unknown"
    assert any("Plug in your iPhone" in n for n in body["needs"])


def test_shot_is_a_marked_placeholder_png_in_mock():
    r = client.get("/screen/shot")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["X-Screen-Live"] == "0"
    with Image.open(io.BytesIO(r.content)) as im:
        assert im.format == "PNG" and im.size[0] >= 400 and im.size[1] >= 700
    download = client.get("/screen/shot", params={"download": True})
    assert "attachment" in download.headers.get("content-disposition", "")


def test_every_start_refuses_honestly_in_mock():
    for path in ("/screen/hd/start", "/screen/airplay/start",
                 "/screen/valeria/start", "/screen/valeria/install",
                 "/screen/valeria/usbmux-setup",
                 "/screen/setup/reveal-developer-mode",
                 "/screen/setup/enable-developer-mode",
                 "/screen/setup/mount-ddi"):
        body = client.post(path).json()
        assert body["ok"] is False and body["reason"], path
    for path in ("/screen/hd/stop", "/screen/airplay/stop",
                 "/screen/valeria/stop"):
        assert client.post(path).json()["running"] is False, path


def test_airplay_stream_refuses_when_nothing_is_mirroring():
    r = client.get("/screen/airplay/stream")
    assert r.status_code == 503
    assert "Start AirPlay receiver" in r.text


def test_mjpeg_stream_serves_multipart_jpeg_frames(monkeypatch):
    # The <img> in Preview needs real multipart framing, not just a 200.
    # TestClient never reports a disconnect, so end the stream the way a
    # server shutdown does: after two frames.
    from app.routers import screen as router
    frames = iter([False, False, True])
    monkeypatch.setattr(router, "shutting_down", lambda: next(frames))
    svc = scr.get_screen()
    real = svc.make_frame
    monkeypatch.setattr(svc, "make_frame",
                        lambda *a: (real(*a)[0], True))  # no 8 s back-off
    r = client.get("/screen/stream", params={"fps": 5, "quality": 60})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "multipart/x-mixed-replace; boundary=frame")
    parts = r.content.split(b"--frame\r\n")[1:]
    assert len(parts) == 2
    for part in parts:
        assert part.startswith(b"Content-Type: image/jpeg\r\n")
        assert part[part.index(b"\r\n\r\n") + 4:][:2] == b"\xff\xd8"


def test_stream_rejects_out_of_range_params():
    assert client.get("/screen/stream", params={"fps": 60}).status_code == 422
    assert client.get("/screen/stream",
                      params={"quality": 5}).status_code == 422


# -- MJPEG encoding -------------------------------------------------------
def test_placeholder_frame_is_encoded_once_and_reused():
    svc = ScreenService(mock=True)
    chunk, live = svc.make_frame("mock-udid", 60)
    assert live is False
    length = int(re.search(rb"Content-Length: (\d+)", chunk).group(1))
    body = chunk[chunk.index(b"\r\n\r\n") + 4:-2]
    assert len(body) == length and body[:2] == b"\xff\xd8"
    assert svc.make_frame("mock-udid", 60)[0] == chunk


def test_live_frame_is_downscaled_to_the_long_edge(monkeypatch):
    big = io.BytesIO()
    Image.new("RGB", (1170, 2532), (10, 200, 30)).save(big, "PNG")
    svc = ScreenService(mock=True)
    monkeypatch.setattr(svc, "take_shot",
                        lambda udid: (big.getvalue(), "image/png", True))
    chunk, live = svc.make_frame("U1", 70, max_dim=480)
    assert live is True
    with Image.open(io.BytesIO(chunk[chunk.index(b"\r\n\r\n") + 4:-2])) as im:
        assert im.format == "JPEG" and max(im.size) == 480
        assert im.size[1] > im.size[0], "aspect (portrait) must be kept"
    # Out-of-range sizes are clamped, never trusted.
    assert scr._clamp_preview_dim(10) == scr.PREVIEW_MAX_DIM_MIN
    assert scr._clamp_preview_dim(99999) == scr.PREVIEW_MAX_DIM_MAX


# -- Preview readiness: Developer Mode, developer image, tunnel ----------
def test_devmode_probe_parses_and_caches():
    assert _svc(_probe_outputs("true")).devmode("U1") == "on"
    assert _svc(_probe_outputs("weird")).devmode("U1") == "unknown"
    svc = _svc(_probe_outputs("false"))
    assert svc.devmode("U1") == "off"
    svc.runner = FakeRunner({})  # would answer "unknown" now
    assert svc.devmode("U1") == "off", "cached for DEVMODE_TTL_SECONDS"


def test_ddi_probe_parses_and_caches():
    def ddi(stdout, code=0):
        return _svc({(PMD3, "mounter", "list", "--udid", "U1"):
                     (code, stdout, "")})
    assert ddi("[]").ddi("U1") == "missing"
    assert ddi(MOUNTED).ddi("U1") == "mounted"
    assert ddi("not json").ddi("U1") == "unknown"
    assert ddi("[]", code=1).ddi("U1") == "unknown"
    assert ScreenService(mock=True).ddi("mock-udid") == "unknown"
    svc = ddi("[]")
    assert svc.ddi("U1") == "missing"
    svc.runner = FakeRunner({})
    assert svc.ddi("U1") == "missing"


@pytest.mark.parametrize("devmode,ddi,tunnel,ios,mode,need", [
    ("false", "[]", "up", "26.0.1", "setup", "Developer Mode is OFF"),
    ("true", "[]", "up", "26.0.1", "setup", "developer image is not mounted"),
    ("true", MOUNTED, "missing", "26.0.1", "setup", "tunneld"),
    ("true", MOUNTED, "up", "26.0.1", "mjpeg", None),
    # iOS <= 16 captures over screenshotr and never heard of tunneld.
    ("true", MOUNTED, "missing", "16.7", "mjpeg", None),
])
def test_status_reports_the_first_blocking_step(monkeypatch, devmode, ddi,
                                                tunnel, ios, mode, need):
    monkeypatch.setattr(scr, "tunneld_state", lambda udid: tunnel)
    body = _svc(_probe_outputs(devmode, ddi)).status(
        "U1", trusted=True, ios_version=ios)
    assert body["mode"] == mode
    assert body["live"] is (mode == "mjpeg")
    if need is None:
        assert body["needs"] == [], body["needs"]
    else:
        assert any(need in n for n in body["needs"]), body["needs"]


def test_devmode_off_does_not_also_nag_about_the_image():
    # One instruction at a time: the image cannot mount before the toggle.
    body = _svc(_probe_outputs("false", "[]")).status(
        "U1", trusted=True, ios_version="26.0.1")
    assert body["ddi"] == "missing"
    assert not any("developer image is not mounted" in n
                   for n in body["needs"])


def test_missing_tunnel_need_names_the_backend_interpreter(monkeypatch):
    monkeypatch.setattr(scr, "tunneld_state", lambda udid: "missing")
    body = _svc(_probe_outputs("true", MOUNTED)).status(
        "U1", trusted=True, ios_version="26.0.1")
    assert scr.TUNNELD_START_COMMAND in " ".join(body["needs"])
    assert scr.TUNNELD_START_COMMAND == (
        f"sudo {sys.executable} -m pymobiledevice3 remote tunneld")


def test_status_without_any_tool_names_the_install():
    svc = ScreenService(runner=FakeRunner({}), which=lambda _: None,
                        mock=False)
    body = svc.status("U1", trusted=True, ios_version="18.0")
    assert body["available"] is False and body["mode"] == "mock"
    assert any("pip install pymobiledevice3" in n for n in body["needs"])


def test_blocked_preview_points_trusted_phones_at_quicktime():
    # Dev Mode off gates HD + Preview, but QuickTime needs trust only.
    qvh = lambda n: f"/usr/bin/{n}"  # noqa: E731 - qvh present => ready
    body = ScreenService(runner=FakeRunner(_probe_outputs("false", "[]")),
                         which=qvh, mock=False).status(
        "U1", trusted=True, ios_version="26.0.1")
    assert body["valeria"]["ready"] is True
    assert any("QuickTime over USB needs no Developer Mode" in n
               for n in body["needs"])
    untrusted = ScreenService(runner=FakeRunner(_probe_outputs("false", "[]")),
                              which=qvh, mock=False).status(
        "U1", trusted=False, ios_version="26.0.1")
    assert any("Tap Trust" in n for n in untrusted["needs"])
    assert not any("Start QuickTime" in n for n in untrusted["needs"])


def test_mock_service_never_probes_host_tools():
    seen: list[str] = []

    def which(name):
        seen.append(name)
        return f"/usr/bin/{name}"

    ScreenService(which=which, mock=True).status("mock-udid")
    assert seen == [], f"mock status probed {seen}"


def test_tunneld_state_reads_the_daemon_list():
    import http.server
    import threading

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"U1": [{"tunnel-port": 1}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
    addr = ("127.0.0.1", srv.server_address[1])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert _real_tunneld_state("U1", address=addr) == "up"
        assert _real_tunneld_state("U2", address=addr) == "missing"
        assert _real_tunneld_state("mock-udid", address=addr) == "unknown"
    finally:
        srv.shutdown()
        srv.server_close()
    # Daemon gone: a refused connection reads as missing, never as up.
    assert _real_tunneld_state("U1", address=addr) == "missing"


# -- Shots ----------------------------------------------------------------
def test_shot_tries_dvt_with_udid_then_coredevice():
    rec = RecordingRunner()
    svc = ScreenService(runner=rec, which=lambda n: f"/usr/bin/{n}",
                        mock=False)
    data, media, live = svc.take_shot("U1")
    assert live is False and media == "image/png" and data[:4] == b"\x89PNG"
    shots = [c for c in rec.calls if "screenshot" in c and "--help" not in c]
    assert "dvt" in shots[0] and shots[0][-2:] == ("--udid", "U1")
    assert any("screen-capture" in c for c in shots), \
        "CoreDevice fallback must still run"


def test_dvt_retry_without_udid_only_when_the_phone_is_alone(monkeypatch):
    def dvt_calls(alone):
        monkeypatch.setattr(scr, "_first_device_is_ours",
                            lambda on_error=False: alone)
        rec = RecordingRunner()
        svc = ScreenService(runner=rec, which=lambda n: f"/usr/bin/{n}",
                            mock=False)
        svc._shot_via_pmd3("U1")
        return [c for c in rec.calls if "dvt" in c]
    assert len(dvt_calls(alone=True)) == 2
    # With several phones "the first USB device" may be someone else's.
    assert len(dvt_calls(alone=False)) == 1


def test_successful_shot_returns_the_pixels_and_wins_next_time():
    class _Writes:
        def run(self, *argv, timeout=15, stdin=None):
            if "dvt" in argv:
                out = argv[argv.index("screenshot") + 1]
                Image.new("RGB", (60, 120)).save(out, "PNG")
                return FakeRunner({argv: (0, "", "")}).run(*argv)
            return FakeRunner({}).run(*argv)

    svc = ScreenService(runner=_Writes(), which=lambda n: f"/usr/bin/{n}",
                        mock=False)
    data, _, live = svc.take_shot("U1")
    assert live is True and data[:4] == b"\x89PNG"
    assert svc._shot_order()[0] == "dvt"


def test_coredevice_shot_passes_udid_only_when_advertised():
    help_argv = (PMD3, "developer", "core-device", "screen-capture",
                 "screenshot", "--help")
    for help_text, want_udid in (("--display-unique-id\n", False),
                                 ("--udid <str>\n", True)):
        rec = RecordingRunner({help_argv: (0, help_text, "")})
        svc = ScreenService(runner=rec, which=lambda n: f"/usr/bin/{n}",
                            mock=False)
        svc._shot_via_coredevice("U1")
        shot = [c for c in rec.calls
                if "screen-capture" in c and "--help" not in c][0]
        assert (shot[-2:] == ("--udid", "U1")) is want_udid


def test_placeholder_names_the_missing_step(monkeypatch):
    shown: list = []
    monkeypatch.setattr(scr, "_placeholder_png",
                        lambda lines=scr.PLACEHOLDER_LINES: shown.append(lines)
                        or b"png")
    _svc(_probe_outputs("false")).take_shot("U1")
    _svc(_probe_outputs("true", "[]")).take_shot("U1")
    svc = _svc()
    monkeypatch.setattr(svc, "_shot_via_coredevice", lambda udid: None)

    def dvt_fails(udid):
        svc._last_dvt_log = "ERROR Unable to connect to Tunneld."

    monkeypatch.setattr(svc, "_shot_via_pmd3", dvt_fails)
    svc.take_shot("U1")
    assert shown == [scr.DEVMODE_OFF_LINES, scr.DDI_MISSING_LINES,
                     scr.TUNNEL_MISSING_LINES]


# -- Setup actions --------------------------------------------------------
def test_setup_actions_run_the_documented_commands_and_drop_caches():
    rec = RecordingRunner({
        (PMD3, "amfi", "reveal-developer-mode", "--udid", "U1"): (0, "", ""),
        (PMD3, "mounter", "auto-mount", "--udid", "U1"): (0, "", ""),
        (PMD3, "mounter", "list", "--udid", "U1"): (0, "[]", ""),
    })
    svc = ScreenService(runner=rec, which=lambda n: f"/usr/bin/{n}",
                        mock=False)
    assert svc.ddi("U1") == "missing"
    assert svc.reveal_devmode("U1")["ok"] is True
    rec.inner = FakeRunner({
        (PMD3, "mounter", "auto-mount", "--udid", "U1"): (0, "", ""),
        (PMD3, "mounter", "list", "--udid", "U1"): (0, MOUNTED, ""),
    })
    assert svc.mount_ddi("U1")["ok"] is True
    assert svc.ddi("U1") == "mounted", "stale 'missing' must be dropped"
    assert (PMD3, "amfi", "reveal-developer-mode", "--udid", "U1") in rec.calls
    # A failing step reports the tool's own words, not a guess.
    bad = _svc({(PMD3, "amfi", "enable-developer-mode", "--udid", "U1"):
                (1, "", "Device is locked")}).enable_devmode("U1")
    assert bad["ok"] is False and "Device is locked" in bad["reason"]


def test_already_mounted_image_is_success():
    r = _svc({(PMD3, "mounter", "auto-mount", "--udid", "U1"):
              (1, "", "DeveloperDiskImage already mounted")}).mount_ddi("U1")
    assert r["ok"] is True


# -- CLI --help probes ----------------------------------------------------
def test_help_probe_only_accepts_a_zero_exit(monkeypatch):
    class _R:
        def __init__(self, code, out):
            self.returncode, self.stdout, self.stderr = code, out, ""

    monkeypatch.setattr(scr.subprocess, "run", lambda argv, **k: _R(
        2, "Error: No such command 'screen-mirror'. --udid"))
    assert scr._screen_mirror_help("pmd3") == ""


def test_failed_help_probe_is_retried_so_a_manual_install_shows_up(
        monkeypatch):
    # Regression: a failed probe used to be cached for the process
    # lifetime, so a fork installed from a terminal read as "no
    # screen-mirror" until the backend restarted.
    class _R:
        returncode, stdout, stderr = 0, "--host --port --udid", ""

    calls: list = []
    monkeypatch.setattr(scr.subprocess, "run",
                        lambda argv, **k: calls.append(argv) or
                        (_R() if len(calls) > 1 else _no_subprocess()))
    clock = [1000.0]
    monkeypatch.setattr(scr.time, "monotonic", lambda: clock[0])
    assert scr._screen_mirror_help("pmd3") == ""
    assert scr._screen_mirror_help("pmd3") == "", "retry is rate-limited"
    clock[0] += scr.CLI_HELP_RETRY_SECONDS + 1
    assert "--udid" in scr._screen_mirror_help("pmd3")
    clock[0] += 10_000
    assert "--udid" in scr._screen_mirror_help("pmd3")
    assert len(calls) == 2, "a positive probe is kept for good"


@pytest.mark.parametrize("help_text,want", [
    ("", ["--bind", "127.0.0.1"]),
    ("--http-port <int>\n--udid <str>\n",
     ["--bind", "127.0.0.1", "--http-port", "8080", "--udid", "U1"]),
    ("--port <int>\n", ["--bind", "127.0.0.1", "--port", "8080"]),
])
def test_serve_web_cmd_passes_only_advertised_flags(monkeypatch, help_text,
                                                    want):
    # pmd3 v11's serve-web aborts on unknown flags ("No such option:
    # --udid"), which is how HD once silently never started.
    monkeypatch.setattr(scr, "_serve_web_help", lambda b: help_text)
    cmd = scr._serve_web_cmd("U1", 8080, PMD3)
    assert cmd[:5] == [PMD3, "developer", "core-device", "display",
                       "serve-web"]
    assert cmd[5:] == want


def test_valeria_cmd_passes_only_advertised_flags(monkeypatch):
    monkeypatch.setattr(scr, "_screen_mirror_help",
                        lambda b: "--host --port --backend --udid")
    assert scr._valeria_cmd("U1", 8081, PMD3) == [
        PMD3, "screen-mirror", "--host", "127.0.0.1", "--port", "8081",
        "--backend", "auto", "--udid", "U1"]
    monkeypatch.setattr(scr, "_screen_mirror_help", lambda b: "--bind")
    assert scr._valeria_cmd("U1", 8081, PMD3) == [
        PMD3, "screen-mirror", "--bind", "127.0.0.1"]


# -- Supervised servers ---------------------------------------------------
def test_servers_log_to_a_file_never_an_undrained_pipe(monkeypatch):
    # stdout=PIPE with nobody reading wedges the child once the buffer
    # fills — on a long session that looks like "the screen froze".
    seen: list = []
    monkeypatch.setattr(scr.subprocess, "Popen",
                        _popen(log_text="hello from the server", seen=seen))
    server = scr._Server("t", 1)
    server.spawn(["tool"], "U1")
    _, kwargs = seen[0]
    assert kwargs["stdout"] is not scr.subprocess.PIPE
    assert kwargs["stderr"] is scr.subprocess.STDOUT
    assert server.alive() and server.udid == "U1"
    assert server.tail() == "hello from the server"
    log = server.log
    server.stop()
    assert not server.alive() and server.tail() == ""
    assert not log.exists(), "stopping must remove the log file"


def test_hd_refuses_a_device_without_the_media_stream(monkeypatch):
    # iOS < 27 advertises nothing and every start dies as 9021.
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_media_support", lambda b: {
        "supportedFeatures": 0,
        "supportedFeaturesDescription": "No supported features"})
    seen: list = []
    monkeypatch.setattr(scr.subprocess, "Popen", _popen(seen=seen))
    r = scr.hd_start("U1", which=lambda _: PMD3)
    assert r["ok"] is False and "iOS 27" in r["reason"]
    assert r["device_says"] == "No supported features"
    assert not seen, "no server may be started for a device that refuses"


def test_hd_refuses_to_guess_between_several_phones(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_first_device_is_ours",
                        lambda on_error=False: False)
    seen: list = []
    monkeypatch.setattr(scr.subprocess, "Popen", _popen(seen=seen))
    r = scr.hd_start("U1", which=lambda _: PMD3)  # help has no --udid
    assert r["ok"] is False and "--udid" in r["reason"] and not seen


def test_hd_starts_and_reports_its_url(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_media_support", lambda b: None)  # unknown
    monkeypatch.setattr(scr._Server, "wait_http",
                        lambda self, url, timeout_s: True)
    monkeypatch.setattr(scr.subprocess, "Popen", _popen())
    r = scr.hd_start("U1", which=lambda _: PMD3, port=8099)
    assert r["ok"] is True and r["url"] == "http://127.0.0.1:8099/"
    assert scr.hd_status() == {"running": True, "udid": "U1",
                               "url": "http://127.0.0.1:8099/"}
    scr.hd_stop()
    assert scr.hd_status()["running"] is False


def test_hd_failure_carries_the_servers_last_words(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_media_support", lambda b: None)
    monkeypatch.setattr(scr.subprocess, "Popen",
                        _popen(_DeadProc, "CoreDeviceError 9021"))
    r = scr.hd_start("U1", which=lambda _: PMD3)
    assert r["ok"] is False and "CoreDeviceError 9021" in r["reason"]
    assert scr.hd_status()["running"] is False


def test_wait_http_gives_up_as_soon_as_the_process_dies():
    server = scr._Server("t", 1)
    server.proc = _DeadProc()
    assert server.wait_http("http://127.0.0.1:9/", timeout_s=30) is False


# -- QuickTime over USB (Valeria) ----------------------------------------
QT_CONFIG_LOG = ("RuntimeError: no QT-capable config (need usbmuxd-master "
                 "with USBMUXD_DEFAULT_DEVICE_MODE=2 to expose mode-2 layout)")
BUSY_LOG = ("RuntimeError: SetActiveConfiguration failed (number=6). "
            "Make sure usbmuxd is the patched build that supports this IPC.")
REFUSED_LOG = ("RuntimeError: SetActiveConfiguration failed (number=1). "
               "Make sure usbmuxd is the patched build that supports this IPC.")
ASLEEP_LOG = ("Valeria: capture handshake completed but iDevice sent no "
              "video clock - screen is likely asleep. Wake it and retry.")
HEALTHY_LOG = ("Valeria: capture started (1170x2532)\n"
               "Screen mirror ready at http://127.0.0.1:8081")


@pytest.fixture
def qt(monkeypatch):
    """A host where the fork is installed and nothing holds the USB."""
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_screen_mirror_help", lambda b: "--udid <str>")
    monkeypatch.setattr(scr, "photo_hold_state", lambda run=None: {
        "held": False, "mounts": [], "gio": True})
    # The real log check, on a short leash (a silent log times out as ok).
    monkeypatch.setattr(scr, "_valeria_capture_ok",
                        lambda timeout_s=5.0: _real_capture_ok(timeout_s=0.2))

    def start(log_text, http_ok=True, cls=_AliveProc):
        monkeypatch.setattr(scr._Server, "wait_http",
                            lambda self, url, timeout_s: http_ok)
        monkeypatch.setattr(scr.subprocess, "Popen", _popen(cls, log_text))
        return scr.valeria_start("U1", which=lambda _: PMD3, trusted=True)

    return start


def test_quicktime_starts_on_a_healthy_capture(qt):
    r = qt(HEALTHY_LOG)
    assert r["ok"] is True and r["running"] is True
    status = scr.valeria_status(which=lambda _: PMD3)
    assert status["running"] is True
    assert status["url"] == f"http://127.0.0.1:{scr.VALERIA_DEFAULT_PORT}/"


def test_quicktime_is_not_ok_when_the_server_died(qt):
    # Capture markers in the log are not enough: a dead server shows
    # nothing, so it must not be reported as running.
    r = qt(HEALTHY_LOG, cls=_DeadProc)
    assert r["ok"] is False and r["running"] is False


@pytest.mark.parametrize("log,http_ok,expect,fix", [
    (QT_CONFIG_LOG, False, "USBMUXD_DEFAULT_DEVICE_MODE=2",
     scr.VALERIA_LINUX_SETUP_URL),
    (BUSY_LOG, False, "gio mount -u", scr.VALERIA_USB_BUSY_FIX),
    # The page answers HTTP while the capture is dead: still a failure.
    (BUSY_LOG, True, "gio mount -u", scr.VALERIA_USB_BUSY_FIX),
    # number=1 is a refused switch (replug), not a held interface.
    (REFUSED_LOG, False, "replug", None),
    (ASLEEP_LOG, True, "asleep", None),
    ("boom: usb claim lost", False,
     "QuickTime server did not come up. Is the iPhone trusted", None),
])
def test_quicktime_failure_names_the_real_cause(qt, log, http_ok, expect,
                                                fix):
    r = qt(log, http_ok=http_ok)
    assert r["ok"] is False and r["running"] is False
    assert expect in r["reason"]
    assert r.get("fix") == fix
    if fix != scr.VALERIA_USB_BUSY_FIX:
        assert "gio mount -u" not in r["reason"]
    assert scr.valeria_status(which=lambda _: PMD3)["running"] is False


def test_quicktime_refuses_untrusted_without_claiming_usb(qt, monkeypatch):
    seen: list = []
    monkeypatch.setattr(scr.subprocess, "Popen", _popen(seen=seen))
    r = scr.valeria_start("U1", which=lambda _: PMD3, trusted=False)
    assert r["ok"] is False and "Trust" in r["reason"]
    assert "no Developer Mode" in r["reason"] and not seen


def test_quicktime_fails_fast_when_a_photo_importer_holds_usb(qt,
                                                              monkeypatch):
    udid = "00008110-0014158C0E9B601E"
    monkeypatch.setattr(scr, "photo_hold_state", lambda run=None: {
        "held": True, "gio": True,
        "mounts": ["gphoto2://Apple_Inc._iPhone_000081100014158C0E9B601E/"]})
    seen: list = []
    monkeypatch.setattr(scr.subprocess, "Popen", _popen(seen=seen))
    r = scr.valeria_start(udid, which=lambda _: PMD3, trusted=True)
    assert r["ok"] is False and r["fix"] == scr.VALERIA_USB_BUSY_FIX
    assert not seen, "a held USB interface must not spawn a USB claim"
    # Another phone's photo mount does not block this one.
    monkeypatch.setattr(scr._Server, "wait_http",
                        lambda self, url, timeout_s: True)
    scr.valeria_start("00008030-000A1B2C3D4E5F60", which=lambda _: PMD3,
                      trusted=True)
    assert seen, "an unrelated mount must not block the start"


def test_quicktime_without_the_fork_names_the_install(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    stock = {"pymobiledevice3": PMD3}.get  # stock pmd3, no qvh
    r = scr.valeria_start("U1", which=stock, trusted=True)
    assert r["ok"] is False and "screen-mirror" in r["reason"]
    assert scr.VALERIA_INSTALL_HINT in r["reason"]
    status = scr.valeria_status(which=stock)
    assert status["ready"] is False and status["screen_mirror"] is False
    assert any("no `screen-mirror` subcommand" in n for n in status["needs"])


def test_photo_hold_probe_parses_gphoto_mounts():
    out = ("Mount(0): iPhone -> "
           "gphoto2://Apple_Inc._iPhone_000081100014158C0E9B601E/\n"
           "Mount(1): Documents -> afc://00008110-0014158C0E9B601E:3/\n")
    body = scr._photo_hold_probe(run=lambda argv, timeout=10: (0, out))
    assert body == {"held": True, "gio": True, "mounts": [
        "gphoto2://Apple_Inc._iPhone_000081100014158C0E9B601E/"]}
    assert scr._mount_matches_udid(body["mounts"][0],
                                   "00008110-0014158C0E9B601E")
    assert not scr._mount_matches_udid(body["mounts"][0], "")
    assert scr._photo_hold_probe(
        run=lambda argv, timeout=10: (1, ""))["gio"] is False


def test_host_probes_are_cached_between_status_polls(monkeypatch):
    calls: list = []
    monkeypatch.setattr(scr, "usbmuxd_state", lambda run=None: calls.append(
        1) or {"linux": True, "ready": False, "needs": ["Install fork."]})
    for _ in range(3):
        body = scr.valeria_status(which=lambda _: None)
    assert len(calls) == 1, "usbmuxd is probed once per TTL, not per poll"
    assert any("Linux one-time USB setup" in n for n in body["needs"])


# -- Linux USB setup (usbmuxd fork) ---------------------------------------
class _FP:
    """pathlib.Path stand-in covering is_file() only."""

    present: set = set()

    def __init__(self, p):
        self._p = str(p)

    def is_file(self):
        return self._p in _FP.present


_FORK_SHOW = ("ExecStart={ path=/usr/local/sbin/usbmuxd ; argv[]=... ; }\n"
              "Environment=USBMUXD_DEFAULT_DEVICE_MODE=2\n")
_DISTRO_SHOW = "ExecStart={ path=/usr/bin/usbmuxd ; argv[]=... ; }\n"


def _usbmux(monkeypatch, present, outputs):
    monkeypatch.setattr(scr.sys, "platform", "linux")
    _FP.present = present
    monkeypatch.setattr(scr, "Path", _FP)
    return scr.usbmuxd_state(
        run=lambda argv, timeout=10: outputs.get(tuple(argv), (1, "")))


def test_usbmuxd_state_ready_only_with_the_fork_running_in_mode_2(
        monkeypatch):
    common = {
        (scr.USBMUXD_FORK_BIN, "--version"): (0, "usbmuxd 1.1.1-abc\n"),
        ("grep", "-a", "-q", "USBMUXD_DEFAULT_DEVICE_MODE",
         scr.USBMUXD_FORK_BIN): (0, ""),
        ("systemctl", "is-active", "usbmuxd"): (0, "active\n"),
    }
    show = ("systemctl", "show", "usbmuxd", "-p", "ExecStart,Environment")
    ok = _usbmux(monkeypatch, {scr.USBMUXD_FORK_BIN},
                 {**common, show: (0, _FORK_SHOW)})
    assert ok["ready"] is True and ok["needs"] == []
    assert ok["fork_version"] == "usbmuxd 1.1.1-abc"
    # Fork installed but the distro binary still runs: not ready.
    stale = _usbmux(monkeypatch, {scr.USBMUXD_FORK_BIN},
                    {**common, show: (0, _DISTRO_SHOW)})
    assert stale["ready"] is False
    assert any("Switch the running usbmuxd" in n for n in stale["needs"])
    distro = _usbmux(monkeypatch, set(), {show: (0, _DISTRO_SHOW)})
    assert distro["ready"] is False and distro["fork_installed"] is False
    assert distro["setup_command"].endswith("setup-valeria-linux.sh")


def test_usbmuxd_state_off_linux_has_nothing_to_do(monkeypatch):
    monkeypatch.setattr(scr.sys, "platform", "darwin")
    assert scr.usbmuxd_state() == {"linux": False, "ready": True,
                                  "needs": []}
    assert scr.valeria_status(which=lambda _: None)["linux_hint"] == ""


def _proc_result(code: int, out: str = ""):
    class _R:
        returncode, stdout, stderr = code, out, ""
    seen: list = []

    def run(argv, **k):
        seen.append(list(argv))
        return _R()
    run.seen = seen
    return run


def test_usbmux_setup_trusts_the_probe_not_the_exit_code(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr.sys, "platform", "linux")
    run = _proc_result(0, "done")
    monkeypatch.setattr(scr.subprocess, "run", run)
    state = {"ready": False}
    monkeypatch.setattr(scr, "usbmuxd_state",
                        lambda run=None: {"linux": True, **state,
                                          "needs": []})
    assert scr.valeria_usbmux_setup()["ok"] is False
    state["ready"] = True
    r = scr.valeria_usbmux_setup()
    assert r["ok"] is True and "replug" in r["note"]
    assert run.seen[0][-1].endswith("setup-valeria-linux.sh")


def test_usbmux_setup_without_a_terminal_hands_over_the_command(
        monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr.sys, "platform", "linux")
    monkeypatch.setattr(scr.subprocess, "run", _proc_result(3))
    r = scr.valeria_usbmux_setup()
    assert r["ok"] is False and "sudo" in r["reason"]
    assert r["command"] == scr.VALERIA_USBMUX_SETUP_COMMAND
    monkeypatch.setattr(scr.sys, "platform", "darwin")
    assert "Linux-only" in scr.valeria_usbmux_setup()["reason"]


# -- One-click fork install -----------------------------------------------
def test_install_pins_construct_typing_for_the_fork():
    # The fork snapshot breaks on construct-typing 0.8+ (DataclassFieldError
    # on import kills every AFC/DVT path), and it allows >=0.7.0 itself.
    assert "construct-typing<0.8" in scr.VALERIA_INSTALL_PACKAGES
    assert '"construct-typing<0.8"' in scr.VALERIA_INSTALL_COMMAND
    assert scr.VALERIA_FORK_URL in scr.VALERIA_INSTALL_PACKAGES


def test_install_reports_pips_own_cause(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr.subprocess, "run", _proc_result(
        1, "Collecting x\nerror: pathspec 'screen-mirror' did not match\n"
           "Failed to build"))
    r = scr.valeria_install(which=lambda _: PMD3)
    assert r["ok"] is False and "pathspec 'screen-mirror'" in r["reason"]
    assert r["command"] == scr.VALERIA_INSTALL_COMMAND
    assert scr._valeria_installing is False, "the busy flag must reset"


def test_install_succeeds_only_when_screen_mirror_appears(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    run = _proc_result(0, "Successfully installed pymobiledevice3")
    monkeypatch.setattr(scr.subprocess, "run", run)
    installed = {"yes": False}
    monkeypatch.setattr(scr, "_screen_mirror_help",
                        lambda b: "--udid" if installed["yes"] else "")
    assert scr.valeria_install(which=lambda _: PMD3)["ok"] is False
    installed["yes"] = True
    assert scr.valeria_install(which=lambda _: PMD3)["already"] is True
    assert run.seen[0][:4] == [sys.executable, "-m", "pip", "install"]


# -- AirPlay --------------------------------------------------------------
def _hint_for(monkeypatch, os_release: dict, helpers=()) -> str:
    monkeypatch.setattr(scr, "_os_release", lambda: os_release)
    return scr.uxplay_install_hint(
        which=lambda n: f"/usr/bin/{n}" if n in helpers else None)


def test_uxplay_hint_matches_the_distro(monkeypatch):
    arch = _hint_for(monkeypatch, {"ID": "arch"}, helpers=("yay",))
    assert arch.startswith("yay -S uxplay") and "apt" not in arch
    assert "makepkg" in _hint_for(monkeypatch, {"ID": "arch"})
    assert _hint_for(monkeypatch, {"ID": "ubuntu", "ID_LIKE": "debian"}) \
        == "sudo apt install uxplay"
    assert _hint_for(monkeypatch, {"ID": "fedora"}) == \
        "sudo dnf install uxplay"
    assert _hint_for(monkeypatch, {"ID": "plan9"}) == scr.UXPLAY_SOURCE_HINT


def test_airplay_status_lists_what_the_host_is_missing(monkeypatch):
    monkeypatch.setattr(scr, "avahi_state", lambda runner=None: "stopped")
    body = scr.airplay_status(which=lambda _: None)
    assert body["ready"] is False and len(body["needs"]) == 2
    monkeypatch.setattr(scr, "avahi_state", lambda runner=None: "running")
    ok = scr.airplay_status(which=lambda n: f"/usr/bin/{n}")
    assert ok["ready"] is True and ok["needs"] == []


def test_airplay_refuses_without_uxplay_or_mdns(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    seen: list = []
    monkeypatch.setattr(scr.subprocess, "Popen", _popen(seen=seen))
    monkeypatch.setattr(scr, "_os_release", lambda: {"ID": "arch"})
    r = scr.airplay_start(which=lambda _: None)
    assert r["ok"] is False and "AUR" in r["reason"] and r["fix"]
    monkeypatch.setattr(scr, "avahi_state", lambda runner=None: "stopped")
    r = scr.airplay_start(which=lambda n: f"/usr/bin/{n}")
    assert r["ok"] is False and "avahi-daemon" in r["reason"]
    assert not seen


def test_airplay_embeds_via_the_mjpeg_sink_or_uses_a_window(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr.time, "sleep", lambda s: None)
    seen: list = []
    monkeypatch.setattr(scr.subprocess, "Popen", _popen(seen=seen))
    r = scr.airplay_start(which=lambda n: f"/usr/bin/{n}")
    cmd = seen[0][0]
    assert r["ok"] is True and r["embedded"] is True
    assert cmd[cmd.index("-vs") + 1] == scr.airplay_sink()
    assert scr.airplay_status()["stream_url"] == "/screen/airplay/stream"
    scr.airplay_stop()
    assert scr.airplay_status()["embedded"] is False
    r = scr.airplay_start(which=lambda n: f"/usr/bin/{n}", embed=False)
    assert r["embedded"] is False and "-vs" not in seen[1][0]
    assert scr.airplay_status()["stream_url"] == ""


def test_airplay_that_dies_at_once_says_why(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr.time, "sleep", lambda s: None)
    monkeypatch.setattr(scr.subprocess, "Popen",
                        _popen(_DeadProc, "Error: port 7000 in use"))
    r = scr.airplay_start(which=lambda n: f"/usr/bin/{n}")
    assert r["ok"] is False and "port 7000 in use" in r["reason"]
    assert scr.airplay_status()["running"] is False


def test_airplay_sink_scales_both_edges_for_rotation():
    sink = scr.airplay_sink(port=9099, long_edge=480, fps=24, quality=65)
    # Ranges on BOTH edges keep the aspect when the phone rotates.
    assert "width=[16,480]" in sink and "height=[16,480]" in sink
    assert "pixel-aspect-ratio=1/1" in sink
    assert "framerate=24/1" in sink and "jpegenc quality=65" in sink
    assert "multipartmux boundary=frame" in sink
    assert sink.endswith("tcpserversink host=127.0.0.1 port=9099")


def test_avahi_state_reads_socket_then_systemd(monkeypatch, tmp_path):
    sock = tmp_path / "avahi.sock"
    monkeypatch.setattr(scr, "AVAHI_SOCKETS", (str(sock),))
    monkeypatch.setattr(scr, "SubprocessRunner", lambda: FakeRunner({
        ("systemctl", "is-active", "avahi-daemon"): (3, "inactive\n", "")}))
    assert _real_avahi_state() == "stopped"
    sock.write_text("")
    assert _real_avahi_state() == "running"


def _relay(handle) -> list:
    async def drive():
        srv = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        got: list = []
        try:
            async for chunk in scr.airplay_frames(port=port, tick=0.05):
                got.append(chunk)
                if len(got) >= 3 or (chunk and chunk.endswith(b"\r\n")):
                    break
        finally:
            srv.close()
            await srv.wait_closed()
        return got
    return asyncio.run(asyncio.wait_for(drive(), timeout=10))


def test_airplay_relay_ticks_while_idle_so_a_closed_tab_is_noticed():
    # A read that parks forever outlives the browser tab and hangs
    # uvicorn's graceful shutdown (every --reload restart).
    async def silent(reader, writer):
        await asyncio.sleep(3)
        writer.close()
    assert _relay(silent) == [None, None, None]


def test_airplay_relay_passes_frames_through_untouched():
    payload = (b"--frame\r\nContent-Type: image/jpeg\r\n"
               b"Content-Length: 4\r\n\r\n\xff\xd8\xff\xd9\r\n")

    async def talker(reader, writer):
        writer.write(payload)
        await writer.drain()
        writer.close()
    assert b"".join(c for c in _relay(talker) if c) == payload


# -- Frontend contract ----------------------------------------------------
def _ts_fields(src: str, name: str) -> dict[str, bool]:
    """Field -> optional, for ``export interface <name> { ... }``."""
    start = src.index("{", src.index(f"export interface {name} ")) + 1
    depth, end = 1, start
    while depth:
        depth += {"{": 1, "}": -1}.get(src[end], 0)
        end += 1
    body = re.sub(r"/\*\*.*?\*/", "", src[start:end - 1], flags=re.S)
    body = re.sub(r"\{[^{}]*\}", "X", body)  # inline object types
    return {m.group(1): bool(m.group(2))
            for m in re.finditer(r"(\w+)(\?)?\s*:", body)}


def test_frontend_types_match_what_the_backend_sends():
    # Every field ScreenView reads must exist in the real payload — a
    # renamed key otherwise renders as a silently empty tab.
    with open(os.path.join(SRC, "api.ts")) as f:
        api = f.read()
    body = _svc(_probe_outputs("true", MOUNTED)).status(
        "U1", trusted=True, ios_version="26.0.1")
    for iface, payload in (("ScreenStatus", body), ("ScreenHd", body["hd"]),
                           ("ScreenValeria", body["valeria"]),
                           ("ScreenAirplay", body["airplay"])):
        fields = _ts_fields(api, iface)
        assert fields, f"could not parse {iface}"
        missing = sorted(set(fields) - set(payload))
        assert not missing, f"{iface} declares fields the API never sends: " \
                            f"{missing}"


def test_screen_api_paths_exist_on_the_backend():
    with open(os.path.join(SRC, "api.ts")) as f:
        api = f.read()
    used = set(re.findall(r"\$\{base\}(/screen/[a-z/-]+)", api))
    routes = set(create_app().openapi()["paths"])
    assert used and not (used - routes), sorted(used - routes)


# -- Phone frame artwork vs the CSS cutouts -------------------------------
def _contour_art() -> dict[str, dict[str, str]]:
    with open(os.path.join(SRC, "components", "IPhoneFrame.tsx")) as f:
        src = f.read()
    block = src.split("const CONTOUR_ART")[1].split("};")[0]
    return {m.group(1): {"portrait": m.group(2), "landscape": m.group(3)}
            for m in re.finditer(r"'?([\w-]+)'?: \{ portrait: '([^']+)', "
                                 r"landscape: '([^']+)' \}", block)}


def _hole(path: str) -> dict[str, float]:
    """Percent box of the transparent screen hole.

    The widest transparent run through the center, over scan lines at
    15-85% of the other axis: rounded corners and the opaque notch or
    island (drawn over the mirror) only ever shorten a run, so the widest
    one is the hole's straight edge.
    """
    with Image.open(path) as im:
        alpha = im.convert("RGBA").getchannel("A")
    w, h = alpha.size
    px = alpha.load()

    def widest(n, m, clear):
        best = (n, 0)
        for i in range(15, 86, 5):
            lo = hi = n // 2
            while lo > 0 and clear(lo - 1, m * i // 100):
                lo -= 1
            while hi < n - 1 and clear(hi + 1, m * i // 100):
                hi += 1
            best = (min(best[0], lo), max(best[1], hi + 1))
        return best

    x0, x1 = widest(w, h, lambda x, y: px[x, y] < 128)
    y0, y1 = widest(h, w, lambda y, x: px[x, y] < 128)
    return {"left": x0 / w * 100, "top": y0 / h * 100,
            "width": (x1 - x0) / w * 100, "height": (y1 - y0) / h * 100}


def _css_box(css: str, selector: str) -> dict[str, float]:
    m = re.search(re.escape(selector) + r"[^{]*\{([^}]*)\}", css)
    assert m, f"apple.css has no rule for {selector}"
    return {k: float(v) for k, v in
            re.findall(r"(left|top|width|height):\s*([\d.]+)%", m.group(1))}


def test_every_contour_places_the_mirror_exactly_in_its_art_hole():
    # The live mirror (img, iframe and the QuickTime canvas) must sit in
    # the artwork's transparent hole in both orientations, or it shows
    # black bars / slides under the bezel. Measured from the PNGs.
    with open(os.path.join(SRC, "apple.css")) as f:
        css = f.read()
    art = _contour_art()
    assert len(art) >= 10, art
    for contour, files in art.items():
        for orient, sel in (
                ("portrait", f".ft-iphone.is-{contour}.has-art"),
                ("landscape", f".ft-iphone.has-art.is-landscape.is-{contour}")):
            hole = _hole(os.path.join(PUBLIC, files[orient].lstrip("/")))
            for el in (".ft-screen-img", ".ft-screen-hd"):
                box = _css_box(css, f"{sel} {el}")
                for k, v in hole.items():
                    assert abs(box[k] - v) < 0.5, (
                        f"{contour} {orient} {el}: {k} {box[k]}% but the "
                        f"art hole is {v:.2f}%")


def test_landscape_art_is_the_portrait_art_rotated():
    for contour, files in _contour_art().items():
        sizes = []
        for orient in ("portrait", "landscape"):
            with open(os.path.join(PUBLIC, files[orient].lstrip("/")),
                      "rb") as f:
                head = f.read(24)
            assert head[:8] == b"\x89PNG\r\n\x1a\n", files[orient]
            sizes.append(struct.unpack(">II", head[16:24]))
        assert sizes[1] == sizes[0][::-1], f"{contour}: {sizes}"
