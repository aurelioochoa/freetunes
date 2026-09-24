import { useMemo, useState } from 'react';
import { SOURCES } from '../sources';
import {
  COMMON_PROCS,
  ERROR_SUBTYPES,
  INFO_GUIDE,
  LOG_LEVEL_ORDER,
  LOG_LEVELS,
  WARN_SUBTYPES,
} from '../logLevels';

/**
 * Documentation tab: the user guide bundled as a static view, so it is
 * always available offline and can never drift from the shipped UI.
 * Developer docs (DEVELOPER.md, SYNC_MODEL.md) stay files in docs/.
 *
 * v2 design: same Apple System Settings shell as Settings (toolbar +
 * icon sidebar + single-category pane) so the two tabs read as one app.
 * Each guide section is a card with its own visual language: numbered
 * steps, mode tiles, callouts, glossary cards, source cards.
 */

type SectionId = 'start' | 'copy' | 'device' | 'backup' | 'files' | 'screen' | 'diagnostics' | 'toolbox' | 'firmware' | 'settings' | 'safety' | 'glossary' | 'sources';

const SECTIONS: { id: SectionId; title: string; blurb: string; icon: string }[] = [
  { id: 'start', title: 'Start', blurb: 'setup install cable trust dev browser', icon: 'rocket' },
  { id: 'copy', title: 'Copy files', blurb: 'copy preview sync music books audiobooks vlc readest bookplayer library trust', icon: 'sync' },
  { id: 'device', title: 'Your iPhone', blurb: 'device iphone specs storage battery banner trust connected model', icon: 'phone' },
  { id: 'backup', title: 'Backup', blurb: 'backup full incremental encrypt verify restore delete manifest idevicebackup2', icon: 'archive' },
  { id: 'files', title: 'Files & photos', blurb: 'files photos dcim export duplicates delete afc browse', icon: 'folder' },
  { id: 'screen', title: 'Live screen', blurb: 'screen live preview quicktime valeria hd airplay usb wifi developer mode screenshot mirror', icon: 'screen' },
  { id: 'diagnostics', title: 'Diagnostics', blurb: 'diagnostics health verification crash syslog log error live sample refurbished', icon: 'pulse' },
  { id: 'toolbox', title: 'Toolbox', blurb: 'toolbox tags duplicates ringtone convert compress heic ffmpeg developer mode', icon: 'wrench' },
  { id: 'firmware', title: 'Firmware', blurb: 'firmware signed ipsw flash dry-run restore gates', icon: 'chip' },
  { id: 'settings', title: 'Settings', blurb: 'settings theme accent model library backend mirror reset appearance', icon: 'sliders' },
  { id: 'safety', title: 'Safety', blurb: 'safety preview delete mirror drm own license', icon: 'shield' },
  { id: 'glossary', title: 'Glossary', blurb: 'glossary jargon bundle afc usbmuxd sha-256 hash mirror drm opds syslog crash backup developer ipsw', icon: 'book' },
  { id: 'sources', title: 'Sources', blurb: 'sources open github vlc readest bookplayer libimobiledevice ifuse license', icon: 'heart' },
];

/** Knowledge-base grouping for the compact index: doing vs looking up. */
const GROUPS: { label: string; ids: SectionId[] }[] = [
  { label: 'Guide', ids: ['start', 'copy', 'device', 'backup', 'files', 'screen', 'diagnostics', 'toolbox', 'firmware', 'settings'] },
  { label: 'Reference', ids: ['safety', 'glossary', 'sources'] },
];

/** Wiki-style backlinks: where to go next from each note. */
const RELATED: Record<SectionId, SectionId[]> = {
  start: ['copy', 'device', 'screen'],
  copy: ['device', 'backup', 'toolbox'],
  device: ['backup', 'diagnostics', 'screen'],
  backup: ['device', 'diagnostics'],
  files: ['copy', 'toolbox', 'backup'],
  screen: ['device', 'diagnostics'],
  diagnostics: ['device', 'backup', 'screen'],
  toolbox: ['copy', 'files', 'firmware'],
  firmware: ['backup', 'toolbox'],
  settings: ['start', 'copy'],
  safety: ['copy', 'backup', 'firmware'],
  glossary: ['copy', 'diagnostics', 'screen'],
  sources: ['start', 'glossary'],
};

const byId: Record<SectionId, { id: SectionId; title: string; blurb: string; icon: string }> =
  Object.fromEntries(SECTIONS.map((s) => [s.id, s])) as Record<SectionId, { id: SectionId; title: string; blurb: string; icon: string }>;

const GLOSSARY: [string, string][] = [
  ['bundle / bundle ID', 'Apple’s internal name for an app, e.g. org.videolan.vlc-ios means “the VLC app”. You never need to type these; freetunes finds them automatically.'],
  ['AFC (Apple File Connection)', 'The USB cable “language” freetunes speaks to exchange files with an app’s folder on the iPhone.'],
  ['usbmuxd', 'A small helper program on your computer that lets many programs share one iPhone USB connection. Installed automatically with freetunes’ dependencies.'],
  ['SHA-256 hash', 'A fingerprint of a file’s contents. freetunes compares fingerprints to know “already there” vs “new or changed” without guessing from file names or dates.'],
  ['mirror mode', 'Optional: also delete from the iPhone files you deleted on the computer. Off by default; enable it in the Settings tab.'],
  ['DRM', 'Copy protection. Protected store purchases only play in Apple’s own apps.'],
  ['OPDS', 'A way for ebook apps to download books from your computer over Wi-Fi instead of cable (planned).'],
  ['syslog / device log', 'The running commentary iOS writes about everything it does — every app and system part. The Diagnostics tab shows a live tail of it; search and level buttons narrow it down.'],
  ['crash report (.ips)', 'A file iOS writes when an app blows up. The Diagnostics tab lists them newest-first; an empty list is a healthy sign.'],
  ['backup (idevicebackup2)', 'A full copy of your iPhone stored on this computer. The Backup tab runs full or incremental backups; turn on encryption to include passwords and health data.'],
  ['Developer Mode', 'An iPhone switch (Settings → Privacy & Security) that unlocks screen capture and deep diagnostics for trusted computers. freetunes can reveal and enable it from the Screen tab; enabling restarts the phone.'],
  ['signed firmware (IPSW)', 'An iOS install file Apple still approves. The Firmware tab lists signed versions only and always dry-runs first — nothing ever flashes without you confirming twice.']
];

function Icon({ name }: { name: string }) {
  const common = { width: 16, height: 16, viewBox: '0 0 16 16', fill: 'none' as const, 'aria-hidden': true };
  const stroke = { stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  switch (name) {
    case 'rocket':
      return (<svg {...common}><path d="M8 1.5c2.5 1.5 3.5 4 3 6.5l2 2-2.5.5c-.8.8-1.8 1.3-2.5 1.5-.7-.2-1.7-.7-2.5-1.5L3 10l2-2c-.5-2.5.5-5 3-6.5Z" {...stroke} /><circle cx="8" cy="6" r="1.2" {...stroke} /><path d="M5.5 10.5c-.5 1-1 2.5-1 4 1.5 0 3-.5 4-1" {...stroke} /></svg>);
    case 'sync':
      return (<svg {...common}><path d="M13.5 8A5.5 5.5 0 0 1 3.6 10M2.5 8a5.5 5.5 0 0 1 9.9-2" {...stroke} /><path d="M11.5 2.5v3h-3M4.5 13.5v-3h3" {...stroke} /></svg>);
    case 'screen':
      return (<svg {...common}><rect x="1.5" y="3" width="13" height="9" rx="1.5" {...stroke} /><path d="M6 13.5h4" {...stroke} /></svg>);
    case 'sliders':
      return (<svg {...common}><path d="M2.5 5h11M2.5 11h11" {...stroke} /><circle cx="6" cy="5" r="1.8" fill="var(--glass)" {...stroke} /><circle cx="10.5" cy="11" r="1.8" fill="var(--glass)" {...stroke} /></svg>);
    case 'shield':
      return (<svg {...common}><path d="M8 1.5 13 3.5v4c0 3.5-2.2 5.8-5 7-2.8-1.2-5-3.5-5-7v-4Z" {...stroke} /><path d="m5.8 7.8 1.6 1.6 2.8-3" {...stroke} /></svg>);
    case 'book':
      return (<svg {...common}><path d="M2 3.5A1.5 1.5 0 0 1 3.5 2H13a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H3.5A1.5 1.5 0 0 1 2 11.5v-8Z" {...stroke} /><path d="M2 11.5A1.5 1.5 0 0 1 3.5 10H14" {...stroke} /><path d="M6 5.5h4M6 7.5h4" {...stroke} /></svg>);
    case 'heart':
      return (<svg {...common}><path d="M8 13.5S2.5 10 2.5 5.8C2.5 4 4 2.8 5.5 2.8c1 0 1.9.5 2.5 1.4.6-.9 1.5-1.4 2.5-1.4 1.5 0 3 1.2 3 3 0 4.2-5.5 7.7-5.5 7.7Z" {...stroke} /></svg>);
    case 'phone':
      return (<svg {...common}><rect x="5" y="1.8" width="6" height="12.4" rx="1.5" {...stroke} /><path d="M7 12.5h2" {...stroke} /></svg>);
    case 'archive':
      return (<svg {...common}><rect x="1.8" y="2.8" width="12.4" height="3.4" rx="1" {...stroke} /><path d="M3.5 6.2v5.3a1.5 1.5 0 0 0 1.5 1.5h6a1.5 1.5 0 0 0 1.5-1.5V6.2M6.5 2.8v3.4h3V2.8" {...stroke} /></svg>);
    case 'folder':
      return (<svg {...common}><path d="M1.8 4.5A1.5 1.5 0 0 1 3.3 3h2.8L7.6 5h4.9a1.5 1.5 0 0 1 1.5 1.5v4.8a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 1.8 11.3Z" {...stroke} /></svg>);
    case 'pulse':
      return (<svg {...common}><path d="M1.5 8h2.8l1.4-3.8 2.8 7.6 1.4-3.8h4.6" {...stroke} /></svg>);
    case 'wrench':
      return (<svg {...common}><path d="M10.2 2.3a3.4 3.4 0 0 0-4.5 4.5L2.3 10.2l3.5 3.5 3.4-3.4a3.4 3.4 0 0 0 4.5-4.5l-2.2 2.2-1.9-1.9Z" {...stroke} /></svg>);
    case 'chip':
      return (<svg {...common}><rect x="4.8" y="4.8" width="6.4" height="6.4" rx="1" {...stroke} /><path d="M6.5 2v2M9.5 2v2M6.5 12v2M9.5 12v2M2 6.5h2M2 9.5h2M12 6.5h2M12 9.5h2" {...stroke} /></svg>);
    case 'search':
      return (<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="6" cy="6" r="4.2" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="m9.3 9.3 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>);
    case 'check':
      return (<svg width="13" height="13" viewBox="0 0 13 13" aria-hidden="true"><path d="m2.5 7 2.6 2.6L10.5 4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>);
    default:
      return null;
  }
}

export default function DocsView() {
  const [active, setActive] = useState<SectionId>('start');
  const [query, setQuery] = useState('');

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return SECTIONS;
    const hay: Record<SectionId, string> = {
      start: 'start setup install dev browser trust',
      copy: 'copy preview sync music books audiobooks vlc readest bookplayer library trust',
      device: 'device iphone specs storage battery banner trust connected model',
      backup: 'backup full incremental encrypt verify restore delete manifest idevicebackup2',
      files: 'files photos dcim export duplicates delete afc browse',
      screen: 'screen live preview quicktime valeria hd airplay usb wifi developer mode screenshot mirror',
      diagnostics: 'diagnostics health verification crash syslog log error live sample refurbished',
      toolbox: 'toolbox tags duplicates ringtone convert compress heic ffmpeg developer mode',
      firmware: 'firmware signed ipsw flash dry-run restore gates',
      settings: 'settings theme accent model library backend mirror reset appearance',
      safety: 'safety preview delete mirror drm own license',
      glossary: `glossary jargon bundle afc usbmuxd sha-256 hash mirror drm opds syslog crash backup developer ipsw ${GLOSSARY.map(([k, v]) => `${k} ${v}`.toLowerCase()).join(' ')}`,
      sources: `sources open github vlc readest bookplayer libimobiledevice ifuse license ${SOURCES.map((s) => `${s.name} ${s.what} ${s.license}`.toLowerCase()).join(' ')}`,
    };
    // Match per word so "trust sync" finds sections mentioning either term.
    const words = q.split(/\s+/);
    return SECTIONS.filter((s) => words.every((w) => hay[s.id].includes(w)));
  }, [query]);

  const isSearching = query.trim().length > 0;
  const shown: SectionId[] = isSearching ? visible.map((s) => s.id) : [active];
  const q = query.trim();

  function go(id: SectionId) { setActive(id); setQuery(''); }

  const activeIdx = SECTIONS.findIndex((s) => s.id === active);
  const prevNote = SECTIONS[(activeIdx - 1 + SECTIONS.length) % SECTIONS.length];
  const nextNote = SECTIONS[(activeIdx + 1) % SECTIONS.length];

  return (
    <div className="ft-settings-v2 ft-docs-v2">
      <div className="ft-set-toolbar glass">
        <div className="ft-set-searchwrap">
          <Icon name="search" />
          <input
            id="ft-docs-search"
            type="search"
            className="ft-set-search"
            placeholder="Search guide (try “Trust” or “AirPlay”)"
            aria-label="Search guide"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && <span className="ft-set-count">{visible.length} match{visible.length === 1 ? '' : 'es'}</span>}
        </div>
        <span className="ft-hint">The user guide — built in, works offline. {isSearching ? `${visible.length} of ${SECTIONS.length} sections match.` : 'Pick a topic on the left.'}</span>
      </div>
      {!isSearching && (
        <p className="ft-hint" aria-label="About this guide">
          About this guide: it lives inside the app, so it works with no internet and can never
          drift from the buttons you see. One section per tab — search above to jump to any of them.
        </p>
      )}

      <div className="ft-set-layout">
        <nav className="ft-kb-side glass" aria-label="Guide index">
          {GROUPS.map((g) => (
            <div key={g.label} className="ft-kb-groupwrap">
              <div className="ft-kb-group" aria-hidden="true">{g.label}</div>
              {g.ids.map((id) => {
                const s = byId[id];
                const highlighted = isSearching ? visible.some((v) => v.id === s.id) : active === s.id;
                return (
                  <button
                    key={s.id}
                    className={`ft-kb-link${highlighted ? ' active' : ''}`}
                    aria-current={!isSearching && active === s.id ? 'page' : undefined}
                    aria-label={s.title}
                    title={s.title}
                    onClick={() => go(s.id)}
                  >
                    <Icon name={s.icon} />
                    <span className="ft-kb-linktext">{s.title}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="ft-set-main">
          {isSearching && visible.length === 0 && (
            <div className="ft-panel ft-set-card">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="search" /></span>
                <div><h3>No section matches “{q}”</h3><p className="ft-hint">Try “Trust”, “Sync” or “AirPlay” — or clear the search to browse.</p></div>
              </header>
              <div><button className="ft-icon-btn" onClick={() => setQuery('')}>Show the whole guide</button></div>
            </div>
          )}

          {shown.includes('start') && (
            <section className="ft-panel ft-set-card" aria-label="Start freetunes">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="rocket" /></span>
                <div><h3>What you need</h3><p className="ft-hint">Three things, then you’re set.</p></div>
              </header>
              <ol className="ft-steps">
                <li><span className="ft-step-num" aria-hidden="true">1</span><div><strong>An iPhone and its USB cable.</strong><span>Plug it in, unlock it, tap <strong>Trust</strong> on the phone screen.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">2</span><div><strong>One free app on the iPhone.</strong><span>Music → <strong>VLC</strong> · Ebooks → <strong>Readest</strong> · Audiobooks → <strong>BookPlayer</strong>.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">3</span><div><strong>freetunes running.</strong><span><span className="ft-kbd">make dev</span>, then open <span className="ft-kbd">http://127.0.0.1:5173</span>.</span></div></li>
              </ol>
              <div className="ft-callout">
                <span className="ft-callout-ico" aria-hidden="true">?</span>
                <p><strong>Why these apps?</strong> Apple doesn’t let other programs write into its own Music and Books apps. But it does let programs hand files to other apps — that open door is what freetunes uses.</p>
              </div>
            </section>
          )}

          {shown.includes('copy') && (
            <section className="ft-panel ft-set-card" aria-label="Copy files">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="sync" /></span>
                <div><h3>Copy files</h3><p className="ft-hint">The normal flow — Preview first, Sync second.</p></div>
              </header>
              <ol className="ft-steps">
                <li><span className="ft-step-num" aria-hidden="true">1</span><div><strong>Trust the computer.</strong><span>Plug in, unlock, tap <strong>Trust</strong> on the phone.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">2</span><div><strong>Pick a library.</strong><span>On the left choose <strong>Music</strong>, <strong>Books</strong> or <strong>Audiobooks</strong>.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">3</span><div><strong>Point at your folder.</strong><span>Type or paste the folder on this computer that holds the files.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">4</span><div><strong>Preview sync.</strong><span><span className="ft-pill push">Copy to iPhone</span> rows will be copied · <span className="ft-pill skip">Already on iPhone</span> rows are skipped.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">5</span><div><strong>Sync.</strong><span>Done — open VLC / Readest / BookPlayer on the phone.</span></div></li>
              </ol>
              <div className="ft-callout tip">
                <span className="ft-callout-ico" aria-hidden="true"><Icon name="check" /></span>
                <p><strong>Tip:</strong> use the search box to find one file in a long list. Click a row to highlight it.</p>
              </div>
            </section>
          )}

          {shown.includes('device') && (
            <section className="ft-panel ft-set-card" aria-label="Your iPhone">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="phone" /></span>
                <div><h3>Your iPhone</h3><p className="ft-hint">Specs, storage and battery at a glance.</p></div>
              </header>
              <ol className="ft-steps">
                <li><span className="ft-step-num" aria-hidden="true">1</span><div><strong>Read the banner.</strong><span>It always says what is true right now: backend stopped, no iPhone, not trusted, or connected with its iOS version.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">2</span><div><strong>Check storage and battery.</strong><span>The bar shows used vs total; the panel lists battery percent and whether it is charging.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">3</span><div><strong>Pick the picture.</strong><span>The iPhone model picker only changes the artwork — the app auto-matches your real phone until you pick manually.</span></div></li>
              </ol>
            </section>
          )}

          {shown.includes('backup') && (
            <section className="ft-panel ft-set-card" aria-label="Back up the iPhone">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="archive" /></span>
                <div><h3>Back up the whole iPhone</h3><p className="ft-hint">Full copy on this computer — the only undo button there is.</p></div>
              </header>
              <ol className="ft-steps">
                <li><span className="ft-step-num" aria-hidden="true">1</span><div><strong>Before you start.</strong><span>Unlocked phone, tap <strong>Trust</strong>, enter the device passcode, keep the screen on and the cable direct.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">2</span><div><strong>Full first, incremental after.</strong><span>A full backup copies everything; later runs only add what changed.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">3</span><div><strong>Turn on encryption.</strong><span>It includes passwords and health data — without it those are skipped, and an encrypted backup needs its password to restore.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">4</span><div><strong>Verify, then trust it.</strong><span>Run <strong>Verify</strong> after big backups; <strong>Restore</strong> writes the backup back, <strong>Delete</strong> removes it from this computer.</span></div></li>
              </ol>
            </section>
          )}

          {shown.includes('files') && (
            <section className="ft-panel ft-set-card" aria-label="Files and photos">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="folder" /></span>
                <div><h3>Files &amp; photos</h3><p className="ft-hint">Look inside the iPhone and pull things out.</p></div>
              </header>
              <ol className="ft-steps">
                <li><span className="ft-step-num" aria-hidden="true">1</span><div><strong>Files tab: browse.</strong><span>Walk the iPhone’s shared folders over the cable, same view as a Finder window.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">2</span><div><strong>Photos tab: export.</strong><span>Your camera roll (DCIM). <strong>Export</strong> downloads to this computer; deleting frees phone space. Import is best-effort.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">3</span><div><strong>Duplicates finder.</strong><span>Groups byte-identical photos so you can keep one copy and delete the rest.</span></div></li>
              </ol>
            </section>
          )}

          {shown.includes('screen') && (
            <section className="ft-panel ft-set-card" aria-label="Watch the live screen">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="screen" /></span>
                <div><h3>Watch your iPhone screen live</h3><p className="ft-hint">View-only — watch and screenshot here, tap on the phone itself.</p></div>
              </header>
              <div className="ft-mode-grid">
                <div className="ft-mode">
                  <span className="ft-pill on">Preview · USB</span>
                  <h4>Works everywhere</h4>
                  <p>Once the phone is trusted. A still image, 1–5 frames per second.</p>
                </div>
                <div className="ft-mode">
                  <span className="ft-pill on">QuickTime · USB</span>
                  <h4>Fast preview, no Developer Mode</h4>
                  <p>30–60 fps H.264 over USB (Valeria) — any trusted iPhone. Shows a fake 9:41 clock while streaming.</p>
                </div>
                <div className="ft-mode">
                  <span className="ft-pill hd">HD · USB</span>
                  <h4>Full-rate video + sound</h4>
                  <p>Only on newer iOS. On older iPhones the button stays greyed out — use QuickTime, Preview or AirPlay.</p>
                </div>
                <div className="ft-mode">
                  <span className="ft-pill air">AirPlay · Wi-Fi</span>
                  <h4>No cable</h4>
                  <p>Needs the <span className="ft-kbd">uxplay</span> receiver and <span className="ft-kbd">avahi-daemon</span>, same Wi-Fi, then Control Center → Screen Mirroring → freetunes.</p>
                </div>
              </div>
              <div className="ft-callout">
                <span className="ft-callout-ico" aria-hidden="true">!</span>
                <p>Modern iOS hides screen capture behind Developer Mode plus a developer image that iOS forgets on every restart. If the screen worked yesterday and is offline today, the Screen tab’s checklist names the exact missing piece — usually one button press.</p>
              </div>
            </section>
          )}

          {shown.includes('diagnostics') && (
            <section className="ft-panel ft-set-card" aria-label="Check the iPhone health">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="pulse" /></span>
                <div><h3>Check your iPhone’s health</h3><p className="ft-hint">Read-only over the cable — nothing changes, nothing uploads.</p></div>
              </header>
              <ol className="ft-steps">
                <li><span className="ft-step-num" aria-hidden="true">1</span><div><strong>Verification.</strong><span>Is the model number retail-new, refurbished, or a service replacement — and is the serial readable.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">2</span><div><strong>Crash reports.</strong><span>Every crash file on the phone, newest first, with kind (crash/jetsam/panic) and exception. Click a row for the local preview. Empty (“None found”) is a healthy sign.</span></div></li>
                <li><span className="ft-step-num" aria-hidden="true">3</span><div><strong>Device log.</strong><span>A live tail of what iOS is doing. Search for an app name, filter by Errors, then <strong>Copy</strong> or <strong>Download .log</strong>.</span></div></li>
              </ol>
              <div className="ft-mode-grid" aria-label="Log filter levels">
                {LOG_LEVEL_ORDER.map((id) => (
                  <div key={id} className="ft-mode" title={`${LOG_LEVELS[id].tooltip} ${LOG_LEVELS[id].whenToUse}`}>
                    <span className="ft-pill on">{LOG_LEVELS[id].label}</span>
                    <h4>{LOG_LEVELS[id].includes}</h4>
                    <p>{LOG_LEVELS[id].whenToUse}</p>
                  </div>
                ))}
              </div>
              <p className="ft-hint">
                These are freetunes’ own filters — not Apple’s levels. Apple grades severity as Debug&nbsp;&lt;&nbsp;Info&nbsp;&lt;&nbsp;Default&nbsp;(&lt;Notice&gt;)&nbsp;&lt;&nbsp;Error&nbsp;&lt;&nbsp;Fault;
                freetunes only matches words, so <span className="ft-mono">&lt;Error&gt;</span> lands in Errors via “error” and <span className="ft-mono">&lt;Notice&gt;</span> lands in Warnings via “notice”.
              </p>
              <div className="ft-chip-row" aria-label="Error keywords">
                {ERROR_SUBTYPES.map((s) => (
                  <span key={s.keyword} className="ft-chip" title={`${s.tooltip} What to do: ${s.action}`}>{s.keyword}</span>
                ))}
              </div>
              <p className="ft-hint">Red rows matched one of these 9 error keywords (checked first, so they win over warnings). Hover any chip for what it means and what to do.</p>
              <div className="ft-chip-row" aria-label="Warning keywords">
                {WARN_SUBTYPES.map((s) => (
                  <span key={s.keyword} className="ft-chip" title={`${s.tooltip} What to do: ${s.action}`}>{s.keyword}</span>
                ))}
              </div>
              <p className="ft-hint">Amber rows matched one of these 8 warning keywords. “Notice” is just Apple’s routine default tag; “low” can mean Jetsam memory pressure; “thermal”/“throttle” mean the device is slowing itself to stay safe.</p>
              <div className="ft-chip-row" aria-label="Processes you will meet">
                {COMMON_PROCS.map((p) => (
                  <span key={p.name} className="ft-chip" title={p.blurb}>{p.name}</span>
                ))}
              </div>
              <p className="ft-hint">{INFO_GUIDE.what} {INFO_GUIDE.tip} Full reference with examples: <span className="ft-mono">docs/DIAGNOSTICS.md</span>.</p>
              <div className="ft-callout">
                <span className="ft-callout-ico" aria-hidden="true">!</span>
                <p><strong>LIVE vs SAMPLE:</strong> the pill says where the bytes came from — your phone just now, or built-in samples when no iPhone is plugged in.</p>
              </div>
            </section>
          )}

          {shown.includes('toolbox') && (
            <section className="ft-panel ft-set-card" aria-label="Local tools">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="wrench" /></span>
                <div><h3>Toolbox</h3><p className="ft-hint">Small jobs on files from your computer or the iPhone.</p></div>
              </header>
              <div className="ft-chip-row" aria-label="Toolbox tools">
                {['Duplicate finder', 'Audio tags', 'Ringtone ≤ 40 s', 'Format conversion', 'Compress photo', 'HEIC → JPG', 'Developer Mode'].map((c) => (
                  <span key={c} className="ft-chip">{c}</span>
                ))}
              </div>
              <p className="ft-hint">Audio and photo tools need <span className="ft-kbd">ffmpeg</span> / Pillow on this computer — the tab says so when they are missing. Leaving the destination empty downloads the result instead of saving it. The Developer Mode tool unlocks live screen and deep diagnostics on iOS 16+.</p>
            </section>
          )}

          {shown.includes('firmware') && (
            <section className="ft-panel ft-set-card" aria-label="Firmware versions">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="chip" /></span>
                <div><h3>Firmware</h3><p className="ft-hint">Look, don’t touch — until you mean it twice.</p></div>
              </header>
              <ul className="ft-check-list">
                <li><span className="ft-check-ico" aria-hidden="true"><Icon name="check" /></span><span><strong>Signed versions only.</strong> Anything Apple no longer approves is not listed and cannot be installed.</span></li>
                <li><span className="ft-check-ico" aria-hidden="true"><Icon name="check" /></span><span><strong>Dry-run first, always.</strong> It shows the exact command and the safety gates — nothing flashes until you confirm twice.</span></li>
              </ul>
            </section>
          )}

          {shown.includes('settings') && (
            <section className="ft-panel ft-set-card" aria-label="Settings">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="sliders" /></span>
                <div><h3>Settings</h3><p className="ft-hint">Every preference in one place. Everything is remembered on this computer.</p></div>
              </header>
              <div className="ft-chip-row" aria-label="Settings categories">
                {['Theme', 'Accent color', 'iPhone model art', 'Library folders', 'Backend status', 'Mirror mode', 'Reset'].map((c) => (
                  <span key={c} className="ft-chip">{c}</span>
                ))}
              </div>
              <p className="ft-hint">Appearance (theme, accent, wallpaper, glass), device art, library folders, backend connection, sync defaults and reset — open the <strong>Settings</strong> tab on the left to change any of them.</p>
            </section>
          )}

          {shown.includes('safety') && (
            <section className="ft-panel ft-set-card" aria-label="Safety notes">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="shield" /></span>
                <div><h3>Safety notes</h3><p className="ft-hint">What freetunes will — and won’t — touch.</p></div>
              </header>
              <ul className="ft-check-list">
                <li><span className="ft-check-ico" aria-hidden="true"><Icon name="check" /></span><span><strong>Preview never changes anything.</strong> Sync only adds files; it never deletes from your iPhone unless you explicitly turn on mirror mode.</span></li>
                <li><span className="ft-check-ico" aria-hidden="true"><Icon name="check" /></span><span>Only copy files you own or that are freely licensed.</span></li>
                <li><span className="ft-check-ico" aria-hidden="true"><Icon name="check" /></span><span>Encrypted Apple purchases (DRM) will not play in VLC / Readest / BookPlayer.</span></li>
              </ul>
            </section>
          )}

          {shown.includes('glossary') && (
            <section className="ft-panel ft-set-card" aria-label="Glossary">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="book" /></span>
                <div><h3>Glossary</h3><p className="ft-hint">Jargon, translated. {GLOSSARY.length} terms.</p></div>
              </header>
              <dl className="ft-gloss-grid">
                {GLOSSARY.map(([term, def]) => (
                  <div key={term} className="ft-gloss-card">
                    <dt>{term}</dt>
                    <dd>{def}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          {shown.includes('sources') && (
            <section className="ft-panel ft-set-card" aria-label="Open-source building blocks">
              <header className="ft-set-head">
                <span className="ft-set-ico"><Icon name="heart" /></span>
                <div><h3>Open-source building blocks</h3><p className="ft-hint">freetunes stands on these free projects.</p></div>
              </header>
              <ul className="ft-src-grid">
                {SOURCES.map((s) => (
                  <li key={s.url + s.what} className="ft-src-card">
                    <a href={s.url} target="_blank" rel="noreferrer">{s.name} <span aria-hidden="true">↗</span></a>
                    <p>{s.what}</p>
                    <span className="ft-lic">{s.license}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {!isSearching && (
            <nav className="ft-panel ft-set-card ft-kb-rel" aria-label="Keep exploring">
              <div className="ft-kb-rel-row">
                <span className="ft-hint">Related</span>
                {RELATED[active].map((id) => (
                  <button key={id} className="ft-kb-chip" onClick={() => go(id)}>
                    {byId[id].title}
                  </button>
                ))}
              </div>
              <div className="ft-kb-prevnext">
                <button className="ft-kb-chip" onClick={() => go(prevNote.id)} aria-label={`Previous note: ${prevNote.title}`}>
                  ← Prev · {prevNote.title}
                </button>
                <button className="ft-kb-chip" onClick={() => go(nextNote.id)} aria-label={`Next note: ${nextNote.title}`}>
                  Next · {nextNote.title} →
                </button>
              </div>
            </nav>
          )}
        </div>
      </div>
    </div>
  );
}
