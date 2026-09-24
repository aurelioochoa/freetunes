import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, type BackupInfo, type BackupRecord } from '../api';

function fmtBytes(size: number): string {
  if (!size || size <= 0) return '—';
  if (size < 1024) return `${size} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let v = size / 1024;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
  return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${units[u]}`;
}

function relTime(iso: string | null | undefined): string {
  if (!iso) return 'never';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  if (diff < 0) return 'just now';
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'yesterday';
  if (days < 30) return `${days} days ago`;
  return new Date(t).toLocaleDateString();
}

type Msg = { kind: 'info' | 'ok' | 'err'; text: string };

export default function BackupView({ udid }: { udid: string }) {
  const [info, setInfo] = useState<BackupInfo | null>(null);
  const [history, setHistory] = useState<BackupRecord[]>([]);
  const [files, setFiles] = useState<{ filename: string; size: string }[]>([]);
  const [msg, setMsg] = useState<Msg>({ kind: 'info', text: 'Whole-iPhone backup via idevicebackup2 (FOSS). Nothing leaves this computer.' });
  const [busy, setBusy] = useState<'backup' | 'restore' | 'verify' | 'delete' | 'encrypt' | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [full, setFull] = useState(true);
  const [query, setQuery] = useState('');
  const [showAll, setShowAll] = useState(false);
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [optSystem, setOptSystem] = useState(false);
  const [optSettings, setOptSettings] = useState(false);
  const [optSkipApps, setOptSkipApps] = useState(false);

  const load = useCallback(async () => {
    if (!udid) {
      setState('ready');
      setInfo(null);
      setHistory([]);
      setFiles([]);
      return;
    }
    setState((s) => (s === 'ready' ? s : 'loading'));
    try {
      const [i, h, f] = await Promise.all([
        api.backupInfo(udid).catch(() => null),
        api.backupHistory(udid).catch(() => [] as BackupRecord[]),
        api.backupFiles(udid).catch(() => [] as { filename: string; size: string }[]),
      ]);
      setInfo(i);
      setHistory(h ?? []);
      setFiles(f ?? []);
      setState('ready');
    } catch {
      setState('error');
    }
  }, [udid]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? files.filter((f) => f.filename.toLowerCase().includes(q))
      : files;
    return list.slice().sort((a, b) => a.filename.localeCompare(b.filename));
  }, [files, query]);

  const shown = showAll ? filtered.slice(0, 500) : filtered.slice(0, 50);
  const keyFiles = history.filter((h) => h.is_key_file);
  const sizeBytes = info?.size_bytes ?? history.reduce((n, h) => n + (h.size_bytes || 0), 0);
  const hasBackup = (info?.has_manifest ?? keyFiles.length > 0) || files.length > 0;
  const stale = useMemo(() => {
    if (!info?.last_backup) return hasBackup;
    const t = Date.parse(info.last_backup);
    return Number.isNaN(t) || Date.now() - t > 14 * 86400e3;
  }, [info, hasBackup]);

  async function runBackup() {
    if (!udid) { setMsg({ kind: 'err', text: 'Plug in your iPhone first.' }); return; }
    setBusy('backup');
    setMsg({ kind: 'info', text: `Backing up (${full ? 'full' : 'incremental'}) — keep the cable in, this can take a while…` });
    try {
      const r = await api.backupRun(udid, full) as { ok: boolean; message?: string; output?: string; error?: string; hint?: string; elapsed_s?: number };
      if (r.ok) {
        setMsg({ kind: 'ok', text: `Backup finished${r.elapsed_s ? ` in ${Math.round(r.elapsed_s)}s` : ''}. Verify it below to be sure.` });
      } else {
        setMsg({ kind: 'err', text: `Backup not run: ${r.message ?? r.error ?? r.hint ?? 'tool unavailable in mock mode'}` });
      }
      await load();
    } catch (e) { setMsg({ kind: 'err', text: `Backup failed: ${String(e)}` }); }
    finally { setBusy(null); }
  }

  async function verify() {
    if (!udid) return;
    setBusy('verify');
    try {
      const r = await api.backupVerify(udid);
      setMsg(r.ok
        ? { kind: 'ok', text: r.message ?? 'Backup looks complete.' }
        : { kind: 'err', text: r.problems?.join(' ') ?? r.message ?? 'Verification failed.' });
      await load();
    } catch (e) { setMsg({ kind: 'err', text: `Verify failed: ${String(e)}` }); }
    finally { setBusy(null); }
  }

  async function toggleEncryption() {
    if (!udid) return;
    const next = !(info?.encrypted ?? false);
    if (next && !window.confirm('Turn on backup encryption? You will need the BACKUP_PASSWORD to restore.')) return;
    if (!next && !window.confirm('Turn OFF encryption? Unencrypted backups expose passwords and health data.')) return;
    setBusy('encrypt');
    try {
      const r = await api.backupEncryption(udid, next);
      setMsg(r.ok
        ? { kind: 'ok', text: `Encryption ${next ? 'on' : 'off'}.` }
        : { kind: 'err', text: `Encryption not changed: ${r.message ?? r.hint ?? 'unavailable'}` });
      await load();
    } catch (e) { setMsg({ kind: 'err', text: `Encryption failed: ${String(e)}` }); }
    finally { setBusy(null); }
  }

  async function restore() {
    if (!udid) return;
    const scope = [optSystem && 'system files', optSettings && 'settings', optSkipApps && 'skip apps'].filter(Boolean).join(', ') || 'user data';
    if (!window.confirm(`Restore will overwrite ${scope} on the iPhone. The phone will reboot. Continue?`)) return;
    setBusy('restore');
    setMsg({ kind: 'info', text: 'Restoring — keep the cable in and do not touch the iPhone…' });
    try {
      const r = await api.backupRestore(udid, { system: optSystem, settings: optSettings, skip_apps: optSkipApps }) as { ok: boolean; message?: string; error?: string };
      setMsg(r.ok
        ? { kind: 'ok', text: 'Restore finished — the iPhone will reboot.' }
        : { kind: 'err', text: `Restore not run: ${r.message ?? r.error ?? 'unavailable'}` });
    } catch (e) { setMsg({ kind: 'err', text: `Restore failed: ${String(e)}` }); }
    finally { setBusy(null); }
  }

  async function remove() {
    if (!udid) return;
    if (!window.confirm('Delete the local backup on THIS computer? The iPhone is untouched.')) return;
    setBusy('delete');
    try {
      const r = await api.backupDelete(udid);
      setMsg(r.ok ? { kind: 'ok', text: r.message ?? 'Deleted.' } : { kind: 'err', text: r.message ?? 'Delete failed.' });
      await load();
    } catch (e) { setMsg({ kind: 'err', text: `Delete failed: ${String(e)}` }); }
    finally { setBusy(null); }
  }

  if (!udid) {
    return (
      <div className="ft-backup">
        <div className="ft-table"><div className="ft-empty">
          <strong>Plug in your iPhone to back it up</strong>
          <p>Whole-device backup over USB with idevicebackup2. Unlock the phone, tap Trust, then come back here.</p>
        </div></div>
      </div>
    );
  }

  return (
    <div className="ft-backup">
      {/* Status hero */}
      <section className="ft-backup-hero glass" aria-label="Backup status">
        <div className="ft-backup-hero-main">
          <div className="ft-fw-eyebrow">
            <span className={`pill ${!hasBackup ? 'skip' : stale ? 'delete' : 'push'}`}>
              {!hasBackup ? 'No backup yet' : stale ? 'Stale' : 'Fresh'}
            </span>
            <span className={`pill ${info?.encrypted ? 'push' : 'skip'}`}>
              {info?.encrypted ? 'Encrypted ✓' : 'Not encrypted'}
            </span>
            {info?.available === false && <span className="ft-hint">tool offline — showing folder on disk</span>}
          </div>
          <h2 className="ft-fw-title">
            {info?.last_backup ? `Last backup ${relTime(info.last_backup)}` : 'No backup yet'}
          </h2>
          <p className="ft-fw-sub" role="status">
            {info?.last_backup && !Number.isNaN(Date.parse(info.last_backup))
              ? new Date(info.last_backup).toLocaleString()
              : 'Run your first backup, then verify it. Encrypted backups also save passwords and Health data.'}
          </p>
          <div className="ft-diag-actions">
            <div className="ft-segment" role="tablist" aria-label="Backup type">
              <button role="tab" aria-selected={full} className={full ? 'on' : ''}
                onClick={() => setFull(true)} title="Full snapshot — slower, self-contained">Full</button>
              <button role="tab" aria-selected={!full} className={!full ? 'on' : ''}
                onClick={() => setFull(false)} title="Incremental — faster, needs the previous backup">Incremental</button>
            </div>
            <button className="ft-sync-btn" disabled={busy !== null} onClick={runBackup}>
              {busy === 'backup' ? 'Backing up…' : 'Back up now'}
            </button>
            <button className="ft-icon-btn" disabled={busy !== null} onClick={verify}>
              {busy === 'verify' ? 'Checking…' : 'Verify'}
            </button>
            <button className="ft-icon-btn" disabled={busy !== null} onClick={load} aria-label="Refresh backup status">⟳</button>
          </div>
          <p className={`ft-result${msg.kind === 'ok' ? ' ok' : msg.kind === 'err' ? ' err' : ''}`} role="status">
            <span aria-hidden="true">{msg.kind === 'ok' ? '✓' : msg.kind === 'err' ? '!' : '·'}</span> {msg.text}
          </p>
        </div>
        <dl className="ft-fw-stats">
          <div><dt>Size on disk</dt><dd>{state === 'ready' ? fmtBytes(sizeBytes) : '…'}</dd></div>
          <div><dt>Files</dt><dd>{info?.file_count ?? files.length}</dd></div>
          <div><dt>Manifest</dt><dd style={{ fontSize: 13 }}>{info?.has_manifest ? 'present ✓' : 'missing'}</dd></div>
        </dl>
      </section>

      {state === 'loading' ? (
        <div className="ft-diag-grid" aria-busy="true">
          <div className="ft-diag-card skeleton" style={{ minHeight: 160 }} />
        </div>
      ) : state === 'error' ? (
        <div className="ft-table"><div className="ft-empty">
          <strong>Could not load backup status</strong>
          <p>Start the backend and reconnect, then retry.</p>
          <button className="ft-sync-btn" onClick={load}>Retry</button>
        </div></div>
      ) : (
        <>
          {/* Checklist + danger zone */}
          <div className="ft-backup-grid">
            <section className="ft-diag-card glass" aria-label="Before you start">
              <header className="ft-diag-head">
                <div><h3>Before you start</h3><p>Three things that decide success.</p></div>
              </header>
              <ul className="ft-gates">
                <li><span aria-hidden="true">{hasBackup ? '✓' : '·'}</span><span><strong>Cable & trust.</strong> USB, unlocked, Trust tapped — Wi-Fi sync is not supported.</span></li>
                <li><span aria-hidden="true">{info?.encrypted ? '✓' : '!'}</span><span><strong>Encryption.</strong> {info?.encrypted ? 'On — passwords and Health are included.' : 'Off — turn it on to include passwords and Health data.'}</span></li>
                <li><span aria-hidden="true">{info?.has_manifest ? '✓' : '·'}</span><span><strong>Space.</strong> Keep twice the iPhone's used storage free on this computer.</span></li>
              </ul>
              <div className="ft-diag-actions">
                <button className="ft-icon-btn" disabled={busy !== null} onClick={toggleEncryption}>
                  {busy === 'encrypt' ? 'Working…' : info?.encrypted ? 'Turn encryption off' : 'Turn encryption on'}
                </button>
                <span className="ft-hint">Password via BACKUP_PASSWORD env — never typed here.</span>
              </div>
              <p className="ft-mono ft-hint" title={info?.backup_dir ?? ''}>{info?.backup_dir ?? '—'}</p>
            </section>

            <section className="ft-diag-card glass" aria-label="Restore">
              <header className="ft-diag-head">
                <div><h3>Restore</h3><p>Overwrites the iPhone. Backup first if unsure.</p></div>
                <button className="ft-icon-btn" aria-expanded={restoreOpen} onClick={() => setRestoreOpen((o) => !o)}>
                  {restoreOpen ? 'Hide options' : 'Options…'}
                </button>
              </header>
              {restoreOpen && (
                <div className="ft-restore-opts">
                  <label><input type="checkbox" checked={optSystem} onChange={(e) => setOptSystem(e.target.checked)} /> System files <span className="ft-hint">(needs a matching iOS)</span></label>
                  <label><input type="checkbox" checked={optSettings} onChange={(e) => setOptSettings(e.target.checked)} /> Settings</label>
                  <label><input type="checkbox" checked={optSkipApps} onChange={(e) => setOptSkipApps(e.target.checked)} /> Skip apps <span className="ft-hint">(faster, reinstall later)</span></label>
                </div>
              )}
              <div className="ft-diag-actions">
                <button className="ft-icon-btn" disabled={busy !== null || !hasBackup} onClick={restore}>
                  {busy === 'restore' ? 'Restoring…' : 'Restore…'}
                </button>
                <button className="ft-link" disabled={busy !== null} onClick={remove} style={{ color: '#c8102e' }}>
                  {busy === 'delete' ? 'Deleting…' : 'Delete local backup'}
                </button>
              </div>
              {!hasBackup && <p className="ft-hint">Nothing to restore yet — run a backup first.</p>}
            </section>
          </div>

          {/* Key files */}
          {keyFiles.length > 0 && (
            <section className="ft-diag-card glass" aria-label="Backup manifest">
              <header className="ft-diag-head">
                <div><h3>Backup manifest</h3><p>{keyFiles.length} key file{s(keyFiles.length)} — the restore reads these first.</p></div>
              </header>
              <div className="ft-keyfiles">
                {keyFiles.map((k) => (
                  <div key={k.name} className="ft-keyfile" title={k.path}>
                    <strong className="ft-mono">{k.name}</strong>
                    <span className="ft-hint">{fmtBytes(k.size_bytes)}{k.mtime ? ` · ${relTime(k.mtime)}` : ''}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Contents */}
          <section className="ft-diag-card glass" aria-label="Backup contents">
            <header className="ft-diag-head">
              <div>
                <h3>Contents</h3>
                <p role="status">{filtered.length === 0 ? 'No file list yet — run a backup first.' : `${filtered.length} file${filtered.length === 1 ? '' : 's'}${query ? ' match' : ''}`}</p>
              </div>
              <button className="ft-icon-btn" onClick={load} aria-label="Refresh file list">⟳</button>
            </header>
            <div className="ft-media-tools">
              <input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder="Search backup files" aria-label="Search backup files" className="ft-search" />
            </div>
            {filtered.length === 0 ? (
              <div className="ft-dup-empty">No backup file list yet — run a backup first. The folder above is where it will land.</div>
            ) : (
              <>
                <div className="ft-table flush" role="table" aria-label="Backup contents">
                  <div className="ft-row head ft-row-backup" role="row"><div>File in backup</div><div>Size</div><div>Status</div></div>
                  {shown.map((f) => (
                    <div className="ft-row ft-row-backup" key={f.filename} role="row">
                      <div className="ft-mono" title={f.filename}>{f.filename}</div>
                      <div className="ft-mono ft-num">{/^\d+$/.test(f.size) ? fmtBytes(Number(f.size)) : (f.size || '—')}</div>
                      <div><span className="pill push">saved</span></div>
                    </div>
                  ))}
                </div>
                {filtered.length > shown.length && (
                  <button className="ft-link" onClick={() => setShowAll(true)}>
                    Show {Math.min(filtered.length, 500) - shown.length} more…
                  </button>
                )}
              </>
            )}
            <details className="ft-tech">
              <summary>Passwords stay safe</summary>
              <p>Encryption passwords are read from the <code>BACKUP_PASSWORD</code> env var, never from the URL or command history. Restore needs the same password the backup was made with.</p>
            </details>
          </section>
        </>
      )}
    </div>
  );
}

function s(n: number): string {
  return n === 1 ? '' : 's';
}
