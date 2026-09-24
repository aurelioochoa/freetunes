import asyncio
import json
import shutil

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..services.devices import get_service
from ..services.diagnostics import (
    get_diagnostics,
    is_relay_banner,
    matched_hint,
    parse_log_process,
    verification_for,
)

router = APIRouter(tags=["diagnostics"])


@router.get("/diagnostics/verification")
def verification(udid: str = Query("")) -> dict:
    devs = get_service().list_devices()
    dev = next((d for d in devs if not udid or d.udid == udid), None)
    if dev is None:
        return verification_for(udid or "mock-udid", "").model_dump()
    return verification_for(dev.udid, dev.model_number, dev.serial).model_dump()


@router.get("/diagnostics/crashes")
def crashes(udid: str = Query("")) -> list[dict]:
    udid = _resolve_udid(udid)
    return [c.model_dump() for c in get_diagnostics().crashes(udid)]


@router.get("/diagnostics/crashes/{filename}")
def crash_detail(filename: str, udid: str = Query("")) -> dict:
    """Truncated local preview of one crash file.

    Parsed on this computer from the last `idevicecrashreport -k` copy
    (max 200 lines / 20KB). Never uploads anything; 404 on unknown names
    or path-traversal attempts.
    """
    udid = _resolve_udid(udid)
    detail = get_diagnostics().crash_detail(udid, filename)
    if detail is None:
        raise HTTPException(status_code=404, detail="Crash report not found")
    return detail


@router.get("/diagnostics/syslog")
def syslog(udid: str = Query(""), lines: int = Query(200),
           q: str = Query(""), level: str = Query("all"),
           window: float = Query(3.0, ge=1.0, le=8.0)) -> dict:
    udid = _resolve_udid(udid)
    return get_diagnostics().syslog(udid, lines, q=q, level=level,
                                    window=window)


@router.get("/diagnostics/syslog/stream")
async def syslog_stream(request: Request, udid: str = Query(""),
                        q: str = Query(""),
                        level: str = Query("all"),
                        limit: int | None = Query(None, ge=1, le=200)) -> StreamingResponse:
    """Real-time device log as Server-Sent Events.

    Each event is `data: {"text": ..., "level": ..., "proc": ...}`.
    Mock mode (or a missing idevicesyslog) emits an honest sample ticker
    so the web log viewer is testable without a phone; a real phone
    streams `idevicesyslog` output line-by-line until the browser leaves.
    Tools present but no phone connected yields hello with live:false and
    an explanatory error event — never fake sample rows. Filtering (`q`,
    `level`) is applied server-side, same rules as `/diagnostics/syslog`.
    `limit` caps the mock ticker (debugging and tests); a real phone
    always streams until disconnect.
    """
    udid = _resolve_udid(udid)
    needle = (q or "").strip().lower()
    lvl = (level or "all").lower()
    if lvl not in ("all", "error", "warn", "info"):
        lvl = "all"

    def _wanted(text: str) -> dict | None:
        # Relay banners (`[connected:UDID]`) are protocol, not phone logs.
        if is_relay_banner(text):
            return None
        lv, hint = matched_hint(text)
        if lvl == "warn" and lv not in ("warn", "error"):
            return None
        if lvl in ("error", "info") and lv != lvl:
            return None
        if needle and needle not in text.lower():
            return None
        return {"text": text, "level": lv, "proc": parse_log_process(text), "match": hint}

    async def gen():
        # Hello event: the viewer shows LIVE vs SAMPLE from this.
        diag = get_diagnostics()
        mock_mode = (not bool(diag.available)
                     or shutil.which("idevicesyslog") is None)
        is_placeholder = udid in ("", "mock-udid")
        # A placeholder UDID never addresses a real phone: `idevicesyslog
        # -u mock-udid` just waits for a device that never appears, so
        # never probe tools with it.
        live = (not is_placeholder and not mock_mode)
        yield f"event: hello\ndata: {json.dumps({'udid': udid, 'live': live})}\n\n"
        if is_placeholder and not mock_mode:
            # Tools present but no iPhone: honest empty, never fake rows.
            yield (f"event: error\ndata: {json.dumps({'message': 'No iPhone connected'})}\n\n")
            return
        if not live:
            i = 0
            while limit is None or i < limit:
                if await request.is_disconnected():
                    break
                line = (f"Sep 18 12:{i // 60:02d}:{i % 60:02d} iPhone "
                        f"sample-process[{100 + (i % 50)}]: freetunes live sample {i}")
                if i % 9 == 3:
                    line += " — thermal warn: throttled for 2s"
                if i % 17 == 7:
                    line += " — backupd error: snapshot failed, retrying"
                row = _wanted(line)
                if row is not None:
                    yield f"data: {json.dumps(row)}\n\n"
                i += 1
                await asyncio.sleep(0.5)
            return
        # Real phone: stream idevicesyslog stdout line-by-line.
        try:
            proc = await asyncio.create_subprocess_exec(
                "idevicesyslog", "-u", udid,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL)
        except (OSError, NotImplementedError) as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
            return
        assert proc.stdout is not None
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    raw = await asyncio.wait_for(proc.stdout.readline(), 1.0)
                except asyncio.TimeoutError:
                    # Heartbeat keeps proxies/EventSource alive on quiet phones.
                    yield ": ping\n\n"
                    continue
                if not raw:
                    break
                text = raw.decode(errors="replace").rstrip("\r\n")
                if not text:
                    continue
                row = _wanted(text)
                if row is not None:
                    yield f"data: {json.dumps(row)}\n\n"
        finally:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/diagnostics/summary")
def summary(udid: str = Query("")) -> dict:
    resolved = _resolve_udid(udid)
    devs = get_service().list_devices()
    dev = next((d for d in devs if d.udid == resolved), None)
    target = dev.udid if dev else "mock-udid"
    model = dev.model_number if dev else ""
    serial = dev.serial if dev else ""
    return get_diagnostics().health(target, model, serial)


def _resolve_udid(udid: str) -> str:
    """Map a requested UDID to a connected phone, else the mock placeholder.

    Empty means "first phone, else mock". A stale/explicit UDID that matches
    no connected phone maps to mock so tools are never probed with an ID
    that makes `idevicesyslog` wait ~8 s for a device that never appears
    (the Diagnostics-stuck-on-loading bug with no iPhone plugged in).
    """
    udid = (udid or "").strip()
    devs = get_service().list_devices()
    if not devs:
        return "mock-udid"
    if not udid:
        return devs[0].udid
    if any(d.udid == udid for d in devs):
        return udid
    return "mock-udid"


def _first_udid() -> str:
    devs = get_service().list_devices()
    return devs[0].udid if devs else "mock-udid"
