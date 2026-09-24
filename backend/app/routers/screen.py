from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse

import asyncio
import time

from ..services.devices import get_service
from ..services.screen import (
    airplay_frames,
    shutting_down,
    airplay_start,
    airplay_status,
    airplay_stop,
    get_screen,
    hd_start,
    hd_status,
    hd_stop,
    valeria_install,
    valeria_start,
    valeria_status,
    valeria_stop,
    valeria_usbmux_setup,
)

router = APIRouter(tags=["screen"])


def _device_ctx(udid: str) -> tuple[str, bool, str]:
    """Resolve (udid, trusted, ios_version) from the live device list."""
    devs = get_service().list_devices()
    if not devs:
        return udid or "mock-udid", False, ""
    if not udid:
        d = devs[0]
        return d.udid, d.trusted, d.ios_version
    for d in devs:
        if d.udid == udid:
            return d.udid, d.trusted, d.ios_version
    d = devs[0]
    return d.udid, d.trusted, d.ios_version


@router.get("/screen/status")
def screen_status(udid: str = Query("")) -> dict:
    """Which live-screen paths work right now + what setup is missing."""
    real_udid, trusted, ios = _device_ctx(udid)
    return get_screen().status(real_udid, trusted=trusted, ios_version=ios)


@router.get("/screen/shot")
def screen_shot(udid: str = Query(""),
                download: bool = Query(False)) -> Response:
    """One live PNG frame (or a clearly-marked placeholder in mock mode).

    `X-Screen-Live: 1` means real iPhone pixels; `0` means placeholder.
    """
    real_udid, _, _ = _device_ctx(udid)
    data, media, live = get_screen().take_shot(real_udid)
    headers = {"X-Screen-Live": "1" if live else "0"}
    if download:
        headers["Content-Disposition"] = \
            'attachment; filename="iphone-screen.png"'
    return Response(content=data, media_type=media, headers=headers)


@router.get("/screen/stream")
async def screen_stream(request: Request,
                        udid: str = Query(""),
                        fps: float = Query(2.0, ge=0.5, le=5.0),
                        quality: int = Query(70, ge=30, le=90),
                        width: int = Query(720, ge=320, le=1600)) -> StreamingResponse:
    """MJPEG screenshot polling for an <img> tag (1-5 fps, view-only).

    This is the compatibility path — full-rate HD lives at /screen/hd
    (pymobiledevice3 serve-web) and over AirPlay via uxplay. The loop
    stops the moment the browser goes away, and backs off to one attempt
    per ~8 s while shots fail so a misconfigured phone is not hammered.
    ``width`` caps the frame's long edge (default 720): the phone
    delivers 1170x2532 PNGs but the browser shows them ~330 px wide,
    so downscaling before JPEG-encoding saves encode, transfer, and
    decode time on every frame. The ~2 s DVT capture itself is fixed
    (see COMPATIBILITY.md); the wait here is counted *after* the
    capture so the requested fps is the actual ceiling, not fps/2.
    """
    real_udid, _, _ = _device_ctx(udid)
    svc = get_screen()
    interval = 1.0 / max(0.5, min(float(fps or 2.0), 5.0))

    async def gen():
        while True:
            if shutting_down() or await request.is_disconnected():
                break
            start = time.monotonic()
            chunk, live = await asyncio.to_thread(
                svc.make_frame, real_udid, quality, width)
            yield chunk
            wait = (interval if live else max(interval, 8.0)) - (
                time.monotonic() - start)
            if wait > 0:
                await asyncio.sleep(wait)

    return StreamingResponse(
        gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.post("/screen/setup/reveal-developer-mode")
def setup_reveal_devmode(udid: str = Query("")) -> dict:
    """Make the Developer Mode row appear in the iPhone's Settings.

    No reboot, no data touched — on a phone that never met a developer
    tool the row is simply absent, so the checklist cannot be followed.
    """
    real_udid, _, _ = _device_ctx(udid)
    return get_screen().reveal_devmode(real_udid)


@router.post("/screen/setup/enable-developer-mode")
def setup_enable_devmode(udid: str = Query("")) -> dict:
    """Turn Developer Mode on — **the iPhone restarts** and then asks."""
    real_udid, _, _ = _device_ctx(udid)
    return get_screen().enable_devmode(real_udid)


@router.post("/screen/setup/mount-ddi")
def setup_mount_ddi(udid: str = Query("")) -> dict:
    """Mount the personalized DeveloperDiskImage (gone after each reboot)."""
    real_udid, _, _ = _device_ctx(udid)
    return get_screen().mount_ddi(real_udid)


@router.get("/screen/hd")
def hd_state() -> dict:
    """Supervised HEVC-over-USB server state (pymobiledevice3 serve-web)."""
    return hd_status()


@router.post("/screen/hd/start")
def hd_begin(udid: str = Query("")) -> dict:
    """Start the HD server; returns the iframe URL on success."""
    real_udid, _, _ = _device_ctx(udid)
    return hd_start(real_udid)


@router.post("/screen/hd/stop")
def hd_end() -> dict:
    return hd_stop()


@router.get("/screen/valeria")
def valeria_state() -> dict:
    """Supervised QuickTime-USB (Valeria H.264) server state."""
    return valeria_status()


@router.post("/screen/valeria/start")
def valeria_begin(udid: str = Query("")) -> dict:
    """Start the QuickTime-USB server; returns the iframe URL on success.

    Faster preview than MJPEG polling (30-60 fps H.264, no Developer Mode)
    — the same protocol QuickTime Player uses. Needs a trusted iPhone
    (no Developer Mode, no developer image). Fights usbmuxd for USB, so
    failures name the USB claim + presentation-mode caveats.
    """
    real_udid, trusted, _ = _device_ctx(udid)
    return valeria_start(real_udid, trusted=trusted)


@router.post("/screen/valeria/stop")
def valeria_end() -> dict:
    return valeria_stop()


@router.post("/screen/valeria/install")
def valeria_install_begin() -> dict:
    """One-click install of the Valeria fork + aiohttp/av (pip, ~1-3 min).

    Runs in the backend's own interpreter so the supervised server sees
    the fork. Returns ok/log on success, reason+command when manual
    install is still needed.
    """
    return valeria_install()


@router.post("/screen/valeria/usbmux-setup")
def valeria_usbmux_setup_begin() -> dict:
    """One-click Linux USB setup for QuickTime (usbmuxd fork, ~5-10 min).

    Builds the fork and switches the systemd service to it with
    USBMUXD_DEFAULT_DEVICE_MODE=2. The privileged steps need root: with
    no terminal for the sudo password this returns the exact command to
    run yourself instead of hanging.
    """
    return valeria_usbmux_setup()


@router.get("/screen/airplay")
def airplay_state() -> dict:
    """Managed uxplay AirPlay receiver state (Wi-Fi, own window)."""
    return airplay_status()


@router.post("/screen/airplay/start")
def airplay_begin(embed: bool = Query(True)) -> dict:
    """Start the receiver; `embed=false` gives uxplay its own window back."""
    return airplay_start(embed=embed)


@router.get("/screen/airplay/stream")
async def airplay_stream(request: Request) -> Response:
    """The AirPlay mirror as MJPEG, for an <img> inside the page.

    uxplay already muxes `boundary=frame` multipart JPEG onto a loopback
    port, so this only relays bytes and stops when the browser leaves.
    """
    state = airplay_status()
    if not state.get("embedded"):
        return Response(
            content=("The AirPlay receiver is not running in embedded "
                     "mode — press Start AirPlay receiver."),
            status_code=503, media_type="text/plain")

    async def gen():
        try:
            async for chunk in airplay_frames():
                # None is an idle tick: nothing to send, but still the
                # moment to notice the browser is gone. Without it this
                # task outlives the tab and stalls uvicorn's shutdown.
                if chunk is not None:
                    yield chunk
                if shutting_down() or await request.is_disconnected():
                    break
        except (OSError, asyncio.CancelledError):
            return

    return StreamingResponse(
        gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.post("/screen/airplay/stop")
def airplay_end() -> dict:
    return airplay_stop()
