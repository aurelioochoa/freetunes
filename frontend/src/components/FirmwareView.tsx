import GlassSelect from './GlassSelect';
import { useCallback, useEffect, useState } from 'react';
import { api, type FirmwareBuild } from '../api';
import { PRODUCT_FRIENDLY, describeProduct, friendlyProductName } from '../devices';

interface DryRunResult {
  ok: boolean;
  confirmed?: boolean;
  command?: string[];
  gates?: string[];
  reason?: string;
  note?: string;
  idevicerestore_found?: boolean;
}

function gb(bytes: number): string {
  if (!bytes) return '—';
  return `${(bytes / 1e9).toFixed(2)} GB`;
}

const MODES = [
  { id: 'quick', label: 'Quick', hint: 'Clean install' },
  { id: 'retain', label: 'Retain', hint: 'Keep data' },
  { id: 'anti-recovery', label: 'Erase', hint: 'Anti-recovery' },
] as const;

const SAFETY = [
  ['Back up first', 'A full backup can undo a bad flash.'],
  ['Signed only', 'This list hides anything Apple stopped signing.'],
  ['Know your Apple ID', 'Activation Lock will ask for it after restore.'],
  ['Keep the cable in', 'Never unplug mid-flash. Use USB, not a hub.'],
  ['Dry-run here', 'Nothing flashes until Phase 5 behind FREETUNES_ALLOW_FLASH=1.'],
];

/** Every ProductType ipsw.me knows, friendly-first for the selector. */
const MODEL_OPTIONS = Object.entries(PRODUCT_FRIENDLY)
  .map(([id, name]) => ({ id, name }))
  .sort((a, b) => a.name.localeCompare(b.name));

export default function FirmwareView({ udid, productType }: { udid: string; productType: string }) {
  const [product, setProduct] = useState(productType || '');
  const [rows, setRows] = useState<FirmwareBuild[]>([]);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [msg, setMsg] = useState('Signed firmware only. Flashing is a dry-run here — nothing on the iPhone changes.');
  const [mode, setMode] = useState<string>('quick');
  const [dry, setDry] = useState<DryRunResult | null>(null);
  const [dryBusy, setDryBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (productType) setProduct(productType);
  }, [productType]);

  const load = useCallback(async (p: string) => {
    const needle = p.trim();
    if (!needle) {
      setStatus('idle');
      setRows([]);
      setMsg('Plug in your iPhone to fill this in, or enter a ProductType — e.g. iPhone14,5, which is a regular iPhone 13.');
      return;
    }
    setStatus('loading');
    setMsg(`Looking up signed firmware for ${describeProduct(needle)}…`);
    try {
      const builds = await api.firmwareSigned(needle);
      setRows(builds);
      setStatus('ready');
      setMsg(builds.length === 0
        ? `No signed builds for ${describeProduct(needle)} (offline, unknown model, or Apple stopped signing).`
        : `${builds.length} signed build${builds.length === 1 ? '' : 's'} for ${describeProduct(needle)}. Pick one to dry-run a flash.`);
    } catch (e) {
      setRows([]);
      setStatus('error');
      setMsg(`Firmware lookup failed: ${String(e)}`);
    }
  }, []);

  // Auto-load only when we actually know the device. No more
  // hardcoded iPhone14,5 placeholder that looks like an iPhone 14.
  useEffect(() => {
    if (productType) load(productType);
    else {
      setStatus('idle');
      setRows([]);
      setMsg('Plug in your iPhone to fill this in, or enter a ProductType — e.g. iPhone14,5, which is a regular iPhone 13.');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productType]);

  async function dryRun(ipsw: string) {
    setDryBusy(ipsw);
    setDry(null);
    setCopied(false);
    try {
      const r = await api.flashDryRun(udid || 'mock-udid', ipsw, mode, true) as DryRunResult;
      setDry(r);
    } catch (e) {
      setDry({ ok: false, reason: String(e) });
    } finally {
      setDryBusy(null);
    }
  }

  const busy = status === 'loading';
  const latest = rows[0];

  return (
    <div className="ft-fw">
      <section className="ft-fw-hero glass" aria-label="Firmware lookup">
        <div className="ft-fw-hero-main">
          <div className="ft-fw-eyebrow">
            <span className="pill skip">Dry-run only</span>
            {!udid && <span className="ft-hint">no iPhone — browsing works, flash uses a placeholder UDID</span>}
          </div>
          <h2 className="ft-fw-title">Signed firmware{latest ? ` · iOS ${latest.version}` : ''}</h2>
          <p className="ft-fw-sub" role="status">{msg}</p>
          <div className="ft-field">
            <label htmlFor="fw-model">iPhone model</label>
            <div className="ft-fw-controls">
              <GlassSelect id="fw-model" label="iPhone model" value={product}
                onChange={(value) => { setProduct(value); load(value); }}
                options={[
                  { value: '', label: 'Choose your iPhone…' },
                  ...MODEL_OPTIONS.map((o) => ({ value: o.id, label: o.name, hint: o.id })),
                ]} />
              <button className="ft-sync-btn" disabled={busy || !product} onClick={() => load(product)}>
                {busy ? 'Loading…' : rows.length ? 'Refresh' : 'List builds'}
              </button>
            </div>
          </div>
          {productType && product !== productType && (
            <p className="ft-hint" style={{ margin: '6px 0 0' }}>
              Detected: {describeProduct(productType)}{' '}
              <button className="ft-link" onClick={() => { setProduct(productType); load(productType); }}>
                Use detected
              </button>
            </p>
          )}
          {product.trim() && (
            <p className="ft-hint" style={{ margin: '6px 0 0' }}>
              {friendlyProductName(product.trim())
                ? `${friendlyProductName(product.trim())} — Apple lists its firmware under ${product.trim()}.`
                : `${product.trim()} — Apple's hardware ID, not the box name.`}
            </p>
          )}
          <div className="ft-mode-block">
            <span className="ft-mode-label" id="fw-mode-label">Flash mode</span>
            <div className="ft-segment fit" role="tablist" aria-labelledby="fw-mode-label">
              {MODES.map((m) => (
                <button key={m.id} role="tab" aria-selected={mode === m.id}
                  className={mode === m.id ? 'on' : ''} onClick={() => setMode(m.id)}
                  title={m.hint}>
                  {m.label}
                </button>
              ))}
            </div>
            <p className="ft-hint">{MODES.find((m) => m.id === mode)?.hint} · applies to the next dry-run.</p>
          </div>
        </div>
        <dl className="ft-fw-stats">
          <div><dt>Signed builds</dt><dd>{busy ? '…' : rows.length}</dd></div>
          <div><dt>Device</dt><dd style={{ fontSize: 13 }}>{productType ? describeProduct(productType) : '—'}</dd></div>
          <div><dt>Largest IPSW</dt><dd>{rows.length ? gb(Math.max(...rows.map((r) => r.filesize || 0))) : '—'}</dd></div>
        </dl>
      </section>

      {busy ? (
        <div className="ft-fw-grid" aria-busy="true">
          {[0, 1, 2].map((i) => <div key={i} className="ft-fw-card skeleton" style={{ minHeight: 148 }} />)}
        </div>
      ) : status === 'error' ? (
        <div className="ft-table flush"><div className="ft-empty">
          <strong>Lookup failed</strong>
          <p>Check your connection and retry.</p>
          <button className="ft-sync-btn" onClick={() => load(product)}>Retry</button>
        </div></div>
      ) : rows.length === 0 ? (
        <div className="ft-table flush"><div className="ft-empty">
          <strong>{status === 'idle' ? 'Find firmware for your iPhone' : 'No signed builds'}</strong>
          <p>{status === 'idle'
            ? 'Plug in your iPhone and trust it, or type its ProductType — iPhone14,5 means a regular iPhone 13. Unsigned builds never appear here.'
            : `Nothing signed for ${describeProduct(product.trim()) || product.trim()}. Apple may have stopped signing it.`}</p>
        </div></div>
      ) : (
        <div className="ft-fw-grid" role="list" aria-label="Signed firmware">
          {rows.map((b, i) => (
            <article key={b.buildid} role="listitem" className={`ft-fw-card glass${i === 0 ? ' latest' : ''}`}>
              <header>
                <div>
                  <div className="ft-fw-ver">iOS {b.version}</div>
                  <div className="ft-mono ft-fw-build">{b.buildid}</div>
                </div>
                {i === 0
                  ? <span className="pill push">Latest · signed</span>
                  : <span className="pill push">Signed ✓</span>}
              </header>
              <dl>
                <div><dt>Size</dt><dd>{gb(b.filesize)}</dd></div>
                <div><dt>Mode</dt><dd>{MODES.find((m) => m.id === mode)?.label}</dd></div>
              </dl>
              <button className="ft-sync-btn block" disabled={dryBusy === b.url} onClick={() => dryRun(b.url)}>
                {dryBusy === b.url ? 'Checking…' : 'Dry-run flash'}
              </button>
            </article>
          ))}
        </div>
      )}

      {dry && (
        <section className={`ft-dry glass${dry.ok ? ' ok' : ' err'}`} aria-label="Dry-run result" aria-live="polite">
          <header>
            <strong>{dry.ok ? 'Dry-run passed — nothing was flashed' : 'Dry-run refused'}</strong>
            {dry.reason && dry.ok === false && <span className="ft-hint">{dry.reason}</span>}
          </header>
          {dry.reason && dry.ok && <p className="ft-hint">{dry.reason}</p>}
          {dry.command && (
            <div className="ft-cmd">
              <code className="ft-mono">{dry.command.join(' ')}</code>
              <button className="ft-icon-btn" onClick={async () => {
                try { await navigator.clipboard.writeText((dry.command ?? []).join(' ')); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* noop */ }
              }}>{copied ? 'Copied ✓' : 'Copy'}</button>
            </div>
          )}
          {dry.idevicerestore_found === false && (
            <p className="ft-warn">idevicerestore is not installed on this computer — install libimobiledevice tools for a real flash.</p>
          )}
          {dry.gates && dry.gates.length > 0 && (
            <ul className="ft-gates">
              {dry.gates.map((g, i) => <li key={i}><span aria-hidden="true">✓</span> {g}</li>)}
            </ul>
          )}
          {dry.note && <p className="ft-hint">{dry.note}</p>}
        </section>
      )}

      <section className="ft-safety glass" aria-label="Safety gates">
        <h3>Safety gates — always, before any flash</h3>
        <ol>
          {SAFETY.map(([t, d]) => (
            <li key={t}><strong>{t}</strong><span>{d}</span></li>
          ))}
        </ol>
      </section>
    </div>
  );
}
