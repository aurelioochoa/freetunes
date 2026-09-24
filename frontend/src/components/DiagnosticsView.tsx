import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, type CrashDetail, type CrashItem, type DiagSummary, type SyslogEntry, type SyslogResult, type Verification } from '../api';
import GlassSelect from './GlassSelect';
import {
  COMMON_PROCS,
  ERROR_SUBTYPES,
  IOS_TAGS_GUIDE,
  LOG_LEVEL_ORDER,
  LOG_LEVELS,
  PROC_TOOLTIP,
  WARN_SUBTYPES,
  matchHint,
  rowLevelTooltip,
  type LogLevelId,
} from '../logLevels';
import {
  COMMON_CRASH_REPORTS,
  CRASH_KINDS,
  CRASH_SUBTYPES,
  IPS_GUIDE,
  JETSAM_REASONS,
  crashKindTooltip,
  crashMeaning,
  type CrashKindId,
} from '../crashLevels';

/** Which classification keyword decided a row's color (backend `match`, else local). */
function matchOf(entry: SyslogEntry): string {
  if (entry.match) return entry.match;
  return matchHint(entry.text).keyword;
}

function entriesOf(log: SyslogResult | null): SyslogEntry[] {
  if (!log) return [];
  if (log.entries && log.entries.length > 0) {
    return log.entries.map((e) => ({
      ...e,
      level: e.level === 'error' || e.level === 'warn' ? e.level : 'info',
      match: e.match ?? matchHint(e.text).keyword,
    }));
  }
  if (!log.lines) return [];
  return log.lines.split('\n').filter(Boolean).map((text) => {
    const m = matchHint(text);
    return { text, level: m.level, match: m.keyword };
  });
}

function fmtBytes(size: number): string {
  if (!size || size <= 0) return '—';
  if (size < 1024) return `${size} B`;
  const units = ['KB', 'MB', 'GB'];
  let v = size / 1024;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
  return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${units[u]}`;
}

function fmtCrashDate(c: CrashItem): { label: string; title: string } {
  const raw = c.date || (c.mtime ? c.mtime.slice(0, 10) : '');
  if (!raw) return { label: '—', title: c.filename };
  let rel = '';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(raw);
  if (m) {
    const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    const days = Math.round((Date.now() - d.getTime()) / 86400000);
    if (days === 0) rel = ' · today';
    else if (days === 1) rel = ' · yesterday';
    else if (days > 1 && days < 60) rel = ` · ${days}d ago`;
  } else if (c.mtime) {
    const d = new Date(c.mtime);
    if (!Number.isNaN(d.getTime())) {
      const days = Math.round((Date.now() - d.getTime()) / 86400000);
      if (days >= 0 && days < 60) rel = ` · ${days}d ago`;
    }
  }
  const full = c.mtime && c.date && c.mtime !== c.date ? `${c.date} (file ${c.mtime})` : (c.mtime || c.date || c.filename);
  return { label: `${raw}${rel}`, title: `${c.filename}${full ? ` · ${full}` : ''}` };
}

function crashKindOf(c: CrashItem): string {
  return (c.kind || 'crash').toLowerCase();
}

function crashKindMeta(kind: string): { label: string; title: string } {
  const k = (kind || 'crash').toLowerCase() as CrashKindId;
  const meta = (CRASH_KINDS as Record<string, { label: string; tooltip: string }>)[k]
    ?? CRASH_KINDS.crash;
  return { label: meta.label, title: crashKindTooltip(k) };
}

function fmtCrashException(c: CrashItem): { label: string; title: string } {
  const exc = (c.exception || '').trim();
  const rsn = (c.reason || '').trim();
  const kind = (c.kind || 'crash').toLowerCase();
  // Jetsam / panic-full / ResetCounter reports carry no Mach exception by
  // design (process table / panicString / reset counts instead) — the
  // Reason row is the evidence there, so say so instead of a bare "—".
  const noExcByDesign = kind === 'jetsam' || kind === 'panic';
  if (!exc && !rsn)
    return {
      label: '—',
      title: noExcByDesign
        ? 'No Mach exception — expected for this kind (Jetsam carries a process table, panic-full a panicString, ResetCounter reset counts). Read the Reason row.'
        : 'No exception parsed from the .ips header — open the row for the file preview.',
    };
  if (exc && !rsn) return { label: exc, title: `Exception: ${exc} — open the row for what it means.` };
  if (!exc && rsn) return { label: rsn.slice(0, 48), title: `Termination: ${rsn}` };
  return { label: exc, title: `Exception: ${exc}\nTermination: ${rsn}` };
}

function crashesToCsv(rows: CrashItem[]): string {
  const esc = (v: string | number) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const head = 'filename,app,date,mtime,kind,size,exception,reason,os_version';
  const lines = rows.map((c) => [
    esc(c.filename), esc(c.app || ''), esc(c.date || ''), esc(c.mtime || ''),
    esc(crashKindOf(c)), c.size || 0, esc(c.exception || ''), esc(c.reason || ''), esc(c.os_version || ''),
  ].join(','));
  return [head, ...lines].join('\n');
}

type LogLevel = LogLevelId;

const KIND_PILL: Record<string, string> = {
  'retail-new': 'push',
  personalized: 'push',
  refurbished: 'delete',
  replacement: 'delete',
  unknown: 'skip',
};

const KIND_LABEL: Record<string, string> = {
  'retail-new': 'Retail new',
  personalized: 'Personalized',
  refurbished: 'Refurbished?',
  replacement: 'Replacement',
  unknown: 'Unknown',
};

export default function DiagnosticsView({ udid }: { udid: string }) {
  const [summary, setSummary] = useState<DiagSummary | null>(null);
  const [ver, setVer] = useState<Verification | null>(null);
  const [crashes, setCrashes] = useState<CrashItem[]>([]);
  const [log, setLog] = useState<SyslogResult | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [logState, setLogState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [crashState, setCrashState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [crashQuery, setCrashQuery] = useState('');
  const [crashSort, setCrashSort] = useState<'date' | 'name' | 'size'>('date');
  const [crashKind, setCrashKind] = useState<'all' | 'crash' | 'jetsam' | 'panic'>('all');
  const [visibleCrashes, setVisibleCrashes] = useState(100);
  const [expandedCrash, setExpandedCrash] = useState<string | null>(null);
  const [crashDetails, setCrashDetails] = useState<Record<string, CrashDetail>>({});
  const [crashDetailLoading, setCrashDetailLoading] = useState<string | null>(null);
  const [logQuery, setLogQuery] = useState('');
  const [logLevel, setLogLevel] = useState<LogLevel>('all');
  const [lineCount, setLineCount] = useState(100);
  const [copied, setCopied] = useState<'log' | 'ver' | 'crash' | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  // Web log viewer: colorized `pretty` rows vs the classic `raw` <pre>.
  const [logView, setLogView] = useState<'pretty' | 'raw'>(() => {
    try { return (localStorage.getItem('freetunes-log-view') as 'pretty' | 'raw') || 'pretty'; }
    catch { return 'pretty'; }
  });
  // Real-time tail over SSE (`/diagnostics/syslog/stream`).
  const [liveTail, setLiveTail] = useState(false);
  const [streamRows, setStreamRows] = useState<SyslogEntry[]>([]);
  const [streamLive, setStreamLive] = useState<boolean | null>(null);
  const [streamError, setStreamError] = useState(false);
  // A quiet (sleeping/locked) iPhone streams almost nothing: after a few
  // seconds of live silence, say so instead of spinning forever.
  const [streamQuiet, setStreamQuiet] = useState(false);
  const [follow, setFollow] = useState(true);
  const logScrollRef = useRef<HTMLDivElement | null>(null);
  // Request ids: on page refresh the first fetch starts with udid='' and a
  // second starts once the device list loads — the slower first response
  // must never clobber the fresh one (that was the appear-then-vanish bug).
  const diagReq = useRef(0);
  const crashReq = useRef(0);

  function changeLogView(v: 'pretty' | 'raw') {
    setLogView(v);
    try { localStorage.setItem('freetunes-log-view', v); } catch { /* private mode */ }
  }

  const loadCrashes = useCallback(async () => {
    if (!udid) {
      setCrashes([]);
      setCrashState('ready');
      return;
    }
    const id = ++crashReq.current;
    setCrashState('loading');
    try {
      const c = await api.crashes(udid).catch(() => null);
      if (id !== crashReq.current) return; // superseded — keep the fresh data
      if (c === null) throw new Error('crash fetch failed');
      setCrashes(c ?? []);
      setCrashState('ready');
    } catch {
      if (id !== crashReq.current) return;
      setCrashState('error');
    }
  }, [udid]);

  const loadAll = useCallback(async () => {
    if (!udid) {
      // No iPhone: honest empty, never sample — matches Backup/Screen.
      // No backend calls; the not-connected card renders below.
      setSummary(null);
      setVer(null);
      setCrashes([]);
      setState('ready');
      setCrashState('ready');
      return;
    }
    const id = ++diagReq.current;
    // Claim the crash generation too: a manual Refresh on the crash table
    // (loadCrashes) bumps the same counter, so a stale loadAll can never
    // clobber a fresher manual refresh and vice-versa.
    const crashId = ++crashReq.current;
    setState((s) => (s === 'ready' ? s : 'loading'));
    setCrashState('loading');
    try {
      // Two requests, not three: /summary already embeds verification, so a
      // separate /verification only doubles lockdown probes. On a hard
      // reload every extra parallel heavy request raises the odds that one
      // idevicecrashreport copy contends and returns a transient [].
      // The fallback keeps verification working if /summary ever fails.
      const [s, c] = await Promise.all([
        api.diagSummary(udid).catch(() => null),
        api.crashes(udid).catch(() => null as CrashItem[] | null),
      ]);
      if (id !== diagReq.current) return; // stale — a newer load owns the view
      let v = s?.verification ?? null;
      if (!v) {
        v = await api.verification(udid).catch(() => null);
        if (id !== diagReq.current) return;
      }
      setSummary(s);
      setVer(v);
      if (crashId !== crashReq.current) return; // superseded by a manual refresh
      if (c === null) {
        setCrashState('error');
      } else if (c.length === 0 && (s?.crash_count ?? 0) > 0) {
        // Inconsistent: the summary copy saw N reports but the list copy
        // came back empty (transient idevicecrashreport contention). Show
        // Retry instead of a misleading "None found — healthy".
        setCrashState('error');
      } else {
        setCrashes(c ?? []);
        setCrashState('ready');
      }
      setState('ready');
    } catch {
      if (id !== diagReq.current) return;
      setState('error');
      if (crashId === crashReq.current) setCrashState('error');
    }
  }, [udid]);

  // Abort stale snapshots so fast typing never stacks 3 s captures.
  const logAbort = useRef<AbortController | null>(null);
  const loadLog = useCallback(async () => {
    if (!udid) {
      // No iPhone: no log to capture; the not-connected card renders below.
      logAbort.current?.abort();
      setLog(null);
      setLogState('ready');
      return;
    }
    logAbort.current?.abort();
    const ctl = new AbortController();
    logAbort.current = ctl;
    setLogState('loading');
    try {
      // Short 2 s window: the backend reuses a fresh capture for
      // filter-only changes, so this is instant when cached.
      const r = await api.syslog(udid, lineCount, logQuery.trim(), logLevel, 2, ctl.signal);
      if (ctl.signal.aborted) return;
      setLog(r);
      setLogState('ready');
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return;
      setLogState('error');
    }
  }, [udid, lineCount, logQuery, logLevel]);

  useEffect(() => { loadAll(); }, [loadAll]);
  useEffect(() => {
    if (liveTail) return; // the stream owns the view while live
    const t = setTimeout(loadLog, logQuery ? 350 : 0);
    return () => clearTimeout(t);
  }, [loadLog, liveTail]);
  useEffect(() => () => logAbort.current?.abort(), []);

  // Real-time tail: one EventSource per (device, filter); the backend
  // filters server-side with the same rules as the snapshot endpoint.
  useEffect(() => {
    if (!liveTail || !udid) return;
    setStreamRows(entriesOf(log).slice(-100));
    setStreamLive(null);
    setStreamError(false);
    const url = api.syslogStreamUrl(udid, logQuery.trim(), logLevel);
    const src = new EventSource(url);
    const onHello = (e: MessageEvent) => {
      try {
        const body = JSON.parse(e.data) as { live?: boolean };
        setStreamLive(body.live ?? false);
      } catch { /* keep unknown */ }
    };
    const onMsg = (e: MessageEvent) => {
      try {
        const row = JSON.parse(e.data) as SyslogEntry;
        if (!row || typeof row.text !== 'string') return;
        const m = matchHint(row.text);
        const level = row.level === 'error' || row.level === 'warn' ? row.level : m.level;
        setStreamRows((prev) => {
          const next = prev.length >= 500 ? prev.slice(prev.length - 499) : prev.slice();
          next.push({ text: row.text, level, proc: row.proc, match: row.match ?? m.keyword });
          return next;
        });
      } catch { /* partial frame */ }
    };
    const onErr = () => setStreamError(true);
    src.addEventListener('hello', onHello as EventListener);
    src.onmessage = onMsg;
    src.onerror = onErr;
    return () => src.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveTail, udid, logQuery, logLevel]);

  // Follow mode: pin the viewer to the newest line as it streams in.
  useEffect(() => {
    if (!liveTail || !follow) return;
    const el = logScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [streamRows, liveTail, follow]);

  // Quiet-phone hint: streaming live but zero rows for a while.
  useEffect(() => {
    if (!liveTail || streamLive !== true || streamRows.length > 0) {
      setStreamQuiet(false);
      return;
    }
    const t = setTimeout(() => setStreamQuiet(true), 12000);
    return () => clearTimeout(t);
  }, [liveTail, streamLive, streamRows.length]);

  const filteredCrashes = useMemo(() => {
    const q = crashQuery.trim().toLowerCase();
    let list = crashes.slice();
    if (crashKind !== 'all') {
      list = list.filter((c) => crashKindOf(c) === crashKind);
    }
    if (q) {
      list = list.filter((c) =>
        `${c.filename} ${c.app ?? ''} ${c.date ?? ''} ${c.mtime ?? ''} ${c.exception ?? ''} ${c.reason ?? ''}`.toLowerCase().includes(q));
    }
    list.sort((a, b) => {
      if (crashSort === 'size') return (b.size || 0) - (a.size || 0);
      if (crashSort === 'name') return a.filename.localeCompare(b.filename);
      const da = a.date || a.mtime || '';
      const db = b.date || b.mtime || '';
      return db.localeCompare(da) || a.filename.localeCompare(b.filename);
    });
    return list;
  }, [crashes, crashQuery, crashSort, crashKind]);

  const crashKindCounts = useMemo(() => {
    const m: Record<string, number> = { crash: 0, jetsam: 0, panic: 0 };
    for (const c of crashes) {
      const k = crashKindOf(c);
      if (k in m) m[k] += 1;
    }
    return m;
  }, [crashes]);

  // Reset pagination when the filter changes.
  useEffect(() => { setVisibleCrashes(100); setExpandedCrash(null); }, [crashQuery, crashKind, crashSort, udid]);

  const totalCrashBytes = useMemo(() => crashes.reduce((n, c) => n + (c.size || 0), 0), [crashes]);
  const verification = summary?.verification ?? ver;
  const status = summary?.status ?? (verification?.refurbished_suspect ? 'attention' : 'unknown');
  const headline = summary?.headline ?? verification?.summary ?? 'Connect your iPhone to complete the check.';

  async function toggleCrashDetail(c: CrashItem) {
    const key = c.filename;
    if (expandedCrash === key) { setExpandedCrash(null); return; }
    setExpandedCrash(key);
    if (crashDetails[key] || crashDetailLoading === key) return;
    setCrashDetailLoading(key);
    try {
      const d = await api.crashDetail(udid, key);
      setCrashDetails((prev) => ({ ...prev, [key]: d }));
    } catch { /* detail stays unavailable — row still shows list fields */ }
    finally { setCrashDetailLoading(null); }
  }

  function downloadCrashesCsv() {
    if (filteredCrashes.length === 0) return;
    const blob = new Blob([crashesToCsv(filteredCrashes)], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `freetunes-crashes-${(udid || 'mock').slice(0, 8)}.csv`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
  }

  async function copyText(text: string, which: 'log' | 'ver' | 'crash') {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(which);
      setTimeout(() => setCopied(null), 1500);
    } catch { /* clipboard unavailable */ }
  }

  function downloadLog() {
    if (!log?.lines) return;
    const blob = new Blob([log.lines], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `freetunes-syslog-${(udid || 'mock').slice(0, 8)}.log`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
  }

  if (!udid) {
    // No iPhone: same not-connected card as Backup/Screen/Device — never
    // placeholder rows or sample logs. No backend calls were made above.
    return (
      <div className="ft-diag">
        <div className="ft-table"><div className="ft-empty">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <rect x="4" y="1.5" width="8" height="13" rx="2" />
            <path d="M7 12.5h2" strokeLinecap="round" />
          </svg>
          <strong>No iPhone connected</strong>
          <p>Plug in your iPhone with a USB cable, unlock it, and tap Trust on the phone. Verification, crash reports, and the device log appear here.</p>
        </div></div>
      </div>
    );
  }

  return (
    <div className="ft-diag">
      {/* Health hero — Apple language: tight Display title, 17px Body sub,
          single blue primary pill + ghost secondary, 4 store-style stats. */}
      <section className="ft-diag-hero glass" aria-label="iPhone health">
        <div className="ft-diag-hero-main">
          <div className="ft-fw-eyebrow">
            <span className={`ft-livepill${status === 'healthy' ? ' is-healthy' : status === 'attention' ? ' is-attention on' : ' is-waiting'}`}>
              {status === 'healthy' ? '● Healthy' : status === 'attention' ? '● Needs a look' : '● Waiting for iPhone'}
            </span>
            {!udid ? (
              <span className="ft-hint">no iPhone — plug in for live data</span>
            ) : log?.lines ? (
              <span className="ft-hint">{log.live ? 'live device log' : 'sample log in mock mode'}</span>
            ) : null}
          </div>
          <h2 className="ft-fw-title">Diagnostics</h2>
          <p className="ft-fw-sub" role="status">{headline}</p>
          <div className="ft-diag-actions">
            <button type="button" className="ft-icon-btn ft-apple-pill primary" onClick={() => { loadAll(); loadLog(); }} aria-label="Refresh diagnostics">Refresh</button>
            {verification && (
              <button type="button" className="ft-icon-btn ft-apple-pill ghost" onClick={() => copyText(
                `Model ${verification.model_number || 'unknown'} → ${verification.kind}\n${(verification.details || []).join('\n')}`,
                'ver')}>
                {copied === 'ver' ? 'Copied ✓' : 'Copy report'}
              </button>
            )}
          </div>
        </div>
        <dl className="ft-fw-stats">
          <div><dt>Crashes</dt><dd className="ft-num">{state === 'ready' ? crashes.length : '…'}</dd></div>
          <div><dt>Log errors</dt><dd className="ft-num">{log ? (log.errors ?? 0) : '…'}</dd></div>
          <div><dt>Log warnings</dt><dd className="ft-num">{log ? (log.warnings ?? 0) : '…'}</dd></div>
          <div>
            <dt>Verification</dt>
            <dd
              data-kind={verification?.kind ?? 'unknown'}
              title={verification?.summary ?? 'Model-origin check from the lockdown model number.'}
            >
              {state === 'ready' ? (verification ? (KIND_LABEL[verification.kind] ?? verification.kind) : '—') : '…'}
            </dd>
          </div>
        </dl>
      </section>

      {state === 'loading' ? (
        <div className="ft-diag-grid" aria-busy="true">
          {[0, 1].map((i) => <div key={i} className="ft-diag-card skeleton" style={{ minHeight: 180 }} />)}
        </div>
      ) : state === 'error' ? (
        <div className="ft-table"><div className="ft-empty">
          <strong>Could not load diagnostics</strong>
          <p>Check the cable, tap Trust on the phone, then press Refresh.</p>
          <button className="ft-sync-btn" onClick={() => { loadAll(); loadLog(); }}>Retry</button>
        </div></div>
      ) : (
        <>
          {/* Verification */}
          <section className="ft-diag-card glass" aria-label="Verification">
            <header className="ft-diag-head">
              <div>
                <h3>Verification</h3>
                <p>{verification?.summary || 'Model-origin check from the lockdown model number.'}</p>
              </div>
              {verification && (
                <span className={`pill ${KIND_PILL[verification.kind] ?? 'skip'}`}>
                  {KIND_LABEL[verification.kind] ?? verification.kind}
                </span>
              )}
            </header>
            <div className="ft-specs">
              <div className="ft-spec"><span>Model number</span><strong className="ft-mono">{verification?.model_number || '—'}</strong></div>
              <div className="ft-spec"><span>Kind</span><strong>{verification?.kind ?? 'unknown'}</strong></div>
              <div className="ft-spec"><span>Refurbished?</span><strong>{verification?.refurbished_suspect ? 'Suspect — see checks' : 'No sign'}</strong></div>
            </div>
            {(verification?.checks?.length ?? 0) > 0 && (
              <ul className="ft-gates">
                {verification!.checks!.map((c, i) => (
                  <li key={i}>
                    <span aria-hidden="true">{c.status === 'pass' ? '✓' : c.status === 'warn' ? '!' : '·'}</span>
                    <span><strong>{c.label}.</strong> {c.detail}</span>
                  </li>
                ))}
              </ul>
            )}
            {(verification?.details?.length ?? 0) > 0 && (
              <details className="ft-tech" open={showDetails} onToggle={(e) => setShowDetails((e.target as HTMLDetailsElement).open)}>
                <summary>Why this verdict ({verification!.details!.length} notes)</summary>
                <ul className="ft-diag-notes">
                  {verification!.details!.map((d, i) => <li key={i}>{d}</li>)}
                </ul>
              </details>
            )}
          </section>

          {/* Crash reports */}
          <section className="ft-diag-card glass" aria-label="Crash reports">
            <header className="ft-diag-head">
              <div>
                <h3>Crash reports</h3>
                <p role="status">
                  {crashState === 'loading'
                    ? 'Reading crash store…'
                    : crashState === 'error'
                      ? 'Could not read crash reports.'
                      : crashes.length === 0
                        ? 'None found — a healthy sign.'
                        : `${filteredCrashes.length} of ${crashes.length} shown · ${fmtBytes(totalCrashBytes)} total`}
                  {crashState === 'ready' && summary && summary.top_crash_apps.length > 0 && (
                    <> · worst:{' '}
                      {summary.top_crash_apps.slice(0, 2).map((t, i) => (
                        <span key={t.app}>
                          {i > 0 && ', '}
                          <button type="button" className="ft-link" title={`Filter to ${t.app}`}
                            onClick={() => setCrashQuery(t.app)}>{t.app} ×{t.count}</button>
                        </span>
                      ))}
                    </>
                  )}
                </p>
              </div>
              <button className={`ft-icon-btn${crashState === 'loading' ? ' is-spinning' : ''}`}
                onClick={loadCrashes} aria-label="Refresh crash reports" disabled={crashState === 'loading'}>
                {crashState === 'loading' ? '◌' : '⟳'}
              </button>
            </header>
            <div className="ft-media-tools">
              <input type="search" value={crashQuery} onChange={(e) => setCrashQuery(e.target.value)}
                placeholder="Filter by app, exception or date" aria-label="Filter crash reports" className="ft-search"
                title="Substring match over filename, app, date, exception and reason" />
              <div className="ft-segment" role="tablist" aria-label="Filter by kind">
                {(['all', 'crash', 'jetsam', 'panic'] as const).map((k) => (
                  <button key={k} role="tab" aria-selected={crashKind === k}
                    className={crashKind === k ? 'on' : ''} onClick={() => setCrashKind(k)}
                    title={k === 'all' ? 'All crash files' : crashKindTooltip(k)}>
                    {k === 'all' ? `All (${crashes.length})` : `${k} (${crashKindCounts[k] ?? 0})`}
                  </button>
                ))}
              </div>
              <div className="ft-segment" role="tablist" aria-label="Sort crashes">
                {(['date', 'name', 'size'] as const).map((s) => (
                  <button key={s} role="tab" aria-selected={crashSort === s}
                    className={crashSort === s ? 'on' : ''} onClick={() => setCrashSort(s)}
                    title={s === 'date' ? 'Newest first (filename date, then file time)' : s === 'name' ? 'Alphabetical by filename' : 'Largest files first'}>
                    {s === 'date' ? 'Newest' : s === 'name' ? 'Name' : 'Size'}
                  </button>
                ))}
              </div>
            </div>
            {crashState === 'ready' && crashes.length > 0 && (
              <p className="ft-hint ft-log-active" role="status"
                title={crashKind === 'all' ? 'All kinds. Hover a kind pill or an exception for why.' : crashKindTooltip(crashKind)}>
                Showing <strong>{crashKind === 'all' ? 'All kinds' : crashKind}</strong>
                {crashKind !== 'all' && <> — {(CRASH_KINDS as Record<string, { includes: string }>)[crashKind]?.includes ?? ''}</>}{' '}
                Hover a kind pill or an exception for why. Click a pattern below to filter.
              </p>
            )}
            <details className="ft-log-help">
              <summary>
                <span className="ft-log-help-title">How is each crash classified?</span>
                <span className="ft-log-help-meta">3 kinds · {COMMON_CRASH_REPORTS.length} common reports · {CRASH_SUBTYPES.length} patterns · .ips header</span>
                <span className="ft-log-help-chev" aria-hidden="true" />
              </summary>
              <div className="ft-log-help-body">
                <p className="ft-hint ft-log-help-intro" title={IPS_GUIDE}>
                  freetunes kinds are its own — not Apple’s levels. Click a kind, report or pattern to filter.
                </p>
                <section aria-label="Crash kinds">
                  <h4 className="ft-log-subhead">Kinds — click to filter</h4>
                  <div className="ft-log-cards" role="list">
                    {(['crash', 'jetsam', 'panic'] as const).map((k) => (
                      <button key={k} type="button" role="listitem"
                        className={`ft-log-card${crashKind === k ? ' is-active' : ''}`}
                        title={`${CRASH_KINDS[k].tooltip} ${CRASH_KINDS[k].long}`}
                        onClick={() => setCrashKind(crashKind === k ? 'all' : k)}>
                        <span className={`ft-kw${k === 'panic' ? ' is-error' : k === 'jetsam' ? ' is-warn' : ' is-proc'}`}>
                          {CRASH_KINDS[k].label} · {crashKindCounts[k] ?? 0}
                        </span>
                        <strong>{CRASH_KINDS[k].includes}</strong>
                        <span className="ft-log-when">{CRASH_KINDS[k].whenToUse}</span>
                      </button>
                    ))}
                  </div>
                </section>
                <section aria-label="Common reports">
                  <h4 className="ft-log-subhead">Common reports — click to filter</h4>
                  <div className="ft-log-kwgrid">
                    <div className="ft-log-kwcol">
                      <span className="ft-log-kwlabel">System names you will meet · click to isolate</span>
                      <span className="ft-log-chips">
                        {COMMON_CRASH_REPORTS.filter((r) => r.filter).map((r) => (
                          <button key={r.name} type="button"
                            className={`ft-kw${r.kind === 'panic' ? ' is-error' : r.kind === 'jetsam' ? ' is-warn' : ' is-proc'}`}
                            title={`${r.tooltip} Click to isolate “${r.filter}”.`}
                            onClick={() => setCrashQuery(r.filter)}>
                            {r.name}
                          </button>
                        ))}
                      </span>
                    </div>
                  </div>
                  <details className="ft-log-kwdetails">
                    <summary>What each common report means &amp; what to do ({COMMON_CRASH_REPORTS.length})</summary>
                    <div className="ft-log-kwdefs">
                      {[COMMON_CRASH_REPORTS.slice(0, 4), COMMON_CRASH_REPORTS.slice(4)].map((group, gi) => (
                        <div key={gi} className="ft-log-kwdef-col">
                          <ul className="ft-log-kwlist">
                            {group.map((r) => (
                              <li key={r.name} className="ft-kwdef" title={r.filter ? `Click to isolate “${r.filter}”.` : r.tooltip}>
                                {r.filter ? (
                                  <button type="button" className="ft-kwdef-head is-stack" onClick={() => setCrashQuery(r.filter)}>
                                    <span className={`ft-kw${r.kind === 'panic' ? ' is-error' : r.kind === 'jetsam' ? ' is-warn' : ' is-proc'}`}>{r.name}</span>
                                    <span className="ft-kwdef-tip">{r.what}</span>
                                  </button>
                                ) : (
                                  <span className="ft-kwdef-head is-stack">
                                    <span className="ft-kw is-proc">{r.name}</span>
                                    <span className="ft-kwdef-tip">{r.what}</span>
                                  </span>
                                )}
                                <span className="ft-kwdef-action">What to do: {r.action}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  </details>
                </section>
                <section aria-label="Exception patterns">
                  <h4 className="ft-log-subhead">Patterns — click to search</h4>
                  <div className="ft-log-kwgrid">
                    <div className="ft-log-kwcol">
                      <span className="ft-log-kwlabel">Exceptions · red thread</span>
                      <span className="ft-log-chips">
                        {CRASH_SUBTYPES.slice(0, 6).map((s) => (
                          <button key={s.hint} type="button" className="ft-kw is-error"
                            title={`${s.tooltip} Click to search for “${s.hint}”.`}
                            onClick={() => setCrashQuery(s.hint)}>
                            {s.hint}
                          </button>
                        ))}
                      </span>
                    </div>
                    <div className="ft-log-kwcol">
                      <span className="ft-log-kwlabel">Termination · amber thread</span>
                      <span className="ft-log-chips">
                        {CRASH_SUBTYPES.slice(6).map((s) => (
                          <button key={s.hint} type="button" className="ft-kw is-warn"
                            title={`${s.tooltip} Click to search for “${s.hint}”.`}
                            onClick={() => setCrashQuery(s.hint)}>
                            {s.hint}
                          </button>
                        ))}
                      </span>
                    </div>
                    <div className="ft-log-kwcol">
                      <span className="ft-log-kwlabel">Jetsam reasons · click to isolate</span>
                      <span className="ft-log-chips">
                        {JETSAM_REASONS.map((p) => (
                          <button key={p.reason} type="button" className="ft-kw is-proc"
                            title={`${p.blurb} Click to isolate “${p.reason}”.`}
                            onClick={() => setCrashQuery(p.reason)}>
                            {p.reason}
                          </button>
                        ))}
                      </span>
                    </div>
                  </div>
                  <details className="ft-log-kwdetails">
                    <summary>What each pattern means &amp; what to do ({CRASH_SUBTYPES.length})</summary>
                    <div className="ft-log-kwdefs">
                      {[{ items: CRASH_SUBTYPES.slice(0, 6), tone: 'is-error' }, { items: CRASH_SUBTYPES.slice(6), tone: 'is-warn' }].map((col, ci) => (
                        <div key={ci} className="ft-log-kwdef-col">
                          <ul className="ft-log-kwlist">
                            {col.items.map((s) => (
                              <li key={s.hint} className="ft-kwdef" title={`Click to search for “${s.hint}”.`}>
                                <button type="button" className="ft-kwdef-head is-stack" onClick={() => setCrashQuery(s.hint)}>
                                  <span className={`ft-kw ${col.tone}`}>{s.hint}</span>
                                  <span className="ft-kwdef-tip">{s.tooltip}</span>
                                </button>
                                <span className="ft-kwdef-action">What to do: {s.action}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  </details>
                </section>
                <p className="ft-hint ft-log-foot">
                  The real bug_type decides the kind (309 crash, 298 Jetsam, 210 panic-full, 115 ResetCounter, 288 stackshot),
                  filename as fallback — the .ips header decides the meaning. Jetsam / panic-full / ResetCounter carry
                  no Mach exception by design (process table / panicString / reset counts instead), so their Exception
                  cell stays “—” and the Reason row is the evidence.
                  Hover any row pill or exception to see why. Sources: Apple “Examining the fields”, “Understanding the exception types”, “Jetsam event reports”.
                </p>
              </div>
            </details>
            {crashState === 'loading' ? (
              <div className="ft-log-loading" aria-label="Loading crash reports" aria-busy="true">
                <span className="ft-spinner" aria-hidden="true" />
                <span>Reading crash store…</span>
              </div>
            ) : crashState === 'error' ? (
              <div className="ft-dup-empty">
                Crash list unavailable — reconnect and retry.
                <div><button className="ft-sync-btn" onClick={loadCrashes}>Retry</button></div>
              </div>
            ) : filteredCrashes.length === 0 ? (
              <div className="ft-dup-empty">
                {crashes.length === 0
                  ? 'No crash reports on this iPhone. If the phone reboots on its own, check back — new .ips files land here.'
                  : 'No crashes match this filter.'}
                {crashes.length > 0 && (crashQuery || crashKind !== 'all') && (
                  <div><button className="ft-link" onClick={() => { setCrashQuery(''); setCrashKind('all'); }}>Clear filter</button></div>
                )}
              </div>
            ) : (
              <div className="ft-table flush" role="list" aria-label="Crash reports">
                <div className="ft-row head ft-row-diag" role="presentation"><div>App / file</div><div>Kind</div><div className="ft-crash-exc-col">Exception</div><div>Date</div><div className="ft-num">Size</div></div>
                {filteredCrashes.slice(0, visibleCrashes).map((c) => {
                  const kind = crashKindOf(c);
                  const meta = crashKindMeta(kind);
                  const when = fmtCrashDate(c);
                  const exc = fmtCrashException(c);
                  const meaning = crashMeaning(c.exception || '', c.reason || '');
                  const open = expandedCrash === c.filename;
                  const detail = crashDetails[c.filename];
                  const loadingDetail = crashDetailLoading === c.filename;
                  return (
                    <div key={c.filename} role="listitem" className={`ft-crash-item is-${kind}`}>
                      <button type="button" className={`ft-row ft-row-diag ft-crash-row${open ? ' is-open' : ''}`}
                        title={`${when.title}${exc.title ? ` · ${exc.title}` : ''}`} aria-expanded={open} onClick={() => toggleCrashDetail(c)}>
                        <div className="ft-cell-main">
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} aria-hidden="true"><path d="M12 4 3.5 19.5h17Z" strokeLinejoin="round" /><path d="M12 10v4 M12 16.8h.01" strokeLinecap="round" /></svg>
                          <span className="ft-crash-app" title={c.filename}>{c.app || c.filename}</span>
                        </div>
                        <div>
                          <span className={`ft-kw${kind === 'panic' ? ' is-error' : kind === 'jetsam' ? ' is-warn' : ' is-proc'}`}
                            title={meta.title}>{meta.label}</span>
                        </div>
                        <div className="ft-mono ft-crash-exc ft-crash-exc-col" title={exc.title}>{exc.label}</div>
                        <div className="ft-mono" title={when.title}>{when.label}</div>
                        <div className="ft-mono ft-num">{fmtBytes(c.size)}</div>
                      </button>
                      {(c.exception || c.reason) && !open && (
                        <div className="ft-hint ft-crash-sub" title={c.reason || c.exception}>
                          {c.exception}{c.exception && c.reason ? ' — ' : ''}{c.reason?.slice(0, 120)}
                        </div>
                      )}
                      {open && (
                        <div className="ft-crash-detail">
                          {meaning && (
                            <p className="ft-hint ft-crash-meaning" title="Plain-words reading of the exception + reason (Apple docs).">
                              <strong>What it means:</strong> {meaning}
                            </p>
                          )}
                          <div className="ft-specs">
                            <div className="ft-spec"><span>File</span><strong className="ft-mono">{c.filename}</strong></div>
                            <div className="ft-spec"><span>Kind</span><strong title={meta.title}>{meta.label} — {kind === 'panic' ? 'whole device went down' : kind === 'jetsam' ? 'low-memory kill' : 'process died'}</strong></div>
                            <div className="ft-spec"><span>Exception</span><strong title={c.exception ? `Mach exception + signal: ${c.exception}` : (kind === 'jetsam' || kind === 'panic') ? 'No Mach exception — expected for this kind (Jetsam: process table, panic-full: panicString, ResetCounter: reset counts). The Reason row is the evidence.' : 'Not parsed from this file’s header — see the preview below.'}>{c.exception || '—'}</strong></div>
                            <div className="ft-spec"><span>Reason</span><strong title={c.reason ? `Termination / report reason: ${c.reason}` : 'Not parsed from this file’s header — see the preview below.'}>{c.reason || '—'}</strong></div>
                            <div className="ft-spec"><span>OS</span><strong title={c.os_version ? `OS build from the .ips header: ${c.os_version}` : 'Not parsed from this file’s header — see the preview below.'}>{c.os_version || '—'}</strong></div>
                          </div>
                          {loadingDetail ? (
                            <p className="ft-hint">Reading header…</p>
                          ) : detail ? (
                            <pre className="ft-log ft-crash-preview" aria-label={`Preview of ${c.filename}`}>{detail.preview}{detail.truncated ? '\n… (truncated to 200 lines — parsed locally, never uploaded)' : ''}</pre>
                          ) : (
                            <p className="ft-hint">No preview — the file left the crash store or is unreadable.</p>
                          )}
                          <div className="ft-diag-actions">
                            <button className="ft-icon-btn" onClick={() => copyText(c.filename, 'crash')}>
                              {copied === 'crash' ? 'Copied ✓' : 'Copy filename'}
                            </button>
                            {detail && (
                              <button className="ft-icon-btn"
                                onClick={() => copyText(`${c.filename}\n${c.exception || ''}\n${c.reason || ''}\n\n${detail.preview}`, 'crash')}>
                                Copy detail
                              </button>
                            )}
                            <button className="ft-link" title={`Search the device log for ${c.app}`}
                              onClick={() => { if (c.app) setLogQuery(c.app); }}>
                              Search log for {c.app || 'app'}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {crashState === 'ready' && filteredCrashes.length > visibleCrashes && (
              <div className="ft-diag-actions">
                <button className="ft-sync-btn" onClick={() => setVisibleCrashes((n) => n + 100)}>
                  Show more ({filteredCrashes.length - visibleCrashes} left)
                </button>
              </div>
            )}
            {crashState === 'ready' && filteredCrashes.length > 0 && (
              <div className="ft-diag-actions">
                <button className="ft-icon-btn" disabled={filteredCrashes.length === 0} onClick={downloadCrashesCsv}>Download .csv</button>
                <button className="ft-icon-btn"
                  onClick={() => copyText(filteredCrashes.slice(0, visibleCrashes).map((c) => c.filename).join('\n'), 'crash')}>
                  {copied === 'crash' ? 'Copied ✓' : 'Copy list'}
                </button>
                <span className="ft-hint">contents parsed on this computer — filenames + truncated preview only, never uploaded</span>
              </div>
            )}
          </section>

          {/* Device log — web log viewer: snapshot + real-time tail */}
          <section className="ft-diag-card glass" aria-label="Device log">
            <header className="ft-diag-head">
              <div>
                <h3>Device log {liveTail ? '(streaming)' : log?.live ? '(live)' : log?.lines ? '(sample)' : udid ? '(waiting for lines)' : '(no iPhone)'}</h3>
                <p role="status">
                  {liveTail
                    ? `${streamRows.length} streamed lines${streamLive === null ? ' · connecting…' : streamLive ? ' · live from iPhone' : ' · sample stream'}${streamError ? ' · reconnecting…' : ''}`
                    : logState === 'ready' && log
                      ? `${log.shown ?? 0} of ${log.total ?? 0} lines shown · ${log.errors ?? 0} errors · ${log.warnings ?? 0} warnings${log.cached ? ' · instant (cached)' : log.capture_ms ? ` · captured in ${(log.capture_ms / 1000).toFixed(1)}s` : ''}`
                      : 'Tail of idevicesyslog — filtered on this computer, never uploaded.'}
                </p>
              </div>
              <span className={`ft-livepill${(liveTail ? (streamLive ?? log?.live) : log?.live) ? ' on streaming' : ''}`}>
                {liveTail ? (streamLive === null ? '● CONNECTING' : streamLive ? '● STREAMING' : '● SAMPLE STREAM') : log?.live ? '● LIVE' : 'SAMPLE'}
              </span>
            </header>
            <div className="ft-media-tools">
              <input type="search" value={logQuery} onChange={(e) => setLogQuery(e.target.value)}
                placeholder="Filter log text (try a process or keyword)" aria-label="Filter log" className="ft-search"
                title="Substring match, case-insensitive — try a process (wifid, backupd, SpringBoard) or a classification keyword (timeout, thermal)" />
              <div className="ft-segment" role="tablist" aria-label="Log level: what each filter keeps (hover for details)">
                {LOG_LEVEL_ORDER.map((l) => (
                  <button key={l} role="tab" aria-selected={logLevel === l}
                    className={logLevel === l ? 'on' : ''} onClick={() => setLogLevel(l)}
                    title={`${LOG_LEVELS[l].tooltip} ${LOG_LEVELS[l].includes}`}
                    aria-label={`${LOG_LEVELS[l].label}: ${LOG_LEVELS[l].tooltip}`}>
                    {LOG_LEVELS[l].label}
                  </button>
                ))}
              </div>
              <div className="ft-segment" role="tablist" aria-label="Log view">
                {(['pretty', 'raw'] as const).map((v) => (
                  <button key={v} role="tab" aria-selected={logView === v}
                    className={logView === v ? 'on' : ''} onClick={() => changeLogView(v)}
                    title={v === 'pretty' ? 'Colorized rows with level + process' : 'Classic plain-text tail'}>
                    {v === 'pretty' ? 'Viewer' : 'Raw'}
                  </button>
                ))}
              </div>
              {!liveTail && (
                <GlassSelect
                  label="Log lines"
                  value={String(lineCount)}
                  onChange={(v) => setLineCount(Number(v))}
                  options={[50, 100, 200, 500].map((n) => ({ value: String(n), label: `${n} lines` }))}
                />
              )}
              <button
                className={`ft-icon-btn${liveTail ? ' primary' : ''}`}
                onClick={() => setLiveTail((v) => !v)}
                aria-pressed={liveTail}
                title={liveTail ? 'Stop the real-time tail' : 'Stream new lines in real time'}>
                {liveTail ? '■ Stop live' : '▶ Live tail'}
              </button>
              {!liveTail && (
                <button className={`ft-icon-btn${logState === 'loading' ? ' is-spinning' : ''}`}
                  onClick={loadLog} aria-label="Refresh log" disabled={logState === 'loading'}>
                  {logState === 'loading' ? '◌' : '⟳'}
                </button>
              )}
            </div>
            <p className="ft-hint ft-log-active" role="status" title={LOG_LEVELS[logLevel].long}>
              Showing <strong>{LOG_LEVELS[logLevel].label}</strong> — {LOG_LEVELS[logLevel].includes}{' '}
              Hover a level button or a row badge for why. Click a keyword below to search it.
            </p>
            <details className="ft-log-help">
              <summary>
                <span className="ft-log-help-title">How is each line classified?</span>
                <span className="ft-log-help-meta">{LOG_LEVEL_ORDER.length} levels · {ERROR_SUBTYPES.length + WARN_SUBTYPES.length} keywords · {COMMON_PROCS.length} processes</span>
                <span className="ft-log-help-chev" aria-hidden="true" />
              </summary>
              <div className="ft-log-help-body">
                <p className="ft-hint ft-log-help-intro" title={IOS_TAGS_GUIDE}>
                  freetunes filters are its own — not Apple’s levels. Click a level or keyword to filter.
                </p>
                <section aria-label="Filter levels">
                  <h4 className="ft-log-subhead">Filter levels</h4>
                  <div className="ft-log-cards" role="list">
                    {LOG_LEVEL_ORDER.map((l) => (
                      <button key={l} type="button" role="listitem"
                        className={`ft-log-card is-${l}${logLevel === l ? ' is-active' : ''}`}
                        title={`${LOG_LEVELS[l].tooltip} ${LOG_LEVELS[l].long}`}
                        onClick={() => setLogLevel(l)}>
                        <span className={`ft-lvl lvl-${l === 'all' ? 'info' : l === 'warn' ? 'warn' : l === 'error' ? 'error' : 'info'}`}>
                          {LOG_LEVELS[l].label}
                        </span>
                        <strong>{LOG_LEVELS[l].includes}</strong>
                        <span className="ft-log-when">{LOG_LEVELS[l].whenToUse}</span>
                      </button>
                    ))}
                  </div>
                </section>
                <section aria-label="Keywords">
                  <h4 className="ft-log-subhead">Keywords — click to search</h4>
                  <div className="ft-log-kwgrid">
                    <div className="ft-log-kwcol">
                      <span className="ft-log-kwlabel">Error · red · checked first</span>
                      <span className="ft-log-chips">
                        {ERROR_SUBTYPES.map((s) => (
                          <button key={s.keyword} type="button" className="ft-kw is-error"
                            title={`${s.tooltip} Click to search for “${s.keyword}”.`}
                            onClick={() => setLogQuery(s.keyword)}>
                            {s.keyword}
                          </button>
                        ))}
                      </span>
                    </div>
                    <div className="ft-log-kwcol">
                      <span className="ft-log-kwlabel">Warning · amber</span>
                      <span className="ft-log-chips">
                        {WARN_SUBTYPES.map((s) => (
                          <button key={s.keyword} type="button" className="ft-kw is-warn"
                            title={`${s.tooltip} Click to search for “${s.keyword}”.`}
                            onClick={() => setLogQuery(s.keyword)}>
                            {s.keyword}
                          </button>
                        ))}
                      </span>
                    </div>
                    <div className="ft-log-kwcol">
                      <span className="ft-log-kwlabel">Processes · click to isolate</span>
                      <span className="ft-log-chips">
                        {COMMON_PROCS.map((p) => (
                          <button key={p.name} type="button" className="ft-kw is-proc"
                            title={`${p.blurb} Click to isolate “${p.name}”.`}
                            onClick={() => setLogQuery(p.name)}>
                            {p.name}
                          </button>
                        ))}
                      </span>
                    </div>
                  </div>
                  <details className="ft-log-kwdetails">
                    <summary>What each keyword means &amp; what to do ({ERROR_SUBTYPES.length + WARN_SUBTYPES.length + COMMON_PROCS.length})</summary>
                    <div className="ft-log-kwdefs">
                      <div className="ft-log-kwdef-col">
                        <ul className="ft-log-kwlist">
                          {ERROR_SUBTYPES.map((s) => (
                            <li key={s.keyword} className="ft-kwdef is-error" title={`Click to search for “${s.keyword}”.`}>
                              <button type="button" className="ft-kwdef-head" onClick={() => setLogQuery(s.keyword)}>
                                <span className="ft-kw is-error">{s.keyword}</span>
                                <span className="ft-kwdef-tip">{s.tooltip}</span>
                              </button>
                              <span className="ft-kwdef-action">What to do: {s.action} <span className="ft-mono">e.g. {s.example}</span></span>
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div className="ft-log-kwdef-col">
                        <ul className="ft-log-kwlist">
                          {WARN_SUBTYPES.map((s) => (
                            <li key={s.keyword} className="ft-kwdef is-warn" title={`Click to search for “${s.keyword}”.`}>
                              <button type="button" className="ft-kwdef-head" onClick={() => setLogQuery(s.keyword)}>
                                <span className="ft-kw is-warn">{s.keyword}</span>
                                <span className="ft-kwdef-tip">{s.tooltip}</span>
                              </button>
                              <span className="ft-kwdef-action">What to do: {s.action} <span className="ft-mono">e.g. {s.example}</span></span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                    <div className="ft-log-kwprocs">
                      <span className="ft-log-kwlabel">Processes you will meet constantly — click to isolate</span>
                      <ul className="ft-log-kwlist is-procs">
                        {COMMON_PROCS.map((p) => (
                          <li key={p.name} className="ft-kwdef is-proc" title={`${p.blurb} Click to isolate “${p.name}”.`}>
                            <button type="button" className="ft-kwdef-head" onClick={() => setLogQuery(p.name)}>
                              <span className="ft-kw is-proc">{p.name}</span>
                              <span className="ft-kwdef-tip">{p.blurb}</span>
                            </button>
                            <span className="ft-kwdef-action">What to do: click to isolate <span className="ft-mono">{p.name}</span> and read its lines around the timestamp.</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </details>
                </section>
                <p className="ft-hint ft-log-foot">
                  Error words win over warning words — hover any row badge to see which word decided its color.
                </p>
              </div>
            </details>
            {liveTail ? (
              <>
                <div className="ft-log-toolbar">
                  <label className="ft-hint ft-check-inline">
                    <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
                    Follow new lines
                  </label>
                  {streamRows.length >= 500 && (
                    <span className="ft-hint">capped at 500 — narrow the filter to see more</span>
                  )}
                </div>
                {streamRows.length === 0 ? (
                  <div className="ft-log-loading" aria-label="Waiting for log lines">
                    <span className="ft-spinner" aria-hidden="true" />
                    <span>Waiting for lines{logQuery || logLevel !== 'all' ? ' matching this filter' : ''}…</span>
                    {streamQuiet && (
                      <span className="ft-log-quiet">
                        Still nothing after a while — the iPhone is quiet (locked or asleep).
                        Unlock it or open an app to generate log traffic.
                      </span>
                    )}
                  </div>
                ) : logView === 'raw' ? (
                  <div className="ft-log" ref={logScrollRef} role="log" aria-label="Streaming device log">
                    {streamRows.map((r, i) => {
                      const kw = matchOf(r);
                      return (
                        <div key={i} className={`ft-logline is-${r.level}`} title={rowLevelTooltip(r.level, kw)}>
                          <span className={`ft-lvl lvl-${r.level}`} title={rowLevelTooltip(r.level, kw)}>{r.level === 'error' ? 'ERR' : r.level === 'warn' ? 'WRN' : 'INF'}</span>
                          <span>{r.text}</span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="ft-logviewer" ref={logScrollRef} role="log" aria-label="Streaming device log">
                    {streamRows.map((r, i) => {
                      const kw = matchOf(r);
                      const tip = rowLevelTooltip(r.level, kw);
                      return (
                        <div key={i} className={`ft-logrow is-${r.level}`}>
                          <span className={`ft-lvl lvl-${r.level}`} title={tip} aria-label={`${r.level}${kw ? `, matched ${kw}` : ''}`}>
                            {r.level === 'error' ? '● ERR' : r.level === 'warn' ? '● WRN' : '● INF'}
                          </span>
                          {r.proc && <span className="ft-logproc" title={PROC_TOOLTIP}>{r.proc}</span>}
                          <span className="ft-logmsg" title={kw ? tip : undefined}>{r.text}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            ) : logState === 'loading' ? (
              <div className="ft-log-loading" aria-label="Loading log" aria-busy="true">
                <span className="ft-spinner" aria-hidden="true" />
                <span>Capturing device log<span className="ft-dots" aria-hidden="true"><i>.</i><i>.</i><i>.</i></span></span>
                <div className="ft-log-shimmer" aria-hidden="true">
                  {[0, 1, 2].map((i) => <i key={i} style={{ width: `${92 - i * 17}%` }} />)}
                </div>
              </div>
            ) : logState === 'error' ? (
              <div className="ft-dup-empty">Log unavailable — reconnect and retry.</div>
            ) : !log?.lines ? (
              <div className="ft-dup-empty">
                {log?.filtered ? 'Nothing matches — clear the filter or widen the level.' : 'No log lines yet.'}
              </div>
            ) : logView === 'raw' ? (
              <pre className="ft-log" aria-label="Device log lines" title="Plain-text tail — switch to Viewer for per-line level colors and hover explanations">{log.lines}</pre>
            ) : (
              <div className="ft-logviewer" role="log" aria-label="Device log lines">
                {entriesOf(log).map((r, i) => {
                  const kw = matchOf(r);
                  const tip = rowLevelTooltip(r.level, kw);
                  return (
                    <div key={i} className={`ft-logrow is-${r.level}`}>
                      <span className={`ft-lvl lvl-${r.level}`} title={tip} aria-label={`${r.level}${kw ? `, matched ${kw}` : ''}`}>
                        {r.level === 'error' ? '● ERR' : r.level === 'warn' ? '● WRN' : '● INF'}
                      </span>
                      {r.proc && <span className="ft-logproc" title={PROC_TOOLTIP}>{r.proc}</span>}
                      <span className="ft-logmsg" title={kw ? tip : undefined}>{r.text}</span>
                    </div>
                  );
                })}
              </div>
            )}
            <div className="ft-diag-actions">
              <button className="ft-icon-btn" disabled={!log?.lines}
                onClick={() => copyText(liveTail ? streamRows.map((r) => r.text).join('\n') : (log?.lines ?? ''), 'log')}>
                {copied === 'log' ? 'Copied ✓' : 'Copy'}
              </button>
              <button className="ft-icon-btn" disabled={!log?.lines} onClick={downloadLog}>Download .log</button>
              {(log?.filtered) && (
                <button className="ft-link" onClick={() => { setLogQuery(''); setLogLevel('all'); }}>Clear filter</button>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
