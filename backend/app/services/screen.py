"""Live iPhone screen (3uTools-style Realtime Screen).

Strict-FOSS, mock-safe. Four USB/Wi-Fi paths, best first:

1. **HD (HEVC over USB)** — ``pymobiledevice3 developer core-device display
   serve-web`` serves the live screen to any modern browser (WebCodecs,
   no ffmpeg). Needs Developer Mode + a trusted device; on iOS 17.4+ the
   tunnel comes up with no root. freetunes supervises the subprocess and
   the UI embeds it in an ``<iframe>``.
2. **QuickTime (USB, Valeria H.264 30-60 fps)** — ``pymobiledevice3
   screen-mirror`` (screen-mirror fork, ``valeria`` backend) or ``qvh
   gstreamer`` (quicktime_video_hack): the same protocol QuickTime Player
   uses, so any trusted phone works with no Developer Mode. freetunes
   supervises the web server and embeds it in an ``<iframe>`` — the
   faster preview when HD is gated (iOS < 27) and MJPEG polling feels
   slow.
 3. **Preview (MJPEG screenshot polling)** — single shots via
   ``pymobiledevice3 developer dvt screenshot`` (verified on iOS 26.0.1),
   falling back to the newer CoreDevice service
   (``developer core-device screen-capture screenshot``) and finally
   legacy ``idevicescreenshot`` (iOS <= 16), re-encoded to
   JPEG and streamed as ``multipart/x-mixed-replace`` at 1-5 fps. Always
   available when a shot provider exists; honest about being low-fps.
 4. **AirPlay (Wi-Fi, full quality + audio)** — managed ``uxplay`` receiver
   (own window, same LAN, Control Center -> Screen Mirroring).

With no device / no tools (CI, ``FREETUNES_MOCK=1``) every endpoint stays
up: ``/screen/shot`` returns a generated placeholder PNG and HD/Valeria/
AirPlay start calls fail with an install/setup hint instead of crashing.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .devices import FakeRunner, SubprocessRunner

#: Where the supervised HD (serve-web) page lives by default — matches the
#: upstream recipe (open http://127.0.0.1:8080/).
HD_DEFAULT_PORT = int(os.environ.get("FREETUNES_SCREEN_HD_PORT", "8080"))

#: Where the supervised QuickTime-USB (Valeria screen-mirror) page lives.
#: 8081 keeps it off HD's 8080 and the AirPlay MJPEG relay's 8091.
VALERIA_DEFAULT_PORT = int(os.environ.get(
    "FREETUNES_SCREEN_VALERIA_PORT",
    os.environ.get("FREETUNES_VALERIA_PORT", "8081")))

#: Fork branch carrying both `valeria` (H.264 capture) and `screen-mirror`
#: (browser viewer). NOTE: there is no `screen-mirror` branch — installing
#: `@screen-mirror` fails in pip with `git checkout -q screen-mirror`.
VALERIA_BRANCH = "feature/screen-mirror-browser-viewer"
VALERIA_FORK_URL = (
    "git+https://github.com/renegadelink/pymobiledevice3.git"
    f"@{VALERIA_BRANCH}"
)
#: One-time Linux host setup for the Valeria path (usbmuxd fork with
#: dynamic-config-switch + USBMUXD_DEFAULT_DEVICE_MODE=2).
VALERIA_LINUX_SETUP_URL = (
    "https://github.com/renegadelink/pymobiledevice3/blob/"
    f"{VALERIA_BRANCH}/docs/guides/valeria-linux-setup.md"
)

VALERIA_INSTALL_HINT = (
    "pip install -U "
    f"\"{VALERIA_FORK_URL}\" "
    "&& pip install aiohttp av \"construct-typing<0.8\"  "
    "(Valeria H.264 over USB; then replug the iPhone and tap Trust)"
)
#: Exact argv for the one-click installer (same packages as the hint above).
#: Installed with the backend's own interpreter so the supervised server
#: sees the fork without a PATH hunt.
VALERIA_INSTALL_PACKAGES = [
    VALERIA_FORK_URL,
    "aiohttp",
    "av",
    # construct-typing 0.8+ rejects this fork snapshot's AFC dataclasses
    # (DataclassFieldError on import), silently killing every AFC/DVT path
    # including Preview shots. The fork allows >=0.7.0, so a bare `-U`
    # would re-break it — pin below 0.8 here too (see requirements.txt).
    "construct-typing<0.8",
]
VALERIA_INSTALL_COMMAND = (
    "pip install -U "
    f"\"{VALERIA_FORK_URL}\" "
    "aiohttp av \"construct-typing<0.8\""
)
QVH_INSTALL_HINT = (
    "or install quicktime_video_hack (qvh): "
    "https://github.com/danielpaulus/quicktime_video_hack "
    "— same QuickTime-USB protocol via `qvh gstreamer`"
)
#: Valeria claims the USB device with libusb, which fights usbmuxd for it.
#: On Linux the capture path additionally needs the usbmuxd fork's
#: dynamic-config-switch branch with USBMUXD_DEFAULT_DEVICE_MODE=2
#: (distro usbmuxd cannot drive the QuickTime alt-config) — and while
#: streaming the phone sits in presentation mode (fake 9:41 clock,
#: notifications hidden), exactly like QuickTime Player.
VALERIA_USBMUX_HINT = (
    "Valeria talks USB directly and fights usbmuxd for the device: if it "
    "fails to claim USB, check udev rules, stop competing usbmuxd clients, "
    "replug the iPhone, and retry. On Linux the capture path also needs "
    "the usbmuxd fork (dynamic-config-switch branch, "
    "USBMUXD_DEFAULT_DEVICE_MODE=2) — see the Valeria Linux setup guide. "
    "While streaming the phone shows a fake "
    "9:41 clock with notifications hidden (presentation mode)."
)
VALERIA_LINUX_HINT = (
    "Linux needs the usbmuxd fork's dynamic-config-switch branch with "
    "USBMUXD_DEFAULT_DEVICE_MODE=2 (distro usbmuxd cannot drive the "
    "QuickTime alt-config). Setup: " + VALERIA_LINUX_SETUP_URL
)
#: Fork binary + systemd drop-in that scripts/setup-valeria-linux.sh owns.
USBMUXD_FORK_BIN = "/usr/local/sbin/usbmuxd"
USBMUXD_OVERRIDE_FILE = \
    "/etc/systemd/system/usbmuxd.service.d/override.conf"
#: One-command Linux USB setup (Arch + Debian/Ubuntu, needs sudo).
VALERIA_USBMUX_SETUP_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts" / "setup-valeria-linux.sh"
)
VALERIA_USBMUX_SETUP_COMMAND = f"bash {VALERIA_USBMUX_SETUP_SCRIPT}"
#: Log signature when the host usbmuxd cannot expose the QuickTime USB
#: alt-config — on Linux this is the distro usbmuxd, which cannot drive
#: it. The fork's own error names the fix (usbmuxd-master with
#: USBMUXD_DEFAULT_DEVICE_MODE=2 to expose the mode-2 layout).
VALERIA_NO_QT_CONFIG_MARKS = (
    "no qt-capable config",
    "usbmuxd_default_device_mode",
    "mode-2 layout",
)
VALERIA_NO_QT_CONFIG_REASON = (
    "This computer's usbmuxd cannot expose the QuickTime USB config the "
    "iPhone needs — the phone is trusted and reachable, but distro "
    "usbmuxd cannot drive the QuickTime alt-config, so there is nothing "
    "to tap or replug on the phone side. One-time Linux fix: stop the "
    "distro usbmuxd, run the usbmuxd fork's dynamic-config-switch branch "
    "as usbmuxd-master with USBMUXD_DEFAULT_DEVICE_MODE=2, replug the "
    "iPhone, tap Trust, and press Start QuickTime again. Setup: "
    + VALERIA_LINUX_SETUP_URL
)


def _valeria_log_names_no_qt_config(tail: str) -> bool:
    """Does the server log blame the host usbmuxd (not trust/USB)?"""
    low = (tail or "").lower()
    return any(m in low for m in VALERIA_NO_QT_CONFIG_MARKS)


#: Log signature when the per-capture USB config switch fails because
#: another program holds the iPhone's USB photo interface — on GNOME
#: desktops this is gvfsd-gphoto2 (the photo importer), which claims the
#: PTP interface the moment the phone plugs in. usbmuxd then answers
#: SetActiveConfiguration with LIBUSB_ERROR_BUSY (number=6): the fork is
#: ready and the phone is trusted, so reinstalling changes nothing — the
#: holder must let go first. NOTE: number=6 (busy) is the signature, not
#: every SetActiveConfiguration failure — e.g. number=1 means the switch
#: itself was refused (wedged phone state, usually fixed by replugging),
#: which must keep the generic retry message, not the unmount one.
VALERIA_USB_BUSY_MARKS = (
    "setactiveconfiguration failed (number=6)",
    "libusb_error_busy",
    "resource busy",
    "errno 16",
)
VALERIA_USB_BUSY_REASON = (
    "Another program on this computer is holding the iPhone's USB photo "
    "interface, so usbmuxd cannot switch it into the QuickTime config "
    "(SetActiveConfiguration comes back busy) — the phone is trusted and "
    "the usbmuxd fork is ready, so there is nothing to reinstall or tap "
    "on the phone side. Fix: eject the iPhone's photo mount (Files shows "
    "it as “iPhone”, or run: gio mount -l | grep -i gphoto, then "
    "gio mount -u the gphoto2:// address), and press Start QuickTime "
    "again — no replug needed."
)
VALERIA_USB_BUSY_FIX = "gio mount -l | grep -i gphoto"


def _valeria_log_names_usb_busy(tail: str) -> bool:
    """Does the server log blame a competing USB claimant (not trust)?"""
    low = (tail or "").lower()
    return any(m in low for m in VALERIA_USB_BUSY_MARKS)

PMD3_INSTALL_HINT = (
    "pip install pymobiledevice3  (then enable Developer Mode on the iPhone, "
    "plug it in, tap Trust)"
)
#: Fallback when the host's package manager is unknown.
UXPLAY_SOURCE_HINT = (
    "build UxPlay from source: https://github.com/FDH2/UxPlay"
    "#building-uxplay-from-source-code"
)


def _os_release() -> dict[str, str]:
    """/etc/os-release as a dict (empty when it cannot be read)."""
    out: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            key, _, value = line.partition("=")
            if key:
                out[key.strip()] = value.strip().strip('"\'')
    except OSError:
        pass
    return out


def uxplay_install_hint(
        which: Callable[[str], str | None] | None = None) -> str:
    """The command that actually installs uxplay *on this host*.

    A Debian command on an Arch box is worse than no hint at all: on Arch
    uxplay is not even in the official repositories, so the honest answer
    names an AUR helper (or a source build) instead.
    """
    which = which or _default_which
    rel = _os_release()
    ids = {rel.get("ID", "")} | set(rel.get("ID_LIKE", "").split())
    if ids & {"arch", "archlinux", "manjaro", "endeavouros", "cachyos"}:
        for helper in ("yay", "paru", "pikaur", "trizen"):
            try:
                if which(helper):
                    return (f"{helper} -S uxplay  (uxplay is in the AUR, "
                            "not Arch's own repos)")
            except Exception:
                continue
        return ("uxplay is AUR-only on Arch: install an AUR helper "
                "(e.g. pacman -S --needed base-devel git && git clone "
                "https://aur.archlinux.org/yay.git && cd yay && makepkg "
                "-si), then: yay -S uxplay")
    if ids & {"debian", "ubuntu", "linuxmint", "pop", "raspbian"}:
        return "sudo apt install uxplay"
    if ids & {"fedora", "rhel", "centos"}:
        return "sudo dnf install uxplay"
    if ids & {"opensuse", "suse", "opensuse-tumbleweed", "opensuse-leap"}:
        return "sudo zypper install uxplay"
    if ids & {"alpine"}:
        return "sudo apk add uxplay"
    if ids & {"gentoo"}:
        return "sudo emerge media-video/uxplay"
    return UXPLAY_SOURCE_HINT


#: mDNS is how the iPhone finds the receiver at all. uxplay starts
#: happily without avahi-daemon and then never appears in Screen
#: Mirroring, which is indistinguishable from "AirPlay is broken".
AVAHI_SOCKETS = ("/run/avahi-daemon/socket", "/var/run/avahi-daemon/socket")


def avahi_state(
        runner: SubprocessRunner | FakeRunner | None = None) -> str:
    """mDNS daemon: "running" | "stopped" | "unknown"."""
    for sock in AVAHI_SOCKETS:
        try:
            if Path(sock).exists():
                return "running"
        except OSError:
            continue
    r = runner or SubprocessRunner()
    try:
        res = r.run("systemctl", "is-active", "avahi-daemon", timeout=8)
    except Exception:
        return "unknown"
    state = (res.stdout or "").strip()
    if state == "active":
        return "running"
    if state in ("inactive", "failed", "unknown", "activating",
                 "deactivating"):
        return "stopped"
    return "unknown"


AVAHI_START_HINT = ("sudo systemctl enable --now avahi-daemon  "
                    "(mDNS: without it the iPhone cannot see the receiver)")

#: uxplay's default sink is a desktop window that floats outside the web
#: UI. Pointing its videosink at a GStreamer MJPEG server instead lets
#: freetunes relay the mirror into the page itself (/screen/airplay/stream),
#: which is what "watch my iPhone in the browser" actually means. Frames
#: are scaled and rate-capped first: JPEG-encoding 1170x2532 at 60 fps
#: would spend a core per viewer for pixels no <img> needs.
AIRPLAY_MJPEG_PORT = int(
    os.environ.get("FREETUNES_AIRPLAY_MJPEG_PORT", "8091"))
#: Longest edge of a relayed frame. A *range* (not a fixed width) is what
#: makes rotation work: videoscale then caps whichever edge is longer and
#: keeps the aspect, so a portrait phone streams 416x900 and a landscape
#: one 900x416 — pinning width=540 instead left landscape at 540x249,
#: soft the moment the viewer fills the content column with it.
AIRPLAY_MJPEG_LONG_EDGE = int(
    os.environ.get("FREETUNES_AIRPLAY_LONG_EDGE",
                   os.environ.get("FREETUNES_AIRPLAY_WIDTH", "900")))
AIRPLAY_MJPEG_FPS = int(os.environ.get("FREETUNES_AIRPLAY_FPS", "30"))
AIRPLAY_MJPEG_QUALITY = int(
    os.environ.get("FREETUNES_AIRPLAY_QUALITY", "70"))


def airplay_sink(port: int = 0, long_edge: int = 0, fps: int = 0,
                 quality: int = 0) -> str:
    """The `-vs` pipeline that turns uxplay into an MJPEG source.

    Both dimensions are given as ranges with ``pixel-aspect-ratio=1/1``:
    videoscale then bounds the longer edge and derives the other from the
    phone's own aspect, which survives the user rotating the device
    mid-stream (1170x2532 -> 416x900, 2532x1170 -> 900x416).
    """
    edge = long_edge or AIRPLAY_MJPEG_LONG_EDGE
    return (
        "videoconvert ! videoscale ! "
        f"video/x-raw,width=[16,{edge}],height=[16,{edge}],"
        "pixel-aspect-ratio=1/1 ! videorate ! "
        f"video/x-raw,framerate={fps or AIRPLAY_MJPEG_FPS}/1 ! "
        f"jpegenc quality={quality or AIRPLAY_MJPEG_QUALITY} ! "
        "multipartmux boundary=frame ! "
        f"tcpserversink host=127.0.0.1 port={port or AIRPLAY_MJPEG_PORT}")


#: Set while the server is shutting down. Long-lived responses (both
#: MJPEG streams) poll it and end themselves: uvicorn waits for in-flight
#: requests forever by default, so one open <img> stream is enough to hang
#: every --reload restart of the dev server.
_shutting_down = False


def begin_shutdown() -> None:
    """Tell the streaming endpoints to wind up (see app.main)."""
    global _shutting_down
    _shutting_down = True


def shutting_down() -> bool:
    return _shutting_down


#: How long the relay waits for the next frame before handing control
#: back to its caller. Nothing arrives until the phone actually mirrors,
#: and a read that parks forever keeps the HTTP response task alive —
#: which is enough to hang uvicorn's graceful shutdown (and therefore
#: every --reload restart) long after the browser tab is gone.
AIRPLAY_IDLE_TICK_SECONDS = 1.0


async def airplay_frames(port: int = 0,
                         tick: float = AIRPLAY_IDLE_TICK_SECONDS):
    """Relay uxplay's MJPEG bytes as-is (GStreamer already frames them).

    ``multipartmux boundary=frame`` emits exactly the multipart framing
    ``/screen/stream`` already serves, so nothing is re-encoded here.
    Yields ``None`` when a tick passes with no frame, so the caller can
    notice the browser left even while the phone is not mirroring yet.
    """
    reader, writer = await asyncio.open_connection(
        "127.0.0.1", port or AIRPLAY_MJPEG_PORT)
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(reader.read(65536), tick)
            except (asyncio.TimeoutError, TimeoutError):
                yield None
                continue
            if not chunk:
                break
            yield chunk
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, asyncio.CancelledError):
            pass

#: Seconds a Developer-Mode probe stays valid. The UI polls /screen/status
#: every 10 s; without this each poll would spend a tunnel setup.
DEVMODE_TTL_SECONDS = 120.0

PLACEHOLDER_LINES = (
    "No live pixels yet",
    "Plug in your iPhone, tap Trust,",
    "then press play.",
)

#: Seconds a DeveloperDiskImage mount probe stays valid. Mount state only
#: changes on reboot/unmount, and the UI polls /screen/status every 10 s.
DDI_TTL_SECONDS = 60.0

#: Placeholder when the phone is there but Developer Mode blocks capture.
DEVMODE_OFF_LINES = (
    "Developer Mode is OFF",
    "Settings -> Privacy & Security",
    "-> Developer Mode -> turn it on",
)

#: Placeholder when Developer Mode is on but the DDI was never mounted.
DDI_MISSING_LINES = (
    "Developer image not mounted",
    "Press \"Mount developer image\"",
    "in the checklist below.",
)

#: Placeholder when every probe passes but shots still fail because the
#: developer tunnel daemon is not running (iOS 17+ routes DVT capture
#: over tunneld; without it the tool answers "Unable to connect to
#: Tunneld" and writes no file).
TUNNEL_MISSING_LINES = (
    "Developer tunnel is OFF",
    "Run in a terminal (needs sudo),",
    "keep it running, press Refresh.",
)

#: Where pymobiledevice3's tunneld daemon listens (plain HTTP GET returns
#: the JSON tunnel list keyed by UDID). Same address the CLI itself uses
#: (pymobiledevice3.tunneld.api.TUNNELD_DEFAULT_ADDRESS).
TUNNELD_ADDRESS = (
    os.environ.get("FREETUNES_TUNNELD_HOST", "127.0.0.1"),
    int(os.environ.get("FREETUNES_TUNNELD_PORT", "49151")),
)
TUNNELD_PROBE_TIMEOUT_S = 2.0

#: Exact sudo command that provides the tunnel Preview needs on iOS 17+.
#: A daemon, not a one-shot: it must keep running in a terminal (the
#: backend cannot sudo for it, same reason usbmux-setup returns a command
#: when there is no terminal for the password). Built from this
#: interpreter on purpose: a bare `python3` usually has no
#: pymobiledevice3 (the backend's venv does), so the literal upstream
#: hint fails here with ModuleNotFoundError.
TUNNELD_START_COMMAND = (
    f"sudo {sys.executable} -m pymobiledevice3 remote tunneld")
TUNNELD_NEED = (
    "Preview needs the developer tunnel (tunneld): iOS 17+ only exposes "
    "screenshots over it, and it is not running on this computer. Run "
    f"`{TUNNELD_START_COMMAND}` in a terminal, keep it running, replug "
    "the iPhone if asked, then press Refresh above."
)

#: Log signature when a DVT shot fails for lack of tunnel (the tool's own
#: words — precise across CLI versions, no iOS-version guessing needed).
TUNNEL_LOG_MARKS = ("unable to connect to tunneld",)


def _dvt_log_names_tunnel(log: str) -> bool:
    """Did the DVT tool itself blame the missing tunneld daemon?"""
    low = (log or "").lower()
    return any(m in low for m in TUNNEL_LOG_MARKS)


def tunneld_state(
        udid: str,
        address: tuple[str, int] | None = None,
        timeout_s: float = TUNNELD_PROBE_TIMEOUT_S) -> str:
    """Developer tunnel for this iPhone: "up" | "missing" | "unknown".

    Fresh localhost HTTP probe on every call (no cache): it costs ~1 ms
    when the daemon is down (refused) and answers per-UDID, so a tunnel
    started in a terminal lights up on the next status poll with no
    stale-cache window. "unknown" means the daemon answered but its
    payload is unreadable — callers must not block on that.
    """
    if not udid or udid == "mock-udid":
        return "unknown"
    host, port = address or TUNNELD_ADDRESS
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/",
                                    timeout=timeout_s) as res:
            payload = json.loads(res.read().decode("utf-8") or "{}")
    except Exception:
        return "missing"
    if not isinstance(payload, dict):
        return "unknown"
    return "up" if udid in payload else "missing"


def _ios_major(ios_version: str) -> int:
    """Major iOS version, 0 when unreadable (never raises)."""
    try:
        return int(str(ios_version or "").split(".")[0])
    except (TypeError, ValueError):
        return 0


def _tunnel_blocks_preview(ios_version: str, tunnel: str) -> bool:
    """Only iOS 17+ routes capture over tunneld (legacy screenshotr on
    older releases never heard of it): with an unknown iOS keep the old
    optimistic claim instead of blocking a phone that needs no tunnel."""
    return _ios_major(ios_version) >= 17 and tunnel == "missing"

#: Shot providers, best first. The DVT instrument leads because it is
#: the one that takes ``--udid`` (so it always targets the phone the UI
#: asked for) and it answers on iOS 26.0.1. CoreDevice's
#: screencaptureservice is the newer service and covers the day the DVT
#: instrument goes away.
SHOT_PROVIDERS = ("dvt", "coredevice")


def _placeholder_png(lines: tuple[str, ...] = PLACEHOLDER_LINES,
                     width: int = 540, height: int = 960) -> bytes:
    """Render a clearly-fake phone-frame PNG (Pillow is a hard dep)."""
    from PIL import Image, ImageDraw  # local import: keeps module import light

    img = Image.new("RGB", (width, height), (24, 24, 28))
    d = ImageDraw.Draw(img)
    # Subtle vertical gradient bands (cheap, no numpy).
    for y in range(0, height, 8):
        shade = 24 + int(14 * y / height)
        d.rectangle([0, y, width, y + 8], fill=(shade, shade, shade + 6))
    # Phone frame.
    m = 46
    d.rounded_rectangle([m, m, width - m, height - m], radius=42,
                        outline=(120, 120, 135), width=3)
    d.rounded_rectangle([width // 2 - 60, m + 12, width // 2 + 60, m + 30],
                        radius=9, fill=(10, 10, 12))
    # Centered-ish text lines.
    y = height // 2 - 30
    for i, line in enumerate(lines):
        d.text((width // 2, y + i * 30), line, fill=(235, 235, 240),
               anchor="mm")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _is_png(data: bytes) -> bool:
    return len(data) > 8 and data[:8] == b"\x89PNG\r\n\x1a\n"


#: Encoded placeholder JPEGs by (quality, max_dim) (see make_frame).
_placeholder_jpeg_cache: dict[tuple[int, int], bytes] = {}

#: Preview-USB downscale bounds. The phone delivers 1170x2532 PNGs; the
#: browser shows them ~330 px wide inside the phone frame, so shipping
#: full-res JPEGs wastes Pillow encode time, loopback bytes, and <img>
#: decode time. Capped like the AirPlay relay (long edge, aspect kept).
PREVIEW_MAX_DIM_DEFAULT = int(
    os.environ.get("FREETUNES_PREVIEW_WIDTH", "720"))
PREVIEW_MAX_DIM_MIN = 320
PREVIEW_MAX_DIM_MAX = 1600


def _clamp_preview_dim(value: int) -> int:
    """Clamp a preview long-edge to the sane range (see make_frame)."""
    try:
        v = int(value or PREVIEW_MAX_DIM_DEFAULT)
    except (TypeError, ValueError):
        v = PREVIEW_MAX_DIM_DEFAULT
    return max(PREVIEW_MAX_DIM_MIN, min(v, PREVIEW_MAX_DIM_MAX))


def _encode_preview_jpeg(im, quality: int, max_dim: int) -> bytes:
    """RGB-convert, downscale, and JPEG-encode one shot.

    ``thumbnail`` with BILINEAR keeps the aspect and is ~3-4x faster
    than a full-res encode on a 1170x2532 shot; it is a no-op when the
    shot is already smaller than ``max_dim`` (e.g. placeholders).
    """
    from PIL import Image  # local import: keeps module import light

    rgb = im.convert("RGB")
    if max(rgb.size) > max_dim:
        rgb.thumbnail((max_dim, max_dim), Image.BILINEAR)
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _default_which(name: str) -> str | None:
    """Locate a helper CLI, including the backend's own venv bin dir.

    Plain ``shutil.which`` misses tools pip-installed into ``backend/.venv``
    (that bin dir is not on PATH when uvicorn is launched from a login
    shell), so also probe ``sys.prefix/bin`` and ``~/.local/bin``.
    """
    found = shutil.which(name)
    if found:
        return found
    for base in (sys.prefix, os.path.expanduser("~/.local")):
        cand = Path(base) / "bin" / name
        try:
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
        except OSError:
            continue
    return None


@dataclass
class ScreenService:
    runner: SubprocessRunner | FakeRunner = field(
        default_factory=SubprocessRunner)
    which: Callable[[str], str | None] = _default_which
    hd_port: int = HD_DEFAULT_PORT
    mock: bool = False
    _devmode_cache: tuple[float, str, str] | None = field(
        default=None, repr=False)
    _ddi_cache: tuple[float, str, str] | None = field(
        default=None, repr=False)
    #: Provider that last delivered live pixels — tried first next time so
    #: an MJPEG stream does not re-probe a dead path on every frame.
    _shot_provider: str = field(default="", repr=False)
    #: stderr+stdout of the last failed DVT shot attempt (the tool's own
    #: words: "Unable to connect to Tunneld" names the missing daemon
    #: precisely, with no iOS-version guessing in the caller).
    _last_dvt_log: str = field(default="", repr=False)
    #: Whether this CLI's CoreDevice screenshot accepts --udid (probed once).
    _coredevice_udid: bool | None = field(default=None, repr=False)

    def tool_path(self, name: str) -> str | None:
        try:
            return None if self.mock else self.which(name)
        except Exception:
            return None

    def tool_present(self, name: str) -> bool:
        return self.tool_path(name) is not None

    # -- status ------------------------------------------------------
    def devmode(self, udid: str) -> str:
        """iPhone Developer Mode: "on" | "off" | "unknown" (cached)."""
        if self.mock or not udid or udid == "mock-udid":
            return "unknown"
        now = time.monotonic()
        cached = self._devmode_cache
        if (cached is not None and cached[1] == udid
                and now - cached[0] < DEVMODE_TTL_SECONDS):
            return cached[2]
        state = "unknown"
        binary = self.tool_path("pymobiledevice3")
        if binary is not None:
            try:
                r = self.runner.run(
                    binary, "amfi", "developer-mode-status",
                    *self._pmd3_udid(udid), timeout=12)
                if r.returncode == 0:
                    v = (r.stdout or "").strip().lower()
                    state = ("on" if v == "true"
                             else "off" if v == "false" else "unknown")
            except Exception:
                pass
        self._devmode_cache = (now, udid, state)
        return state

    def ddi(self, udid: str) -> str:
        """DeveloperDiskImage mount: "mounted" | "missing" | "unknown".

        Every capture path (CoreDevice, DVT, idevicescreenshot) needs the
        image mounted; on iOS 17+ it is a *personalized* image fetched per
        boot, so a phone that was just restarted reports "missing" until
        ``mounter auto-mount`` runs again.
        """
        if self.mock or not udid or udid == "mock-udid":
            return "unknown"
        now = time.monotonic()
        cached = self._ddi_cache
        if (cached is not None and cached[1] == udid
                and now - cached[0] < DDI_TTL_SECONDS):
            return cached[2]
        state = "unknown"
        binary = self.tool_path("pymobiledevice3")
        if binary is not None:
            try:
                r = self.runner.run(binary, "mounter", "list",
                                    *self._pmd3_udid(udid), timeout=15)
                if r.returncode == 0:
                    out = (r.stdout or "").strip()
                    try:
                        images = json.loads(out) if out else []
                    except ValueError:
                        images = None
                    if isinstance(images, list):
                        state = "mounted" if images else "missing"
            except Exception:
                pass
        self._ddi_cache = (now, udid, state)
        return state

    def _forget_setup_cache(self) -> None:
        """Drop cached Developer Mode / DDI probes after a setup action."""
        self._devmode_cache = None
        self._ddi_cache = None
        self._shot_provider = ""

    # -- setup actions (host side of the on-device checklist) ----------
    def reveal_devmode(self, udid: str) -> dict:
        """Make the Developer Mode row appear in Settings (no reboot).

        On a phone that never talked to a developer tool the row is simply
        not there, which is the single most common reason the checklist
        looks impossible to follow.
        """
        return self._setup_run(
            udid, ("amfi", "reveal-developer-mode"), timeout=20,
            ok_note="Developer Mode now appears on the iPhone under "
                    "Settings -> Privacy & Security. Turn it on there "
                    "(the phone restarts), then press Refresh.")

    def enable_devmode(self, udid: str) -> dict:
        """Turn Developer Mode on. The iPhone reboots and asks to confirm."""
        return self._setup_run(
            udid, ("amfi", "enable-developer-mode"), timeout=30,
            ok_note="The iPhone is restarting. After it boots, tap Turn On "
                    "in the Developer Mode prompt, unlock it, then press "
                    "Refresh.")

    def mount_ddi(self, udid: str) -> dict:
        """Download + mount the personalized DeveloperDiskImage."""
        return self._setup_run(
            udid, ("mounter", "auto-mount"), timeout=300,
            ok_note="Developer image mounted — press Refresh and the live "
                    "pixels appear.")

    def _setup_run(self, udid: str, args: tuple[str, ...], timeout: int,
                   ok_note: str) -> dict:
        if self.mock or not udid or udid == "mock-udid":
            return {"ok": False, "reason": "No iPhone — plug one in over "
                                           "USB and tap Trust."}
        binary = self.tool_path("pymobiledevice3")
        if binary is None:
            return {"ok": False, "reason": PMD3_INSTALL_HINT}
        try:
            r = self.runner.run(binary, *args, *self._pmd3_udid(udid),
                                timeout=timeout)
        except Exception as e:  # pragma: no cover - runner already soft-fails
            return {"ok": False, "reason": str(e)}
        self._forget_setup_cache()
        if r.returncode == 0:
            return {"ok": True, "note": ok_note}
        detail = ((r.stderr or "") + (r.stdout or "")).strip()
        if "already mounted" in detail.lower():
            return {"ok": True, "note": "Developer image was already "
                                        "mounted."}
        return {"ok": False,
                "reason": detail[-400:] or "pymobiledevice3 refused the "
                                           "request — is the iPhone "
                                           "unlocked and trusted?"}

    def status(self, udid: str, trusted: bool = False,
               ios_version: str = "") -> dict:
        pmd3 = self.tool_present("pymobiledevice3")
        shot = self.tool_present("idevicescreenshot")
        uxplay = self.tool_present("uxplay")
        hd = hd_status()
        # tool_path, not which: mock mode must not probe host tools.
        air = airplay_status(self.tool_path)
        valeria = valeria_status(self.tool_path)
        qvh = valeria.get("qvh", False)
        device = bool(udid and udid != "mock-udid")
        needs: list[str] = []
        if not device:
            needs.append("Plug in your iPhone over USB and tap Trust.")
        elif not trusted:
            needs.append("Tap Trust on the iPhone and unlock it.")
        if not pmd3 and not shot and not qvh:
            needs.append(f"No screenshot tool found — {PMD3_INSTALL_HINT}.")
        devmode = self.devmode(udid) if (pmd3 and device) else "unknown"
        if pmd3 and device and devmode == "off":
            needs.append("Developer Mode is OFF on this iPhone — HD and "
                         "Preview both need it. On the phone: Settings -> "
                         "Privacy & Security -> Developer Mode -> turn it on, "
                         "restart when asked, then tap Turn On. Afterwards "
                         "press ⟳ up top and the live pixels appear.")
        elif pmd3 and device and devmode != "on":
            # "unknown" only: with Developer Mode provably on there is
            # nothing to ask for, and a checklist that never empties reads
            # as "still broken".
            needs.append("Enable Developer Mode on the iPhone "
                         "(Settings -> Privacy & Security) for HD + DVT shots.")
        # The DeveloperDiskImage is the second half of the setup and is
        # forgotten on every reboot — probing it costs one lockdown call.
        # It gates HD + Preview only: QuickTime-USB (Valeria/QVH) and
        # AirPlay need neither Developer Mode nor the image.
        ddi = self.ddi(udid) if (pmd3 and device) else "unknown"
        if pmd3 and device and devmode != "off" and ddi == "missing":
            needs.append("The developer image is not mounted on this iPhone "
                         "— HD and Preview need it, and iOS drops it on "
                         "each restart. Press “Mount developer image” "
                         "below (one download, ~10-60 s), then ⟳.")
        # iOS 17+ routes DVT capture over the tunneld daemon: with it
        # down every shot fails as "Unable to connect to Tunneld" while
        # devmode+ddi both look green, which used to report a fake live
        # Preview. Probe it fresh (localhost HTTP, ~1 ms when down) and
        # only when nothing else already blocks, so legacy (iOS <= 16)
        # phones that never heard of tunneld keep the old claim.
        tunnel = "unknown"
        if (pmd3 and device and devmode == "on" and ddi == "mounted"):
            tunnel = tunneld_state(udid)
            if _tunnel_blocks_preview(ios_version, tunnel):
                needs.append(TUNNELD_NEED)
        mode = "mock"
        if device and (pmd3 or shot or qvh):
            # "mjpeg" means a shot provider exists AND nothing known blocks
            # it. With Developer Mode provably off or the DDI provably not
            # mounted, shots return placeholders, so report "setup"
            # (live=False) instead of overclaiming. Valeria/QVH need no
            # Developer Mode and no image, so they stay usable while
            # Preview says setup — say so, or the checklist reads as
            # "nothing works" on a phone QuickTime would stream fine.
            blocked = (devmode == "off" or ddi == "missing"
                       or _tunnel_blocks_preview(ios_version, tunnel))
            mode = "setup" if blocked else "mjpeg"
            if (blocked and trusted and valeria.get("ready")
                    and not valeria.get("running")):
                needs.append("QuickTime over USB needs no Developer Mode "
                             "and no developer image — this trusted iPhone "
                             "streams already. Press Start QuickTime above "
                             "(30–60 fps H.264; the phone shows a fake 9:41 "
                             "clock with notifications hidden while "
                             "streaming).")
        if valeria.get("running"):
            mode = "valeria"
        if hd.get("running"):
            mode = "hd"
        return {
            "udid": udid,
            "available": device and (pmd3 or shot or qvh),
            "mode": mode,
            "live": mode in ("mjpeg", "hd", "valeria"),
            "developer_mode": devmode,
            "ddi": ddi,
            "tunneld": tunnel,
            "needs": needs,
            "ios_version": ios_version,
            "backends": {
                "pymobiledevice3": pmd3,
                "idevicescreenshot": shot,
                "uxplay": uxplay,
                "qvh": qvh,
                "valeria": valeria.get("screen_mirror", False),
            },
            "hd": hd,
            "valeria": valeria,
            "airplay": air,
            "hints": {
                "pymobiledevice3": PMD3_INSTALL_HINT,
                "uxplay": air["install_hint"],
                "valeria": VALERIA_INSTALL_HINT,
            },
        }

    # -- single shots -------------------------------------------------
    def take_shot(self, udid: str,
                  lines: tuple[str, ...] | None = None) -> tuple[bytes, str, bool]:
        """Return (image_bytes, media_type, live).

        Live PNG when a provider delivers; otherwise a placeholder PNG
        (live=False) so callers never 500 in mock mode. ``lines`` lets the
        caller state *why* there are no live pixels (e.g. Developer Mode).
        """
        if not self.mock and udid != "mock-udid":
            pmd3_path = self.tool_path("pymobiledevice3")
            if pmd3_path is not None:
                for provider in self._shot_order():
                    data = (self._shot_via_coredevice(udid)
                            if provider == "coredevice"
                            else self._shot_via_pmd3(udid))
                    if data is not None:
                        self._shot_provider = provider
                        return data, "image/png", True
                self._shot_provider = ""
                # pymobiledevice3 exists but no provider delivered (e.g.
                # Developer Mode off, or the DDI is not mounted): legacy
                # idevicescreenshot cannot succeed on iOS 17+ either — fail
                # fast instead of stacking timeouts. Name the reason when
                # the (cached) probes — or the tool's own log — know it.
                if lines is None:
                    lines = (TUNNEL_MISSING_LINES
                             if _dvt_log_names_tunnel(self._last_dvt_log)
                             else self._why_no_pixels(udid))
                return _placeholder_png(lines), "image/png", False
            if self.tool_present("idevicescreenshot"):
                data = self._shot_via_idevicescreenshot(udid)
                if data is not None:
                    return data, "image/png", True
        return _placeholder_png(lines or PLACEHOLDER_LINES), "image/png", False

    def _shot_order(self) -> tuple[str, ...]:
        """Providers to try, last winner first (stream frames stay cheap)."""
        won = self._shot_provider
        if won in SHOT_PROVIDERS:
            return (won,) + tuple(p for p in SHOT_PROVIDERS if p != won)
        return SHOT_PROVIDERS

    def _why_no_pixels(self, udid: str) -> tuple[str, ...]:
        """Placeholder text naming the step that is actually missing."""
        if self.devmode(udid) == "off":
            return DEVMODE_OFF_LINES
        if self.ddi(udid) == "missing":
            return DDI_MISSING_LINES
        return PLACEHOLDER_LINES

    def _coredevice_takes_udid(self, binary: str) -> bool:
        """Does this CLI let us name the phone for the CoreDevice shot?

        pmd3 v11's ``screen-capture screenshot`` is RSD-only and rejects
        ``--udid`` ("No such option"), unlike its DVT sibling. Probed once
        per process off ``--help``, so a newer CLI that grows the flag
        starts using it with no code change.
        """
        if self._coredevice_udid is None:
            try:
                r = self.runner.run(binary, "developer", "core-device",
                                    "screen-capture", "screenshot",
                                    "--help", timeout=15)
                text = (r.stdout or "") + (r.stderr or "")
                self._coredevice_udid = "--udid" in text
            except Exception:
                self._coredevice_udid = False
        return bool(self._coredevice_udid)

    def _run_shot(self, *argv: str) -> tuple[bytes | None, str]:
        """Run one screenshot CLI into a private temp file.

        ``argv`` holds ``{out}`` where the output path goes. Returns
        (image bytes or None, the tool's own words when it failed).
        """
        tmpdir = Path(tempfile.mkdtemp(prefix="freetunes-shot-"))
        out = tmpdir / "shot.png"
        try:
            r = self.runner.run(*(str(out) if a == "{out}" else a
                                  for a in argv), timeout=25)
            if (r.returncode == 0 and out.is_file()
                    and out.stat().st_size > 100):
                return out.read_bytes(), ""
            return None, f"{r.stderr or ''}\n{r.stdout or ''}"
        except Exception as e:
            return None, str(e)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _shot_via_coredevice(self, udid: str) -> bytes | None:
        """CoreDevice screencaptureservice — the newer capture service."""
        pmd3 = self.tool_path("pymobiledevice3") or "pymobiledevice3"
        if self._coredevice_takes_udid(pmd3):
            tail = self._pmd3_udid(udid)
        else:
            # Without the flag this command grabs the first USB device.
            # With one phone that is the phone; with several it could be
            # somebody else's screen, so decline instead of guessing.
            if not _first_device_is_ours():
                return None
            tail = []
        data, _ = self._run_shot(pmd3, "developer", "core-device",
                                 "screen-capture", "screenshot", "{out}",
                                 *tail)
        return data

    def _shot_via_pmd3(self, udid: str) -> bytes | None:
        """DVT screenshot instrument; remembers the tool's failure log."""
        pmd3 = self.tool_path("pymobiledevice3") or "pymobiledevice3"
        base = (pmd3, "developer", "dvt", "screenshot", "{out}")
        data, self._last_dvt_log = self._run_shot(*base,
                                                  *self._pmd3_udid(udid))
        if (data is None and self._pmd3_udid(udid)
                and _first_device_is_ours()):
            # Retry without the selector (older/newer CLI layouts) — only
            # when the "first USB device" it then picks can only be ours.
            data, log = self._run_shot(*base)
            self._last_dvt_log += "\n" + log
        return data

    def _shot_via_idevicescreenshot(self, udid: str) -> bytes | None:
        tool = self.tool_path("idevicescreenshot") or "idevicescreenshot"
        sel = ["-u", udid] if udid and udid != "mock-udid" else []
        data, _ = self._run_shot(tool, *sel, "{out}")
        return data

    @staticmethod
    def _pmd3_udid(udid: str) -> list[str]:
        """pmd3 v11 takes ``--udid`` as a *subcommand* Device Option: it
        must trail the subcommand path (a global ``--udid`` aborts with
        "No such option")."""
        if udid and udid != "mock-udid":
            return ["--udid", udid]
        return []

    # -- MJPEG ---------------------------------------------------------
    def make_frame(self, udid: str, quality: int = 70,
                   max_dim: int = PREVIEW_MAX_DIM_DEFAULT,
                   ) -> tuple[bytes, bool]:
        """Encode one multipart MJPEG chunk; returns (chunk, live).

        Non-live placeholder frames are JPEG-encoded once per
        (quality, max_dim) and reused, so a broken setup costs one
        screenshot attempt per frame, not a re-encode plus an attempt.
        Live shots are downscaled to ``max_dim`` (long edge) first:
        a 1170x2532 PNG encoded at 720p is ~4x fewer pixels to
        encode, ship, and decode than full-res, which is where the
        "Preview feels slow" time actually goes (the ~2 s DVT capture
        itself cannot be shortened from here).
        """
        from PIL import Image  # local import: keeps module import light

        quality = max(30, min(int(quality or 70), 90))
        max_dim = _clamp_preview_dim(max_dim)
        data, _, live = self.take_shot(udid)
        frame = None if live else _placeholder_jpeg_cache.get(
            (quality, max_dim))
        if frame is None:
            try:
                with Image.open(io.BytesIO(data)) as im:
                    frame = _encode_preview_jpeg(im, quality, max_dim)
            except Exception:
                frame = data
            if not live:
                _placeholder_jpeg_cache[(quality, max_dim)] = frame
        return ((b"--frame\r\nContent-Type: image/jpeg\r\n"
                 b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
                 + frame + b"\r\n"), live)


def _first_device_is_ours(on_error: bool = False) -> bool:
    """May a CLI without ``--udid`` safely take "the first USB device"?

    Only when at most one phone is plugged in: with several it could be
    somebody else's screen. ``on_error`` answers when the lookup fails.
    """
    from .devices import get_service  # local: avoids an import cycle
    try:
        return len(get_service().list_devices()) <= 1
    except Exception:
        return on_error


# -- supervised subprocesses (HD serve-web, Valeria, uxplay) ------------
class _Server:
    """One supervised helper process and the log file it writes.

    Output goes to a file, never ``stdout=PIPE``: an undrained pipe
    wedges the child once the OS buffer fills (~64 KB of logs), which on
    a long session looks exactly like "the screen froze" — and the log's
    last lines are the only honest failure reason there is.
    """

    def __init__(self, name: str, port: int = 0) -> None:
        self.name = name
        self.port = port
        self.proc: subprocess.Popen | None = None
        self.log: Path | None = None
        self.udid = ""

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/" if self.alive() else ""

    def spawn(self, cmd: list[str], udid: str = "") -> None:
        """Start ``cmd`` logging to a fresh temp file (raises OSError)."""
        self.stop()
        fd, path = tempfile.mkstemp(prefix=f"freetunes-{self.name}-",
                                    suffix=".log")
        os.close(fd)
        self.log = Path(path)
        try:
            with self.log.open("w") as fh:
                self.proc = subprocess.Popen(
                    cmd, stdout=fh, stderr=subprocess.STDOUT, text=True)
        except OSError:
            self.stop()
            raise
        self.udid = udid

    def tail(self, limit: int = 500) -> str:
        """Last words of the server, for an honest failure reason."""
        if self.log is None:
            return ""
        try:
            return self.log.read_text(errors="replace").strip()[-limit:]
        except OSError:
            return ""

    def wait_http(self, url: str, timeout_s: float) -> bool:
        """Poll ``url`` until it answers; False once the process died."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(url, timeout=2) as res:
                    if res.status < 500:
                        return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def stop(self) -> None:
        p, self.proc, self.udid = self.proc, None, ""
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        log, self.log = self.log, None
        if log is not None:
            try:
                log.unlink()
            except OSError:
                pass


_hd = _Server("hd", HD_DEFAULT_PORT)
_valeria = _Server("valeria", VALERIA_DEFAULT_PORT)
_airplay = _Server("airplay")
#: True while the running receiver renders into the page, not a window.
_airplay_embedded: bool = False


def _mock_env() -> bool:
    return os.environ.get("FREETUNES_MOCK", "0") == "1"


def _which_soft(which: Callable[[str], str | None], name: str) -> str | None:
    """``which(name)`` that never raises."""
    try:
        return which(name)
    except Exception:
        return None


#: ``--help`` text per (binary, subcommand). Only successful probes are
#: kept for good; a failed one is retried after this many seconds, so a
#: fork installed by hand in a terminal lights up on the next status poll
#: instead of reading as "missing" until the backend restarts.
CLI_HELP_RETRY_SECONDS = 30.0
_help_cache: dict[tuple[str, ...], tuple[float, str]] = {}


def _cli_help(binary: str, *sub: str) -> str:
    """``<binary> <sub...> --help`` text, "" when that subcommand is absent.

    Stock pymobiledevice3 answers ``No such command 'screen-mirror'`` with
    a non-zero exit — that must read as "not there", so only a zero-exit
    help text counts.
    """
    key = (binary, *sub)
    hit = _help_cache.get(key)
    if hit is not None and (hit[1] or time.monotonic() - hit[0]
                            < CLI_HELP_RETRY_SECONDS):
        return hit[1]
    text = ""
    try:
        r = subprocess.run([binary, *sub, "--help"], capture_output=True,
                           text=True, timeout=20)
        if r.returncode == 0:
            text = (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        pass
    _help_cache[key] = (time.monotonic(), text)
    return text


def _serve_web_help(binary: str) -> str:
    return _cli_help(binary, "developer", "core-device", "display",
                     "serve-web")


def _screen_mirror_help(binary: str) -> str:
    return _cli_help(binary, "screen-mirror")


def hd_status() -> dict:
    running = _hd.alive()
    return {"running": running, "udid": _hd.udid if running else "",
            "url": _hd.url}


def hd_start(udid: str, which: Callable[[str], str | None] = _default_which,
             port: int = HD_DEFAULT_PORT) -> dict:
    """Supervise `pymobiledevice3 ... display serve-web`; honest failures."""
    if _mock_env():
        return {"ok": False, "running": False,
                "reason": "Mock mode — plug in a trusted iPhone with "
                          "Developer Mode on, then start HD."}
    if _hd.alive():
        return {"ok": True, "running": True, "udid": _hd.udid,
                "url": _hd.url, "note": "HD server already running."}
    binary = _which_soft(which, "pymobiledevice3")
    if not binary:
        return {"ok": False, "running": False, "reason": PMD3_INSTALL_HINT}
    if ("--udid" not in _serve_web_help(binary)
            and not _first_device_is_ours(on_error=True)):
        # Without the flag serve-web takes the first USB device: with
        # several phones, streaming the wrong screen is not a mistake
        # worth making silently.
        return {"ok": False, "running": False,
                "reason": "This pymobiledevice3 cannot be told which "
                          "iPhone to stream (its serve-web has no "
                          "--udid). Unplug the other devices, or use "
                          "Preview/AirPlay instead."}
    info = _media_support(binary)
    if info is not None and not info.get("supportedFeatures"):
        return {"ok": False, "running": False,
                "reason": HD_UNSUPPORTED_REASON,
                "device_says": info.get("supportedFeaturesDescription", "")}
    _hd.port = port
    try:
        _hd.spawn(_serve_web_cmd(udid, port, binary), udid)
    except OSError as e:
        return {"ok": False, "running": False, "reason": str(e)}
    if _hd.wait_http(f"http://127.0.0.1:{port}/", timeout_s=25.0):
        return {"ok": True, "running": True, "udid": udid, "url": _hd.url}
    tail = _hd.tail()
    _hd.stop()
    hint = ("Is Developer Mode on (Settings -> Privacy & Security), the "
            "phone trusted + unlocked, and iOS 17.4+?")
    return {"ok": False, "running": False,
            "reason": f"HD server did not come up. {hint} {tail}".strip()}


#: Apple gates the CoreDevice media stream (what HD rides on) to
#: iOS 27+. Below that the display service advertises no features at all
#: and every start request comes back as CoreDeviceError 9021, "Remote
#: control requires iOS 27.0 or later on this device" — verified on an
#: iPhone 13 / iOS 26.0.1. Cheaper (and more honest) to ask first than to
#: hand the user a viewer page that will never show a frame.
HD_UNSUPPORTED_REASON = (
    "This iPhone does not offer the CoreDevice media stream HD needs: "
    "Apple gates it to iOS 27 or newer (the phone answers “Remote "
    "control requires iOS 27.0 or later”). Use Preview (USB) for "
    "stills, or AirPlay (Wi-Fi) for full-rate video with sound."
)


def _media_support(binary: str) -> dict | None:
    """``display get-media-support-info`` as a dict, None if unreadable.

    The command is RSD-only (no ``--udid``), so callers must already have
    settled which phone they mean.
    """
    try:
        r = subprocess.run(
            [binary, "developer", "core-device", "display",
             "get-media-support-info"],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (r.stdout or "").strip()
    if r.returncode != 0 or not out:
        return None
    try:
        info = json.loads(out)
    except ValueError:
        return None
    return info if isinstance(info, dict) else None


def _serve_web_cmd(udid: str, port: int, binary: str) -> list[str]:
    """Build the serve-web argv, passing only flags this CLI really has.

    pmd3 v11's ``display serve-web`` is RSD-only and aborts on ``--udid``
    ("No such option") — passing it anyway meant HD never started. Same
    story for the port flag, so both are gated on the ``--help`` text.
    """
    tail = ["developer", "core-device", "display", "serve-web",
            "--bind", "127.0.0.1"]
    help_text = _serve_web_help(binary)
    if "--http-port" in help_text:
        tail += ["--http-port", str(port)]
    elif "--port" in help_text:
        tail += ["--port", str(port)]
    if udid and udid != "mock-udid" and "--udid" in help_text:
        tail += ["--udid", udid]
    return [binary] + tail


def hd_stop() -> dict:
    _hd.stop()
    return {"ok": True, "running": False}


# -- QuickTime-USB (Valeria H.264 30-60 fps, no Developer Mode) -----------
def _valeria_cmd(udid: str, port: int, binary: str) -> list[str]:
    """Build the screen-mirror argv, passing only flags this CLI really has.

    The fork is still moving: flag names differ between snapshots, and
    passing an unknown flag aborts the server at launch (the same way
    ``--udid`` once broke HD's serve-web). Gate everything on the
    ``--help`` text so a newer CLI lights up with no code change.

    Real CLI (feature/screen-mirror-browser-viewer): ``--host`` (not
    ``--bind``), ``--port`` (not ``--http-port``), ``--backend`` taking
    ``auto | cmio | libusb`` (never ``valeria`` — default ``auto`` already
    picks cmio on macOS, libusb elsewhere). Device selection rides the
    typer-injected service provider, so ``--udid`` is only passed when
    the CLI advertises it.
    """
    tail = ["screen-mirror"]
    help_text = _screen_mirror_help(binary)
    if "--host" in help_text:
        tail += ["--host", "127.0.0.1"]
    elif "--bind" in help_text:
        tail += ["--bind", "127.0.0.1"]
    if "--port" in help_text:
        tail += ["--port", str(port)]
    elif "--http-port" in help_text:
        tail += ["--http-port", str(port)]
    # Explicit `auto` documents intent (platform pick) and is a no-op
    # against the default; never pass `--backend valeria` — the fork
    # rejects it (valid: auto | cmio | libusb).
    if "--backend" in help_text:
        tail += ["--backend", "auto"]
    if udid and udid != "mock-udid" and "--udid" in help_text:
        tail += ["--udid", udid]
    return [binary] + tail


#: Log signature when USB was claimed fine but the iPhone sends no video
#: clock because its screen is asleep/locked ("capture handshake
#: completed but iDevice sent no video clock"). Nothing on the host side
#: fixes this — the phone must be woken up. (An asleep phone also fails
#: earlier stages, so this check comes after the USB-level signatures.)
VALERIA_ASLEEP_MARKS = (
    "no video clock",
    "screen is likely asleep",
)
VALERIA_ASLEEP_REASON = (
    "The iPhone's screen is asleep (or locked) — QuickTime claimed USB "
    "fine, but the phone sends no video until it wakes. Press the side "
    "button, unlock it, and press Start QuickTime again (no replug, no "
    "reinstall)."
)


def _valeria_log_names_asleep(tail: str) -> bool:
    """Does the server log blame the asleep phone (not host/USB)?"""
    low = (tail or "").lower()
    return any(m in low for m in VALERIA_ASLEEP_MARKS)


#: Log lines proving the USB capture itself came up (not just the viewer
#: page). The page serves HTTP even when capture is dead, so HTTP-ok
#: alone once reported a false success while the phone streamed nothing.
VALERIA_CAPTURE_OK_MARKS = (
    "capture started",
    "screen mirror ready",
)

#: Any refusal of the USB config switch means the capture is dead, even
#: when it is not the gvfs-busy case (see VALERIA_USB_BUSY_MARKS): the
#: message mapping below decides *which* failure it is, this only decides
#: that pixels will not come.
VALERIA_CAPTURE_DEAD_MARKS = (
    "setactiveconfiguration failed",
)


def _valeria_capture_ok(timeout_s: float = 5.0) -> bool:
    """Did the capture come up (not just the HTTP page)?

    Polls the server log: success markers win at once, known-fatal
    signatures (busy USB, no QT-capable usbmuxd config) fail at once,
    and a silent log times out as ok — a slow capture must not block
    the Start button longer than this, the failure mapping below stays
    as the backstop.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        tail = _valeria.tail(2000).lower()
        if any(m in tail for m in VALERIA_CAPTURE_OK_MARKS):
            return True
        if (_valeria_log_names_no_qt_config(tail)
                or _valeria_log_names_usb_busy(tail)
                or _valeria_log_names_asleep(tail)
                or any(m in tail for m in VALERIA_CAPTURE_DEAD_MARKS)):
            return False
        time.sleep(0.5)
    return True


def _valeria_start_failure(tail: str) -> dict:
    """Map the server's last words to the honest failure dict."""
    if _valeria_log_names_no_qt_config(tail):
        # The log names the host usbmuxd, not trust or the cable: lead
        # with the fork fix instead of "is the iPhone trusted?".
        return {"ok": False, "running": False,
                "reason": f"{VALERIA_NO_QT_CONFIG_REASON} {tail}".strip(),
                "fix": VALERIA_LINUX_SETUP_URL}
    if _valeria_log_names_usb_busy(tail):
        # The fork is ready but a desktop photo importer (gvfsd-gphoto2)
        # holds the PTP interface, so the config switch comes back busy:
        # lead with the unmount fix instead of "is the iPhone trusted?".
        return {"ok": False, "running": False,
                "reason": f"{VALERIA_USB_BUSY_REASON} {tail}".strip(),
                "fix": VALERIA_USB_BUSY_FIX}
    if _valeria_log_names_asleep(tail):
        # USB was claimed fine; the phone just sends no video while its
        # screen sleeps. No host-side fix exists — say wake, not reinstall.
        return {"ok": False, "running": False,
                "reason": f"{VALERIA_ASLEEP_REASON} {tail}".strip()}
    hint = ("Is the iPhone trusted + unlocked? " + VALERIA_USBMUX_HINT)
    return {"ok": False, "running": False,
            "reason": f"QuickTime server did not come up. {hint} {tail}".strip()}


#: Host probes the 10 s status poll would otherwise re-run every time
#: (gio + four systemctl/grep calls). Mounts and the usbmuxd service only
#: change on plug/unplug/setup, so a short TTL costs nothing in accuracy.
PROBE_TTL_SECONDS = 15.0
_probe_cache: dict[str, tuple[float, dict]] = {}


def _cached_probe(key: str, probe: Callable[[], dict]) -> dict:
    now = time.monotonic()
    hit = _probe_cache.get(key)
    if hit is not None and now - hit[0] < PROBE_TTL_SECONDS:
        return hit[1]
    value = probe()
    _probe_cache[key] = (now, value)
    return value


def photo_hold_state(run: Callable | None = None) -> dict:
    """Is a desktop photo importer holding the iPhone's USB interface?

    On GNOME desktops gvfsd-gphoto2 claims the PTP interface the moment
    the phone plugs in, and the QuickTime capture switch then fails as
    SetActiveConfiguration number=6 (busy). Needs no root to detect or
    to release (``gio mount -u`` on the user's own mount).
    """
    return _cached_probe("photo_hold", lambda: _photo_hold_probe(run))


def _photo_hold_probe(run: Callable | None = None) -> dict:
    run = run or _run_capture
    code, out = run(["gio", "mount", "-l"], timeout=5)
    if code != 0 and not out:
        return {"held": False, "mounts": [], "gio": False}
    mounts = sorted(set(
        m.group(1) for line in (out or "").splitlines()
        for m in [re.search(r"->\s*(gphoto2://\S+)", line)] if m))
    return {"held": bool(mounts), "mounts": mounts, "gio": True}


def _mount_matches_udid(addr: str, udid: str) -> bool:
    """Does a gphoto2:// address name this iPhone (serial = UDID)?"""
    norm = re.sub(r"[^0-9a-f]", "", (addr or "").lower())
    want = re.sub(r"[^0-9a-f]", "", (udid or "").lower())
    return bool(want) and want in norm


def _run_capture(argv: list[str], timeout: int = 10) -> tuple[int, str]:
    """Run once, returning (returncode, stdout); never raises."""
    try:
        r = subprocess.run(list(argv), capture_output=True, text=True,
                           timeout=timeout)
        return r.returncode, (r.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def usbmuxd_state(run: Callable | None = None) -> dict:
    """Host usbmuxd vs the QuickTime fork: is the Linux USB setup done?

    On non-Linux there is nothing to set up (macOS drives QuickTime mode
    itself), so ``ready`` is True. On Linux ``ready`` means the fork
    binary is installed *and* the running service is that binary with
    ``USBMUXD_DEFAULT_DEVICE_MODE=2`` — anything less still fails as
    "no QT-capable config". ``run`` is injectable for tests. Uncached:
    the status poll goes through ``_cached_probe`` instead.
    """
    run = run or _run_capture
    if not sys.platform.startswith("linux"):
        return {"linux": False, "ready": True, "needs": []}
    fork = Path(USBMUXD_FORK_BIN).is_file()
    version, has_mode = "", False
    if fork:
        _, out = run([USBMUXD_FORK_BIN, "--version"])
        version = (out.strip().splitlines() or [""])[0].strip()
        code, _ = run(["grep", "-a", "-q", "USBMUXD_DEFAULT_DEVICE_MODE",
                       USBMUXD_FORK_BIN])
        has_mode = code == 0
    _, out = run(["systemctl", "is-active", "usbmuxd"])
    active = out.strip() == "active"
    _, show = run(["systemctl", "show", "usbmuxd", "-p",
                   "ExecStart,Environment"])
    show = show or ""
    m = re.search(r"path=([^ ;]+)", show)
    exec_path = m.group(1) if m else ""
    env_mode2 = "USBMUXD_DEFAULT_DEVICE_MODE=2" in show
    override = Path(USBMUXD_OVERRIDE_FILE).is_file()
    fork_running = exec_path.startswith("/usr/local/")
    ready = bool(fork and has_mode and active and env_mode2
                 and fork_running)
    needs: list[str] = []
    if not ready:
        if not (fork and has_mode):
            needs.append("Install the usbmuxd fork (dynamic-config-switch "
                         "branch): the distro usbmuxd cannot drive the "
                         "QuickTime alt-config.")
        if not (active and fork_running):
            needs.append("Switch the running usbmuxd service to the fork "
                         "binary (/usr/local/sbin/usbmuxd).")
        if not env_mode2:
            needs.append("Run usbmuxd with USBMUXD_DEFAULT_DEVICE_MODE=2 "
                         "(systemd drop-in).")
        needs.append(f"One command does all of it: "
                     f"{VALERIA_USBMUX_SETUP_COMMAND} (needs sudo; "
                     f"~5-10 min build the first time). Revert any time "
                     f"with: bash {VALERIA_USBMUX_SETUP_SCRIPT} --revert")
    return {
        "linux": True,
        "ready": ready,
        "fork_installed": fork,
        "fork_version": version,
        "has_device_mode": has_mode,
        "service_active": active,
        "service_binary": exec_path,
        "env_mode2": env_mode2,
        "override_present": override,
        "needs": needs,
        "setup_command": VALERIA_USBMUX_SETUP_COMMAND,
    }


def valeria_status(
        which: Callable[[str], str | None] | None = None) -> dict:
    """QuickTime-USB mirror state *and* what this host still needs.

    No Developer Mode, no developer image: any trusted iPhone works. The
    price is USB contention — Valeria claims the device with libusb and
    fights usbmuxd for it — plus presentation mode (fake 9:41 clock).
    On Linux there is one host prerequisite: the usbmuxd fork (distro
    usbmuxd fails every start as "no QT-capable config").
    """
    which = which or _default_which
    running = _valeria.alive()
    pmd3_bin = _which_soft(which, "pymobiledevice3")
    have_qvh = _which_soft(which, "qvh") is not None
    # Only claim the backend when the CLI advertises screen-mirror.
    screen_mirror = bool(pmd3_bin and _screen_mirror_help(pmd3_bin))
    needs: list[str] = []
    if not pmd3_bin and not have_qvh:
        needs.append(f"Install the QuickTime-USB route: {VALERIA_INSTALL_HINT}")
    elif pmd3_bin and not screen_mirror and not have_qvh:
        needs.append(
            "This pymobiledevice3 has no `screen-mirror` subcommand — "
            f"{VALERIA_INSTALL_HINT}. {QVH_INSTALL_HINT}.")
    usb = _cached_probe("usbmuxd", usbmuxd_state)
    if usb.get("linux") and not usb.get("ready") and not running:
        # Proactive, not after a 20 s doomed start: distro usbmuxd fails
        # every QuickTime start as "no QT-capable config".
        needs.append(
            "Linux one-time USB setup: the distro usbmuxd cannot drive "
            "the QuickTime alt-config. "
            f"{usb['needs'][0] if usb.get('needs') else ''} "
            f"Run: {VALERIA_USBMUX_SETUP_COMMAND} (needs sudo) or press "
            "“Run Linux USB setup” below.".strip())
    return {
        "running": running,
        "udid": _valeria.udid if running else "",
        "url": _valeria.url,
        "backend": "screen-mirror" if running or screen_mirror else (
            "qvh" if have_qvh else ""),
        "ready": screen_mirror or have_qvh,
        "needs": needs,
        "install_hint": VALERIA_INSTALL_HINT,
        "install_command": VALERIA_INSTALL_COMMAND,
        "install_running": _valeria_installing,
        "qvh_hint": QVH_INSTALL_HINT,
        "usbmux_hint": VALERIA_USBMUX_HINT,
        "linux_hint": (VALERIA_LINUX_HINT
                       if sys.platform.startswith("linux") else ""),
        "linux_setup_url": VALERIA_LINUX_SETUP_URL,
        "usbmuxd": usb,
        "qvh": have_qvh,
        "screen_mirror": screen_mirror,
        "photo_hold": photo_hold_state(),
        "log": _valeria.tail() if running else "",
    }


def _valeria_trusted(udid: str) -> bool | None:
    """Trust state for the QuickTime gate: True | False | None (unknown).

    Unknown (no device service, lookup failure) must NOT block: the USB
    claim below fails honest on its own. Only a provable "not trusted"
    refuses early, so the user gets "tap Trust" instead of a USB-claim
    riddle. Developer Mode is deliberately never consulted here — the
    QuickTime protocol works on any trusted iPhone with no Developer
    Mode and no developer image.
    """
    if not udid or udid == "mock-udid":
        return False
    try:
        from .devices import get_service  # local: avoids an import cycle
        devs = get_service().list_devices()
    except Exception:
        return None
    for d in devs:
        if d.udid == udid:
            return bool(d.trusted)
    return None


def valeria_start(udid: str,
                  which: Callable[[str], str | None] = _default_which,
                  port: int = VALERIA_DEFAULT_PORT,
                  trusted: bool | None = None) -> dict:
    """Supervise `pymobiledevice3 screen-mirror`; honest failures.

    Faster preview than MJPEG polling (H.264 30-60 fps, WebCodecs in the
    browser). Gate: the iPhone must be trusted (the QuickTime protocol
    still pairs over lockdown). No Developer Mode, no developer image —
    any trusted iPhone streams; while streaming the phone sits in
    presentation mode (fake 9:41 clock, notifications hidden), exactly
    like QuickTime Player. Fights usbmuxd for USB — the failure reason
    says so instead of "it just does not work".
    """
    if _mock_env():
        return {"ok": False, "running": False,
                "reason": "Mock mode — plug in a trusted iPhone over USB, "
                          "then start QuickTime."}
    if _valeria.alive():
        return {"ok": True, "running": True, "udid": _valeria.udid,
                "url": _valeria.url, "backend": "screen-mirror",
                "note": "QuickTime server already running."}
    if trusted is None:
        trusted = _valeria_trusted(udid)
    if trusted is False:
        return {"ok": False, "running": False,
                "reason": ("This iPhone is not trusted — unlock it, tap "
                           "Trust in the prompt, then press Start QuickTime "
                           "again. QuickTime needs trust, but no Developer "
                           "Mode and no developer image.")}
    binary = _which_soft(which, "pymobiledevice3")
    if not binary:
        hint = VALERIA_INSTALL_HINT + (
            ". qvh is present — run `qvh gstreamer` in a terminal as the "
            "manual fallback." if _which_soft(which, "qvh")
            else f". {QVH_INSTALL_HINT}.")
        return {"ok": False, "running": False, "reason": hint}
    help_text = _screen_mirror_help(binary)
    if not help_text:
        return {"ok": False, "running": False,
                "reason": ("This pymobiledevice3 has no `screen-mirror` "
                           f"subcommand — {VALERIA_INSTALL_HINT}. "
                           f"{QVH_INSTALL_HINT}.")}
    if "--udid" not in help_text and not _first_device_is_ours(on_error=True):
        # Without the flag screen-mirror takes the first USB device: with
        # several phones, streaming the wrong screen is not a mistake
        # worth making silently.
        return {"ok": False, "running": False,
                "reason": "This screen-mirror cannot be told which "
                          "iPhone to stream (no --udid). Unplug the "
                          "other devices, or use Preview instead."}
    # Fast-fail before claiming USB: a desktop photo importer holding the
    # PTP interface dooms the capture switch (SetActiveConfiguration
    # number=6) while the viewer page still serves HTTP — which used to
    # report a false success with zero frames. Name the release step
    # instead of spawning a server that can never capture.
    hold = photo_hold_state()
    if hold.get("held") and (not udid or any(
            _mount_matches_udid(m, udid) for m in hold.get("mounts", []))):
        return _valeria_start_failure(
            "SetActiveConfiguration failed (number=6). gvfs photo mount "
            "held: " + ", ".join(hold.get("mounts", [])))
    _valeria.port = port
    try:
        _valeria.spawn(_valeria_cmd(udid, port, binary), udid)
    except OSError as e:
        return {"ok": False, "running": False, "reason": str(e)}
    # The viewer page answers HTTP even when the capture itself is dead
    # (busy USB, wrong usbmuxd): confirm pixels before ok.
    if (_valeria.wait_http(f"http://127.0.0.1:{port}/", timeout_s=20.0)
            and _valeria_capture_ok() and _valeria.alive()):
        return {"ok": True, "running": True, "udid": udid,
                "url": _valeria.url, "backend": "screen-mirror"}
    tail = _valeria.tail()
    _valeria.stop()
    return _valeria_start_failure(tail)


def valeria_stop() -> dict:
    _valeria.stop()
    return {"ok": True, "running": False}


#: True while POST /screen/valeria/install is running pip. /screen/status
#: and /screen/valeria surface it as install_running so the UI can disable
#: both buttons instead of stacking two pip runs.
_valeria_installing: bool = False


def _pip_failure_reason(output: str) -> str:
    """First meaningful error lines from pip output (git/pip/build errors).

    Pip buries the cause (e.g. `git checkout -q <ref>` for a nonexistent
    branch) above the trailing `Failed to build ...` summary, so return
    the most diagnostic lines instead of the whole log.
    """
    lines = [ln.strip() for ln in (output or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    keys = ("error:", "failed", "checkout", "no such", "not found",
            "could not", "unable", "errno", "refusing")
    hits = [ln for ln in lines if any(k in ln.lower() for k in keys)]
    # Prefer the earliest diagnostic hit plus its successor for context,
    # fall back to the last two lines (pip's own summary).
    if hits:
        first = lines.index(hits[0])
        return " ".join(lines[first:first + 2])[-500:]
    return " ".join(lines[-2:])[-500:]


def valeria_install(
        which: Callable[[str], str | None] | None = None,
        timeout_s: int = 300) -> dict:
    """One-click install of the QuickTime-USB (Valeria) dependencies.

    Runs ``sys.executable -m pip install -U <fork> aiohttp av`` so the
    packages land in the backend's own environment — the same interpreter
    that later probes ``screen-mirror --help``. Clears the help cache
    afterwards so a fresh fork lights up with no restart.
    """
    global _valeria_installing
    which = which or _default_which
    if _mock_env():
        return {"ok": False, "installed": False,
                "reason": "Mock mode — install on the real host with: "
                          + VALERIA_INSTALL_COMMAND}
    if _valeria_installing:
        return {"ok": False, "installed": False, "install_running": True,
                "reason": "Install already running — wait for it to finish, "
                          "then press Refresh."}
    pmd3_bin = _which_soft(which, "pymobiledevice3")
    if pmd3_bin and _screen_mirror_help(pmd3_bin):
        return {"ok": True, "installed": True, "already": True,
                "note": "QuickTime dependencies already installed — "
                        "press Start QuickTime."}
    _valeria_installing = True
    try:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-U",
                 *VALERIA_INSTALL_PACKAGES],
                capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return {"ok": False, "installed": False,
                    "reason": f"Install timed out after {timeout_s}s — "
                              "run manually: " + VALERIA_INSTALL_COMMAND,
                    "command": VALERIA_INSTALL_COMMAND}
        except OSError as e:
            return {"ok": False, "installed": False,
                    "reason": str(e), "command": VALERIA_INSTALL_COMMAND}
        tail = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        tail = tail[-2000:] if len(tail) > 2000 else tail
        # The fork may have landed under a fresh sys.prefix/bin — drop the
        # cached probe so the next status sees it with no restart.
        _help_cache.clear()
        fresh_bin = _which_soft(which, "pymobiledevice3")
        if proc.returncode == 0 and fresh_bin and _screen_mirror_help(fresh_bin):
            return {"ok": True, "installed": True,
                    "note": "Installed — replug the iPhone, tap Trust, "
                            "then press Start QuickTime.",
                    "log": tail}
        pip_cause = _pip_failure_reason(tail)
        # A pip/build failure is a packaging problem, not a USB-claim
        # problem: surface pip's own words first (e.g. a bad git ref or no
        # network), then the manual command + qvh fallback. The usbmux
        # hint belongs to start-time USB claims, not here.
        reason = "Install failed"
        if pip_cause:
            reason += f": {pip_cause}"
        reason += ". Try manually: " + VALERIA_INSTALL_COMMAND + ". "
        reason += QVH_INSTALL_HINT + "."
        return {"ok": False, "installed": False, "reason": reason,
                "log": tail, "command": VALERIA_INSTALL_COMMAND}
    finally:
        _valeria_installing = False


#: True while POST /screen/valeria/usbmux-setup is running the Linux USB
#: setup (build takes minutes). Surfaced so the UI disables the button
#: instead of stacking two builds.
_usbmux_setup_running: bool = False


def valeria_usbmux_setup(timeout_s: int = 600) -> dict:
    """Run scripts/setup-valeria-linux.sh (same pattern as valeria_install).

    Builds the usbmuxd fork and switches the systemd service to it with
    USBMUXD_DEFAULT_DEVICE_MODE=2. The install/configure steps need root:
    with no terminal to type the sudo password into (the usual backend
    case) the script exits 3 fast, and this returns the exact terminal
    command instead of hanging on a prompt nobody can answer.
    """
    global _usbmux_setup_running
    if _mock_env():
        return {"ok": False, "installed": False,
                "reason": "Mock mode — run on the real Linux host: "
                          + VALERIA_USBMUX_SETUP_COMMAND}
    if _usbmux_setup_running:
        return {"ok": False, "installed": False, "install_running": True,
                "reason": "USB setup already running — wait for it to "
                          "finish (the first build takes ~5-10 min), then "
                          "press Refresh."}
    if not sys.platform.startswith("linux"):
        return {"ok": False, "installed": False,
                "reason": "This setup is Linux-only (usbmuxd). macOS "
                          "drives QuickTime mode in its own usbmuxd — "
                          "just press Start QuickTime."}
    script = str(VALERIA_USBMUX_SETUP_SCRIPT)
    if not Path(script).is_file():
        return {"ok": False, "installed": False,
                "reason": "Setup script not found next to the backend "
                          "(expected scripts/setup-valeria-linux.sh). "
                          "Full guide: " + VALERIA_LINUX_SETUP_URL,
                "command": VALERIA_LINUX_SETUP_URL}
    _usbmux_setup_running = True
    try:
        try:
            proc = subprocess.run(
                ["bash", script],
                capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return {"ok": False, "installed": False,
                    "reason": f"USB setup timed out after {timeout_s}s — "
                              "run in a terminal where you can watch it: "
                              + VALERIA_USBMUX_SETUP_COMMAND,
                    "command": VALERIA_USBMUX_SETUP_COMMAND}
        except OSError as e:
            return {"ok": False, "installed": False,
                    "reason": str(e), "command": VALERIA_USBMUX_SETUP_COMMAND}
        tail = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        tail = tail[-2000:] if len(tail) > 2000 else tail
        if proc.returncode == 3:
            return {"ok": False, "installed": False,
                    "reason": "That step needs root and there is no "
                              "terminal to type the sudo password into. "
                              "Re-run it yourself (the build is already "
                              "done, so it goes straight to install): "
                              + VALERIA_USBMUX_SETUP_COMMAND,
                    "log": tail, "command": VALERIA_USBMUX_SETUP_COMMAND}
        # Trust the probe, not the exit code: only a running fork with
        # MODE=2 actually unblocks QuickTime.
        _probe_cache.pop("usbmuxd", None)
        state = usbmuxd_state()
        if proc.returncode == 0 and state.get("ready"):
            return {"ok": True, "installed": True,
                    "note": "USB setup done — replug the iPhone, tap "
                            "Trust, then press Start QuickTime.",
                    "log": tail}
        reason = ("USB setup did not finish"
                  + (f": {tail[-500:]}" if tail else "")
                  + ". Try in a terminal: " + VALERIA_USBMUX_SETUP_COMMAND
                  + ". Full guide: " + VALERIA_LINUX_SETUP_URL)
        return {"ok": False, "installed": False, "reason": reason,
                "log": tail, "command": VALERIA_USBMUX_SETUP_COMMAND}
    finally:
        _usbmux_setup_running = False


def airplay_status(
        which: Callable[[str], str | None] | None = None) -> dict:
    """Receiver state *and* what this host still needs to run one."""
    which = which or _default_which
    running = _airplay.alive()
    have_uxplay = _which_soft(which, "uxplay") is not None
    avahi = avahi_state()
    hint = uxplay_install_hint(which)
    needs: list[str] = []
    if not have_uxplay:
        needs.append(f"Install the receiver: {hint}")
    if avahi == "stopped":
        needs.append(f"Start the mDNS daemon: {AVAHI_START_HINT}")
    embedded = running and _airplay_embedded
    return {
        "running": running,
        "name": "freetunes" if running else "",
        "howto": AIRPLAY_HOWTO,
        "embedded": embedded,
        "stream_url": "/screen/airplay/stream" if embedded else "",
        "uxplay": have_uxplay,
        "avahi": avahi,
        "ready": have_uxplay and avahi != "stopped",
        "needs": needs,
        "install_hint": hint,
        "avahi_hint": AVAHI_START_HINT,
        "log": _airplay.tail(400) if running else "",
    }


AIRPLAY_HOWTO = ("iPhone Control Center -> Screen Mirroring -> freetunes "
                 "(same Wi-Fi on both)")


def airplay_start(which: Callable[[str], str | None] = _default_which,
                  embed: bool = True) -> dict:
    """Start a managed `uxplay` AirPlay receiver.

    ``embed`` (the default) renders the mirror into freetunes' own page
    instead of uxplay's floating desktop window; pass False to get the
    standalone window back (useful for full resolution or when GStreamer
    lacks the JPEG elements).
    """
    global _airplay_embedded
    if _mock_env():
        return {"ok": False, "running": False,
                "reason": "Mock mode — AirPlay needs real Wi-Fi + uxplay."}
    if _airplay.alive():
        return {"ok": True, "running": True, "name": "freetunes",
                "embedded": _airplay_embedded, "howto": AIRPLAY_HOWTO}
    binary = _which_soft(which, "uxplay")
    if not binary:
        hint = uxplay_install_hint(which)
        return {"ok": False, "running": False,
                "reason": f"No uxplay on this computer — {hint}",
                "fix": hint}
    if avahi_state() == "stopped":
        # uxplay would start and publish to nobody: the phone finds the
        # receiver over mDNS, so this is a refusal, not a warning.
        return {"ok": False, "running": False,
                "reason": "The mDNS daemon (avahi-daemon) is not running, so "
                          "the iPhone cannot discover the receiver. Start it "
                          f"with: {AVAHI_START_HINT}",
                "fix": AVAHI_START_HINT}
    cmd = [binary, "-n", "freetunes"]
    if embed:
        cmd += ["-vs", airplay_sink()]
    try:
        _airplay.spawn(cmd)
    except OSError as e:
        return {"ok": False, "running": False, "reason": str(e)}
    _airplay_embedded = embed
    time.sleep(1.5)
    if not _airplay.alive():
        tail = _airplay.tail(400)
        airplay_stop()
        return {"ok": False, "running": False,
                "reason": ("uxplay exited at once. " + tail).strip()}
    return {"ok": True, "running": True, "name": "freetunes",
            "embedded": embed, "howto": AIRPLAY_HOWTO,
            "log": _airplay.tail(400)}


def airplay_stop() -> dict:
    global _airplay_embedded
    _airplay_embedded = False
    _airplay.stop()
    return {"ok": True, "running": False}


_screen: ScreenService | None = None


def get_screen() -> ScreenService:
    """Process-wide service; mock mode forces placeholder-only shots."""
    global _screen
    if _screen is None:
        _screen = ScreenService(mock=_mock_env())
    return _screen
