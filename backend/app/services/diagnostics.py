"""Diagnostics: verification-lite, crash reports, syslog tail.

All FOSS via libimobiledevice CLI. Mock mode returns honest samples so
the UI is testable without a phone.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field

from ..models import CrashItem, VerificationCheck, VerificationReport
from .devices import SubprocessRunner

MODEL_KIND = {
    "M": "retail-new",
    "F": "refurbished",
    "N": "replacement",
    "P": "personalized",
}

KIND_BLURB = {
    "retail-new": "Sold new at retail. First letter M.",
    "refurbished": "Refurbished by Apple. First letter F — worth a closer look at battery and history.",
    "replacement": "Replacement unit from Apple service. First letter N.",
    "personalized": "Engraved / personalized at purchase. First letter P.",
    "unknown": "Could not tell from the model number — unplug/replug or check Settings → General → About.",
}

ERROR_HINTS = ("error", "fault", "failed", "crash", "panic", "exception", "denied", "timeout", "corrupt")
WARN_HINTS = ("warn", "notice", "throttle", "low", "deprecat", "retry", "slow", "thermal")

#: Human explanation per classification keyword. Single source of truth
#: for the web log viewer's tooltips (`frontend/src/logLevels.ts` mirrors
#: the one-liners) and for docs/DIAGNOSTICS.md "filter levels & keywords".
#: Keep each value to one short sentence — it renders inside a `title`
#: tooltip. Longer what/action texts live in logLevels.ts only.
ERROR_HINT_INFO = {
    "error": "Generic failure word; also matches Apple's own <Error> tag (os_log_error, always persisted).",
    "fault": "Apple’s most serious level (os_log_fault): a component reporting itself as broken, with extra diagnostics captured.",
    "failed": "An operation ran and finished as a failure — often retryable.",
    "crash": "A process died abnormally — iOS’s ReportCrash writes a .ips file for it.",
    "panic": "Kernel panic — the whole device went down or nearly did; always worth opening.",
    "exception": "Unhandled exception thrown by app or system code (e.g. NSException).",
    "denied": "Sandbox/permission refusal — iOS blocked something an app tried (Apple documents these as sandbox violations).",
    "timeout": "Timed out waiting — network, lock or IPC reply that never came.",
    "corrupt": "Corrupt data detected — file, database or cache header that does not parse.",
}

WARN_HINT_INFO = {
    "warn": "Generic caution word — including iOS low-memory (Jetsam) warnings.",
    "notice": "Matches Apple’s <Notice> tag — the default os_log level: routine, persisted chatter.",
    "throttle": "The device is deliberately slowing something down — power, thermal or policy.",
    "low": "Low resource — memory, disk, battery or signal. Memory pressure can end in Jetsam kills.",
    "deprecat": "Deprecated API in use — developer noise, harmless unless it is your app.",
    "retry": "The operation will be retried — transient by definition; loops are the problem.",
    "slow": "Slow operation — a performance hint, not a failure.",
    "thermal": "Thermal pressure — the device is warm and may throttle CPU, radio or charging.",
}

#: Human explanation per filter level. Mirrored in logLevels.ts.
#: Note: these are freetunes' own filters, NOT Apple's os_log levels
#: (Debug < Info < Default/Notice < Error < Fault).
LEVEL_INFO = {
    "all": "Everything, unfiltered — start here to see the raw tail.",
    "warn": "Warnings AND errors — the best first question is “is something wrong?”.",
    "error": "Only errors — failures, the smallest and most serious slice.",
    "info": "Routine chatter with no error/warn keyword — the largest, noisiest slice.",
}

#: Human explanation per crash kind. Single source of truth for the web
#: crash viewer's pills (`frontend/src/crashLevels.ts` mirrors the
#: one-liners) and for docs/DIAGNOSTICS.md "How freetunes classifies crashes".
#: Keep each value to one short sentence — it renders inside a `title`
#: tooltip. Longer what/action texts live in crashLevels.ts only.
#: Sources: Apple "Examining the fields in a crash report",
#: "Understanding the exception types in a crash report",
#: "Identifying high-memory use with Jetsam event reports",
#: "Interpreting the JSON format of a crash report".
CRASH_KIND_INFO = {
    "crash": "App or system process crash (.ips) — ReportCrash wrote a file for a dead process.",
    "jetsam": "Jetsam / low-memory kill — iOS terminated the process under memory pressure, not a bug in that app alone.",
    "panic": "Kernel panic — the whole device went down or nearly did; always worth opening.",
    "unknown": "Unclassified crash file — name has no crash-ish extension.",
}

#: Common exception / termination patterns, for docs + future tooltips.
#: Keys are substring hints matched against `exception` + `reason`.
CRASH_PATTERN_INFO = {
    "EXC_CRASH (SIGABRT)": "Abort signal — unhandled language exception, failed assertion, or abort() called.",
    "EXC_CRASH (SIGKILL)": "Killed by the system — watchdog, memory limit, or force-quit. Check the termination reason.",
    "EXC_BAD_ACCESS (SIGSEGV)": "Segmentation fault — invalid or out-of-bounds memory address.",
    "EXC_BAD_ACCESS (SIGBUS)": "Bus error — misaligned address or pointer-authentication failure.",
    "EXC_BREAKPOINT (SIGTRAP)": "Breakpoint trap — violated requirement or Swift runtime trap.",
    "EXC_RESOURCE": "Resource limit exceeded — CPU time, memory, or I/O (read the subtype).",
    "0x8badf00d": "Watchdog kill — the app hung (SpringBoard namespace, ate bad food).",
    "per-process-limit": "Jetsam reason — the process crossed its own resident-memory limit.",
    "vm-pageshortage": "Jetsam reason — system-wide free-page shortage; background deaths protect the foreground app.",
    "jettisoned": "Jetsam reason — the system jettisoned the process for another reason (not a per-process or page-shortage kill).",
}

#: Live-stream lines that are classified correctly (they *are* errors) but
#: are known-benign OS chatter — excluded only from the health gate, never
#: from the counts or the log view itself.
BENIGN_NOISE_HINTS = (
    "decode: mismatch",  # constant kernel IOSurface spam on iOS 26
)


def _is_benign_noise(line: str) -> bool:
    low = (line or "").lower()
    return any(h in low for h in BENIGN_NOISE_HINTS)


#: Placeholder UDIDs that never address a real phone. Probing tools with
#: one (`idevicesyslog -u mock-udid`) makes the relay wait for a device
#: that will never appear (~8 s per call), which is what left Diagnostics
#: on "loading" with no iPhone plugged in. Never probe tools with these —
#: serve mock sample in mock mode, honest empty when tools are present
#: but no phone is connected (like Files/Photos: empty, not fake).
MOCK_UDIDS = ("", "mock-udid")


def _is_mock_udid(udid: str) -> bool:
    return (udid or "") in MOCK_UDIDS


def verification_for(udid: str, model_number: str, serial: str = "") -> VerificationReport:
    prefix = (model_number or "").strip()[:1].upper()
    kind = MODEL_KIND.get(prefix, "unknown")
    suspect = kind in ("refurbished", "replacement")
    details = [
        f"Model number {model_number or 'unknown'} → {kind}.",
        "F = refurbished by Apple, N = replacement device, M = retail new, P = engraved.",
        "Storage-upgrade check needs a physical open-up; AFC vs lockdown mismatch only hints at reporting bugs (see COMPATIBILITY.md #1572).",
    ]
    if serial:
        details.append(f"Serial {serial[:3]}… present (full serial never leaves this computer).")

    if kind == "retail-new":
        summary = "Looks like a retail-new iPhone — no refurbishment flag from the model number."
    elif kind == "refurbished":
        summary = "Model number starts with F — refurbished by Apple. Not a defect on its own, but check battery health and backup age."
    elif kind == "replacement":
        summary = "Model number starts with N — a service replacement unit. Pair it with a fresh backup."
    elif kind == "personalized":
        summary = "Personalized (engraved) retail unit — same as retail-new for diagnostics."
    else:
        summary = "Model number unreadable — connect and trust the iPhone, then re-check."

    checks = [
        VerificationCheck(
            label="Model origin",
            status="warn" if suspect else ("pass" if kind != "unknown" else "info"),
            detail=KIND_BLURB.get(kind, KIND_BLURB["unknown"]),
        ),
        VerificationCheck(
            label="Serial visible",
            status="pass" if serial else "info",
            detail=("Serial readable over lockdown; only the first 3 characters are shown, nothing leaves this computer."
                    if serial else "Serial not readable yet — trust the iPhone and re-check."),
        ),
        VerificationCheck(
            label="Storage reporting",
            status="info",
            detail="iOS 17+ lockdown over-reports free space (upstream #1572); freetunes prefers AFC FSFreeBytes when available.",
        ),
    ]
    return VerificationReport(udid=udid, model_number=model_number or "",
                              kind=kind, refurbished_suspect=suspect,
                              details=details, checks=checks, summary=summary)


_CRASH_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def parse_crash(filename: str) -> tuple[str, str]:
    """Split `SpringBoard-2026-09-10.ips` → (`SpringBoard`, `2026-09-10`)."""
    base = (filename or "").rsplit("/", 1)[-1]
    stem = re.sub(r"\.(ips|crash|log|txt)$", "", base, flags=re.IGNORECASE)
    m = _CRASH_DATE.search(stem)
    date = m.group(1) if m else ""
    app = stem
    if date:
        app = stem[:m.start()].rstrip("-_ .") or stem
    # `Sample-Crash-2026-09-18` → `Sample-Crash`
    app = app or stem
    return app, date


def sanitize_crash_filename(filename: str) -> str:
    """Basename-only guard for the detail endpoint (blocks path traversal)."""
    base = (filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if not base or base in (".", "..") or ".." in base or "/" in base:
        return ""
    # Only crash-ish extensions are servable.
    if not re.search(r"\.(ips|crash|log|txt)$", base, flags=re.IGNORECASE):
        return ""
    return base


def classify_crash_kind(filename: str) -> str:
    """panic | jetsam | crash | unknown — from the filename alone.

    - panic: kernel panics (`panic-full`, `panic-`) and unexpected
      reboots without a panic (`ResetCounter` — bug_type 115). Both mean
      the whole device went down, never just one app.
    - jetsam: low-memory kills (`JetsamEvent`, `LowMemory`, `low-memory`).
    - crash: everything else with a crash-ish extension, including
      system maintenance reports (`OTAUpdate`, `softwareupdated`) and
      thermal/stackshot snapshots. The name guide in
      `frontend/src/crashLevels.ts` explains what each one means.
    """
    low = (filename or "").lower()
    if ("panic" in low or "resetcounter" in low or "reset-counter" in low
            or "reset_count" in low or "reset-count" in low):
        return "panic"
    if ("jetsam" in low or "lowmemory" in low or "low-memory" in low
            or "jsevent" in low):
        return "jetsam"
    if re.search(r"\.(ips|crash|log|txt)$", low):
        return "crash"
    return "unknown"


#: bug_type → kind override. The filename decides the kind first
#: (offline, no file read); when the header parses, the real log type
#: wins. Sources: Apple "Interpreting the JSON format of a crash
#: report" (309 crash, 288 stackshot) + "Identifying high-memory use
#: with Jetsam event reports" (298 Jetsam) + community-observed
#: panic-full (210) and ResetCounter (115) first lines.
BUG_TYPE_KIND = {
    "309": "crash",
    "298": "jetsam",
    "288": "crash",  # stackshot snapshot — diagnostic, not a fatal crash
    "210": "panic",  # panic-full
    "115": "panic",  # ResetCounter — reboot without a panic string
    "305": "crash",  # AccessoryCrash
    "202": "crash",  # CPU resource (EXC_RESOURCE)
    "142": "crash",  # disk-writes resource
    "145": "crash",  # disk-writes resource variant seen in the wild
}


def _try_json_object(s: str) -> dict | None:
    try:
        doc = json.loads(s)
    except (ValueError, TypeError):
        return None
    return doc if isinstance(doc, dict) else None


def _format_termination(term: dict) -> str:
    """Human line from a crash-report `termination` object.

    Real keys per Apple "Interpreting the JSON format": namespace, code
    (decimal — shown hex, e.g. 2343432205 → 0x8badf00d), indicator,
    byProc/byPid, flags. Legacy `reason`/`description` still honoured.
    """
    if not isinstance(term, dict):
        return str(term or "")[:256]
    legacy = term.get("reason") or term.get("description") or ""
    if isinstance(legacy, str) and legacy.strip():
        return legacy.strip()[:256]
    ns = str(term.get("namespace") or "").strip()
    code = term.get("code")
    indicator = str(term.get("indicator") or "").strip()
    by_proc = str(term.get("byProc") or term.get("by_proc") or "").strip()
    by_pid = term.get("byPid", term.get("by_pid", ""))
    code_s = ""
    if isinstance(code, bool):
        pass
    elif isinstance(code, int):
        try:
            code_s = f"0x{code & 0xFFFFFFFF:x}"
        except (ValueError, TypeError):
            code_s = str(code)
    elif isinstance(code, str) and code.strip():
        code_s = code.strip()
        # Decimal string from JSON → hex for readability (0x8badf00d style).
        if re.fullmatch(r"\d+", code_s):
            try:
                code_s = f"0x{int(code_s) & 0xFFFFFFFF:x}"
            except ValueError:
                pass
    parts: list[str] = []
    if ns and code_s:
        parts.append(f"Namespace {ns}, Code {code_s}")
    elif ns:
        parts.append(f"Namespace {ns}")
    elif code_s:
        parts.append(f"Code {code_s}")
    if indicator:
        parts.append(indicator)
    if by_proc:
        parts.append(f"by {by_proc}" + (f"[{by_pid}]" if by_pid != "" and by_pid is not None else ""))
    line = " — ".join(p for p in parts if p).strip()
    return line[:256]


def _format_jetsam_reason(report: dict) -> str:
    """One line from a JetsamEvent report (bug_type 298).

    Jetsam reports carry no exception/backtrace — just a device-wide
    process table. Only the jettisoned process has `reason`
    (per-process-limit, vm-pageshortage, vnode-limit, highwater,
    fc-thrashing, jettisoned). Report victim + largestProcess so a
    victim that is not the cause reads correctly. Sources: Apple
    "Identifying high-memory use with Jetsam event reports".
    """
    procs = report.get("processes")
    largest = str(report.get("largestProcess") or "").strip()
    victim = ""
    vreasons: list[str] = []
    if isinstance(procs, list):
        for p in procs:
            if not isinstance(p, dict):
                continue
            r = str(p.get("reason") or "").strip()
            if r:
                vreasons.append((str(p.get("name") or "").strip(), r,
                                 p.get("rpages")))
        # Usually exactly one process carries a reason; join a few max.
    if vreasons:
        name, rsn, rpages = vreasons[0]
        extra = ""
        if isinstance(rpages, int) and rpages > 0:
            mem = report.get("memoryStatus") or {}
            ps = mem.get("pageSize") if isinstance(mem, dict) else None
            if isinstance(ps, int) and ps > 0:
                try:
                    mb = rpages * ps / (1024 * 1024)
                    extra = f" ({rpages} pages × {ps} B ≈ {mb:.0f} MB)"
                except (ValueError, TypeError, OverflowError):
                    extra = f" ({rpages} pages)"
            else:
                extra = f" ({rpages} pages)"
        victim = f"Jetsam {rsn} — {name or 'unknown process'}{extra}"
        if largest and largest not in (name or ""):
            victim += f" (largest: {largest})"
        if len(vreasons) > 1:
            victim += f" (+{len(vreasons) - 1} more)"
        return victim[:256]
    if largest:
        return f"Jetsam event — largest process: {largest} (no per-process reason parsed)"[:256]
    return ""


def _format_panic_reason(report: dict, text: str) -> str:
    """First line of `panicString` (bug_type 210), truncated."""
    ps = report.get("panicString") if isinstance(report, dict) else None
    if isinstance(ps, str) and ps.strip():
        first = ps.strip().splitlines()[0].strip()
        return first[:256]
    m = re.search(r"panic\s*\(.*?\).*", text or "", flags=re.IGNORECASE)
    if m:
        return m.group(0).strip()[:256]
    return ""


def _format_reset_reason(report: dict, text: str) -> str:
    """ResetCounter (bug_type 115): reset / boot-failure counts."""
    bits: list[str] = []
    def _grab(d: dict, *keys: str) -> str:
        for k in keys:
            v = d.get(k)
            if v is not None and v != "":
                return str(v).strip()
        return ""
    if isinstance(report, dict):
        rc = _grab(report, "Reset count", "ResetCount", "resetCount", "reset_count")
        bf = _grab(report, "Boot failure count", "BootFailureCount",
                   "bootFailureCount", "boot_failure_count")
        faults = _grab(report, "Boot faults", "BootFaults", "bootFaults")
        if rc:
            bits.append(f"Reset count: {rc}")
        if bf:
            bits.append(f"Boot failure count: {bf}")
        if faults:
            bits.append(f"Boot faults: {faults}")
    if not bits and text:
        m = re.search(r"Reset count:\s*([^\r\n]+)", text)
        if m:
            bits.append(f"Reset count: {m.group(1).strip()}")
        m = re.search(r"Boot failure count:\s*([^\r\n]+)", text)
        if m:
            bits.append(f"Boot failure count: {m.group(1).strip()}")
        m = re.search(r"Boot faults:\s*([^\r\n]+)", text)
        if m:
            bits.append(f"Boot faults: {m.group(1).strip()}")
    return "; ".join(bits)[:256]


def _format_os_version(meta: dict | None, report: dict | None) -> str:
    """Best-effort OS string from metadata `os_version` or report body.

    Metadata carries e.g. "iPhone OS 26.0.1 (23A341)". The report body
    carries either `osVersion: {train, build}` (crash 309) or `build:
    "iPhone OS …"` (Jetsam 298 / panic 210). Legacy single-JSON
    `os_version` string/dict still honoured for tests and old files.
    """
    for d in (meta, report):
        if isinstance(d, dict):
            v = d.get("os_version")
            if isinstance(v, str) and v.strip():
                return v.strip()[:64]
    if isinstance(report, dict):
        osv = report.get("osVersion") or report.get("osversion")
        if isinstance(osv, dict):
            train = str(osv.get("train") or osv.get("version") or "").strip()
            build = str(osv.get("build") or "").strip()
            combo = f"{train} ({build})".strip() if (train or build) else ""
            # Avoid "(build)" / "train ()" artefacts.
            if train and build and build not in train:
                combo = f"{train} ({build})"
            elif train:
                combo = train
            elif build:
                combo = build
            if combo and combo not in ("()", "( )"):
                return combo[:64]
        elif isinstance(osv, str) and osv.strip():
            return osv.strip()[:64]
        b = report.get("build")
        if isinstance(b, str) and b.strip():
            return b.strip()[:64]
    return ""


def parse_crash_header_text(text: str) -> dict:
    """Extract exception/reason/os_version (+bug_type) from .ips text.

    Real .ips files since iOS 15 are TWO JSON objects (Apple
    "Interpreting the JSON format of a crash report"): line 1 is IPS
    metadata (`bug_type`, `os_version`, `name`, …), the remainder is
    the report (`exception {type, signal}`, `termination {namespace,
    code, indicator, …}`, `osVersion {train, build}` for bug_type 309;
    `processes[] + largestProcess + memoryStatus.pageSize` for Jetsam
    298; `panicString` for panic-full 210; reset counts for
    ResetCounter 115). The old single-JSON shape and legacy
    `.crash`-text greps still work as fallback. Fail-soft: "" fields
    when unreadable. Everything is local; nothing is uploaded.
    """
    out = {"exception": "", "reason": "", "os_version": "",
           "bug_type": "", "name": ""}
    if not text or not text.strip():
        return out
    stripped = text.strip()
    lines = stripped.splitlines()
    meta: dict | None = None
    report: dict | None = None
    # First non-empty line is the IPS metadata object in real files.
    first = ""
    for ln in lines:
        if ln.strip():
            first = ln.strip()
            break
    if first.startswith("{"):
        meta = _try_json_object(first)
        # Real IPS metadata always carries bug_type (309/298/210/115/…)
        # plus timestamp + incident_id. `os_version`/`name` alone are NOT
        # enough — legacy single-JSON report bodies also use `os_version`.
        if meta is not None and ("bug_type" in meta or (
                "timestamp" in meta and "incident_id" in meta)):
            rest = stripped[len(stripped) - len(stripped.lstrip()):]
            # Remainder after the first JSON line.
            nl = stripped.find("\n")
            rest = stripped[nl + 1:] if nl != -1 else ""
            if rest.strip().startswith("{"):
                # The report object can be large; 200KB cap keeps header
                # parsing cheap and never touches the thread dump tail.
                report = _try_json_object(
                    rest if len(rest) < 200000 else rest[:200000])
            if report is None:
                # Metadata-only file (or truncated copy): still useful
                # for OS + bug_type + name.
                pass
        else:
            meta = None
    if meta is None and report is None:
        # Single-JSON shape (unit tests, mocks, old files).
        single = _try_json_object(
            stripped if len(stripped) < 200000 else stripped[:200000])
        if single is not None:
            # Heuristic: metadata keys present without a second object →
            # treat as report for exception parsing, metadata for OS.
            report = single
            if any(k in single for k in ("bug_type", "timestamp",
                                         "incident_id")) and "exception" not in single \
                    and "termination" not in single and "processes" not in single \
                    and "panicString" not in single:
                meta = single
                report = None
    if not isinstance(meta, dict):
        meta = None
    if not isinstance(report, dict):
        report = None
    if meta is not None:
        bt = meta.get("bug_type")
        if bt is not None and str(bt).strip():
            out["bug_type"] = str(bt).strip()[:16]
        nm = meta.get("name")
        if isinstance(nm, str) and nm.strip():
            out["name"] = nm.strip()[:128]
    if report is not None and not out["bug_type"]:
        bt = report.get("bug_type")
        if bt is not None and str(bt).strip():
            out["bug_type"] = str(bt).strip()[:16]
    # --- exception: "TYPE (SIGNAL)" per Examining-the-fields mapping ---
    if report is not None:
        exc = report.get("exception")
        if isinstance(exc, dict):
            typ = str(exc.get("type") or "").strip()
            sig = str(exc.get("signal") or "").strip()
            if typ and sig:
                out["exception"] = f"{typ} ({sig})"[:128]
            elif typ:
                out["exception"] = typ[:128]
            elif sig:
                out["exception"] = sig[:128]
            else:
                # e.g. {"exception": "EXC_CRASH (SIGABRT)"} is handled
                # below via the str branch; dict with only `exception`
                # key mirrors the same shape.
                alt = exc.get("exception")
                if isinstance(alt, str) and alt.strip():
                    out["exception"] = alt.strip()[:128]
        elif isinstance(exc, str) and exc.strip():
            out["exception"] = exc.strip()[:128]
    # --- reason: termination → Jetsam → panic → reset → asi/legacy ---
    if report is not None:
        term = report.get("termination")
        if isinstance(term, (dict, str)) and term:
            formatted = _format_termination(term)  # type: ignore[arg-type]
            if formatted:
                out["reason"] = formatted
        if not out["reason"] and out["bug_type"] == "298":
            out["reason"] = _format_jetsam_reason(report)
        if not out["reason"] and (
                out["bug_type"] == "210" or "panicString" in report):
            out["reason"] = _format_panic_reason(report, stripped)
        if not out["reason"] and (
                out["bug_type"] == "115" or "Reset count" in report
                or "Boot failure count" in report):
            out["reason"] = _format_reset_reason(report, stripped)
        if not out["reason"]:
            # Jetsam/panic/reset shapes even when bug_type is missing
            # (truncated metadata, renamed files).
            jr = _format_jetsam_reason(report)
            if jr and ("processes" in report or "largestProcess" in report
                       or "memoryStatus" in report):
                out["reason"] = jr
        if not out["reason"] and "panicString" in report:
            out["reason"] = _format_panic_reason(report, stripped)
        if not out["reason"]:
            rr = _format_reset_reason(report, stripped)
            if rr and ("Reset count" in stripped or "Boot failure" in stripped):
                out["reason"] = rr
        if not out["reason"]:
            for k in ("termination_reason", "terminationReason", "reason"):
                v = report.get(k)
                if isinstance(v, str) and v.strip():
                    out["reason"] = v.strip()[:256]
                    break
        if not out["reason"]:
            # Application Specific Information, e.g. "abort() called"
            # (pycrashreport shows it as the headline for SIGABRT).
            asi = report.get("asi")
            if isinstance(asi, dict):
                for v in asi.values():
                    vals = v if isinstance(v, list) else [v]
                    for item in vals:
                        if isinstance(item, str) and item.strip():
                            out["reason"] = item.strip()[:256]
                            break
                    if out["reason"]:
                        break
    # --- os_version ---
    out["os_version"] = _format_os_version(meta, report)
    if report is not None and not out["os_version"]:
        # Legacy single-JSON dict shape {"os_version": {...}}.
        for k in ("os_version", "osVersion", "osversion"):
            if k == "os_version" and meta is not None:
                continue  # already checked above
            v = report.get(k)
            if isinstance(v, str) and v.strip():
                out["os_version"] = v.strip()[:64]
                break
            if isinstance(v, dict):
                train = str(v.get("train") or v.get("version") or "")
                build = str(v.get("build") or "")
                combo = f"{train} ({build})".strip() if (train or build) else ""
                if combo:
                    out["os_version"] = combo[:64]
                    break
    if not out["exception"] and not out["reason"] and not out["os_version"]:
        # Legacy .crash text fallback (Exception Type: / Termination
        # Reason: / OS Version:) — and last-resort greps for panic and
        # reset counters inside truncated copies.
        m = re.search(r"Exception Type:\s*([^\r\n]+)", stripped)
        if m:
            out["exception"] = m.group(1).strip()[:128]
        m = re.search(r"Termination Reason:\s*([^\r\n]+)", stripped)
        if m:
            out["reason"] = m.group(1).strip()[:256]
        m = re.search(r"OS Version:\s*([^\r\n]+)", stripped)
        if m:
            out["os_version"] = m.group(1).strip()[:64]
        if not out["reason"]:
            pr = _format_panic_reason({}, stripped)
            if pr and "panic(" in stripped.lower():
                out["reason"] = pr
        if not out["reason"]:
            rr = _format_reset_reason({}, stripped)
            if rr:
                out["reason"] = rr
        if not out["os_version"]:
            m = re.search(
                r"(iPhone OS [0-9][^\r\n\",}]{0,40})", stripped)
            if m:
                out["os_version"] = m.group(1).strip()[:64]
    return out


def _read_crash_header(path: str, limit: int = 65536) -> dict:
    """Read at most `limit` bytes of one crash file and parse its header."""
    try:
        with open(path, "rb") as f:
            raw = f.read(limit)
        text = raw.decode(errors="replace")
    except OSError:
        return {"exception": "", "reason": "", "os_version": "",
                "bug_type": "", "name": ""}
    return parse_crash_header_text(text)


def matched_hint(line: str) -> tuple[str, str]:
    """Classify a line AND report which classification keyword won.

    Returns (level, keyword): `keyword` is the ERROR/WARN hint that matched,
    or "" for info. Error hints win over warn hints (checked first).
    """
    low = (line or "").lower()
    for h in ERROR_HINTS:
        if h in low:
            return "error", h
    for h in WARN_HINTS:
        if h in low:
            return "warn", h
    return "info", ""


def classify_log_line(line: str) -> str:
    level, _ = matched_hint(line)
    return level


#: `... sample-process[101]: msg` → `sample-process`;
#: `... wifid(WiFiPolicy)[54] <Notice>: msg` → `wifid` (subsystem in
#: parens and the iOS `<Level>:` tag are skipped). Real idevicesyslog
#: lines carry no hostname, mock lines carry `iPhone` — so the pattern
#: searches anywhere instead of anchoring token positions.
_LOG_PROC_PID = re.compile(
    r"([\w.\-]+)(?:\(.*?\))?\[\d+\]\s*(?:<[^>]+>\s*)?:"
)
_LOG_TS = re.compile(r"^[A-Z][a-z]{2}\s+\d+\s+[\d:.]+\s+")


def parse_log_process(line: str) -> str:
    """Extract the process name from an idevicesyslog line ("" if unknown)."""
    text = line or ""
    m = _LOG_PROC_PID.search(text)
    if m:
        return m.group(1)
    # No `[pid]:` — fall back to the token before the first colon after
    # the timestamp (e.g. `kernel: ...`), minus any `<Level>` tag.
    stripped = _LOG_TS.sub("", text)
    head = stripped.split(":", 1)[0] if ":" in stripped else ""
    head = re.sub(r"<[^>]+>", "", head).strip()
    token = head.split()[-1] if head.split() else ""
    token = re.sub(r"\(.*", "", token).strip()
    # Relay banners (`[connected:UDID]`), paths and level tags are not
    # processes — never surface them as one in the web viewer.
    if not token or token[0] in "<[" or "/" in token:
        return ""
    return token[:64]


#: idevicesyslog's own relay chatter — connection banners, not phone logs.
#: Seen live: `[connected:00008110-0014158C0E9B601E]` as the first line.
_RELAY_BANNERS = (
    re.compile(r"^\[connected[ :].*"),
    re.compile(r"^\[disconnected.*"),
)


def is_relay_banner(line: str) -> bool:
    """True for idevicesyslog protocol lines (never a phone log line)."""
    text = (line or "").strip()
    return any(pat.match(text) for pat in _RELAY_BANNERS)


def strip_relay_banners(text: str) -> str:
    """Drop relay banners so counts, filters and the viewer see phone logs."""
    if not text:
        return ""
    return "\n".join(ln for ln in text.splitlines()
                     if not is_relay_banner(ln))


def parse_log_entry(line: str) -> dict:
    """One structured log row for the web log viewer (color + table view).

    `match` names the classification keyword that decided the level ("" for info)
    so the viewer can tooltip *why* a row is red/amber/blue without
    re-implementing the classifier.
    """
    level, hint = matched_hint(line)
    return {"text": line, "level": level,
            "proc": parse_log_process(line), "match": hint}


def summarize_syslog(text: str) -> dict:
    lines = (text or "").splitlines()
    errors = sum(1 for ln in lines if classify_log_line(ln) == "error")
    warns = sum(1 for ln in lines if classify_log_line(ln) == "warn")
    return {"total": len(lines), "errors": errors, "warnings": warns}


MOCK_CRASHES = [
    ("Sample-Crash-2026-09-18.ips", 12400),
    ("SpringBoard-2026-09-10.ips", 8300),
    ("WhatsApp-2026-09-08.ips", 5210),
]

#: Canned header details for mock mode so the detail UI is testable offline.
#: Real phones parse these from the .ips JSON header locally.
MOCK_CRASH_META: dict[str, dict] = {
    "Sample-Crash-2026-09-18.ips": {
        "kind": "crash",
        "exception": "EXC_CRASH (SIGABRT)",
        "reason": "abort() called — sample exception for offline UI",
        "os_version": "iOS 26.0.1 (23A341)",
        "mtime": "2026-09-18T12:00:00",
    },
    "SpringBoard-2026-09-10.ips": {
        "kind": "crash",
        "exception": "EXC_BAD_ACCESS (SIGSEGV)",
        "reason": "KERN_INVALID_ADDRESS at 0x0000000000000000",
        "os_version": "iOS 26.0.1 (23A341)",
        "mtime": "2026-09-10T09:14:00",
    },
    "WhatsApp-2026-09-08.ips": {
        "kind": "crash",
        "exception": "EXC_CRASH (SIGKILL)",
        "reason": "Jetsam-style memory kill (per-process limit)",
        "os_version": "iOS 26.0.1 (23A341)",
        "mtime": "2026-09-08T21:02:00",
    },
}


def _mtime_iso(ts: float) -> str:
    try:
        return datetime.datetime.fromtimestamp(ts).isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return ""


@dataclass
class Diagnostics:
    runner: object = field(default_factory=SubprocessRunner)
    available: bool | None = None
    #: Raw capture cache: udid -> (monotonic_ts, text, live). Re-filtering a
    #: fresh capture is instant; re-running idevicesyslog for every keystroke
    #: is what made the log view feel slow.
    _log_cache: dict = field(default_factory=dict, repr=False)
    #: Seconds a raw capture stays reusable for a new filter/window request.
    log_cache_ttl: float = 8.0
    #: Crash list cache: udid -> (monotonic_ts, list[CrashItem]).
    #: idevicecrashreport copies every .ips file per call; without this the
    #: summary + list endpoints each pay for a full copy.
    _crash_cache: dict = field(default_factory=dict, repr=False)
    #: Crash cache TTL — longer than the log cache (crash store changes rarely).
    crash_cache_ttl: float = 30.0
    #: Last temp copy per udid, kept so the detail endpoint can serve a
    #: truncated preview without re-copying. Cleaned on the next refresh.
    _crash_dirs: dict = field(default_factory=dict, repr=False)
    #: Serializes `idevicecrashreport -k` copies per process. Without this,
    #: a hard reload fires /diagnostics/summary (which copies internally)
    #: and /diagnostics/crashes concurrently for the same udid; the two
    #: parallel copies contend on the device/lockdown and one fails with a
    #: transient [] that wipes the crash table until the next soft reload
    #: hits the 30 s cache. Double-checked after acquiring.
    _crash_lock: threading.RLock = field(default_factory=threading.RLock,
                                         repr=False, compare=False)
    #: Same for idevicesyslog captures (shorter TTL, cheaper to re-run).
    _log_lock: threading.RLock = field(default_factory=threading.RLock,
                                       repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.available is None:
            mock = os.environ.get("FREETUNES_MOCK", "0") == "1"
            self.available = not mock
        if not isinstance(getattr(self, "_log_cache", None), dict):
            self._log_cache = {}
        if not isinstance(getattr(self, "_crash_cache", None), dict):
            self._crash_cache = {}
        if not isinstance(getattr(self, "_crash_dirs", None), dict):
            self._crash_dirs = {}
        for _attr in ("_crash_lock", "_log_lock"):
            _lock = getattr(self, _attr, None)
            if _lock is None or not (hasattr(_lock, "acquire") and hasattr(_lock, "release")):
                setattr(self, _attr, threading.RLock())

    def _enrich(self, filename: str, size: int, mtime: str = "",
                header: dict | None = None) -> CrashItem:
        app, date = parse_crash(filename)
        kind = classify_crash_kind(filename)
        h = header or {}
        meta = MOCK_CRASH_META.get(filename, {})
        return CrashItem(
            filename=filename, size=size, app=app, date=date,
            mtime=mtime or str(meta.get("mtime", "")),
            kind=str(h.get("kind") or meta.get("kind") or kind),
            exception=str(h.get("exception") or meta.get("exception") or ""),
            reason=str(h.get("reason") or meta.get("reason") or ""),
            os_version=str(h.get("os_version") or meta.get("os_version") or ""),
        )

    def _remember_crash_dir(self, udid: str, outdir: str) -> None:
        old = self._crash_dirs.get(udid)
        if old and old != outdir:
            shutil.rmtree(old, ignore_errors=True)
        self._crash_dirs[udid] = outdir

    def _drop_crash_dir(self, udid: str) -> None:
        old = self._crash_dirs.pop(udid, None)
        if old:
            shutil.rmtree(old, ignore_errors=True)

    def crashes(self, udid: str) -> list[CrashItem]:
        if not self.available or shutil.which("idevicecrashreport") is None:
            return [self._enrich(name, size) for name, size in MOCK_CRASHES]
        if _is_mock_udid(udid):
            # Tools present but no iPhone (placeholder UDID): honest empty,
            # never fake sample — matches Files/Photos which return [] here.
            # Never probe `idevicecrashreport -u mock-udid`.
            return []
        now = time.monotonic()
        hit = self._crash_cache.get(udid)
        if hit is not None and now - hit[0] < self.crash_cache_ttl:
            return hit[1]
        with self._crash_lock:
            # Double-checked: a concurrent /summary + /crashes pair on a
            # hard reload would otherwise run two copies at once; the loser
            # fails and returns a transient [] that empties the table.
            now = time.monotonic()
            hit = self._crash_cache.get(udid)
            if hit is not None and now - hit[0] < self.crash_cache_ttl:
                return hit[1]
            return self._crashes_uncached(udid, now)

    def _crashes_uncached(self, udid: str, now: float) -> list[CrashItem]:
        outdir = tempfile.mkdtemp(prefix="ft-crashes-")
        try:
            # -k/--keep: copy without deleting the reports off the phone.
            # Without it the first read would drain the device's crash store.
            r = self.runner.run(  # type: ignore[union-attr]
                "idevicecrashreport", "-u", udid, "-k", outdir, timeout=60)
            if r.returncode != 0:
                shutil.rmtree(outdir, ignore_errors=True)
                return []
            import os as _os
            rows: list[tuple[str, int, str]] = []
            try:
                names = _os.listdir(outdir)
            except OSError:
                shutil.rmtree(outdir, ignore_errors=True)
                return []
            # Stat everything first, THEN sort by recency and slice: the old
            # code sliced the first 500 alphabetically and could drop the
            # newest reports on phones with large crash stores.
            for name in names:
                p = _os.path.join(outdir, name)
                try:
                    st = _os.stat(p)
                except OSError:
                    continue
                if not _os.path.isfile(p):
                    continue
                rows.append((name, st.st_size, _mtime_iso(st.st_mtime)))
            enriched: list[CrashItem] = []
            for name, size, mtime in rows:
                p = _os.path.join(outdir, name)
                header = _read_crash_header(p)
                # Filename kind first (offline, no read needed); the real
                # bug_type from the parsed header wins when present, so a
                # renamed Jetsam/panic/ResetCounter file still lands in the
                # right filter.
                kind = classify_crash_kind(name)
                bug_kind = BUG_TYPE_KIND.get(str(header.get("bug_type") or "").strip())
                header["kind"] = bug_kind or kind
                try:
                    enriched.append(self._enrich(name, size, mtime, header))
                except (ValueError, TypeError):
                    continue
            # Newest first: filename date wins, mtime breaks ties, undated sink.
            enriched.sort(
                key=lambda c: (bool(c.date), c.date, c.mtime, c.filename),
                reverse=True)
            items = enriched[:500]
            self._crash_cache[udid] = (now, items)
            self._remember_crash_dir(udid, outdir)
            # Any sibling temp dirs from older runs are stale — remove them
            # so /tmp does not fill with ft-crashes-* copies.
            try:
                import glob as _glob
                for stale in _glob.glob(
                        os.path.join(tempfile.gettempdir(), "ft-crashes-*")):
                    if stale != outdir and stale not in self._crash_dirs.values():
                        shutil.rmtree(stale, ignore_errors=True)
            except (OSError, TypeError):
                pass
            return items
        except Exception:
            shutil.rmtree(outdir, ignore_errors=True)
            return []

    def crash_detail(self, udid: str, filename: str) -> dict | None:
        """Truncated local preview of one crash file (never uploads).

        Returns {item, preview} or None when unknown/forbidden. Mock mode
        serves canned previews from MOCK_CRASH_META.
        """
        safe = sanitize_crash_filename(filename)
        if not safe:
            return None
        items = self.crashes(udid)
        item = next((c for c in items if c.filename == safe), None)
        if item is None:
            return None
        if not self.available or shutil.which("idevicecrashreport") is None:
            # Mock mode only: canned previews. Tools present + placeholder
            # UDID never reaches here (crashes() is [] → item None → 404).
            meta = MOCK_CRASH_META.get(safe, {})
            preview = (
                f"{safe}\nApp: {item.app}  Date: {item.date or item.mtime or '—'}\n"
                f"Exception: {item.exception or '—'}\n"
                f"Reason: {item.reason or '—'}\n"
                f"OS: {item.os_version or '—'}\n"
                f"(sample preview in mock mode — connect an iPhone for the real header)")
            return {"item": item.model_dump(), "preview": preview,
                    "truncated": True, "live": False}
        outdir = self._crash_dirs.get(udid)
        path = os.path.join(outdir, safe) if outdir else ""
        if not path or not os.path.isfile(path):
            # Cache expired or dir cleaned — force one fresh copy.
            self._crash_cache.pop(udid, None)
            self._drop_crash_dir(udid)
            self.crashes(udid)
            outdir = self._crash_dirs.get(udid)
            path = os.path.join(outdir, safe) if outdir else ""
            if not path or not os.path.isfile(path):
                return None
        try:
            with open(path, "rb") as f:
                raw = f.read(20000)
            preview = raw.decode(errors="replace")
        except OSError:
            return None
        lines = preview.splitlines()
        truncated = len(lines) > 200 or len(raw) >= 20000
        preview = "\n".join(lines[:200])
        return {"item": item.model_dump(), "preview": preview,
                "truncated": truncated, "live": True}

    def syslog(self, udid: str, lines: int = 200,
               q: str = "", level: str = "all",
               window: float = 3.0) -> dict:
        lines = max(1, min(1000, lines))
        q = (q or "").strip().lower()
        level = (level or "all").lower()
        if level not in ("all", "error", "warn", "info"):
            level = "all"
        # Short capture window keeps the UI snappy: the old 8 s default
        # blocked every Refresh/filter change. 1–8 s, default 3 s.
        try:
            window = float(window or 3.0)
        except (TypeError, ValueError):
            window = 3.0
        window = max(1.0, min(8.0, window))
        if not self.available or shutil.which("idevicesyslog") is None:
            sample_lines = [
                f"Sep 18 12:00:{i:02d} iPhone sample-process[{100+i}]: freetunes mock log line {i}"
                for i in range(20)
            ]
            # Sprinkle realistic severities so the level filter is demonstrable offline.
            sample_lines[3] += " — thermal warn: throttled for 2s"
            sample_lines[7] += " — backupd error: snapshot failed, retrying"
            sample = "\n".join(sample_lines[:min(lines, 20)])
            return self._filter_log(udid, sample, False, q, level,
                                    requested=lines, cached=False,
                                    capture_ms=0, window=window)
        if _is_mock_udid(udid):
            # Tools present but no iPhone: honest empty, never fake sample
            # and never `idevicesyslog -u mock-udid` (waits ~8 s for a
            # device that never appears). Matches Files/Photos → [].
            return self._filter_log(udid, "", False, q, level,
                                    requested=lines, cached=False,
                                    capture_ms=0, window=window)

        # Reuse a fresh capture so typing a filter does not re-run the
        # relay: idevicesyslog streams forever, the timeout *is* the stop
        # condition (there is no `-n LINES` on libimobiledevice 1.4.0 —
        # `-n` means --network there). SubprocessRunner keeps the partial
        # capture on timeout; take the tail here.
        cached = False
        now = time.monotonic()
        hit = self._log_cache.get(udid)
        if hit is not None and now - hit[0] < self.log_cache_ttl:
            text, live = hit[1], hit[2]
            cached = True
            capture_ms = 0
        else:
            with self._log_lock:
                now = time.monotonic()
                hit = self._log_cache.get(udid)
                if hit is not None and now - hit[0] < self.log_cache_ttl:
                    text, live = hit[1], hit[2]
                    cached = True
                    capture_ms = 0
                else:
                    text, capture_ms = self._capture_with_retry(udid, window)
                    text = strip_relay_banners(text)
                    if not text.strip():
                        return self._filter_log(udid, "", False, q, level,
                                                requested=lines, cached=False,
                                                capture_ms=capture_ms, window=window)
                    live = True
                    self._log_cache[udid] = (now, text, live)
        tail = "\n".join(text.splitlines()[-max(lines * 3, lines):])
        return self._filter_log(udid, tail, live, q, level, requested=lines,
                                cached=cached, capture_ms=capture_ms,
                                window=window)

    def _capture_with_retry(self, udid: str, window: float) -> tuple[str, int]:
        """Run the relay; on a quiet phone retry once up to ~8 s total.

        A sleeping iPhone trickles almost nothing — a short window then
        returns empty where the old fixed 8 s window caught a few lines.
        The fast path stays fast (one short capture); only an empty
        capture pays for the extra slice.
        """
        started = time.monotonic()
        first = max(1, int(window))
        r = self.runner.run(  # type: ignore[union-attr]
            "idevicesyslog", "-u", udid, timeout=first)
        text = (r.stdout or "")[-40000:]
        if strip_relay_banners(text).strip() or first >= 8:
            return text, int((time.monotonic() - started) * 1000)
        r2 = self.runner.run(  # type: ignore[union-attr]
            "idevicesyslog", "-u", udid, timeout=8 - first)
        text2 = (r2.stdout or "")[-40000:]
        if strip_relay_banners(text2).strip():
            text = text2
        return text, int((time.monotonic() - started) * 1000)

    @staticmethod
    def _filter_log(udid: str, text: str, live: bool, q: str, level: str,
                    requested: int = 200, cached: bool = False,
                    capture_ms: int = 0, window: float = 3.0) -> dict:
        raw = (text or "").splitlines()
        kept: list[str] = []
        for ln in raw:
            lv = classify_log_line(ln)
            if level == "warn" and lv not in ("warn", "error"):
                continue
            elif level in ("error", "info") and lv != level:
                continue
            if q and q not in ln.lower():
                continue
            kept.append(ln)
        # Cap at the requested tail: the capture window can hold more than
        # the UI asked for (wider net for filters), but `shown <= requested`.
        kept = kept[-max(1, requested):]
        summary = summarize_syslog(text)
        entries = [parse_log_entry(ln) for ln in kept]
        return {"udid": udid, "lines": "\n".join(kept), "live": live,
                "total": len(raw), "shown": len(kept),
                "errors": summary["errors"], "warnings": summary["warnings"],
                "filtered": bool(q or level != "all"), "requested": requested,
                "entries": entries, "cached": cached,
                "capture_ms": capture_ms, "window": window}

    def health(self, udid: str, model_number: str = "", serial: str = "") -> dict:
        ver = verification_for(udid, model_number, serial)
        crashes = self.crashes(udid)
        log = self.syslog(udid, lines=100)
        crash_warn = len(crashes) >= 5
        # Gate on *actionable* errors, not the raw count: the live stream
        # always carries benign kernel chatter (e.g. the constant IOSurface
        # "decode: mismatch" spam on iOS 26), which would otherwise pin the
        # hero on "attention" for a healthy phone. The full count is still
        # reported as log_errors below and in the log view.
        actionable = sum(
            1 for ln in (log.get("lines", "") or "").splitlines()
            if classify_log_line(ln) == "error" and not _is_benign_noise(ln)
        )
        log_warn = actionable >= 3
        if ver.refurbished_suspect or crash_warn or log_warn:
            status = "attention"
            headline = "Needs a look — " + ", ".join([
                *(["possible refurbished unit"] if ver.refurbished_suspect else []),
                *([f"{len(crashes)} crash reports"] if crash_warn else []),
                *([f"{actionable} log errors"] if log_warn else []),
            ])
        elif not model_number:
            status = "unknown"
            headline = "Connect your iPhone to complete the check."
        else:
            status = "healthy"
            headline = "No red flags — model looks retail, crashes and log errors are quiet."
        # Group crashes by app for the hero.
        by_app: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        for c in crashes:
            by_app[c.app or c.filename] = by_app.get(c.app or c.filename, 0) + 1
            k = (c.kind or "crash").lower()
            by_kind[k] = by_kind.get(k, 0) + 1
        top_apps = sorted(by_app.items(), key=lambda kv: -kv[1])[:5]
        return {"udid": udid, "status": status, "headline": headline,
                "verification": ver.model_dump(),
                "crash_count": len(crashes),
                "top_crash_apps": [{"app": k, "count": v} for k, v in top_apps],
                "crash_kinds": by_kind,
                "log_errors": log.get("errors", 0), "log_warnings": log.get("warnings", 0),
                "log_live": log.get("live", False)}


_diag: Diagnostics | None = None


def get_diagnostics() -> Diagnostics:
    global _diag
    if _diag is None:
        mock = os.environ.get("FREETUNES_MOCK", "0") == "1"
        _diag = Diagnostics(available=False) if mock else Diagnostics()
    return _diag
