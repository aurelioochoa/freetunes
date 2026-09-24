import type { ReactNode } from 'react';
import type { AppInfo } from '../api';

const APP_ICONS: Record<string, string> = {
  music: '/app-vlc.svg',
  books: '/app-readest.svg',
  audiobooks: '/app-bookplayer.svg'
};

const ICONS: Record<string, ReactNode> = {
  music: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M6 12.5a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm8-9a2 2 0 1 1-4 0 2 2 0 0 1 4 0ZM6 10.5V3l8-2v8" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  books: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M2 3.5A1.5 1.5 0 0 1 3.5 2H13a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H3.5A1.5 1.5 0 0 1 2 11.5v-8Z" />
      <path d="M2 11.5A1.5 1.5 0 0 1 3.5 10H14" />
    </svg>
  ),
  audiobooks: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M3 10V8a5 5 0 0 1 10 0v2" strokeLinecap="round" />
      <rect x="1.5" y="9.5" width="3" height="4" rx="1.5" />
      <rect x="11.5" y="9.5" width="3" height="4" rx="1.5" />
    </svg>
  ),
  backup: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <ellipse cx="8" cy="3.5" rx="5" ry="2" />
      <path d="M3 3.5v9c0 1.1 2.2 2 5 2s5-.9 5-2v-9" />
      <path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2" />
    </svg>
  ),
  photos: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="1.5" y="3" width="13" height="10" rx="2" />
      <circle cx="8" cy="8" r="2.5" />
      <path d="M5 3l1.5-1.5h3L11 3" />
    </svg>
  ),
  files: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h3l1.5 2h4.5A1.5 1.5 0 0 1 14 6.5v5A1.5 1.5 0 0 1 12.5 13h-9A1.5 1.5 0 0 1 2 11.5v-7Z" />
    </svg>
  ),
  diagnostics: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M2 9h3l2-5 2 8 2-3h3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  toolbox: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M10.5 2.5a2.5 2.5 0 0 0-3.4 3L2 10.6V14h3.4l5.1-5.1a2.5 2.5 0 0 0 3-3.4l-1.8 1.8-2.1-.6-.6-2.1 1.5-2.1Z" strokeLinejoin="round" />
    </svg>
  ),
  firmware: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M8 1.5v9m0 0L5 7.5M8 10.5l3-3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M2.5 12.5h11" strokeLinecap="round" />
    </svg>
  ),
  device: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="4" y="1.5" width="8" height="13" rx="2" />
      <path d="M7 12.5h2" strokeLinecap="round" />
    </svg>
  ),
  screen: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="1.5" y="3" width="13" height="9" rx="1.5" />
      <path d="M6 13.5h4" strokeLinecap="round" />
    </svg>
  ),
  docs: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M2 3.5A1.5 1.5 0 0 1 3.5 2H13a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H3.5A1.5 1.5 0 0 1 2 11.5v-8Z" />
      <path d="M2 11.5A1.5 1.5 0 0 1 3.5 10H14" />
      <path d="M6 5.5h4M6 7.5h4" strokeLinecap="round" />
    </svg>
  ),
  settings: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="8" cy="8" r="2.2" />
      <path d="M8 1.8v2M8 12.2v2M1.8 8h2M12.2 8h2M3.6 3.6l1.4 1.4M11 11l1.4 1.4M12.4 3.6 11 5M5 11l-1.4 1.4" strokeLinecap="round" />
    </svg>
  )
};

export default function Sidebar({ view, setView, counts = {}, apps = [], connectedName }: {
  view: string;
  setView: (v: string) => void;
  counts?: Record<string, number>;
  apps?: AppInfo[];
  connectedName?: string;
}) {
  const items: [string, string, string][] = [
    ['music', 'Music', 'org.videolan.vlc-ios'],
    ['books', 'Books', 'com.readest.readest'],
    ['audiobooks', 'Audiobooks', 'com.tortugapower.BookPlayer'],
    ['photos', 'Photos', ''],
    ['screen', 'Screen', ''],
    ['files', 'Files', ''],
    ['backup', 'Backup', ''],
    ['diagnostics', 'Diagnostics', ''],
    ['toolbox', 'Toolbox', ''],
    ['firmware', 'Firmware', '']
  ];
  const installedById: Record<string, boolean> = {};
  for (const a of apps) installedById[a.bundle_id] = a.installed;
  return (
    <aside className="ft-sidebar">
      <div className="ft-brand">free<span>tunes</span></div>
      <div className="ft-section">Devices</div>
      <div className="ft-nav">
        <button className={view === 'device' ? 'active' : ''} onClick={() => setView('device')}>
          {ICONS.device}<span className="ft-nav-label">{connectedName || 'iPhone (USB)'}</span>
        </button>
      </div>
      <div className="ft-section">Library</div>
      <div className="ft-nav">
        {items.map(([k, label, bid]) => {
          const missing = bid !== '' && apps.length > 0 && installedById[bid] === false;
          return (
            <button key={k}
              className={`${view === k ? 'active' : ''}${missing ? ' not-installed' : ''}`}
              onClick={() => setView(k)}
              title={missing ? 'Not installed on the iPhone — get it free on the App Store' : label}>
              {APP_ICONS[k]
                ? <img src={APP_ICONS[k]} alt="" aria-hidden="true" className="ft-appicon" />
                : ICONS[k]}
              <span className="ft-nav-label">{label}</span>
              {missing
                ? <span className="ft-missing">get app</span>
                : (counts[k] ?? 0) > 0 && <span className="ft-badge">{counts[k]}</span>}
            </button>
          );
        })}
      </div>
      <div className="ft-section">General</div>
      <div className="ft-nav">
        {(['docs', 'settings'] as const).map((k) => {
          const label = k === 'docs' ? 'Documentation' : 'Settings';
          return (
            <button key={k}
              className={view === k ? 'active' : ''}
              onClick={() => setView(k)}
              title={label}>
              {ICONS[k]}
              <span className="ft-nav-label">{label}</span>
              {(counts[k] ?? 0) > 0 && <span className="ft-badge">{counts[k]}</span>}
            </button>
          );
        })}
      </div>
    </aside>
  );
}
