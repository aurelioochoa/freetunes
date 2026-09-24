/**
 * Device-log taxonomy: filter levels + classification keywords.
 *
 * Mirrors `backend/app/services/diagnostics.py` (`LEVEL_INFO`,
 * `ERROR_HINT_INFO`, `WARN_HINT_INFO`). Keep both sides in sync: the backend
 * decides the level, the viewer only explains it.
 *
 * Correct names — "tipo/subtipo" was wrong, don't use it:
 * - **Filter level** = the `level=` filter: all | warn | error | info.
 *   This is freetunes' own filter, NOT Apple's log level.
 * - **Classification keyword** = the word that pushed one line into
 *   error/warn (`match` on each `SyslogEntry`). Info lines have none.
 * - **iOS level tag** = Apple's own `<Debug> <Info> <Notice> <Error> …`
 *   tag from the unified logging system (`os_log`). freetunes only sees it
 *   as text: `<Error>` contains "error", `<Notice>` contains "notice".
 * - **Process** = who wrote the line (`proc` on each entry).
 */

export type LogLevelId = 'all' | 'warn' | 'error' | 'info';
export type LogRowLevel = 'error' | 'warn' | 'info';

export interface LogLevelMeta {
  id: LogLevelId;
  /** Segment button label. */
  label: string;
  /** One-line explanation — also the button `title` tooltip. */
  tooltip: string;
  /** Longer card text for the “How is each line classified?” help. */
  long: string;
  /** What the filter keeps, in plain words. */
  includes: string;
  /** When to reach for this filter. */
  whenToUse: string;
}

export const LOG_LEVEL_ORDER: LogLevelId[] = ['all', 'warn', 'error', 'info'];

export const LOG_LEVELS: Record<LogLevelId, LogLevelMeta> = {
  all: {
    id: 'all',
    label: 'All',
    tooltip: 'All lines, unfiltered — the raw tail as iOS wrote it.',
    long: 'No freetunes filtering. iOS writes Debug through Fault into one stream; you see it all, newest last.',
    includes: 'Keeps every line.',
    whenToUse: 'Start here to see the raw tail, then narrow down.',
  },
  warn: {
    id: 'warn',
    label: 'Warnings+',
    tooltip: 'Warnings AND errors — start here when asking “is something wrong?”.',
    long: 'Every warning plus every error. Info chatter is hidden, so a repeated red/amber process stands out.',
    includes: 'Keeps warn + error lines.',
    whenToUse: 'The best default when hunting problems.',
  },
  error: {
    id: 'error',
    label: 'Errors',
    tooltip: 'Only errors — failures, the smallest and most serious slice.',
    long: 'Only lines with a failure keyword. When this is empty, there is no smoking gun in the current window — widen to Warnings+.',
    includes: 'Keeps error lines only.',
    whenToUse: 'Find the one failure behind a symptom.',
  },
  info: {
    id: 'info',
    label: 'Info',
    tooltip: 'Routine chatter with no error/warn keyword — the largest, noisiest slice.',
    long: 'Everything left over: normal heartbeats from configd, wifid, SpringBoard and friends. Noisy by design — a quiet phone still streams little, a busy one streams a lot. By itself it never means “healthy” or “sick”.',
    includes: 'Keeps info lines only.',
    whenToUse: 'Check what the phone was doing around a timestamp, or confirm a process is alive at all.',
  },
};

/** A word that pushes a line into red/amber. `tooltip` stays the one-liner
 *  (backend `*_HINT_INFO` mirrors it); `what` + `action` power the legend. */
export interface LogSubtype {
  keyword: string;
  level: LogRowLevel;
  /** One-liner — tooltip + legend title (mirrored in the backend). */
  tooltip: string;
  /** What this word usually means on iOS (2–3 sentences). */
  what: string;
  /** What to do when you keep seeing it. */
  action: string;
  /** Short realistic fragment, shown in the legend. */
  example: string;
}

/** Error keywords — any of these words makes a line red. Checked first,
 *  so they win over warning words. */
export const ERROR_SUBTYPES: LogSubtype[] = [
  {
    keyword: 'error', level: 'error',
    tooltip: 'Generic failure word; also matches Apple’s own <Error> tag (os_log_error, always persisted).',
    what: 'The catch-all: either a component writing the word “error”, or Apple’s <Error> level tag from the unified logging system (os_log_error), which the system always persists to disk.',
    action: 'Group by process: one process repeating “error” is a lead; scattered single errors are usually noise.',
    example: 'backupd error: snapshot failed',
  },
  {
    keyword: 'fault', level: 'error',
    tooltip: 'Apple’s most serious level (os_log_fault): a component reporting itself as broken, with extra diagnostics captured.',
    what: 'Fault is the top of Apple’s scale — above error. Code logs a fault when an invariant breaks (a state that should be impossible). The system captures richer diagnostics for faults than for plain errors.',
    action: 'Treat like an error but heavier: note the process and look for a matching crash report.',
    example: 'os_fault in mediaserverd',
  },
  {
    keyword: 'failed', level: 'error',
    tooltip: 'An operation ran and finished as a failure — often retryable.',
    what: 'Something was attempted and did not succeed: a snapshot, a sync, a network request, a write. Often followed by a retry or a fallback, which is why “failed” alone is not proof anything is broken.',
    action: 'Read the next lines: “failed … retrying … ok” is transient; “failed” looping every few seconds is the real problem.',
    example: 'snapshot failed, retrying',
  },
  {
    keyword: 'crash', level: 'error',
    tooltip: 'A process died abnormally — iOS’s ReportCrash writes a .ips file for it.',
    what: 'The process terminated unexpectedly (exception, bad memory access, watchdog kill). Apple documents crash reports as the record of how the app terminated, including the code on each thread.',
    action: 'Open the Crash reports card and match app + date — the .ips file is the primary evidence, the log line is just the pointer.',
    example: 'SpringBoard crash detected',
  },
  {
    keyword: 'panic', level: 'error',
    tooltip: 'Kernel panic — the whole device went down or nearly did; always worth opening.',
    what: 'A panic means the kernel itself hit an unrecoverable state and the device rebooted (or froze on the way). Unlike an app crash, a panic implicates hardware, drivers or the kernel — never just one app.',
    action: 'Always open it: check the timestamp against unexpected reboots, then look for a panic log (panic-*.ips) alongside normal crash reports.',
    example: 'panic: kernel trap',
  },
  {
    keyword: 'exception', level: 'error',
    tooltip: 'Unhandled exception thrown by app or system code (e.g. NSException).',
    what: 'An Objective-C/Swift exception propagated without a handler — bad argument, out-of-bounds access, violated assertion. It usually ends the process, so it pairs with a crash report.',
    action: 'Note the exception name if shown, match it to the .ips file, and reproduce the triggering action.',
    example: 'uncaught exception NSRange',
  },
  {
    keyword: 'denied', level: 'error',
    tooltip: 'Sandbox/permission refusal — iOS blocked something an app tried (Apple documents these as sandbox violations).',
    what: 'Apple’s sandbox stops processes from exceeding their privileges (file writes, network, device access) and the denial is logged, e.g. “Sandbox: App deny(1) file-write /path”. Denials are enforcement working as designed, not a bug in iOS.',
    action: 'Check what was blocked and which app: a blocked path your workflow needs is a lead; background denials from system daemons are usually harmless.',
    example: 'sandbox denied file-write',
  },
  {
    keyword: 'timeout', level: 'error',
    tooltip: 'Timed out waiting — network, lock or IPC reply that never came.',
    what: 'An operation waited longer than its deadline: sync, backup, network request, inter-process reply. Timeouts are the classic transient failure — they happen on bad networks and busy systems.',
    action: 'Transient once; a pattern if it repeats at fixed intervals or for one host — then check connectivity and the other endpoint.',
    example: 'sync timeout after 30s',
  },
  {
    keyword: 'corrupt', level: 'error',
    tooltip: 'Corrupt data detected — file, database or cache header that does not parse.',
    what: 'A component read data that fails validation: truncated file, bad database page, damaged cache. Unlike timeouts, corruption does not heal by retrying — the bytes themselves are suspect.',
    action: 'Back up first, then re-sync or restore that data; if several processes report corruption, suspect storage rather than one app.',
    example: 'corrupt database header',
  },
];

/** Warning keywords — any of these words makes a line amber, unless an
 *  error word in the same line already made it red. */
export const WARN_SUBTYPES: LogSubtype[] = [
  {
    keyword: 'warn', level: 'warn',
    tooltip: 'Generic caution word — including iOS low-memory (Jetsam) warnings.',
    what: 'The catch-all for caution: memory warnings, resource warnings, API warnings. Apple’s Jetsam memory system also surfaces through “memory warn” style lines before the system starts killing processes.',
    action: 'Read the noun after “warn”: memory/disk/battery warnings deserve attention, vague ones usually do not.',
    example: 'memory warn: Jetsam',
  },
  {
    keyword: 'notice', level: 'warn',
    tooltip: 'Matches Apple’s <Notice> tag — the default os_log level: routine, persisted chatter.',
    what: 'In Apple’s unified logging, the default level shows as <Notice>. It is persisted to disk and carries no severity by itself — most wifid/configd routine lines wear this tag. freetunes flags it as a warning only so Warnings+ stays a useful “not-info” bucket.',
    action: 'Ignore single notices; only clusters from one process around a symptom matter.',
    example: 'wifid(WiFiPolicy)[54] <Notice>',
  },
  {
    keyword: 'throttle', level: 'warn',
    tooltip: 'The device is deliberately slowing something down — power, thermal or policy.',
    what: 'Throttling is iOS protecting itself: reducing CPU, radio, background work or charging rate to stay within power/thermal/policy budgets. The throttled work is delayed, not failed.',
    action: 'Check for sibling thermal/low-power lines; if the phone is hot or in Low Power Mode, throttling is expected.',
    example: 'throttled for 2s',
  },
  {
    keyword: 'low', level: 'warn',
    tooltip: 'Low resource — memory, disk, battery or signal. Memory pressure can end in Jetsam kills.',
    what: '“Low” always quantifies a resource running out. Low memory is the sharpest: Apple’s Jetsam mechanism kills processes (largest first) when pages run out, which then looks like a crash. Low disk/battery/signal degrade features instead of killing.',
    action: 'Check storage and battery; if apps “crash” under load with low-memory lines nearby, read the Jetsam event report, not just the log tail.',
    example: 'low memory warning',
  },
  {
    keyword: 'deprecat', level: 'warn',
    tooltip: 'Deprecated API in use — developer noise, harmless unless it is your app.',
    what: 'A process called an API Apple marked deprecated. The call still works; the warning exists for developers to migrate before a future iOS removes it.',
    action: 'Ignore unless you develop the app named in the line.',
    example: 'deprecated API usage',
  },
  {
    keyword: 'retry', level: 'warn',
    tooltip: 'The operation will be retried — transient by definition; loops are the problem.',
    what: 'A failure with a plan: the component schedules another attempt. One retry that succeeds is the system working; retries that never succeed are a failure wearing a warning word.',
    action: 'Watch the outcome: “retry … ok” is fine, “retry” every N seconds forever is the symptom to chase.',
    example: 'will retry in 5s',
  },
  {
    keyword: 'slow', level: 'warn',
    tooltip: 'Slow operation — a performance hint, not a failure.',
    what: 'Something took longer than its budget: frame commit, launch, IPC reply. Slow lines mark where time went, which is why they cluster around hangs and stutters rather than crashes.',
    action: 'Note the process and duration; pair with timeouts or watchdog lines if the UI actually hung.',
    example: 'slow frame commit',
  },
  {
    keyword: 'thermal', level: 'warn',
    tooltip: 'Thermal pressure — the device is warm and may throttle CPU, radio or charging.',
    what: 'iOS monitors temperature and sheds load before damage: throttling performance, dimming, pausing charging. Thermal lines explain a whole class of “slow while hot” behavior.',
    action: 'Cool down, remove the case, unplug if charging; re-test cold before blaming an app.',
    example: 'thermal warn: throttled',
  },
];

export const SUBTYPE_BY_KEYWORD: Record<string, LogSubtype> = Object.fromEntries(
  [...ERROR_SUBTYPES, ...WARN_SUBTYPES].map((s) => [s.keyword, s]),
);

/** What the Info filter is and is not. Info has no keywords by definition. */
export const INFO_GUIDE = {
  title: 'Info — routine iOS chatter',
  what: 'Info is the remainder: every line with none of the 17 keywords above. It is mostly Apple’s Debug/Info/Default levels doing their job — heartbeats, state changes, successful operations.',
  noisy: 'It is the largest slice by far, and its volume says nothing about health: a locked phone streams almost nothing, an unlocking phone bursts. Never read “many info lines” as a problem.',
  tip: 'Use Info to answer “was the process alive?” and “what happened right before timestamp T?” — then switch back to Warnings+ for verdicts.',
};

/** Processes you will meet constantly, so info lines read less cryptic. */
export const COMMON_PROCS: { name: string; blurb: string }[] = [
  { name: 'kernel', blurb: 'The core itself — memory (Jetsam), panics, IOSurface spam.' },
  { name: 'SpringBoard', blurb: 'Home screen + app launching; crashes here kill the UI.' },
  { name: 'backboardd', blurb: 'Touch/display pipeline; hangs show up here first.' },
  { name: 'configd', blurb: 'System configuration daemon — constant, mostly harmless.' },
  { name: 'wifid', blurb: 'Wi-Fi policy and scans; the classic <Notice> chatterbox.' },
  { name: 'backupd', blurb: 'Backup engine — “error/failed” here threatens backups.' },
  { name: 'CommCenter', blurb: 'Cellular radio; signal/timeout lines belong here.' },
  { name: 'mDNSResponder', blurb: 'Local networking (Bonjour/AirPlay discovery).' },
  { name: 'identityservicesd', blurb: 'Apple ID / iMessage / FaceTime identity traffic.' },
  { name: 'mediaserverd', blurb: 'Audio/video pipeline; faults here break playback.' },
];

/** Apple’s own level tags, as they appear inside relayed lines. */
export const IOS_TAGS_GUIDE =
  'Apple’s unified logging (os_log) grades severity as Debug < Info < Default (<Notice>) < Error < Fault. ' +
  'Debug lives in memory only; Info/Default/Notice are routine and persisted; Error/Fault are always persisted. ' +
  'freetunes does not read the tag — it matches words, so <Error> lands in Errors via “error” and <Notice> lands in Warnings via “notice”.';

/** Client-side fallback when an entry predates the backend `match` field. */
export function matchHint(line: string): { level: LogRowLevel; keyword: string } {
  const low = (line || '').toLowerCase();
  for (const s of ERROR_SUBTYPES) {
    if (s.keyword && low.includes(s.keyword)) return { level: 'error', keyword: s.keyword };
  }
  for (const s of WARN_SUBTYPES) {
    if (s.keyword && low.includes(s.keyword)) return { level: 'warn', keyword: s.keyword };
  }
  return { level: 'info', keyword: '' };
}

/** Tooltip for a log row badge: why this color. */
export function rowLevelTooltip(level: LogRowLevel, keyword: string): string {
  if (level === 'error') {
    const sub = SUBTYPE_BY_KEYWORD[keyword];
    return sub
      ? `Error — matched “${keyword}”: ${sub.tooltip}`
      : 'Error — contains a failure keyword (error, crash, denied, …).';
  }
  if (level === 'warn') {
    const sub = SUBTYPE_BY_KEYWORD[keyword];
    return sub
      ? `Warning — matched “${keyword}”: ${sub.tooltip}`
      : 'Warning — contains a caution keyword (warn, retry, thermal, …).';
  }
  return 'Info — routine iOS chatter, no error/warn keyword matched.';
}

export const PROC_TOOLTIP =
  'Process that wrote this line — parsed from “proc[pid]:” or “proc(subsystem)[pid] <Level>:”. Try it in the search box to isolate one app.';
