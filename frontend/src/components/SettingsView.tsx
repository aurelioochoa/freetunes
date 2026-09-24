import { useMemo, useState } from 'react';
import {
  ACCENTS, BACKGROUNDS, DENSITIES, DEVICE_MODELS, GLASSES, THEMES,
  type AccentName, type BackgroundName, type DensityName, type GlassName, type ThemeName
} from '../devices';
import GlassSelect from './GlassSelect';
import BgPreview from './BgPreview';

export interface SettingsProps {
  theme: ThemeName;
  setTheme: (t: ThemeName) => void;
  accent: AccentName;
  setAccent: (a: AccentName) => void;
  background: BackgroundName;
  setBackground: (b: BackgroundName) => void;
  glass: GlassName;
  setGlass: (g: GlassName) => void;
  density: DensityName;
  setDensity: (d: DensityName) => void;
  reduceMotion: boolean;
  setReduceMotion: (v: boolean) => void;
  reduceTransparency: boolean;
  setReduceTransparency: (v: boolean) => void;
  modelId: string;
  modelAuto: boolean;
  onPickModel: (id: string) => void;
  detectedModelName: string;
  musicDir: string;
  setMusicDir: (v: string) => void;
  booksDir: string;
  setBooksDir: (v: string) => void;
  audiobooksDir: string;
  setAudiobooksDir: (v: string) => void;
  mirrorDelete: boolean;
  setMirrorDelete: (v: boolean) => void;
  /** null while the first health check is still in flight. */
  backendUp: boolean | null;
  backendUrl: string;
  onReset: () => void;
}

const PREF_KEYS = [
  'freetunes-theme', 'freetunes-accent', 'freetunes-background',
  'freetunes-glass', 'freetunes-density', 'freetunes-reduce-motion',
  'freetunes-reduce-transparency', 'freetunes-model', 'freetunes-model-auto',
  'freetunes-music-dir', 'freetunes-books-dir', 'freetunes-audiobooks-dir',
  'freetunes-mirror-delete', 'freetunes-model-id-live'
];

type SectionId = 'appearance' | 'wallpaper' | 'glass' | 'device' | 'library' | 'backend' | 'sync' | 'reset';

const SECTIONS: { id: SectionId; title: string; blurb: string; icon: string }[] = [
  { id: 'appearance', title: 'Appearance', blurb: 'theme accent density', icon: 'sun' },
  { id: 'wallpaper', title: 'Wallpaper', blurb: 'background aurora orbs mesh matrix starfield waves dusk confetti rain animated', icon: 'image' },
  { id: 'glass', title: 'Glass & Motion', blurb: 'liquid glass transparency motion', icon: 'sliders' },
  { id: 'device', title: 'Device Art', blurb: 'iphone model auto follow header', icon: 'phone' },
  { id: 'library', title: 'Library', blurb: 'music books audiobooks folders vlc', icon: 'folder' },
  { id: 'backend', title: 'Backend', blurb: 'daemon usb connection url status', icon: 'server' },
  { id: 'sync', title: 'Sync', blurb: 'mirror delete defaults preview', icon: 'sync' },
  { id: 'reset', title: 'Reset', blurb: 'defaults forget preferences', icon: 'trash' }
];

function Icon({ name }: { name: string }) {
  const common = { width: 16, height: 16, viewBox: '0 0 16 16', fill: 'none' as const, 'aria-hidden': true };
  const stroke = { stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  switch (name) {
    case 'sun':
      return (<svg {...common}><circle cx="8" cy="8" r="3" {...stroke} /><path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1" {...stroke} /></svg>);
    case 'image':
      return (<svg {...common}><rect x="1.5" y="2.5" width="13" height="11" rx="2" {...stroke} /><circle cx="5.5" cy="6.5" r="1.2" {...stroke} /><path d="M2.5 12l3.5-3.5 2.5 2.5 2-2 3 3" {...stroke} /></svg>);
    case 'sliders':
      return (<svg {...common}><path d="M2.5 5h11M2.5 11h11" {...stroke} /><circle cx="6" cy="5" r="1.8" fill="var(--glass)" {...stroke} /><circle cx="10.5" cy="11" r="1.8" fill="var(--glass)" {...stroke} /></svg>);
    case 'phone':
      return (<svg {...common}><rect x="4.5" y="1.5" width="7" height="13" rx="1.8" {...stroke} /><path d="M7 12.5h2" {...stroke} /></svg>);
    case 'folder':
      return (<svg {...common}><path d="M1.5 4.5c0-.8.7-1.5 1.5-1.5h3l1.2 1.5h5.3c.8 0 1.5.7 1.5 1.5v5c0 .8-.7 1.5-1.5 1.5H3c-.8 0-1.5-.7-1.5-1.5z" {...stroke} /></svg>);
    case 'server':
      return (<svg {...common}><rect x="2" y="2.5" width="12" height="4.5" rx="1.2" {...stroke} /><rect x="2" y="9" width="12" height="4.5" rx="1.2" {...stroke} /><path d="M4 4.7h.1M4 11.2h.1" {...stroke} /></svg>);
    case 'sync':
      return (<svg {...common}><path d="M13.5 8A5.5 5.5 0 0 1 3.6 10M2.5 8a5.5 5.5 0 0 1 9.9-2" {...stroke} /><path d="M11.5 2.5v3h-3M4.5 13.5v-3h3" {...stroke} /></svg>);
    default:
      return (<svg {...common}><path d="M2.5 4h11M6.5 4V2.5h3V4M4 4l.7 8.5c.1.8.7 1.5 1.5 1.5h3.6c.8 0 1.4-.7 1.5-1.5L12 4" {...stroke} /></svg>);
  }
}

const ACCENT_DOT: Record<AccentName, string> = {
  blue: '#0071e3',
  purple: '#a259ff',
  green: '#30d158',
  orange: '#ff9f0a',
  pink: '#ff375f',
  red: '#ff453a',
  yellow: '#e0a800',
  mint: '#63e6be',
  cyan: '#5ac8fa'
};

/**
 * Settings tab: macOS System Settings style — icon sidebar + search +
 * single-category pane. Appearance prefs are new; library/backend/sync
 * keep their existing behavior, restyled as Liquid Glass cards.
 */
export default function SettingsView(props: SettingsProps) {
  const {
    theme, setTheme, accent, setAccent, background, setBackground,
    glass, setGlass, density, setDensity, reduceMotion, setReduceMotion,
    reduceTransparency, setReduceTransparency,
    modelId, modelAuto, onPickModel, detectedModelName,
    musicDir, setMusicDir, booksDir, setBooksDir,
    audiobooksDir, setAudiobooksDir, mirrorDelete, setMirrorDelete,
    backendUp, backendUrl, onReset
  } = props;
  const [active, setActive] = useState<SectionId>('appearance');
  const [query, setQuery] = useState('');
  const [copied, setCopied] = useState(false);
  const [resetDone, setResetDone] = useState(false);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return SECTIONS;
    return SECTIONS.filter((s) =>
      `${s.title} ${s.blurb}`.toLowerCase().includes(q));
  }, [query]);

  const isSearching = query.trim().length > 0;
  const shown: SectionId[] = isSearching ? visible.map((s) => s.id) : [active];

  async function copyUrl() {
    try {
      await navigator.clipboard.writeText(backendUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard unavailable */ }
  }

  function reset() {
    try {
      for (const k of PREF_KEYS) localStorage.removeItem(k);
    } catch { /* private mode */ }
    onReset();
    setResetDone(true);
    setTimeout(() => setResetDone(false), 2500);
  }

  const backendLabel = backendUp === null
    ? 'Checking…'
    : backendUp ? 'Running' : 'Not running';

  const modelOptions = useMemo(() => ([
    { value: 'auto', label: 'Follow iPhone automatically', hint: detectedModelName ? `Now: ${detectedModelName}` : 'Recommended' },
    ...DEVICE_MODELS.map((m) => ({ value: m.id, label: m.name, hint: m.screen }))
  ]), [detectedModelName]);

  const selectedModel = DEVICE_MODELS.find((m) => m.id === modelId);

  return (
    <div className="ft-settings-v2">
      <div className="ft-set-toolbar glass">
        <div className="ft-set-searchwrap">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <circle cx="6" cy="6" r="4.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <path d="m9.3 9.3 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <input
            type="search"
            className="ft-set-search"
            placeholder="Search settings (try “aurora” or “glass”)"
            aria-label="Search settings"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && <span className="ft-set-count">{visible.length} match{visible.length === 1 ? '' : 'es'}</span>}
        </div>
        <span className="ft-hint">Apple-style preferences — everything saves instantly on this computer.</span>
      </div>

      <div className="ft-set-layout">
        <nav className="ft-set-side glass" aria-label="Settings categories">
          {SECTIONS.map((s) => {
            const highlighted = isSearching ? visible.some((v) => v.id === s.id) : active === s.id;
            return (
              <button
                key={s.id}
                className={`ft-set-nav${highlighted ? ' active' : ''}`}
                aria-current={!isSearching && active === s.id ? 'page' : undefined}
                aria-label={s.title}
                title={s.title}
                onClick={() => { setActive(s.id); setQuery(''); }}
              >
                <span className="ft-set-ico"><Icon name={s.icon} /></span>
                <span className="ft-set-navtext">{s.title}</span>
                {s.id === 'device' && modelAuto && <span className="ft-set-auto">Auto</span>}
              </button>
            );
          })}
        </nav>

        <div className="ft-set-main">
          {shown.includes('appearance') && (
            <section className="ft-panel ft-set-card" aria-label="Appearance">
              <header className="ft-set-head"><span className="ft-set-ico"><Icon name="sun" /></span><div><h3>Appearance</h3><p className="ft-hint">Theme, accent and density. Follows your computer by default.</p></div></header>
              <div className="ft-set-row">
                <div className="ft-set-label">Theme</div>
                <div className="ft-segment" role="tablist" aria-label="Theme">
                  {THEMES.map((t) => (
                    <button key={t.id} role="tab" aria-selected={theme === t.id}
                      className={theme === t.id ? 'on' : ''} onClick={() => setTheme(t.id)}>
                      {t.id === 'system' ? 'Auto' : t.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="ft-set-row">
                <div className="ft-set-label">Accent color</div>
                <div className="ft-swatches" role="radiogroup" aria-label="Accent color">
                  {ACCENTS.map((a) => (
                    <button key={a.id} role="radio" aria-checked={accent === a.id}
                      className={`ft-swatch${accent === a.id ? ' on' : ''}`}
                      title={a.label} onClick={() => setAccent(a.id)}>
                      <span className="ft-dot" style={{ background: ACCENT_DOT[a.id] }} />
                      <span className="ft-swatch-name">{a.label}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="ft-set-row">
                <div className="ft-set-label">Density</div>
                <div className="ft-segment" role="tablist" aria-label="Density">
                  {DENSITIES.map((d) => (
                    <button key={d.id} role="tab" aria-selected={density === d.id}
                      className={density === d.id ? 'on' : ''} onClick={() => setDensity(d.id)}>
                      {d.label}
                    </button>
                  ))}
                </div>
              </div>
            </section>
          )}

          {shown.includes('wallpaper') && (
            <section className="ft-panel ft-set-card" aria-label="Wallpaper">
              <header className="ft-set-head"><span className="ft-set-ico"><Icon name="image" /></span><div><h3>Wallpaper</h3><p className="ft-hint">Animated backgrounds behind everything. Static saves battery.</p></div></header>
              <div className="ft-bg-tiles" role="radiogroup" aria-label="Background">
                {BACKGROUNDS.map((b) => (
                  <button key={b.id} role="radio" aria-checked={background === b.id}
                    className={`ft-bg-tile bg-preview-${b.id}${background === b.id ? ' on' : ''}`}
                    onClick={() => setBackground(b.id)} title={`${b.label} — ${b.blurb}`}>
                    <BgPreview id={b.id} />
                    <span className="ft-bg-name">{b.label}</span>
                    <span className="ft-bg-check">{background === b.id ? '✓' : ''}</span>
                  </button>
                ))}
              </div>
              <div className="ft-set-row">
                <div className="ft-set-label">Style</div>
                <GlassSelect
                  label="Background style"
                  value={background}
                  onChange={(v) => setBackground(v as BackgroundName)}
                  options={BACKGROUNDS.map((b) => ({ value: b.id, label: b.label, hint: b.blurb }))}
                />
              </div>
            </section>
          )}

          {shown.includes('glass') && (
            <section className="ft-panel ft-set-card" aria-label="Glass and motion">
              <header className="ft-set-head"><span className="ft-set-ico"><Icon name="sliders" /></span><div><h3>Glass &amp; Motion</h3><p className="ft-hint">Liquid Glass lives on bars and menus — never on the content itself.</p></div></header>
              <div className="ft-set-row">
                <div className="ft-set-label">Glass intensity</div>
                <GlassSelect
                  label="Glass intensity"
                  value={glass}
                  onChange={(v) => setGlass(v as GlassName)}
                  options={GLASSES.map((g) => ({ value: g.id, label: g.label, hint: g.blurb }))}
                />
              </div>
              <label className="ft-switch" htmlFor="ft-set-motion">
                <div><strong>Reduce motion</strong><span className="ft-hint">Stops aurora, orbs and transitions.</span></div>
                <input id="ft-set-motion" type="checkbox" checked={reduceMotion}
                  onChange={(e) => setReduceMotion(e.target.checked)} />
                <span className="ft-track" aria-hidden="true"><span className="ft-switch-thumb" /></span>
              </label>
              <label className="ft-switch" htmlFor="ft-set-transp">
                <div><strong>Reduce transparency</strong><span className="ft-hint">Solid bars and menus. Best readability.</span></div>
                <input id="ft-set-transp" type="checkbox" checked={reduceTransparency}
                  onChange={(e) => setReduceTransparency(e.target.checked)} />
                <span className="ft-track" aria-hidden="true"><span className="ft-switch-thumb" /></span>
              </label>
            </section>
          )}

          {shown.includes('device') && (
            <section className="ft-panel ft-set-card" aria-label="Device art">
              <header className="ft-set-head"><span className="ft-set-ico"><Icon name="phone" /></span><div><h3>Device Art {modelAuto ? <span className="ft-set-auto">Auto</span> : <span className="ft-set-auto">Pinned</span>}</h3><p className="ft-hint">The header render follows your connected iPhone until you override it here — the only place to change it.</p></div></header>
              <div className="ft-set-row">
                <div className="ft-set-label">Header iPhone</div>
                <GlassSelect
                  label="Header iPhone"
                  title="Auto follows the connected iPhone; pick a model to pin it"
                  value={modelAuto ? 'auto' : modelId}
                  onChange={(v) => onPickModel(v)}
                  options={modelOptions}
                />
              </div>
              {selectedModel && (
                <p className="ft-hint">{modelAuto ? `Following ${detectedModelName || selectedModel.name} automatically. ` : ''}{selectedModel.name} · {selectedModel.screen} · {selectedModel.unlock}. Purely cosmetic — sync works the same on every model.</p>
              )}
            </section>
          )}

          {shown.includes('library') && (
            <section className="ft-panel ft-set-card" aria-label="Library folders">
              <header className="ft-set-head"><span className="ft-set-ico"><Icon name="folder" /></span><div><h3>Library folders</h3><p className="ft-hint">Where each view reads music, books and audiobooks.</p></div></header>
              <div className="ft-lib-list">
                <div className="ft-lib-row">
                  <label htmlFor="ft-set-music"><strong>Music</strong><span>Goes into VLC</span></label>
                  <input id="ft-set-music" value={musicDir} onChange={(e) => setMusicDir(e.target.value)} placeholder="/path/to/music" />
                </div>
                <div className="ft-lib-row">
                  <label htmlFor="ft-set-books"><strong>Books</strong><span>Go into Readest</span></label>
                  <input id="ft-set-books" value={booksDir} onChange={(e) => setBooksDir(e.target.value)} placeholder="/path/to/books" />
                </div>
                <div className="ft-lib-row">
                  <label htmlFor="ft-set-audiobooks"><strong>Audiobooks</strong><span>Go into BookPlayer</span></label>
                  <input id="ft-set-audiobooks" value={audiobooksDir} onChange={(e) => setAudiobooksDir(e.target.value)} placeholder="/path/to/audiobooks" />
                </div>
              </div>
            </section>
          )}

          {shown.includes('backend') && (
            <section className="ft-panel ft-set-card" aria-label="Backend connection">
              <header className="ft-set-head"><span className="ft-set-ico"><Icon name="server" /></span><div><h3>Backend</h3><p className="ft-hint">Local daemon — browsers can’t speak USB directly.</p></div></header>
              <div className="ft-specs">
                <div className="ft-spec">
                  <span>Status</span>
                  <strong>{backendLabel}</strong>
                </div>
                <div className="ft-spec">
                  <span>URL</span>
                  <strong className="ft-mono">{backendUrl}</strong>
                  <button className="ft-icon-btn" onClick={copyUrl}>
                    {copied ? 'Copied ✓' : 'Copy'}
                  </button>
                </div>
              </div>
              <p className="ft-hint">
                Same-origin in the browser — if it says “Not running”, start it with <span className="ft-mono">make dev</span> and refresh.
              </p>
            </section>
          )}

          {shown.includes('sync') && (
            <section className="ft-panel ft-set-card" aria-label="Sync defaults">
              <header className="ft-set-head"><span className="ft-set-ico"><Icon name="sync" /></span><div><h3>Sync defaults</h3><p className="ft-hint">Applies to the next Preview and Sync.</p></div></header>
              <label className="ft-check" htmlFor="ft-set-mirror">
                <input id="ft-set-mirror" type="checkbox" checked={mirrorDelete}
                  onChange={(e) => setMirrorDelete(e.target.checked)} />
                <span>Mirror mode — also delete from the iPhone files I deleted on the computer</span>
              </label>
              <p className="ft-hint">Off by default. Preview never changes anything either way.</p>
            </section>
          )}

          {shown.includes('reset') && (
            <section className="ft-panel ft-set-card" aria-label="Reset preferences">
              <header className="ft-set-head"><span className="ft-set-ico"><Icon name="trash" /></span><div><h3>Reset</h3><p className="ft-hint">Forget every preference on this computer and restore defaults.</p></div></header>
              <div>
                <button className="ft-icon-btn" onClick={reset}>
                  {resetDone ? 'Defaults restored ✓' : 'Reset all preferences'}
                </button>
              </div>
            </section>
          )}

          {query.trim() && visible.length === 0 && (
            <div className="ft-panel ft-set-card"><p className="ft-hint">No settings match “{query}”. Try “aurora”, “glass” or “iphone”.</p></div>
          )}
        </div>
      </div>
    </div>
  );
}
