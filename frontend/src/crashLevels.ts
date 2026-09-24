/**
 * Crash-report taxonomy: kinds + exception / termination hints.
 *
 * Mirrors `backend/app/services/diagnostics.py` (`CRASH_KIND_INFO`).
 * Keep both sides in sync: the backend classifies from the filename,
 * the viewer only explains it.
 *
 * Sources (Apple Developer Documentation, 2026):
 * - Interpreting the JSON format of a crash report
 *   https://developer.apple.com/documentation/xcode/interpreting-the-json-format-of-a-crash-report
 * - Examining the fields in a crash report
 *   https://developer.apple.com/documentation/xcode/examining-the-fields-in-a-crash-report
 * - Understanding the exception types in a crash report
 *   https://developer.apple.com/documentation/xcode/understanding-the-exception-types-in-a-crash-report
 * - Identifying high-memory use with Jetsam event reports
 *   https://developer.apple.com/documentation/xcode/identifying-high-memory-use-with-jetsam-event-reports
 *
 * Correct names — mirrors the device-log viewer wording:
 * - **Kind** = panic | jetsam | crash | unknown: freetunes' own filter,
 *   decided from the real `bug_type` first (309 crash, 298 jetsam,
 *   210/115 panic) with the filename as fallback
 *   (backend `classify_crash_kind` + `BUG_TYPE_KIND`). Not Apple's level.
 * - **Exception** = the Mach exception + BSD signal from the `.ips`
 *   JSON header (`exception.type` + `exception.signal`), e.g.
 *   `EXC_CRASH (SIGABRT)`. Parsed locally from the first 64KB.
 * - **Reason** = termination info (`termination.namespace/code/indicator`
 *   or legacy `Termination Reason`), e.g. `Namespace SPRINGBOARD,
 *   Code 0x8badf00d` (watchdog kill).
 * - **.ips file** = JSON since iOS 15: one metadata object + one
 *   report object (exception, termination, threads, binary images).
 */

export type CrashKindId = 'crash' | 'jetsam' | 'panic' | 'unknown';

export interface CrashKindMeta {
  id: CrashKindId;
  /** Pill label. */
  label: string;
  /** One-line explanation — also the pill `title` tooltip. */
  tooltip: string;
  /** Longer card text for the "How is each crash classified?" help. */
  long: string;
  /** What the filter keeps, in plain words. */
  includes: string;
  /** When to reach for this filter. */
  whenToUse: string;
}

export const CRASH_KIND_ORDER: CrashKindId[] = ['crash', 'jetsam', 'panic'];

export const CRASH_KINDS: Record<CrashKindId, CrashKindMeta> = {
  crash: {
    id: 'crash',
    label: 'crash',
    tooltip: 'App or system process crash (.ips) — ReportCrash wrote a file for a dead process.',
    long: 'A process died abnormally: unhandled exception, bad memory access, abort(), or killed by another component. The .ips file holds the exception type, termination reason and thread backtraces — that file is the evidence.',
    includes: 'Keeps app / system crashes.',
    whenToUse: 'Start here: one app repeating is a lead; scattered singles are noise.',
  },
  jetsam: {
    id: 'jetsam',
    label: 'jetsam',
    tooltip: 'Jetsam / low-memory kill — iOS terminated the process under memory pressure, not a bug in that app alone.',
    long: 'iOS has no swap: under memory pressure the kernel (memorystatus) kills processes, largest-first. The JetsamEvent report lists every process and the kill reason (per-process-limit, vm-pageshortage, …) — there are no thread backtraces to symbolicate.',
    includes: 'Keeps low-memory kills.',
    whenToUse: 'Apps that "crash" under load with low-memory log lines — read the Jetsam report, not just the log tail.',
  },
  panic: {
    id: 'panic',
    label: 'panic',
    tooltip: 'Kernel panic — the whole device went down or nearly did; always worth opening.',
    long: 'The kernel itself hit an unrecoverable state and the device rebooted. Unlike an app crash, a panic implicates hardware, drivers or the kernel — never just one app. Check the timestamp against unexpected reboots.',
    includes: 'Keeps kernel panics.',
    whenToUse: 'Any unexpected reboot — open the panic log first, then look for patterns.',
  },
  unknown: {
    id: 'unknown',
    label: '?',
    tooltip: 'Unclassified crash file — name has no crash-ish extension.',
    long: 'The file did not match any known crash pattern. It is kept so nothing is hidden, but it rarely carries a parseable header.',
    includes: 'Keeps unclassified files.',
    whenToUse: 'Only when hunting a missing file.',
  },
};

/** One exception / termination pattern worth recognizing. `hint` is the
 *  clickable filter text; `tooltip` stays the one-liner. */
export interface CrashSubtype {
  hint: string;
  /** One-liner — chip `title` tooltip. */
  tooltip: string;
  /** What this pattern usually means (1–2 sentences). */
  what: string;
  /** What to do when you keep seeing it. */
  action: string;
}

export const CRASH_SUBTYPES: CrashSubtype[] = [
  {
    hint: 'EXC_CRASH (SIGABRT)',
    tooltip: 'Abort signal — unhandled language exception (e.g. NSException), failed assertion, or abort() called.',
    what: 'The classic app crash: an Objective-C/Swift exception propagated without a handler, or code called abort(). Pairs with a Last Exception Backtrace naming the throwing frame.',
    action: 'Note the exception name, match app + date, reproduce the triggering action.',
  },
  {
    hint: 'EXC_CRASH (SIGKILL)',
    tooltip: 'Killed by the system — watchdog, memory limit, or force-quit. Check the termination reason.',
    what: 'The OS terminated the process: watchdog timeout (0x8badf00d), exceeded a resource limit, or the user force-quit. The reason field, not the signal, tells which.',
    action: 'Read the reason: 0x8badf00d = hung (watchdog); Jetsam reason = memory; else check who killed it (byProc).',
  },
  {
    hint: 'EXC_BAD_ACCESS (SIGSEGV)',
    tooltip: 'Segmentation fault — invalid or out-of-bounds memory address.',
    what: 'The process touched memory it does not own: dangling pointer, out-of-bounds index at the native level, or use-after-free.',
    action: 'Needs the symbolicated backtrace — the crashing thread and binary image point at the faulty code.',
  },
  {
    hint: 'EXC_BAD_ACCESS (SIGBUS)',
    tooltip: 'Bus error — misaligned address or pointer-authentication failure.',
    what: 'Like SIGSEGV but the address itself is malformed: misaligned access or an ARM pointer-authentication failure.',
    action: 'Same as SIGSEGV: symbolicate, then inspect the faulting thread.',
  },
  {
    hint: 'EXC_BREAKPOINT (SIGTRAP)',
    tooltip: 'Breakpoint trap — violated requirement or Swift runtime trap (e.g. failed force-unwrap).',
    what: 'Swift traps (unexpected nil, out-of-range, failed cast) and explicit breakpoints surface here. In release builds it is almost always a language-level trap.',
    action: 'Look for the Swift trap message in the reason; match to the source line after symbolication.',
  },
  {
    hint: 'EXC_RESOURCE',
    tooltip: 'Resource limit exceeded — CPU time, memory, or I/O (look for the subtype).',
    what: 'The OS stopped a runaway process: too much CPU, too many wakeups, or too much memory. The subtype names the exhausted resource.',
    action: 'Read the subtype + reason: CPU = hot loop; memory = pairs with Jetsam; wakeups = background abuse.',
  },
  {
    hint: '0x8badf00d',
    tooltip: 'Watchdog kill — the app hung (ate bad food): foreground too long at launch, or blocked the main thread.',
    what: 'SpringBoard’s watchdog terminates unresponsive apps. The termination namespace is SPRINGBOARD with code 0x8badf00d ("ate bad food").',
    action: 'Inspect what the main thread was doing — the backtrace shows where it was stuck.',
  },
  {
    hint: 'per-process-limit',
    tooltip: 'Jetsam reason — the process crossed its own resident-memory limit.',
    what: 'The single most common Jetsam cause for one app: it grew past the per-process ceiling and became eligible for termination, even if the device had free memory elsewhere.',
    action: 'Reduce that app’s footprint; multiply rpages × pageSize (usually 16384) for bytes used.',
  },
  {
    hint: 'vm-pageshortage',
    tooltip: 'Jetsam reason — system-wide free-page shortage; background deaths protect the foreground app.',
    what: 'The whole device ran short of free pages, so the system reclaimed background processes to keep the foreground app alive. Your app may be the victim, not the cause.',
    action: 'Check largestProcess: if it is not your app, the pressure came from elsewhere.',
  },
];

export const JETSAM_REASONS: { reason: string; blurb: string }[] = [
  { reason: 'per-process-limit', blurb: 'Crossed its own memory ceiling — the top cause for a single app.' },
  { reason: 'vm-pageshortage', blurb: 'System-wide page shortage — background kills protect the foreground app.' },
  { reason: 'vnode-limit', blurb: 'Too many open files system-wide — kills free vnodes, not the culprit.' },
  { reason: 'highwater', blurb: 'A daemon exceeded its expected footprint.' },
  { reason: 'fc-thrashing', blurb: 'File-cache thrashing — mapped files churned too fast.' },
  { reason: 'jettisoned', blurb: 'Jettisoned for another reason — neither per-process nor page-shortage.' },
];

/**
 * Most common report names in the crash store. `filter` is the clickable
 * text placed in the filter box (matches filename, app, exception, reason).
 * Kind is where the file lands in freetunes' own kind filter.
 *
 * Sources: Apple "Interpreting the JSON format of a crash report"
 * (bug_type 309 crash / 288 stackshot, two JSON objects), Apple
 * "Identifying high-memory use with Jetsam event reports" (bug_type 298,
 * process table + reason + largestProcess, no backtrace), Apple Support
 * Community first-line samples (panic-full bug_type 210 with panicString,
 * ResetCounter bug_type 115 with Reset/Boot-failure counts), and the
 * `softwareupdated` OTA daemon seen as a normal entry in Jetsam process
 * tables.
 */
export interface CommonCrashReport {
  /** Display name (parsed app name). */
  name: string;
  /** Text placed in the filter box when clicked. */
  filter: string;
  kind: CrashKindId;
  /** One-liner — chip `title` tooltip. */
  tooltip: string;
  /** What this report is (1–2 sentences). */
  what: string;
  /** What to do when you keep seeing it. */
  action: string;
}

export const COMMON_CRASH_REPORTS: CommonCrashReport[] = [
  {
    name: 'JetsamEvent',
    filter: 'JetsamEvent',
    kind: 'jetsam',
    tooltip: 'Low-memory system report (bug_type 298) — iOS killed processes under memory pressure, not one app crashing.',
    what: 'A device-wide memory snapshot: every process with its page count, the kill reason on the jettisoned process only, and largestProcess naming the hungriest one. There is no thread backtrace to symbolicate.',
    action: 'Read the Reason (per-process-limit = that app grew too big; vm-pageshortage = victim, check largestProcess), then free memory or lighten the hungriest app.',
  },
  {
    name: 'OTAUpdate',
    filter: 'OTAUpdate',
    kind: 'crash',
    tooltip: 'Software-update system report — the iOS OTA pipeline (softwareupdated), not a third-party app crash.',
    what: 'Files from the over-the-air update machinery checking, downloading or preparing iOS. A small run (e.g. ×3) right after an update attempt is expected bookkeeping noise.',
    action: 'If Settings → General → Software Update succeeds, ignore them. If updates fail, free storage, fix network, retry — then check whether new ones stop appearing.',
  },
  {
    name: 'SpringBoard',
    filter: 'SpringBoard',
    kind: 'crash',
    tooltip: 'Home-screen / app-launcher crash — SpringBoard died and the UI restarted.',
    what: 'SpringBoard owns the home screen, app launching and the watchdog that kills hung apps (0x8badf00d). One stray file is noise; repeats mean system instability.',
    action: 'Note the iOS version and what you were doing (launching which app?), match app + date, reproduce — scattered singles are noise.',
  },
  {
    name: 'backboardd',
    filter: 'backboardd',
    kind: 'crash',
    tooltip: 'Touch / display server crash — backboardd feeds touch events to the screen.',
    what: 'A core system daemon between the touchscreen/display and apps. Crashes here blank or freeze touch rather than killing one app.',
    action: 'One file after a hard knock or deep discharge is noise; repeats with touch freezes point at digitizer/display hardware or a bad reboot — back up, update iOS, re-test.',
  },
  {
    name: 'panic-full',
    filter: 'panic-full',
    kind: 'panic',
    tooltip: 'Kernel panic (bug_type 210) — the whole device went down; the panicString names the subsystem.',
    what: 'The kernel hit an unrecoverable state and rebooted. The report carries a panicString (first line is the verdict), kernel backtrace and loaded kexts — never one app’s bug.',
    action: 'Match the timestamp against unexpected reboots, read the first panicString line (SMC/sensor lines implicate flexes and battery), and treat repeats as hardware until proven otherwise.',
  },
  {
    name: 'ResetCounter',
    filter: 'ResetCounter',
    kind: 'panic',
    tooltip: 'Unexpected reboot without a panic (bug_type 115) — Reset count + Boot failure count, no panicString.',
    what: 'The device rebooted but left no kernel panic behind, so the log records reset/boot-failure counts and boot faults instead. Common after a forced restart or a power cut.',
    action: 'A single file after you force-restarted is noise. Repeats with no panic-full alongside mean unstable power/boot — check battery health, cable/charger, and update iOS.',
  },
  {
    name: 'ThermalEvent',
    filter: 'ThermalEvent',
    kind: 'crash',
    tooltip: 'Thermal / stackshot snapshot (bug_type 288 family) — a diagnostic sample, not a fatal crash.',
    what: 'The system sampled all threads under thermal pressure or a watchdog window. Like Jetsam it describes the device, not one dead process — there is little to symbolicate.',
    action: 'Ignore singles. Clusters with hot-device log lines (thermal, throttle) mean heat or sustained load — cool down, close heavy apps, re-test cold.',
  },
  {
    name: 'Third-party app',
    filter: '',
    kind: 'crash',
    tooltip: 'Third-party / Apple app crash (bug_type 309) — exception + termination reason + thread backtraces.',
    what: 'A normal crash report: Mach exception + BSD signal (how it died), termination namespace/code (who killed it), and the faulting thread. This is the file to symbolicate.',
    action: 'Match app + date, read Exception and Reason, reproduce the triggering action — one app repeating is a lead.',
  },
];

/** How `.ips` files work, in one paragraph (help intro tooltip). */
export const IPS_GUIDE =
  'Since iOS 15 crash reports are JSON (.ips): line 1 is metadata (bug_type, OS, name), ' +
  'the rest is the report. freetunes parses SpringBoard-2026-09-10.ips → app SpringBoard, ' +
  'date 2026-09-10 from the filename, kind from the real bug_type first ' +
  '(309 crash, 298 JetsamEvent, 210 panic-full, 115 ResetCounter, 288 stackshot) with the ' +
  'filename as fallback, and exception / reason / OS from the first 64KB — locally, never uploaded. ' +
  'Jetsam reports (298) carry a process table instead of backtraces; panic-full (210) carries a ' +
  'panicString; ResetCounter (115) carries reset/boot-failure counts; all three have no Mach exception by design.';

/** Tooltip for a kind pill: why this color. */
export function crashKindTooltip(kind: string): string {
  const k = (kind || 'crash').toLowerCase() as CrashKindId;
  const meta = CRASH_KINDS[k] ?? CRASH_KINDS.crash;
  return `${meta.label} — ${meta.tooltip}`;
}

/** Short "what it means" line for an expanded row, from exception/reason. */
export function crashMeaning(exception: string, reason: string): string {
  const exc = (exception || '').toUpperCase();
  const rsn = (reason || '').toLowerCase();
  if (rsn.includes('reset count') || rsn.includes('boot failure'))
    return 'Unexpected reboot without a panic (ResetCounter): the device went down but left no panicString. Singles after a forced restart are noise; repeats mean unstable power/boot.';
  if (rsn.includes('8badf00d') || rsn.includes('watchdog'))
    return 'Watchdog kill: the app hung and SpringBoard terminated it (0x8badf00d). The main-thread backtrace shows where it was stuck.';
  if (exc.includes('SIGABRT') || exc.includes('EXC_CRASH'))
    return 'Aborted: usually an unhandled exception or failed assertion. The Last Exception Backtrace names the throwing frame.';
  if (exc.includes('SIGSEGV') || exc.includes('SIGBUS') || exc.includes('BAD_ACCESS'))
    return 'Bad memory access: the process touched an address it does not own. Symbolicate the crashing thread.';
  if (exc.includes('BREAKPOINT') || exc.includes('SIGTRAP') || exc.includes('SIGILL'))
    return 'Trap: a Swift runtime trap or violated requirement. Look for the trap message in the reason.';
  if (exc.includes('RESOURCE'))
    return 'Resource limit: the OS stopped a runaway process. The subtype names the exhausted resource.';
  if (rsn.includes('per-process-limit') || rsn.includes('vm-pageshortage') || rsn.includes('jetsam'))
    return 'Low-memory kill: Jetsam freed this process under pressure. Check the Jetsam process table, not a backtrace.';
  if (exc.includes('PANIC') || rsn.includes('panic'))
    return 'Kernel panic: the whole device went down. Match the timestamp against unexpected reboots.';
  return '';
}
