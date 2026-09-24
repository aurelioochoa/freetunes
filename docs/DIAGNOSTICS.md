# freetunes diagnostics: logs & crash reports

Yes — logs and crash reports work. The **Diagnostics** tab (sidebar) shows
three device-side sources plus a health summary, all read-only over USB.
Verified 2026-09-23 on iPhone 13 (iPhone14,5), iOS 26.0.1, libimobiledevice
1.4.0: verification `retail-new`, live syslog streaming, crash list (empty —
the phone genuinely has none).

## What device logs are visible

| Source | Endpoint | Tool | What you see |
|---|---|---|---|
| Verification | `GET /diagnostics/verification?udid=` | `ideviceinfo` (lockdown) | Model origin (M/F/N/P → retail/refurbished/replacement/personalized), serial presence, storage-reporting note |
| Crash reports | `GET /diagnostics/crashes?udid=` | `idevicecrashreport -k` | Every `.ips` file on the phone: app + date parsed from filename, file mtime, size, kind (crash/jetsam/panic), exception + reason + OS from the `.ips` JSON header (parsed locally). Newest first, max 500 |
| Crash detail | `GET /diagnostics/crashes/{filename}?udid=` | last `-k` copy on disk | One file's list fields + truncated preview (first 200 lines / 20KB). 404 on unknown names or path traversal |
| Device log | `GET /diagnostics/syslog?udid=&lines=&q=&level=&window=` | `idevicesyslog` | Live tail of the iOS system log: every process (configd, wifid, kernel, SpringBoard, apps…), short capture window (see below), structured `entries` per line for the colorized viewer |
| Device log (real-time) | `GET /diagnostics/syslog/stream?udid=&q=&level=` (SSE) | `idevicesyslog` | True live tail: one `data: {"text","level","proc","match"}` event per line until the browser leaves; the viewer's **▶ Live tail** button uses it |
| Health summary | `GET /diagnostics/summary?udid=` | combines all three | `healthy` / `attention` / `unknown` + one-line headline, crash count, top crashing apps, log error/warning counts |

What is **not** a device log (shown elsewhere, don't confuse them):

- **Backend server log** — the terminal running `make dev`: timestamped
  `HH:MM:SS [LEVEL] name: message` lines for every API call
  (`backend/app/logging_setup.py`; routine `/devices` + `/apps` polls are
  quieted to DEBUG so errors stay visible). Set `FREETUNES_LOG_LEVEL=debug`
  for the full firehose.
- **Screen receiver logs** — the HD/AirPlay receiver's own stdout, surfaced
  in the Screen tab. Host-side, not from the phone.

## Reading the device log

One line looks like this:

```
Sep 23 13:17:12.467014 wifid(WiFiPolicy)[54] <Notice>: __WiFiDeviceManagerEvaluateAPEnvironment: …
│                      │   │              │    │          └ message
│                      │   │              │    └ level tag from iOS: <Debug> <Notice> <Error> …
│                      │   │              └ PID
│                      │   └ subsystem
│                      └ process name
└ timestamp (phone clock)
```

The UI offers three filters, all applied **on this computer** (the phone
always streams the full tail; nothing is uploaded anywhere):

- **Text search** (`q`) — substring match, case-insensitive, e.g. `wifid`,
  `backupd`, `SpringBoard`. Hover the box for ideas; clicking a keyword chip
  in the legend searches it.
- **Level** (`level=all|warn|error|info`) — freetunes classifies each line by
  keyword (see “How freetunes classifies lines” below). `warn` means
  "warnings *and* errors". iOS's own `<Error>`/`<Notice>` tags feed into
  this only insofar as the words appear in the line.
- **Line count** (`lines=50|100|200|500`, max 1000) — how many of the most
  recent matching lines to keep. `total` = raw lines captured in the window,
  `shown` = lines returned after filtering (`shown ≤ requested`).

### How freetunes classifies lines: filter levels & keywords

Names matter — “tipo/subtipo” was wrong. The viewer uses three distinct
things (hover any button, chip or row badge for the same one-line text —
below is the source of truth: backend `ERROR_HINT_INFO` / `WARN_HINT_INFO` /
`LEVEL_INFO`, long texts in `frontend/src/logLevels.ts`):

- **Filter level** — freetunes’ own filter: All, Warnings+, Errors, Info.
  Not Apple’s levels.
- **Classification keyword** — the word that pushed one line into red/amber
  (`match` on each structured row, `""` for info). 9 error words (checked
  first) + 8 warning words.
- **iOS level tag** — Apple’s own `<Debug> <Info> <Notice> <Error> …` tag
  from the unified logging system (`os_log`), which grades severity as
  Debug < Info < Default (<Notice>) < Error < Fault. Debug lives in memory
  only; Info/Default/Notice are routine and persisted; Error/Fault are
  always persisted. freetunes does not read the tag — it matches words, so
  `<Error>` lands in Errors via “error” and `<Notice>` lands in Warnings
  via “notice”.
- **Process** — who wrote the line (`proc`), parsed from `proc[pid]:` or
  `proc(subsystem)[pid] <Level>:`.

| Filter level | Button | Keeps | When to use it |
|---|---|---|---|
| All | All | Every line | See the raw tail before narrowing down. |
| Warnings+ | Warnings+ | warn **and** error | First question “is something wrong?” — start here. |
| Errors | Errors | error only | Find the one failure behind a symptom; the smallest, most serious slice. |
| Info | Info | info only | Was the process alive? What happened right before time T? The largest, noisiest slice. |

Error keywords — any of these words makes a line **red** (checked first, so they win over warning words):

| Keyword | What it usually means on iOS | What to do | Example |
|---|---|---|---|
| `error` | Generic failure; also Apple’s `<Error>` tag (`os_log_error`, always persisted). | Group by process: one process repeating “error” is a lead. | `backupd error: snapshot failed` |
| `fault` | Apple’s top level (`os_log_fault`): a component reporting itself broken, with extra diagnostics captured. | Treat as a heavy error; look for a matching crash report. | `os_fault in mediaserverd` |
| `failed` | An operation ran and finished as a failure — often retryable. | Read the next lines: “failed … retrying … ok” is transient; looping “failed” is the problem. | `snapshot failed, retrying` |
| `crash` | A process died abnormally; ReportCrash writes a `.ips` file. | Open Crash reports, match app + date — the `.ips` is the evidence. | `SpringBoard crash detected` |
| `panic` | Kernel panic: the whole device went down or nearly did. | Always open it; check against unexpected reboots and panic logs. | `panic: kernel trap` |
| `exception` | Unhandled exception (e.g. `NSException`): bad argument, out-of-bounds, failed assertion. | Note the name, match the `.ips`, reproduce the action. | `uncaught exception NSRange` |
| `denied` | Sandbox refusal: iOS blocked a file/network/device access (Apple documents these as sandbox violations). | Check what was blocked and which app; background daemon denials are usually harmless. | `sandbox denied file-write` |
| `timeout` | Waited past a deadline: network, lock, IPC reply. | Once is transient; fixed-interval repeats point at connectivity or the other endpoint. | `sync timeout after 30s` |
| `corrupt` | Data failing validation: truncated file, bad DB page, damaged cache. | Back up first, then re-sync/restore that data; multi-process corruption suggests storage. | `corrupt database header` |

Warning keywords — any of these words makes a line **amber**:

| Keyword | What it usually means on iOS | What to do | Example |
|---|---|---|---|
| `warn` | Generic caution, incl. low-memory (Jetsam) warnings. | Read the noun after “warn”; memory/disk/battery deserve attention. | `memory warn: Jetsam` |
| `notice` | Apple’s `<Notice>` = the default `os_log` level: routine, persisted chatter. | Ignore singles; only clusters around a symptom matter. | `wifid(WiFiPolicy)[54] <Notice>` |
| `throttle` | The device deliberately slowing work: power, thermal or policy. | Look for sibling thermal/low-power lines; expected when hot or in Low Power Mode. | `throttled for 2s` |
| `low` | A resource running out: memory, disk, battery, signal. Low memory ends in Jetsam kills (largest process first), which then look like crashes. | Check storage/battery; for “crashes” under load with low-memory lines, read the Jetsam report. | `low memory warning` |
| `deprecat` | Deprecated API called — still works, flagged for developers. | Ignore unless you develop the named app. | `deprecated API usage` |
| `retry` | A failure with a plan: another attempt is scheduled. | “retry … ok” is the system working; endless retries are the symptom. | `will retry in 5s` |
| `slow` | Something exceeded its time budget: frame, launch, IPC. | Note process + duration; pair with timeouts if the UI hung. | `slow frame commit` |
| `thermal` | Thermal pressure: iOS sheds load (throttle, dim, pause charging) before damage. | Cool down, remove case, unplug; re-test cold before blaming an app. | `thermal warn: throttled` |

Info — the remainder, by definition keyword-free: Apple’s Debug/Info/Default
levels doing their job (heartbeats, state changes, successes). It is the
largest slice and its volume says nothing about health: a locked phone
streams almost nothing, an unlocking phone bursts. Use it to answer “was
the process alive?” and “what happened right before T?”.

Processes you will meet constantly: `kernel` (memory/Jetsam, panics,
IOSurface spam), `SpringBoard` (home screen + launches), `backboardd`
(touch/display), `configd` (constant, harmless), `wifid` (the classic
`<Notice>` chatterbox), `backupd` (“error/failed” here threatens backups),
`CommCenter` (cellular), `mDNSResponder` (Bonjour/AirPlay), `identityservicesd`
(Apple ID/iMessage), `mediaserverd` (audio/video).

Rules: error words win over warning words. Each structured row carries
`match` (the winning keyword, `""` for info) so the viewer can tooltip
*why* without re-classifying. The `IOSurface "decode: mismatch"` line is a
real error by keyword but known-benign OS spam on iOS 26: it still shows
and counts, but never flips the health headline (see Health rules).

The header always reports `N of M lines shown · E errors · W warnings`, plus
a **LIVE** / **SAMPLE** pill: `live: true` means the bytes came from your
phone just now.

### Why a short window, not history

`idevicesyslog` on libimobiledevice 1.4.0 is a pure stream — it has no
"last N lines" flag (`-n` means `--network` there; passing a number errors
with `Unknown command`). So the backend runs the relay, records a short
window (`window=1–8`, default 3 s), and keeps the tail. A fresh capture is
reused for ~8 s, so typing a filter is instant (`cached: true`) instead of
re-running the relay per keystroke. A sleeping iPhone trickles almost
nothing: when the first capture comes back empty the backend retries once
(up to ~8 s total — `capture_ms` reports what it really took), and the
viewer says the phone is quiet instead of showing nothing. For continuous
output use the SSE stream above. For deep history, use
`idevicesyslog archive PATH` directly — that path is intentionally not in
the UI (multi-GB tarballs).

`idevicesyslog`'s own `[connected:UDID]` / `[disconnected]` banners are
protocol, not phone logs: the backend strips them before counting,
filtering and streaming, so they never appear as rows.

## Crash reports

`idevicecrashreport` copies the phone's `.ips` files into a temp dir and the
backend parses `SpringBoard-2026-09-10.ips` → app `SpringBoard`, date
`2026-09-10`. Always fetched with `-k/--keep`, so reading never deletes
reports off the phone. An empty list ("None found — a healthy sign") means
the phone has no stored crashes, not a failure — distinguish it from the
`SAMPLE` pill (mock mode) and the error card (cable/trust problem).

Each row carries `mtime` (file modification time, for undated names), `kind`
(`panic` for kernel panics, `jetsam` for low-memory kills, else `crash`),
and `exception` / `reason` / `os_version` parsed locally from the `.ips`
JSON header (first 64KB only — never the full thread dump). The list result
is cached ~30s so the summary + list don't each pay for a full copy, stale
`ft-crashes-*` temp dirs are cleaned, and the newest 500 are kept by
(date, mtime) — not alphabetically.

### How freetunes classifies crashes: kinds, exceptions & reasons

Names matter — same discipline as the device-log viewer (filter level vs
classification keyword vs iOS tag). The crash card uses four distinct
things (hover any pill, exception or row for the same one-line text —
below is the source of truth: backend `CRASH_KIND_INFO` /
`CRASH_PATTERN_INFO`, long texts in `frontend/src/crashLevels.ts`):

- **Kind** — freetunes' own filter from the real `bug_type` first
  (`BUG_TYPE_KIND`: 309 crash, 298 jetsam, 210/115 panic, 288/305/202/142
  crash), filename as fallback (`classify_crash_kind`): All, crash,
  jetsam, panic. Not Apple's level.
- **Exception** — the Mach exception + BSD signal from the `.ips` report
  (`exception.type` + `exception.signal`), e.g. `EXC_CRASH (SIGABRT)`.
  Parsed locally. Jetsam / panic-full / ResetCounter reports carry no
  Mach exception by design — their Exception cell stays `—` and the
  Reason row is the evidence.
- **Reason** — termination info (`termination.namespace/code/indicator`
  + `byProc`, code shown hex, e.g. `Namespace SPRINGBOARD,
  Code 0x8badf00d`); for Jetsam the kill reason + victim + largestProcess
  (`Jetsam per-process-limit — MyApp (largest: OtherApp)`); for panic-full
  the first `panicString` line; for ResetCounter the reset / boot-failure
  counts. Parsed locally.
- **.ips file** — JSON since iOS 15: line 1 is metadata (`bug_type`,
  `os_version`, `name`), the rest is the report (exception, termination,
  threads, binary images for 309; process table for Jetsam 298;
  `panicString` for panic 210; reset counts for 115). freetunes parses
  `SpringBoard-2026-09-10.ips` → app `SpringBoard`, date `2026-09-10`,
  and exception / reason / OS from the first 64KB — locally, never uploaded.

| Kind | Pill | Keeps | When to use it |
|---|---|---|---|
| crash | crash | App / system crashes | Start here: one app repeating is a lead; scattered singles are noise. |
| jetsam | jetsam | Low-memory kills | Apps that "crash" under load with low-memory log lines — read the Jetsam report, not just the log tail. |
| panic | panic | Kernel panics + unexpected reboots (ResetCounter) | Any unexpected reboot — open the panic log first. |

Common reports — the names you will actually meet (same list as the
in-app "How is each crash classified?" tab, `COMMON_CRASH_REPORTS`):

| Report | Kind | What it is | What to do |
|---|---|---|---|
| `JetsamEvent` | jetsam | Low-memory system report (`bug_type` 298): device-wide process table + kill `reason`, no backtrace. | Read the Reason; `per-process-limit` = that app grew too big, `vm-pageshortage` = victim — check `largestProcess`. |
| `OTAUpdate` | crash | Software-update system report from the iOS OTA pipeline (`softwareupdated`), not a third-party crash. A small run (e.g. ×3) after an update attempt is expected noise. | If Software Update succeeds, ignore. If updates fail, free storage, fix network, retry. |
| `SpringBoard` | crash | Home-screen / launcher died; owns the `0x8badf00d` watchdog. | Repeats = system instability; match app + date, reproduce. |
| `backboardd` | crash | Touch / display server. | Singles are noise; repeats with touch freezes point at display hardware or a bad reboot. |
| `panic-full` | panic | Kernel panic (`bug_type` 210): `panicString` + kernel backtrace + kexts, never one app. | Match timestamp vs reboots; sensor/SMC first lines implicate flexes/battery; repeats = hardware until proven otherwise. |
| `ResetCounter` | panic | Reboot with no panic (`bug_type` 115): reset / boot-failure counts instead of a `panicString`. | Single after a forced restart is noise; repeats with no `panic-full` = unstable power/boot. |
| `ThermalEvent` / `StackShot` | crash | Thermal / stackshot snapshot (`bug_type` 288 family): diagnostic sample, not fatal. | Ignore singles; clusters with thermal/throttle log lines mean heat or sustained load. |
| `AppName` (e.g. `WhatsApp`) | crash | Normal app crash (`bug_type` 309): exception + reason + faulting thread to symbolicate. | One app repeating is a lead; match app + date, reproduce. |

Exception / termination patterns — any of these in the header tells you
*how* the process ended (Apple "Understanding the exception types"):

| Pattern | What it usually means | What to do |
|---|---|---|
| `EXC_CRASH (SIGABRT)` | Abort: unhandled language exception (e.g. `NSException`), failed assertion, `abort()` called. | Note the exception name, match app + date, reproduce the action. |
| `EXC_CRASH (SIGKILL)` | Killed by the system: watchdog, memory limit, force-quit. | Read the reason: `0x8badf00d` = hung; Jetsam reason = memory; else check `byProc`. |
| `EXC_BAD_ACCESS (SIGSEGV)` | Segfault: invalid / out-of-bounds address. | Symbolicate — crashing thread + binary image point at the fault. |
| `EXC_BAD_ACCESS (SIGBUS)` | Bus error: misaligned address or pointer-auth failure. | Same as SIGSEGV. |
| `EXC_BREAKPOINT (SIGTRAP)` | Trap: Swift runtime trap (nil, cast, bounds) or violated requirement. | Look for the trap message in the reason. |
| `EXC_RESOURCE` | Runaway stopped: CPU / memory / wakeups (read the subtype). | Subtype names the resource: CPU = hot loop; memory = Jetsam. |
| `0x8badf00d` | Watchdog: app hung, SpringBoard killed it ("ate bad food"). | Main-thread backtrace shows where it stuck. |
| `per-process-limit` | Jetsam: process crossed its own memory ceiling. | Reduce footprint; `rpages × pageSize` (usually 16384) = bytes. |
| `vm-pageshortage` | Jetsam: system-wide page shortage; background deaths protect the foreground. | Check `largestProcess` — victim may not be the cause. |
| `jettisoned` | Jetsam: jettisoned for another reason (neither per-process nor page-shortage). | Check `largestProcess` and neighbouring reasons; treat as memory pressure. |

Jetsam reports (`bug_type` 298) differ from crash reports: they carry a
device-wide process table and kill `reason` (`per-process-limit`,
`vm-pageshortage`, `vnode-limit`, `highwater`, `fc-thrashing`,
`jettisoned`) instead of thread backtraces — there is nothing to
symbolicate. Panics implicate hardware/drivers/kernel, never just one
app: match the timestamp against unexpected reboots. ResetCounter files
mean a reboot left no panic at all — counts, not a backtrace.

Sources: Apple [Interpreting the JSON format](https://developer.apple.com/documentation/xcode/interpreting-the-json-format-of-a-crash-report),
[Examining the fields](https://developer.apple.com/documentation/xcode/examining-the-fields-in-a-crash-report),
[Understanding the exception types](https://developer.apple.com/documentation/xcode/understanding-the-exception-types-in-a-crash-report),
[Jetsam event reports](https://developer.apple.com/documentation/xcode/identifying-high-memory-use-with-jetsam-event-reports).

The web card adds kind filter chips, an Exception column, relative dates
(`Sep 10 · 13d ago`), a "How is each crash classified?" guide (kind cards
+ common-report chips + pattern chips + Jetsam reasons, mirroring the log
viewer), clickable `worst: App ×N` filters, expandable rows with "What it means"
plus a truncated preview (`GET /diagnostics/crashes/{filename}`, max 200
lines / 20KB), `Search log for <app>` cross-link, `Show more`
pagination, and CSV export.

## Health rules (`/diagnostics/summary`)

- `unknown` — no model number readable (plug in, Trust, re-check).
- `attention` — refurbished/replacement model letter, **or** ≥ 5 crash
  reports, **or** ≥ 3 *actionable* log errors in the window.
- `healthy` — none of the above.

"Actionable" matters: the live stream always carries benign kernel chatter
(notably the constant `IOSurface "decode: mismatch"` spam on iOS 26). Those
lines still count toward `log_errors` and appear in the log view, but are
excluded from the attention gate so a healthy phone doesn't read as sick
(see `BENIGN_NOISE_HINTS` in `backend/app/services/diagnostics.py`).

## Mock mode vs live

With `FREETUNES_MOCK=1` (default) the endpoints return honest samples with
`live: false`, and the UI says **SAMPLE** / "no iPhone — showing sample
data": 3 sample crashes, 20 sample log lines (including one warning and one
error so the filters are demonstrable). No UDID needed — `mock-udid` works.

## Troubleshooting

| Symptom | Meaning | Fix |
|---|---|---|
| Log shows `SAMPLE` | Mock mode or no phone | Unset `FREETUNES_MOCK`, plug in, Trust |
| `live` but 0 lines | Relay produced nothing in 8 s | Re-check cable/Trust; retry — a sleeping phone streams little |
| "Could not load diagnostics" card | Backend unreachable/error | `make dev` running? cable seated? Trust tapped? |
| `0 crashes` with LIVE | Phone genuinely has none | Healthy sign, not a bug |
| `attention` from log errors | ≥ 3 non-benign errors in window | Search the log for `error`, check which app/process repeats |

## Privacy

Full serials and log contents never leave this computer — filtering,
counting and the `.log` download all happen locally. The UI shows only the
first 3 serial characters. Crash file *headers* (exception, reason, OS
version) and truncated previews are parsed locally on this computer from the
`-k` copy — never uploaded anywhere. Only filenames, sizes and the truncated
preview are served to the browser.
