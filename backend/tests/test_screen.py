"""Live-screen (3uTools-style realtime view) tests.

Hermetic (FREETUNES_MOCK=1): no device, no tools — every endpoint must
stay up with placeholder pixels and honest setup hints, never 500.
"""
import io

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import screen as scr
from app.services.devices import FakeRunner
from app.services.screen import ScreenService

app = create_app()
client = TestClient(app)


def test_status_shape_mock():
    body = client.get("/screen/status").json()
    assert body["mode"] == "mock"
    assert body["available"] is False
    assert body["live"] is False
    assert isinstance(body["needs"], list) and len(body["needs"]) >= 1
    assert {"pymobiledevice3", "idevicescreenshot", "uxplay"} <= set(
        body["backends"])
    assert {"running", "url"} <= set(body["hd"])
    assert {"running", "howto"} <= set(body["airplay"])
    assert "pymobiledevice3" in body["hints"]


def test_shot_returns_placeholder_png_in_mock():
    r = client.get("/screen/shot")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["X-Screen-Live"] == "0"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(r.content) > 1000


def test_shot_download_disposition():
    r = client.get("/screen/shot", params={"download": True})
    assert "attachment" in r.headers.get("content-disposition", "")


def test_mjpeg_first_frame_framing():
    svc = ScreenService(mock=True)
    chunk, live = svc.make_frame("mock-udid", 60)
    assert live is False  # placeholder in mock mode
    assert chunk.startswith(b"--frame\r\nContent-Type: image/jpeg\r\n")
    start = chunk.index(b"\r\n\r\n") + 4
    jpg = chunk[:-2]
    assert jpg[start:start + 2] == b"\xff\xd8"  # real JPEG bytes for <img>
    # Placeholder JPEG is encoded once and reused.
    again, _ = svc.make_frame("mock-udid", 60)
    assert again == chunk


def test_hd_and_airplay_refuse_honestly_in_mock():
    hd = client.post("/screen/hd/start").json()
    assert hd["ok"] is False and "reason" in hd
    assert client.post("/screen/hd/stop").json()["running"] is False
    assert client.get("/screen/hd").json()["running"] is False
    ap = client.post("/screen/airplay/start").json()
    assert ap["ok"] is False and "reason" in ap
    assert client.post("/screen/airplay/stop").json()["running"] is False
    assert "Screen Mirroring" in client.get("/screen/airplay").json()["howto"]


def test_status_no_tools_no_device_names_install():
    svc = ScreenService(runner=FakeRunner({}), which=lambda _: None,
                        mock=False)
    body = svc.status("some-udid", trusted=True, ios_version="18.0")
    assert body["available"] is False
    assert any("pip install pymobiledevice3" in n for n in body["needs"])


def test_shot_falls_back_when_providers_fail():
    svc = ScreenService(runner=FakeRunner({}), mock=False,
                        which=lambda name: f"/usr/bin/{name}")
    data, media, live = svc.take_shot("U1")
    assert live is False and media == "image/png"
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_serve_web_cmd_never_passes_unknown_flags():
    # Unknown binary: the --help probe must fail soft and the command
    # must stay at the documented base form — no port flag and no --udid
    # without proof the CLI has them. pmd3 v11's serve-web aborts with
    # "No such option: --udid", which is how HD silently never started.
    scr._serve_web_help_cache.clear()
    cmd = scr._serve_web_cmd("U1", 8080, "/nonexistent/pymobiledevice3")
    assert cmd[0] == "/nonexistent/pymobiledevice3"
    assert "--udid" not in cmd
    assert "--port" not in cmd and "--http-port" not in cmd
    assert "serve-web" in cmd and cmd[-2:] == ["--bind", "127.0.0.1"]


def test_serve_web_cmd_uses_flags_the_cli_advertises(monkeypatch):
    scr._serve_web_help_cache.clear()
    monkeypatch.setattr(scr, "_serve_web_help",
                        lambda b: "--http-port <int>\n--udid <str>\n")
    cmd = scr._serve_web_cmd("U1", 8080, "pymobiledevice3")
    assert cmd[-2:] == ["--udid", "U1"]
    assert "--http-port" in cmd and "8080" in cmd


def test_placeholder_is_valid_image():
    from PIL import Image
    data, _, live = ScreenService(mock=True).take_shot("mock-udid")
    assert live is False
    with Image.open(io.BytesIO(data)) as im:
        assert im.size[0] >= 400 and im.size[1] >= 700


def _svc_with_devmode(state: str) -> ScreenService:
    return ScreenService(
        runner=FakeRunner({
            ("/usr/bin/pymobiledevice3", "amfi", "developer-mode-status",
             "--udid", "U1"): (0, f"{state}\n", ""),
        }),
        which=lambda name: f"/usr/bin/{name}",
        mock=False)


def test_devmode_probe_parses_on_off():
    assert _svc_with_devmode("true").devmode("U1") == "on"
    assert _svc_with_devmode("false").devmode("U1") == "off"
    assert _svc_with_devmode("weird").devmode("U1") == "unknown"


def test_devmode_off_means_setup_not_live():
    body = _svc_with_devmode("false").status("U1", trusted=True,
                                             ios_version="26.0.1")
    assert body["developer_mode"] == "off"
    assert body["mode"] == "setup"
    assert body["live"] is False
    assert any("Developer Mode is OFF" in n for n in body["needs"])


def test_devmode_on_means_mjpeg_live():
    body = _svc_with_devmode("true").status("U1", trusted=True,
                                            ios_version="26.0.1")
    assert body["developer_mode"] == "on"
    assert body["mode"] == "mjpeg"
    assert body["live"] is True


def test_devmode_result_is_cached():
    svc = _svc_with_devmode("false")
    assert svc.devmode("U1") == "off"
    svc.runner = FakeRunner({})  # would fail now; cache must cover it
    assert svc.devmode("U1") == "off"


# -- frontend contract: the Screen tab must be fully wired ----------------
import os as _os

_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
_SRC = _os.path.join(_ROOT, "frontend", "src")
_API = _os.path.join(_SRC, "api.ts")
_VIEW = _os.path.join(_SRC, "components", "ScreenView.tsx")
_SIDE = _os.path.join(_SRC, "components", "Sidebar.tsx")
_APP = _os.path.join(_SRC, "App.tsx")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def test_screen_api_clients_exist():
    api = _read(_API)
    for fn in ("screenStatus", "screenShotUrl", "screenStreamUrl",
               "screenSnapshot", "screenHdStart", "screenHdStop",
               "screenAirplayStart", "screenAirplayStop"):
        assert fn in api, f"api.ts missing {fn}() client"
    assert "X-Screen-Live" in api, "snapshot must honor the live header"


def test_screen_view_covers_all_three_modes():
    view = _read(_VIEW)
    for label in ("Preview (USB)", "HD (USB)", "AirPlay (Wi-Fi)"):
        assert label in view, f"ScreenView missing mode tab: {label}"
    for token in ("api.screenStatus", "api.screenSnapshot",
                  "api.screenHdStart", "LIVE", "PLACEHOLDER",
                  "needs", "Screenshot"):
        assert token in view, f"ScreenView missing: {token}"
    assert "useEffect" in view, "screen status must load on mount"


def test_screen_tab_wired_into_chrome():
    assert "Screen" in _read(_SIDE), "Sidebar missing the Screen entry"
    app = _read(_APP)
    assert "ScreenView" in app, "App must render ScreenView"
    assert "'screen'" in app or '"screen"' in app, \
        "App must route the screen view"


# -- iOS 17-26 setup: Developer Mode + DeveloperDiskImage ----------------
class RecordingRunner:
    """FakeRunner that also remembers the argv of every call."""

    def __init__(self, outputs=None):
        self.calls: list[tuple[str, ...]] = []
        self.inner = FakeRunner(outputs or {})

    def run(self, *args: str, timeout: int = 15, stdin: str | None = None):
        self.calls.append(tuple(args))
        return self.inner.run(*args, timeout=timeout, stdin=stdin)


def _svc(outputs: dict) -> ScreenService:
    return ScreenService(runner=FakeRunner(outputs),
                         which=lambda name: f"/usr/bin/{name}", mock=False)


def _ddi_svc(stdout: str, code: int = 0) -> ScreenService:
    return _svc({
        ("/usr/bin/pymobiledevice3", "mounter", "list",
         "--udid", "U1"): (code, stdout, ""),
    })


def test_ddi_probe_parses_mount_state():
    assert _ddi_svc("[]").ddi("U1") == "missing"
    assert _ddi_svc('[{"ImageSignature": "abc"}]').ddi("U1") == "mounted"
    assert _ddi_svc("not json").ddi("U1") == "unknown"
    assert _ddi_svc("[]", code=1).ddi("U1") == "unknown"
    assert ScreenService(mock=True).ddi("mock-udid") == "unknown"


def test_ddi_result_is_cached():
    svc = _ddi_svc("[]")
    assert svc.ddi("U1") == "missing"
    svc.runner = FakeRunner({})  # would answer "unknown" now
    assert svc.ddi("U1") == "missing"


def test_unmounted_ddi_blocks_live_even_with_devmode_on():
    svc = _svc({
        ("/usr/bin/pymobiledevice3", "amfi", "developer-mode-status",
         "--udid", "U1"): (0, "true\n", ""),
        ("/usr/bin/pymobiledevice3", "mounter", "list",
         "--udid", "U1"): (0, "[]", ""),
    })
    body = svc.status("U1", trusted=True, ios_version="26.0.1")
    assert body["ddi"] == "missing"
    assert body["mode"] == "setup" and body["live"] is False
    assert any("developer image is not mounted" in n for n in body["needs"])


def test_mounted_ddi_plus_devmode_is_live(monkeypatch):
    monkeypatch.setattr(scr, "tunneld_state", lambda udid: "up")
    svc = _svc({
        ("/usr/bin/pymobiledevice3", "amfi", "developer-mode-status",
         "--udid", "U1"): (0, "true\n", ""),
        ("/usr/bin/pymobiledevice3", "mounter", "list",
         "--udid", "U1"): (0, '[{"ImageType": "Personalized"}]', ""),
    })
    body = svc.status("U1", trusted=True, ios_version="26.0.1")
    assert body["ddi"] == "mounted"
    assert body["tunneld"] == "up"
    assert body["mode"] == "mjpeg" and body["live"] is True
    assert not any("developer image" in n for n in body["needs"])


def test_ready_phone_has_an_empty_checklist(monkeypatch):
    # Developer Mode on + image mounted + tunnel up: nothing left to ask.
    monkeypatch.setattr(scr, "tunneld_state", lambda udid: "up")
    svc = _svc({
        ("/usr/bin/pymobiledevice3", "amfi", "developer-mode-status",
         "--udid", "U1"): (0, "true\n", ""),
        ("/usr/bin/pymobiledevice3", "mounter", "list",
         "--udid", "U1"): (0, '[{"ImageType": "Personalized"}]', ""),
    })
    body = svc.status("U1", trusted=True, ios_version="26.0.1")
    assert body["live"] is True
    assert body["needs"] == [], body["needs"]


def test_devmode_off_does_not_nag_about_the_ddi():
    # One instruction at a time: the image cannot mount before the toggle.
    svc = _svc({
        ("/usr/bin/pymobiledevice3", "amfi", "developer-mode-status",
         "--udid", "U1"): (0, "false\n", ""),
        ("/usr/bin/pymobiledevice3", "mounter", "list",
         "--udid", "U1"): (0, "[]", ""),
    })
    body = svc.status("U1", trusted=True, ios_version="26.0.1")
    assert body["ddi"] == "missing"
    assert not any("developer image is not mounted" in n
                   for n in body["needs"])


def test_shot_tries_dvt_then_coredevice():
    # DVT leads: it is the path verified on iOS 26.0.1 and the only one
    # that takes --udid. CoreDevice covers the day DVT disappears.
    rec = RecordingRunner()
    svc = ScreenService(runner=rec, which=lambda n: f"/usr/bin/{n}",
                        mock=False)
    _, _, live = svc.take_shot("U1")
    assert live is False
    shots = [c for c in rec.calls if "screenshot" in c and "--help" not in c]
    assert shots, "no screenshot attempt was made"
    assert "dvt" in shots[0] and shots[0][-2:] == ("--udid", "U1")
    assert any("screen-capture" in c for c in shots), \
        "CoreDevice fallback must still run"


def test_coredevice_shot_omits_udid_when_the_cli_rejects_it():
    # pmd3 v11: `screen-capture screenshot` has no --udid. Passing it
    # anyway is how this path silently never worked.
    help_no_udid = ("/usr/bin/pymobiledevice3", "developer", "core-device",
                    "screen-capture", "screenshot", "--help")
    rec = RecordingRunner({help_no_udid: (0, "--display-unique-id\n", "")})
    svc = ScreenService(runner=rec, which=lambda n: f"/usr/bin/{n}",
                        mock=False)
    svc._shot_via_coredevice("U1")
    shots = [c for c in rec.calls
             if "screen-capture" in c and "--help" not in c]
    assert shots, "CoreDevice shot never ran"
    assert "--udid" not in shots[0]
    # A CLI that does advertise the flag gets it.
    rec2 = RecordingRunner({help_no_udid: (0, "--udid <str>\n", "")})
    svc2 = ScreenService(runner=rec2, which=lambda n: f"/usr/bin/{n}",
                         mock=False)
    svc2._shot_via_coredevice("U1")
    shots2 = [c for c in rec2.calls
              if "screen-capture" in c and "--help" not in c]
    assert shots2 and shots2[0][-2:] == ("--udid", "U1")


def test_shot_order_prefers_the_last_winner():
    svc = ScreenService(mock=True)
    assert svc._shot_order() == scr.SHOT_PROVIDERS
    svc._shot_provider = "coredevice"
    assert svc._shot_order()[0] == "coredevice"
    assert set(svc._shot_order()) == set(scr.SHOT_PROVIDERS)


def test_placeholder_names_the_missing_step():
    svc = _svc({
        ("/usr/bin/pymobiledevice3", "amfi", "developer-mode-status",
         "--udid", "U1"): (0, "true\n", ""),
        ("/usr/bin/pymobiledevice3", "mounter", "list",
         "--udid", "U1"): (0, "[]", ""),
    })
    assert svc._why_no_pixels("U1") == scr.DDI_MISSING_LINES
    off = _svc_with_devmode("false")
    assert off._why_no_pixels("U1") == scr.DEVMODE_OFF_LINES


def test_setup_actions_run_the_documented_commands():
    rec = RecordingRunner({
        ("/usr/bin/pymobiledevice3", "amfi", "reveal-developer-mode",
         "--udid", "U1"): (0, "", ""),
        ("/usr/bin/pymobiledevice3", "mounter", "auto-mount",
         "--udid", "U1"): (0, "", ""),
    })
    svc = ScreenService(runner=rec, which=lambda n: f"/usr/bin/{n}",
                        mock=False)
    assert svc.reveal_devmode("U1")["ok"] is True
    assert svc.mount_ddi("U1")["ok"] is True
    assert ("/usr/bin/pymobiledevice3", "amfi", "reveal-developer-mode",
            "--udid", "U1") in rec.calls
    assert ("/usr/bin/pymobiledevice3", "mounter", "auto-mount",
            "--udid", "U1") in rec.calls
    # A failing step reports the tool's own words, not a guess.
    bad = _svc({}).enable_devmode("U1")
    assert bad["ok"] is False and bad["reason"]


def test_setup_actions_clear_the_probe_caches():
    svc = _ddi_svc("[]")
    assert svc.ddi("U1") == "missing"
    svc.runner = FakeRunner({
        ("/usr/bin/pymobiledevice3", "mounter", "auto-mount",
         "--udid", "U1"): (0, "", ""),
        ("/usr/bin/pymobiledevice3", "mounter", "list",
         "--udid", "U1"): (0, '[{"ImageType": "Personalized"}]', ""),
    })
    assert svc.mount_ddi("U1")["ok"] is True
    assert svc.ddi("U1") == "mounted"  # stale "missing" must be gone


def test_setup_endpoints_refuse_honestly_in_mock():
    for path in ("/screen/setup/reveal-developer-mode",
                 "/screen/setup/enable-developer-mode",
                 "/screen/setup/mount-ddi"):
        body = client.post(path).json()
        assert body["ok"] is False and body["reason"]


def test_status_exposes_ddi_field_in_mock():
    assert client.get("/screen/status").json()["ddi"] == "unknown"


_DEVMODE = _os.path.join(_SRC, "components", "DevModeControls.tsx")
_PANEL = _os.path.join(_SRC, "components", "DevicePanel.tsx")


def test_setup_is_reachable_from_the_ui():
    api = _read(_API)
    for fn in ("screenRevealDevMode", "screenEnableDevMode",
               "screenMountDdi"):
        assert fn in api, f"api.ts missing {fn}() client"
    assert "ddi: string" in api, "ScreenStatus must carry the DDI state"
    ctl = _read(_DEVMODE)
    for token in ("Show Developer Mode on iPhone", "Mount developer image",
                  "restarts iPhone", "api.screenRevealDevMode",
                  "api.screenEnableDevMode", "api.screenMountDdi",
                  "status.ddi" if "status.ddi" in ctl else "ddi"):
        assert token in ctl, f"DevModeControls missing: {token}"
    # Enabling Developer Mode reboots the phone: never on one stray click.
    assert "armReboot" in ctl, "the reboot button must ask for confirmation"


def test_setup_controls_live_on_both_screens():
    # Same component in both places, so the Screen tab and the device
    # page cannot drift apart.
    for path, where in ((_VIEW, "ScreenView"), (_PANEL, "DevicePanel")):
        src = _read(path)
        assert "DevModeControls" in src, f"{where} must render DevModeControls"


# -- HD honestly refuses what iOS 26 will not do -------------------------
def test_hd_refuses_when_the_device_has_no_media_stream(monkeypatch):
    # iOS < 27: the display service advertises nothing and every start
    # request dies as CoreDeviceError 9021. Say so instead of handing the
    # user a viewer page that will never paint a frame.
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_media_support", lambda binary: {
        "supportedFeatures": 0,
        "supportedFeaturesDescription": "No supported features are available",
    })
    monkeypatch.setattr(scr, "_serve_web_help", lambda b: "--udid <str>\n")
    spawned: list = []
    monkeypatch.setattr(scr.subprocess, "Popen",
                        lambda *a, **k: spawned.append(a) or None)
    r = scr.hd_start("U1", which=lambda _: "/usr/bin/pymobiledevice3")
    assert r["ok"] is False and r["running"] is False
    assert "iOS 27" in r["reason"]
    assert not spawned, "no server may be started for a device that refuses"


def test_hd_still_starts_when_capabilities_are_unreadable(monkeypatch):
    # Unknown != unsupported: a probe that fails must not block HD.
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_media_support", lambda binary: None)
    monkeypatch.setattr(scr, "_serve_web_help", lambda b: "--udid <str>\n")
    monkeypatch.setattr(scr, "_wait_http_ok", lambda url, timeout_s=25.0: True)

    class _P:
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=5): pass

    monkeypatch.setattr(scr.subprocess, "Popen", lambda *a, **k: _P())
    try:
        r = scr.hd_start("U1", which=lambda _: "/usr/bin/pymobiledevice3")
        assert r["ok"] is True and r["running"] is True
    finally:
        scr.hd_stop()


def test_hd_log_goes_to_a_file_not_an_undrained_pipe():
    # stdout=PIPE with nobody reading wedges serve-web once the pipe
    # buffer fills, which looks like "the live screen froze".
    src = io.open(scr.__file__).read()
    assert "stdout=subprocess.PIPE" not in src
    assert scr._hd_log_tail() == ""  # no server running: no log, no crash


# -- AirPlay: name the command that works on THIS host -------------------
def _hint_for(os_release: str, helpers=(), monkeypatch=None) -> str:
    monkeypatch.setattr(scr, "_os_release",
                        lambda: dict(
                            line.split("=", 1) for line in
                            os_release.strip().splitlines() if "=" in line))
    return scr.uxplay_install_hint(
        which=lambda n: f"/usr/bin/{n}" if n in helpers else None)


def test_install_hint_matches_the_distro(monkeypatch):
    # Arch: uxplay is not in the official repos at all, so "apt install"
    # (and even "pacman -S") would send the user nowhere.
    arch = _hint_for("ID=arch", helpers=("yay",), monkeypatch=monkeypatch)
    assert "yay -S uxplay" in arch and "AUR" in arch
    assert "apt" not in arch

    bare_arch = _hint_for("ID=arch", helpers=(), monkeypatch=monkeypatch)
    assert "AUR" in bare_arch and "makepkg" in bare_arch

    deb = _hint_for("ID=ubuntu\nID_LIKE=debian", monkeypatch=monkeypatch)
    assert deb == "sudo apt install uxplay"

    fed = _hint_for("ID=fedora", monkeypatch=monkeypatch)
    assert "dnf install uxplay" in fed

    unknown = _hint_for("ID=plan9", monkeypatch=monkeypatch)
    assert unknown == scr.UXPLAY_SOURCE_HINT


def test_airplay_status_lists_what_the_host_is_missing(monkeypatch):
    monkeypatch.setattr(scr, "avahi_state", lambda runner=None: "stopped")
    body = scr.airplay_status(which=lambda _: None)
    assert body["ready"] is False
    assert body["uxplay"] is False and body["avahi"] == "stopped"
    assert len(body["needs"]) == 2
    assert any("Install the receiver" in n for n in body["needs"])
    assert any("avahi-daemon" in n for n in body["needs"])

    monkeypatch.setattr(scr, "avahi_state", lambda runner=None: "running")
    ok = scr.airplay_status(which=lambda n: f"/usr/bin/{n}")
    assert ok["ready"] is True and ok["needs"] == []


def test_airplay_refuses_without_mdns(monkeypatch):
    # uxplay would start and publish to nobody; the phone discovers the
    # receiver over mDNS, so this is a refusal with a fix, not a warning.
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "avahi_state", lambda runner=None: "stopped")
    spawned: list = []
    monkeypatch.setattr(scr.subprocess, "Popen",
                        lambda *a, **k: spawned.append(a) or None)
    r = scr.airplay_start(which=lambda n: f"/usr/bin/{n}")
    assert r["ok"] is False and not spawned
    assert "avahi-daemon" in r["reason"] and r["fix"]


def test_airplay_missing_binary_names_the_local_command(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_os_release", lambda: {"ID": "arch"})
    r = scr.airplay_start(which=lambda _: None)
    assert r["ok"] is False
    assert "AUR" in r["reason"] and r["fix"]


def test_airplay_keeps_uxplays_own_words():
    # DEVNULL threw away the only useful diagnosis there is.
    src = io.open(scr.__file__).read()
    assert "stdout=subprocess.DEVNULL" not in src
    assert scr._airplay_log_tail() == ""


def test_avahi_state_reads_socket_then_systemd(monkeypatch, tmp_path):
    sock = tmp_path / "avahi.sock"
    monkeypatch.setattr(scr, "AVAHI_SOCKETS", (str(sock),))
    monkeypatch.setattr(scr, "SubprocessRunner",
                        lambda: FakeRunner({("systemctl", "is-active",
                                             "avahi-daemon"): (
                                                3, "inactive\n", "")}))
    assert scr.avahi_state() == "stopped"
    sock.write_text("")
    assert scr.avahi_state() == "running"


def test_airplay_ui_shows_the_commands():
    view = _read(_VIEW)
    for token in ("airNeeds", "airReady", "status.airplay.log"):
        assert token in view, f"ScreenView missing: {token}"
    api = _read(_API)
    assert "install_hint" in api and "avahi" in api


# -- AirPlay renders inside the page, not a floating window --------------
def test_airplay_sink_is_an_mjpeg_server_pipeline():
    sink = scr.airplay_sink(port=9099, long_edge=480, fps=24, quality=65)
    # Scaled + rate-capped before encoding: full-res 60 fps JPEG would
    # spend a core per viewer on pixels an <img> cannot use.
    assert "videoscale" in sink
    # Ranges on BOTH edges, not a pinned width: that is what survives the
    # phone being rotated mid-stream (portrait 416x900, landscape 900x416).
    assert "width=[16,480]" in sink and "height=[16,480]" in sink
    assert "pixel-aspect-ratio=1/1" in sink  # keeps the phone's shape
    assert "framerate=24/1" in sink and "jpegenc quality=65" in sink
    # Same framing /screen/stream already serves, so nothing is re-encoded.
    assert "multipartmux boundary=frame" in sink
    assert "tcpserversink host=127.0.0.1 port=9099" in sink


def test_airplay_start_asks_uxplay_for_that_sink(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "avahi_state", lambda runner=None: "running")
    monkeypatch.setattr(scr, "_wait_http_ok", lambda *a, **k: True)
    seen: list[list[str]] = []

    class _P:
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=5): pass

    def fake_popen(cmd, *a, **k):
        seen.append(list(cmd))
        return _P()

    monkeypatch.setattr(scr.subprocess, "Popen", fake_popen)
    try:
        r = scr.airplay_start(which=lambda n: f"/usr/bin/{n}")
        assert r["ok"] is True and r["embedded"] is True
        assert "-vs" in seen[0]
        assert "tcpserversink" in seen[0][seen[0].index("-vs") + 1]
        state = scr.airplay_status(which=lambda n: f"/usr/bin/{n}")
        assert state["embedded"] is True
        assert state["stream_url"] == "/screen/airplay/stream"
    finally:
        scr.airplay_stop()

    # Opting out gives uxplay its own window back.
    seen.clear()
    monkeypatch.setattr(scr.subprocess, "Popen", fake_popen)
    try:
        r = scr.airplay_start(which=lambda n: f"/usr/bin/{n}", embed=False)
        assert r["embedded"] is False and "-vs" not in seen[0]
        assert scr.airplay_status(
            which=lambda n: f"/usr/bin/{n}")["stream_url"] == ""
    finally:
        scr.airplay_stop()


def test_airplay_stream_refuses_when_nothing_is_mirroring():
    r = client.get("/screen/airplay/stream")
    assert r.status_code == 503
    assert "Start AirPlay receiver" in r.text


def test_stopping_clears_the_embedded_flag():
    scr.airplay_stop()
    assert scr.airplay_status(which=lambda _: None)["embedded"] is False


def test_airplay_mirror_is_rendered_in_the_page():
    view = _read(_VIEW)
    for token in ("api.screenAirplayStreamUrl", "airEmbedded",
                  "AIRPLAY LIVE", "Bring the mirror into this page",
                  "Use a separate window"):
        assert token in view, f"ScreenView missing: {token}"
    api = _read(_API)
    assert "screenAirplayStreamUrl" in api and "embed" in api


def test_frame_follows_the_sharing_iphone():
    # The contour must match the phone that is sharing, even when USB
    # drops but AirPlay keeps going: App remembers the last live model id
    # and ScreenView offers a manual Frame picker on top.
    view = _read(_VIEW)
    for token in ("ft-contour", "freetunes-frame", "effModel",
                  "iphone-se", "iphone-13", "iphone-15", "iphone-16-pro"):
        assert token in view, f"ScreenView missing frame picker: {token}"
    app = _read(_APP)
    assert "freetunes-model-id-live" in app, \
        "App must remember the last live model for the Screen frame"
    assert "model-id-live" in app and "ScreenView" in app


def test_all_contours_share_art_frames_portrait_and_landscape():
    # Same contours vertical + horizontal: every hardware contour has a
    # portrait frame and a rotated landscape frame, both with a real
    # transparent screen hole the live mirror shows through.
    import struct as _st
    public = _os.path.join(_ROOT, "frontend", "public")
    frames = {
        "iphone-13-frame.png": (1000, 2023),
        "iphone-island-frame.png": (1000, 2028),
        "iphone-pro-frame.png": (1000, 2051),
        "iphone-se-frame.png": (1000, 2023),
        "iphone-11-frame.png": (960, 1926),
    }
    for name, (w, h) in frames.items():
        portrait = _os.path.join(public, name)
        landscape = _os.path.join(public, name.replace("-frame.png", "-frame-landscape.png"))
        for path in (portrait, landscape):
            assert _os.path.exists(path), f"missing {path}"
            with open(path, "rb") as f:
                head = f.read(32)
            assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
            iw, ih = _st.unpack(">II", head[16:24])
            if path == portrait:
                assert (iw, ih) == (w, h), f"{name} size {(iw, ih)} != {(w, h)}"
            else:
                assert (iw, ih) == (h, w), f"{path} must be the portrait art rotated"
        # the portrait hole must be transparent at its center
        from PIL import Image as _Image
        im = _Image.open(portrait).convert("RGBA")
        assert im.getpixel((im.size[0] // 2, im.size[1] // 2))[3] < 128, \
            f"{name} screen hole is not transparent"
    frame = _read(_os.path.join(_SRC, "components", "IPhoneFrame.tsx"))
    for contour in ("se", "notch", "island", "pro", "iphone11"):
        assert contour in frame, f"IPhoneFrame must map contour: {contour}"
    assert "CONTOUR_ART" in frame and "landscape" in frame, \
        "IPhoneFrame must pick portrait/landscape art per contour"


def test_art_holes_sized_per_contour():
    # Each contour's mirror insets must match its own artwork hole.
    css = _read(_os.path.join(_SRC, "apple.css"))
    for selector, width, height in (
        (".ft-iphone.is-island.has-art", "89.3%", "95.41%"),
        (".ft-iphone.is-pro.has-art", "91.1%", "96.68%"),
        (".ft-iphone.is-se.has-art", "85.9%", "75.38%"),
        (".ft-iphone.is-iphone11.has-art", "86.88%", "93.82%"),
    ):
        assert selector in css, f"missing art rules for {selector}"
        rules = selector + " .ft-screen-img"
        assert rules in css, f"missing mirror sizing for {selector}"
        block = css.split(rules)[1].split("}")[0]
        assert f"width: {width}" in block and f"height: {height}" in block, \
            f"{selector} mirror must sit in its own hole"
    for landscape in ("is-notch", "is-island", "is-pro", "is-se", "is-iphone11"):
        assert f"has-art.is-landscape.{landscape}" in css, \
            f"missing landscape art rules for {landscape}"


def test_header_mini_follows_live_contour():
    header = _read(_os.path.join(_SRC, "components", "DeviceHeader.tsx"))
    assert "CONTOUR_MINI" in header and "contourForModel" in header
    assert "device?.model_id" in header, \
        "header mini must follow the connected iPhone"
    public = _os.path.join(_ROOT, "frontend", "public")
    for mini in ("iphone-se-mini.png", "iphone-notch-mini.png",
                 "iphone-island-mini.png", "iphone-pro-mini.png",
                 "iphone-11-mini.png"):
        assert _os.path.exists(_os.path.join(public, mini)), f"missing {mini}"


def test_header_carousel_shows_whole_image():
    # The idle carousel slot is a fixed 52x105 box, but minis have
    # different aspects (Duo is wide, Pro/Max are extra tall). With
    # object-fit:cover the slot crops Duo by width (~80px) and the
    # tall Pros by height (up to ~10px). Contain shows the whole
    # device render instead.
    css = _read(_os.path.join(_SRC, "apple.css"))
    assert ".ft-device img" in css
    dev_block = css.split(".ft-device img")[1].split("}")[0]
    assert "object-fit: contain" in dev_block, \
        "header slot must show the whole device, not cover-crop it"
    assert ".ft-carousel img" in css
    car_block = css.split(".ft-carousel img")[1].split("}")[0]
    assert "object-fit: contain" in car_block, \
        "carousel must show the whole device, not cover-crop it"
    assert "object-fit: cover" not in dev_block and \
        "object-fit: cover" not in car_block, \
        "cover crops Duo by width and tall Pros by height"
    assert 'img[data-model="iphone-16-pro"]' not in css, \
        "the 1px bleed hack only made sense for cover cropping"


def test_header_carousel_assets_match_slot():
    # Every DEVICE_MODELS svg must exist and share the slot aspect
    # (52/105) so contain fits it fully with no crop and no guesswork.
    import re as _re
    import struct as _st
    devices = _read(_os.path.join(_SRC, "devices.ts"))
    svgs = sorted(set(_re.findall(r"svg:\s*'([^']+)'", devices)))
    assert len(svgs) >= 40, f"expected the full lineup, got {len(svgs)}"
    public = _os.path.join(_ROOT, "frontend", "public")
    slot = 52 / 105
    for svg in svgs:
        path = _os.path.join(public, svg.lstrip("/"))
        assert _os.path.exists(path), f"missing carousel art {svg}"
        with open(path, "rb") as f:
            head = f.read(32)
        assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{svg} is not a PNG"
        w, h = _st.unpack(">II", head[16:24])
        assert abs(w / h - slot) / slot < 0.01, \
            f"{svg} aspect {w}/{h} != slot 52/105: contain would letterbox hard"


def test_header_duo_pair_slide():
    # Duo open + folded share one wider slide, side by side — each is
    # too narrow on its own to read at 52px.
    header = _read(_os.path.join(_SRC, "components", "DeviceHeader.tsx"))
    assert "CAROUSEL_SLIDES" in header, "carousel must group Duo into one slide"
    assert "iphone-duo-folded" in header and "is-duo-pair" in header
    assert "is-duo" in header, "Duo slide must widen the slot"
    css = _read(_os.path.join(_SRC, "apple.css"))
    assert ".ft-device.is-duo" in css
    duo_block = css.split(".ft-device.is-duo")[1].split("}")[0]
    assert "104px" in duo_block, "Duo slot must be double width"
    assert ".ft-slide.is-duo-pair" in css, "pair must lay out side by side"
    assert "88px" in css, "Duo slot must stay double width on small screens"


def test_preview_usb_hides_contour_without_iphone():
    # Like HD and AirPlay: with no iPhone connected the Preview tab shows
    # the plain empty state, not an empty phone contour.
    view = _read(_VIEW)
    marker = ") : !udid ? ("
    assert marker in view, "Preview must branch on a missing iPhone"
    # only the no-iPhone alternative itself: up to the next branch separator
    snippet = view.split(marker)[1].split(") : (")[0]
    assert "ft-empty" in snippet and "No iPhone connected" in snippet
    assert "IPhoneFrame" not in snippet and "ft-iphone-wrap" not in snippet


def test_art_frame_sizes_the_mirror_explicitly():
    # An <img> is a replaced element: with inset positioning alone it
    # keeps its intrinsic size and overflows the artwork cutout (black
    # bars + cropped sides). The art-frame rule must set width/height.
    css = _read(_os.path.join(_SRC, "apple.css"))
    assert ".ft-iphone.is-notch.has-art .ft-screen-img" in css
    block = css.split(".ft-iphone.is-notch.has-art .ft-screen-img")[1]
    block = block.split("}")[0]
    assert "width: 88.9%" in block and "height: 95.29%" in block, \
        "art cutout must size the live mirror to the measured hole"
    assert "width: auto" not in block, \
        "auto width leaves the intrinsic size and breaks the fit"
    assert _os.path.exists(_os.path.join(
        _ROOT, "frontend", "public", "iphone-13-frame.png")), \
        "notch frame artwork must be vendored"


def test_art_frame_sizes_the_iframe_mirror_explicitly():
    # Same cutout bug, live-video edition: the notch portrait block sized
    # <img> mirrors but left <iframe> on the full-box fallback, so the
    # QuickTime/HD viewer page rendered behind the bezels instead of inside
    # the hole. Every portrait contour must position the iframe identically
    # to its stills.
    css = _read(_os.path.join(_SRC, "apple.css"))
    for selector, width, height in (
        (".ft-iphone.is-notch.has-art", "88.9%", "95.29%"),
        (".ft-iphone.is-island.has-art", "89.3%", "95.41%"),
        (".ft-iphone.is-pro.has-art", "91.1%", "96.68%"),
        (".ft-iphone.is-se.has-art", "85.9%", "75.38%"),
        (".ft-iphone.is-iphone11.has-art", "86.88%", "93.82%"),
    ):
        rules = selector + " iframe.ft-screen-hd"
        assert rules in css, f"missing iframe sizing for {selector}"
        block = css.split(rules)[1].split("}")[0]
        assert f"width: {width}" in block and f"height: {height}" in block, \
            f"{selector} iframe must sit in its own hole"


def test_art_iframe_overscans_viewer_chrome():
    # Embedded viewers are whole pages (canvas + status footer), not bare
    # video: a hole-exact iframe shows the footer's top edge inside the
    # cutout. Art-framed iframes must overscan so the canvas covers the
    # hole and the page chrome falls behind the opaque frame art.
    css = _read(_os.path.join(_SRC, "apple.css"))
    rules = ".ft-iphone.has-art .ft-iphone-screen iframe.ft-screen-hd"
    assert rules in css, "art-framed viewer iframes must overscan"
    block = css.split(rules)[1].split("}")[0]
    assert "transform:" in block and "scale(" in block, \
        "overscan must zoom the viewer page past the hole edges"
    assert "transform-origin:" in block, \
        "overscan must anchor on the video, not the page corner"


def test_airplay_relay_ticks_while_idle_so_it_can_notice_a_closed_tab():
    # A read that parks forever keeps the HTTP response task alive after
    # the browser is gone, which hangs uvicorn's graceful shutdown — i.e.
    # every --reload restart of the dev server.
    import asyncio as _aio

    async def drive():
        server_saw: list[bool] = []

        async def handle(reader, writer):
            server_saw.append(True)
            await _aio.sleep(3)  # silent peer: no frames yet
            writer.close()

        srv = await _aio.start_server(handle, "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        ticks = 0
        try:
            async for chunk in scr.airplay_frames(port=port, tick=0.05):
                assert chunk is None  # nothing mirrored yet
                ticks += 1
                if ticks >= 3:
                    break  # a caller can leave: that is the whole point
        finally:
            srv.close()
            await srv.wait_closed()
        return ticks, server_saw

    ticks, saw = _aio.run(_aio.wait_for(drive(), timeout=10))
    assert ticks == 3 and saw == [True]


# -- QuickTime-USB gate: trust yes, Developer Mode never -----------------
def _blocked_svc() -> ScreenService:
    # Developer Mode OFF + image missing: HD and Preview are gated, but a
    # trusted phone must still be offered QuickTime (qvh present => ready).
    return ScreenService(
        runner=FakeRunner({
            ("/usr/bin/pymobiledevice3", "amfi", "developer-mode-status",
             "--udid", "U1"): (0, "false\n", ""),
            ("/usr/bin/pymobiledevice3", "mounter", "list",
             "--udid", "U1"): (0, "[]", ""),
        }),
        which=lambda name: f"/usr/bin/{name}",
        mock=False)


def test_devmode_off_names_quicktime_bypass_when_ready():
    scr._valeria_help_cache.clear()
    try:
        body = _blocked_svc().status("U1", trusted=True,
                                     ios_version="26.0.1")
        assert body["mode"] == "setup" and body["live"] is False
        assert any("Developer Mode is OFF" in n for n in body["needs"])
        assert any("QuickTime over USB needs no Developer Mode" in n
                   for n in body["needs"]), body["needs"]
    finally:
        scr._valeria_help_cache.clear()


def test_no_quicktime_bypass_when_untrusted():
    # Without trust QuickTime is blocked too: the checklist must say
    # "tap Trust", not "press Start QuickTime".
    scr._valeria_help_cache.clear()
    try:
        body = _blocked_svc().status("U1", trusted=False,
                                     ios_version="26.0.1")
        assert any("Tap Trust" in n for n in body["needs"])
        assert not any("Start QuickTime" in n for n in body["needs"])
    finally:
        scr._valeria_help_cache.clear()


def test_ddi_wording_excludes_quicktime():
    scr._valeria_help_cache.clear()
    try:
        svc = _svc({
            ("/usr/bin/pymobiledevice3", "amfi", "developer-mode-status",
             "--udid", "U1"): (0, "true\n", ""),
            ("/usr/bin/pymobiledevice3", "mounter", "list",
             "--udid", "U1"): (0, "[]", ""),
        })
        body = svc.status("U1", trusted=True, ios_version="26.0.1")
        assert body["ddi"] == "missing"
        assert not any("every capture path" in n for n in body["needs"])
        assert any("HD and Preview need it" in n for n in body["needs"])
    finally:
        scr._valeria_help_cache.clear()


def test_valeria_start_refuses_untrusted_without_spawning(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    scr.valeria_stop()
    spawned: list = []
    monkeypatch.setattr(scr.subprocess, "Popen",
                        lambda *a, **k: spawned.append(a) or None)
    r = scr.valeria_start("U1", which=lambda _: "/usr/bin/pymobiledevice3",
                          trusted=False)
    assert r["ok"] is False and r["running"] is False
    assert "Trust" in r["reason"] and "no Developer Mode" in r["reason"]
    assert not spawned, "an untrusted phone must not spawn a USB claim"


def test_valeria_start_needs_no_devmode(monkeypatch):
    # Developer Mode OFF + image missing must still start: QuickTime is
    # the same protocol QuickTime Player uses (trust only).
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_screen_mirror_help", lambda b: "--udid <str>\n")
    monkeypatch.setattr(scr, "photo_hold_state",
                        lambda run=None: {"held": False, "mounts": [],
                                          "gio": True})
    monkeypatch.setattr(scr, "_valeria_capture_ok", lambda timeout_s=5.0: True)
    monkeypatch.setattr(scr, "_wait_valeria_http_ok",
                        lambda url, timeout_s=20.0: True)

    class _P:
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=5): pass

    monkeypatch.setattr(scr.subprocess, "Popen", lambda *a, **k: _P())
    scr.valeria_stop()
    try:
        r = scr.valeria_start("U1", which=lambda _: "/usr/bin/pymobiledevice3",
                              trusted=True)
        assert r["ok"] is True and r["running"] is True
    finally:
        scr.valeria_stop()


# -- QuickTime-USB on Linux: name the usbmuxd fork, not trust ------------
QT_CONFIG_LOG = (
    "RuntimeError: no QT-capable config (need usbmuxd-master with "
    "USBMUXD_DEFAULT_DEVICE_MODE=2 to expose mode-2 layout)"
)


def _dead_valeria_popen(log_text: str):
    """Fake Popen that dies after writing log_text to the log file."""

    class _P:
        def poll(self): return 1
        def terminate(self): pass
        def wait(self, timeout=5): pass

    def fake_popen(cmd, *a, **k):
        fh = k.get("stdout")
        if fh is not None:
            try:
                fh.write(log_text)
            except (OSError, ValueError):
                pass
        return _P()

    return fake_popen


def test_valeria_start_names_linux_usbmux_fork_on_qt_config_error(
        monkeypatch):
    # The fork's own error blames the host usbmuxd (distro usbmuxd cannot
    # drive the QuickTime alt-config): the reason must lead with the fork
    # fix, not "is the iPhone trusted?".
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_screen_mirror_help", lambda b: "--udid <str>\n")
    monkeypatch.setattr(scr, "photo_hold_state",
                        lambda run=None: {"held": False, "mounts": [],
                                          "gio": True})
    monkeypatch.setattr(scr, "_wait_valeria_http_ok",
                        lambda url, timeout_s=20.0: False)
    monkeypatch.setattr(scr.subprocess, "Popen",
                        _dead_valeria_popen(QT_CONFIG_LOG))
    scr.valeria_stop()
    try:
        r = scr.valeria_start("U1", which=lambda _: "/usr/bin/pymobiledevice3",
                              trusted=True)
        assert r["ok"] is False and r["running"] is False
        assert "USBMUXD_DEFAULT_DEVICE_MODE=2" in r["reason"]
        assert scr.VALERIA_LINUX_SETUP_URL in r["reason"]
        assert r.get("fix") == scr.VALERIA_LINUX_SETUP_URL
        assert not r["reason"].startswith(
            "QuickTime server did not come up. Is the iPhone trusted"), \
            "the log names usbmuxd — trust is not the question"
    finally:
        scr.valeria_stop()


def test_valeria_generic_failure_still_asks_about_trust(monkeypatch):
    # A log with no usbmuxd signature keeps the old trust/USB question.
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_screen_mirror_help", lambda b: "--udid <str>\n")
    monkeypatch.setattr(scr, "photo_hold_state",
                        lambda run=None: {"held": False, "mounts": [],
                                          "gio": True})
    monkeypatch.setattr(scr, "_wait_valeria_http_ok",
                        lambda url, timeout_s=20.0: False)
    monkeypatch.setattr(scr.subprocess, "Popen",
                        _dead_valeria_popen("boom: usb claim lost"))
    scr.valeria_stop()
    try:
        r = scr.valeria_start("U1", which=lambda _: "/usr/bin/pymobiledevice3",
                              trusted=True)
        assert r["ok"] is False
        assert r["reason"].startswith(
            "QuickTime server did not come up. Is the iPhone trusted")
        assert "fix" not in r
    finally:
        scr.valeria_stop()


# -- QuickTime-USB on Linux: name the gvfs holder, not trust ------------
BUSY_LOG = (
    "RuntimeError: SetActiveConfiguration failed (number=6). "
    "Make sure usbmuxd is the patched build that supports this IPC."
)


def test_valeria_start_names_gvfs_holder_on_busy_error(monkeypatch):
    # The fork is ready but gvfsd-gphoto2 holds the PTP interface, so the
    # per-capture switch comes back busy: the reason must lead with the
    # unmount fix, not "is the iPhone trusted?".
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_screen_mirror_help", lambda b: "--udid <str>\n")
    monkeypatch.setattr(scr, "photo_hold_state",
                        lambda run=None: {"held": False, "mounts": [],
                                          "gio": True})
    monkeypatch.setattr(scr, "_wait_valeria_http_ok",
                        lambda url, timeout_s=20.0: False)
    monkeypatch.setattr(scr.subprocess, "Popen",
                        _dead_valeria_popen(BUSY_LOG))
    scr.valeria_stop()
    try:
        r = scr.valeria_start("U1", which=lambda _: "/usr/bin/pymobiledevice3",
                              trusted=True)
        assert r["ok"] is False and r["running"] is False
        assert "gio mount -u" in r["reason"]
        assert "gphoto" in r["reason"]
        assert r.get("fix") == scr.VALERIA_USB_BUSY_FIX
        assert not r["reason"].startswith(
            "QuickTime server did not come up. Is the iPhone trusted"), \
            "the log names a USB claimant — trust is not the question"
    finally:
        scr.valeria_stop()


def test_valeria_status_exposes_linux_hint_on_linux(monkeypatch):
    scr.valeria_stop()
    monkeypatch.setattr(scr.sys, "platform", "linux")
    body = scr.valeria_status(which=lambda _: None)
    assert "USBMUXD_DEFAULT_DEVICE_MODE=2" in body["linux_hint"]
    assert body["linux_setup_url"].endswith("valeria-linux-setup.md")
    monkeypatch.setattr(scr.sys, "platform", "darwin")
    assert scr.valeria_status(which=lambda _: None)["linux_hint"] == ""


def test_quicktime_tab_shows_linux_setup_hint():
    view = _read(_VIEW)
    assert "valeria.linux_hint" in view, \
        "ScreenView must render the Linux usbmuxd-fork note"
    api = _read(_API)
    assert "linux_hint" in api and "linux_setup_url" in api, \
        "ScreenValeria must carry the Linux setup fields"


def test_quicktime_uses_native_viewer_with_toolbar_fps():
    # The fork's viewer is a whole page (canvas + status footer): embedded
    # as an iframe it letterboxes the video, parks its footer inside the
    # cutout, and scrolls at embed heights. The live branch must render the
    # native canvas viewer (bare video, no page) and keep the fps readout
    # in the freetunes toolbar above the frame instead.
    view = _read(_VIEW)
    assert "ValeriaViewer" in view, \
        "QuickTime live branch must use the native canvas viewer"
    assert "<iframe src={valeriaUrl}" not in view, \
        "the fork's viewer page must not be iframed into the cutout"
    assert "valeriaFps" in view and "fps" in view, \
        "fps must stay visible in the toolbar"
    native = _read(_os.path.join(_SRC, "components", "ValeriaViewer.tsx"))
    assert "wsUrl" in native and "new WebSocket(wsUrl)" in native, \
        "native viewer must be fed the server socket, not a page URL"
    assert "+ '/ws'" in view or '+ "/ws"' in view, \
        "ScreenView must derive the video socket from the server URL"
    assert "VideoDecoder" in native and "hasIdr" in native, \
        "native viewer must decode the fork's H.264 socket protocol"
    assert "id=\"bar\"" not in native and "Valeria/libusb" not in native, \
        "native viewer must not reintroduce a status footer"


# -- Linux USB setup: usbmuxd fork probe + one-command setup -------------
class _FP:
    """Stand-in for pathlib.Path covering is_file() only."""

    present: set = set()

    def __init__(self, p):
        self._p = str(p)

    def is_file(self):
        return self._p in _FP.present


def _usbmux_run(outputs: dict):
    def run(argv, timeout=10):
        return outputs.get(tuple(argv), (1, ""))
    return run


_FORK_SHOW = ("ExecStart={ path=/usr/local/sbin/usbmuxd ; "
              "argv[]=/usr/local/sbin/usbmuxd --user usbmux --systemd ; }\n"
              "Environment=USBMUXD_DEFAULT_DEVICE_MODE=2\n")
_DISTRO_SHOW = ("ExecStart={ path=/usr/bin/usbmuxd ; "
                "argv[]=/usr/bin/usbmuxd --user usbmux --systemd ; }\n"
                "Environment=\n")


def test_usbmuxd_state_not_linux_reports_nothing_to_do(monkeypatch):
    monkeypatch.setattr(scr.sys, "platform", "darwin")
    assert scr.usbmuxd_state() == {"linux": False, "ready": True,
                                  "needs": []}


def test_usbmuxd_state_linux_ready(monkeypatch):
    monkeypatch.setattr(scr.sys, "platform", "linux")
    _FP.present = {scr.USBMUXD_FORK_BIN, scr.USBMUXD_OVERRIDE_FILE}
    monkeypatch.setattr(scr, "Path", _FP)
    run = _usbmux_run({
        (scr.USBMUXD_FORK_BIN, "--version"): (0, "usbmuxd 1.1.1-abc1234\n"),
        ("grep", "-a", "-q", "USBMUXD_DEFAULT_DEVICE_MODE",
         scr.USBMUXD_FORK_BIN): (0, ""),
        ("systemctl", "is-active", "usbmuxd"): (0, "active\n"),
        ("systemctl", "show", "usbmuxd", "-p",
         "ExecStart,Environment"): (0, _FORK_SHOW),
    })
    body = scr.usbmuxd_state(run=run)
    assert body["linux"] is True and body["ready"] is True
    assert body["needs"] == [] and body["env_mode2"] is True
    assert body["service_binary"] == scr.USBMUXD_FORK_BIN
    assert body["has_device_mode"] is True


def test_usbmuxd_state_linux_distro_names_setup(monkeypatch):
    monkeypatch.setattr(scr.sys, "platform", "linux")
    _FP.present = set()  # no fork, no drop-in
    monkeypatch.setattr(scr, "Path", _FP)
    run = _usbmux_run({
        ("systemctl", "is-active", "usbmuxd"): (0, "active\n"),
        ("systemctl", "show", "usbmuxd", "-p",
         "ExecStart,Environment"): (0, _DISTRO_SHOW),
    })
    body = scr.usbmuxd_state(run=run)
    assert body["linux"] is True and body["ready"] is False
    assert body["service_binary"] == "/usr/bin/usbmuxd"
    assert any("fork" in n for n in body["needs"])
    assert body["setup_command"].endswith("setup-valeria-linux.sh")


def test_valeria_status_adds_linux_setup_need(monkeypatch):
    monkeypatch.setattr(
        scr, "usbmuxd_state",
        lambda run=None: {"linux": True, "ready": False,
                          "needs": ["Install the usbmuxd fork."]})
    scr._valeria_help_cache.clear()
    try:
        svc = ScreenService(runner=FakeRunner({}),
                            which=lambda _: None, mock=False)
        body = svc.status("some-udid", trusted=True, ios_version="18.0")
        assert any("Linux one-time USB setup" in n
                   for n in body["valeria"]["needs"])
        assert body["valeria"]["usbmuxd"]["ready"] is False
    finally:
        scr._valeria_help_cache.clear()


def _fake_proc_run(returncode: int, out: str = ""):
    class _R:
        def __init__(self):
            self.returncode = returncode
            self.stdout = out
            self.stderr = ""

    seen: list = []

    def fake_run(argv, **k):
        seen.append(list(argv))
        return _R()

    fake_run.seen = seen
    return fake_run


def test_valeria_usbmux_setup_runs_script_and_trusts_probe(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr.sys, "platform", "linux")
    fake_run = _fake_proc_run(0, "USB setup done\n")
    monkeypatch.setattr(scr.subprocess, "run", fake_run)
    monkeypatch.setattr(scr, "usbmuxd_state",
                        lambda run=None: {"linux": True, "ready": True,
                                          "needs": []})
    r = scr.valeria_usbmux_setup()
    assert r["ok"] is True and r["installed"] is True
    assert fake_run.seen and \
        fake_run.seen[0][-1].endswith("setup-valeria-linux.sh")
    assert "replug" in r["note"]


def test_valeria_usbmux_setup_exit3_names_terminal(monkeypatch):
    # Exit 3 = a sudo step with no terminal: hand over the exact command,
    # never hang on a password prompt nobody can answer.
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr.sys, "platform", "linux")
    monkeypatch.setattr(scr.subprocess, "run", _fake_proc_run(3, "NEEDS-ROOT"))
    r = scr.valeria_usbmux_setup()
    assert r["ok"] is False
    assert "terminal" in r["reason"] and "sudo" in r["reason"]
    assert r["command"].endswith("setup-valeria-linux.sh")


def test_valeria_usbmux_setup_refuses_off_linux(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr.sys, "platform", "darwin")
    r = scr.valeria_usbmux_setup()
    assert r["ok"] is False and "Linux-only" in r["reason"]


def test_valeria_usbmux_setup_endpoint_honest_in_mock():
    body = client.post("/screen/valeria/usbmux-setup").json()
    assert body["ok"] is False and body["reason"]


def test_linux_usb_setup_wired_into_quicktime_tab():
    api = _read(_API)
    assert "screenValeriaUsbmuxSetup" in api
    assert "ScreenUsbmuxd" in api and "usbmuxd" in api
    view = _read(_VIEW)
    for token in ("usbmuxSetup", "Run Linux USB setup", "qtUsbmux",
                  "usbmuxing"):
        assert token in view, f"ScreenView missing: {token}"


def test_airplay_relay_passes_frames_through_untouched():
    import asyncio as _aio

    payload = (b"--frame\r\nContent-Type: image/jpeg\r\n"
               b"Content-Length: 4\r\n\r\n\xff\xd8\xff\xd9\r\n")

    async def drive():
        async def handle(reader, writer):
            writer.write(payload)
            await writer.drain()
            writer.close()

        srv = await _aio.start_server(handle, "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        got = b""
        try:
            async for chunk in scr.airplay_frames(port=port, tick=0.05):
                if chunk:
                    got += chunk
                if got.endswith(b"\r\n") and b"\xff\xd8" in got:
                    break
        finally:
            srv.close()
            await srv.wait_closed()
        return got

    assert _aio.run(_aio.wait_for(drive(), timeout=10)) == payload


# -- Honest state: tunnel probe, dead-capture check, photo pre-check -----
def _ready_svc():
    return _svc({
        ("/usr/bin/pymobiledevice3", "amfi", "developer-mode-status",
         "--udid", "U1"): (0, "true\n", ""),
        ("/usr/bin/pymobiledevice3", "mounter", "list",
         "--udid", "U1"): (0, '[{"ImageType": "Personalized"}]', ""),
    })


def test_tunneld_command_names_the_backend_interpreter():
    import sys as _sys
    assert scr.TUNNELD_START_COMMAND.startswith("sudo ")
    assert _sys.executable in scr.TUNNELD_START_COMMAND
    assert "remote tunneld" in scr.TUNNELD_START_COMMAND


def test_tunneld_state_reads_the_daemon_list():
    import http.server as _http
    import json as _json
    import threading as _th

    payload = {"U1": [{"tunnel-address": "127.0.0.1", "tunnel-port": 1}]}

    class _H(_http.BaseHTTPRequestHandler):
        def do_GET(self):
            body = _json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = _http.HTTPServer(("127.0.0.1", 0), _H)
    port = srv.server_address[1]
    _th.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert scr.tunneld_state("U1", address=("127.0.0.1", port)) == "up"
        assert scr.tunneld_state("U2", address=("127.0.0.1", port)) == "missing"
        assert scr.tunneld_state(
            "mock-udid", address=("127.0.0.1", port)) == "unknown"
    finally:
        srv.shutdown()
        srv.server_close()
    # Daemon gone: refused connection reads as missing, never as up.
    assert scr.tunneld_state("U1", address=("127.0.0.1", port)) == "missing"


def test_status_names_missing_tunnel_on_ios17(monkeypatch):
    monkeypatch.setattr(scr, "tunneld_state", lambda udid: "missing")
    body = _ready_svc().status("U1", trusted=True, ios_version="26.0.1")
    assert body["tunneld"] == "missing"
    assert body["mode"] == "setup" and body["live"] is False
    assert any("tunneld" in n for n in body["needs"])
    assert scr.TUNNELD_START_COMMAND in " ".join(body["needs"])


def test_status_ignores_tunnel_on_legacy_ios(monkeypatch):
    # iOS <= 16 captures over screenshotr, which never heard of tunneld:
    # a missing daemon must not block the old claim.
    monkeypatch.setattr(scr, "tunneld_state", lambda udid: "missing")
    body = _ready_svc().status("U1", trusted=True, ios_version="16.7")
    assert body["mode"] == "mjpeg" and body["live"] is True


def test_dvt_log_names_tunnel():
    assert scr._dvt_log_names_tunnel(
        "ERROR Unable to connect to Tunneld. start one with sudo")
    assert not scr._dvt_log_names_tunnel("boom: usb claim lost")
    assert not scr._dvt_log_names_tunnel("")


def test_take_shot_placeholder_names_tunnel(monkeypatch):
    svc = ScreenService(runner=FakeRunner({}),
                        which=lambda n: f"/usr/bin/{n}", mock=False)

    def _fail(udid):
        svc._last_dvt_log = ("WARNING Got an InvalidServiceError. "
                             "ERROR Unable to connect to Tunneld.")
        return None

    monkeypatch.setattr(svc, "_shot_via_pmd3", _fail)
    monkeypatch.setattr(svc, "_shot_via_coredevice", lambda udid: None)
    monkeypatch.setattr(scr, "_placeholder_png", lambda lines: lines)
    data, media, live = svc.take_shot("U1")
    assert live is False and media == "image/png"
    assert data == scr.TUNNEL_MISSING_LINES


def test_photo_hold_probe_parses_gphoto_mounts():
    out = ("Mount(0): iPhone -> "
           "gphoto2://Apple_Inc._iPhone_000081100014158C0E9B601E/\n"
           "Mount(1): Documents -> afc://00008110-0014158C0E9B601E:3/\n")
    body = scr._photo_hold_probe(run=lambda argv, timeout=10: (0, out))
    assert body["held"] is True and body["gio"] is True
    assert body["mounts"] == [
        "gphoto2://Apple_Inc._iPhone_000081100014158C0E9B601E/"]
    assert scr._mount_matches_udid(body["mounts"][0],
                                   "00008110-0014158C0E9B601E") is True
    assert scr._photo_hold_probe(
        run=lambda argv, timeout=10: (0, ""))["held"] is False
    assert scr._photo_hold_probe(
        run=lambda argv, timeout=10: (1, ""))["gio"] is False


def test_valeria_fails_fast_when_photo_held(monkeypatch):
    # A held PTP interface dooms the spawn: refuse with the release
    # command instead of a server that can never capture.
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_screen_mirror_help", lambda b: "--udid <str>\n")
    monkeypatch.setattr(scr, "photo_hold_state",
                        lambda run=None: {
                            "held": True,
                            "mounts": ["gphoto2://Apple_Inc._iPhone_"
                                       "000081100014158C0E9B601E/"],
                            "gio": True})
    spawned: list = []
    monkeypatch.setattr(scr.subprocess, "Popen",
                        lambda *a, **k: spawned.append(a) or None)
    scr.valeria_stop()
    r = scr.valeria_start("00008110-0014158C0E9B601E",
                          which=lambda _: "/usr/bin/pymobiledevice3",
                          trusted=True)
    assert r["ok"] is False and r["running"] is False
    assert not spawned, "a held USB interface must not spawn a USB claim"
    assert "gio mount -u" in r["reason"]
    assert r.get("fix") == scr.VALERIA_USB_BUSY_FIX


def test_valeria_reports_dead_capture_after_http_ok(monkeypatch):
    # The viewer page answers HTTP while the capture itself is dead
    # (busy USB here): pixels must be confirmed before ok.
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_screen_mirror_help", lambda b: "--udid <str>\n")
    monkeypatch.setattr(scr, "photo_hold_state",
                        lambda run=None: {"held": False, "mounts": [],
                                          "gio": True})
    monkeypatch.setattr(scr, "_wait_valeria_http_ok",
                        lambda url, timeout_s=20.0: True)
    monkeypatch.setattr(scr.subprocess, "Popen",
                        _dead_valeria_popen(BUSY_LOG))
    scr.valeria_stop()
    try:
        r = scr.valeria_start("U1", which=lambda _: "/usr/bin/pymobiledevice3",
                              trusted=True)
        assert r["ok"] is False and r["running"] is False
        assert "gio mount -u" in r["reason"]
        assert r.get("fix") == scr.VALERIA_USB_BUSY_FIX
    finally:
        scr.valeria_stop()


def test_valeria_ok_when_capture_healthy(monkeypatch):
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_screen_mirror_help", lambda b: "--udid <str>\n")
    monkeypatch.setattr(scr, "photo_hold_state",
                        lambda run=None: {"held": False, "mounts": [],
                                          "gio": True})
    monkeypatch.setattr(scr, "_wait_valeria_http_ok",
                        lambda url, timeout_s=20.0: True)
    monkeypatch.setattr(scr.subprocess, "Popen", _dead_valeria_popen(
        "Valeria: capture started (1170x2532)\n"
        "Screen mirror ready at http://127.0.0.1:8081"))
    scr.valeria_stop()
    try:
        r = scr.valeria_start("U1", which=lambda _: "/usr/bin/pymobiledevice3",
                              trusted=True)
        assert r["ok"] is True and r["running"] is True
    finally:
        scr.valeria_stop()


def test_screen_status_carries_tunnel_and_photo_hold():
    api = _read(_API)
    assert "tunneld" in api, "ScreenStatus must carry the tunnel state"
    assert "photo_hold" in api, "ScreenValeria must carry the photo-hold state"


def test_valeria_numbered_switch_refusal_is_not_blamed_on_gvfs(monkeypatch):
    # number=1 is a refused switch (wedged phone state: replug), not a
    # held interface — it must keep the generic retry message, whose fix
    # is replugging, not unmounting.
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_screen_mirror_help", lambda b: "--udid <str>\n")
    monkeypatch.setattr(scr, "photo_hold_state",
                        lambda run=None: {"held": False, "mounts": [],
                                          "gio": True})
    monkeypatch.setattr(scr, "_wait_valeria_http_ok",
                        lambda url, timeout_s=20.0: False)
    monkeypatch.setattr(scr.subprocess, "Popen", _dead_valeria_popen(
        "RuntimeError: SetActiveConfiguration failed (number=1). "
        "Make sure usbmuxd is the patched build that supports this IPC."))
    scr.valeria_stop()
    try:
        r = scr.valeria_start("U1", which=lambda _: "/usr/bin/pymobiledevice3",
                              trusted=True)
        assert r["ok"] is False and r["running"] is False
        assert "fix" not in r
        assert "replug" in r["reason"]
        assert "gio mount -u" not in r["reason"]
    finally:
        scr.valeria_stop()


def test_valeria_names_asleep_phone_not_the_host(monkeypatch):
    # USB claimed fine but the phone sends no video clock: the fix is
    # waking the iPhone, not touching the host setup.
    monkeypatch.setenv("FREETUNES_MOCK", "0")
    monkeypatch.setattr(scr, "_screen_mirror_help", lambda b: "--udid <str>\n")
    monkeypatch.setattr(scr, "photo_hold_state",
                        lambda run=None: {"held": False, "mounts": [],
                                          "gio": True})
    monkeypatch.setattr(scr, "_wait_valeria_http_ok",
                        lambda url, timeout_s=20.0: True)
    monkeypatch.setattr(scr.subprocess, "Popen", _dead_valeria_popen(
        "Valeria: capture handshake completed but iDevice sent no video "
        "clock - screen is likely asleep. Wake it and retry."))
    scr.valeria_stop()
    try:
        r = scr.valeria_start("U1", which=lambda _: "/usr/bin/pymobiledevice3",
                              trusted=True)
        assert r["ok"] is False and r["running"] is False
        assert "asleep" in r["reason"] and "side" in r["reason"]
        assert "fix" not in r
    finally:
        scr.valeria_stop()
