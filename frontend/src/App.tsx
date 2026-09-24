import { useEffect, useMemo, useState } from 'react';
import './apple.css';
import { watchSystemFavicon } from './favicon';
import { api, type AppInfo, type Device, type SyncItem, type SyncPreview } from './api';
import { DEVICE_MODELS, type AccentName, type BackgroundName, type DensityName, type GlassName, type ThemeName } from './devices';
import Sidebar from './components/Sidebar';
import DeviceHeader from './components/DeviceHeader';
import DevicePanel from './components/DevicePanel';
import SyncTable from './components/SyncTable';
import BackupView from './components/BackupView';
import { FilesView, PhotosView } from './components/MediaViews';
import DiagnosticsView from './components/DiagnosticsView';
import ScreenView from './components/ScreenView';
import ToolboxView from './components/ToolboxView';
import FirmwareView from './components/FirmwareView';
import DocsView from './components/DocsView';
import SettingsView from './components/SettingsView';
import MatrixRain from './components/MatrixRain';
import RainWindow from './components/RainWindow';

const FALLBACK_APPS: AppInfo[] = [
  { bundle_id: 'org.videolan.vlc-ios', name: 'VLC', file_sharing: true, installed: true },
  { bundle_id: 'com.readest.readest', name: 'Readest', file_sharing: true, installed: true },
  { bundle_id: 'com.tortugapower.BookPlayer', name: 'BookPlayer', file_sharing: true, installed: true }
];

const VIEW_APP: Record<string, string> = {
  device: '',
  music: 'org.videolan.vlc-ios',
  books: 'com.readest.readest',
  audiobooks: 'com.tortugapower.BookPlayer',
  photos: '',
  screen: '',
  files: '',
  backup: '',
  diagnostics: '',
  toolbox: '',
  firmware: '',
  docs: '',
  settings: ''
};

const VIEW_LABEL: Record<string, string> = {
  device: 'Your iPhone at a glance — specs, storage, battery',
  music: 'Music goes into the VLC app',
  books: 'Books go into the Readest app',
  audiobooks: 'Audiobooks go into the BookPlayer app',
  photos: 'Photos on the iPhone (DCIM) — export works, import is best-effort',
  screen: 'Live iPhone screen — 3uTools-style realtime view, HD over USB or AirPlay',
  files: 'Browse files on the iPhone over AFC',
  backup: 'Back up the whole iPhone with idevicebackup2',
  diagnostics: 'Verification, crash reports and device log',
  toolbox: 'Local tools: tags, duplicates, ringtones, conversion',
  firmware: 'Signed firmware only — dry-run, nothing flashes yet',
  docs: 'The user guide — built in, works offline',
  settings: 'Every preference in one place — appearance, folders, sync defaults'
};

function stored<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T) ?? fallback;
  } catch {
    return fallback;
  }
}

export default function App() {
  const [view, setView] = useState(() =>
    (window.location.hash || '').replace('#/', '') || 'music');
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 900);
  const [theme, setTheme] = useState<ThemeName>(() => stored('freetunes-theme', 'system'));
  const [accent, setAccent] = useState<AccentName>(() => stored('freetunes-accent', 'blue'));
  const [background, setBackground] = useState<BackgroundName>(() => stored('freetunes-background', 'aurora'));
  const [glass, setGlass] = useState<GlassName>(() => stored('freetunes-glass', 'balanced'));
  const [density, setDensity] = useState<DensityName>(() => stored('freetunes-density', 'comfortable'));
  const [reduceMotion, setReduceMotion] = useState(() => {
    try { return localStorage.getItem('freetunes-reduce-motion') === '1'; } catch { return false; }
  });
  const [reduceTransparency, setReduceTransparency] = useState(() => {
    try { return localStorage.getItem('freetunes-reduce-transparency') === '1'; } catch { return false; }
  });
  const [modelId, setModelId] = useState<string>(() => stored('freetunes-model', 'iphone-15'));
  const [modelManual, setModelManual] = useState(() => {
    try { return localStorage.getItem('freetunes-model-auto') === '0'; } catch { return false; }
  });
  const [devices, setDevices] = useState<Device[]>([]);
  const [backendUp, setBackendUp] = useState<boolean | null>(null);
  const [apps, setApps] = useState<AppInfo[]>(FALLBACK_APPS);
  const [musicDir, setMusicDir] = useState<string>(() => stored('freetunes-music-dir', '/home/aurelio/Music'));
  const [booksDir, setBooksDir] = useState<string>(() => stored('freetunes-books-dir', '/home/aurelio/Music'));
  const [audiobooksDir, setAudiobooksDir] = useState<string>(() => stored('freetunes-audiobooks-dir', '/home/aurelio/Music'));
  const [mirrorDelete, setMirrorDelete] = useState(() => {
    try {
      return localStorage.getItem('freetunes-mirror-delete') === '1';
    } catch {
      return false;
    }
  });
  const [query, setQuery] = useState('');
  const [preview, setPreview] = useState<SyncPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [pairing, setPairing] = useState(false);

  const target = VIEW_APP[view] || '—';
  const viewLabel = VIEW_LABEL[view] ?? 'Pick a section on the left';
  const appName = apps.find((a) => a.bundle_id === target)?.name ?? '';
  const model = DEVICE_MODELS.find((m) => m.id === modelId) ?? DEVICE_MODELS[0];
  const isSyncView = view === 'music' || view === 'books' || view === 'audiobooks';

  function changeView(v: string) {
    setView(v);
    window.location.hash = `#/${v}`;
  }

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
    root.setAttribute('data-accent', accent);
    root.setAttribute('data-background', background);
    root.setAttribute('data-glass', glass);
    root.setAttribute('data-density', density);
    if (reduceMotion) root.setAttribute('data-reduce-motion', '1');
    else root.removeAttribute('data-reduce-motion');
    if (reduceTransparency) root.setAttribute('data-reduce-transparency', '1');
    else root.removeAttribute('data-reduce-transparency');
    try {
      localStorage.setItem('freetunes-theme', theme);
      localStorage.setItem('freetunes-accent', accent);
      localStorage.setItem('freetunes-background', background);
      localStorage.setItem('freetunes-glass', glass);
      localStorage.setItem('freetunes-density', density);
      localStorage.setItem('freetunes-reduce-motion', reduceMotion ? '1' : '0');
      localStorage.setItem('freetunes-reduce-transparency', reduceTransparency ? '1' : '0');
      localStorage.setItem('freetunes-model', modelId);
      localStorage.setItem('freetunes-model-auto', modelManual ? '0' : '1');
      localStorage.setItem('freetunes-music-dir', musicDir);
      localStorage.setItem('freetunes-books-dir', booksDir);
      localStorage.setItem('freetunes-audiobooks-dir', audiobooksDir);
      localStorage.setItem('freetunes-mirror-delete', mirrorDelete ? '1' : '0');
    } catch { /* private mode */ }
  }, [theme, accent, background, glass, density, reduceMotion, reduceTransparency, modelId, modelManual, musicDir, booksDir, audiobooksDir, mirrorDelete]);

  // Run after appearance attributes are applied, including restored preferences.
  useEffect(() => watchSystemFavicon(), [theme, accent]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    try {
      const [d, a] = await Promise.all([api.devices(), api.apps()]);
      setDevices(d);
      setApps(a);
      setBackendUp(true);
    } catch {
      setBackendUp(false);
    }
  }

  // Match the device render to the real iPhone until the user picks manually.
  // Follows any detected iPhone (trusted or not) so an untrusted-but-plugged
  // iPhone 11 already shows its own art while it waits for Trust.
  useEffect(() => {
    if (modelManual) return;
    const known = devices.find((d) => d.model_id && DEVICE_MODELS.some((m) => m.id === d.model_id));
    if (known) setModelId(known.model_id);
  }, [devices, modelManual]);

  // Remember the last real iPhone seen over USB, so the Screen tab can
  // still draw the right contour when the cable drops but Wi-Fi mirroring
  // (AirPlay) keeps going.
  const liveModelId = devices[0]?.model_id || '';
  useEffect(() => {
    if (!liveModelId) return;
    try {
      localStorage.setItem('freetunes-model-id-live', liveModelId);
    } catch { /* private mode */ }
  }, [liveModelId]);
  function storedLiveModel(): string {
    try {
      return localStorage.getItem('freetunes-model-id-live') || '';
    } catch {
      return '';
    }
  }

  const rows: SyncItem[] = useMemo(() => {
    if (!preview) return [];
    const all = [...preview.to_push, ...preview.to_delete, ...preview.to_skip];
    const q = query.trim().toLowerCase();
    if (!q) return all;
    return all.filter((r) => r.filename.toLowerCase().includes(q));
  }, [preview, query]);

  const counts = useMemo(
    () => ({ [view]: preview?.to_push.length ?? 0 }),
    [view, preview]
  );

  const banner = backendUp === false
    ? { cls: 'off', text: 'Backend is not running — start it with: make dev-backend, then refresh.' }
    : devices.length === 0
      ? { cls: 'off', text: 'No iPhone detected — plug it in with a USB cable, unlock it, and tap Trust on the phone.' }
      : !devices[0].trusted
        ? { cls: 'warn', text: `Found ${devices[0].name || 'your iPhone'} but it is not trusted — tap Trust on the phone and unlock it.` }
        : { cls: 'on', text: `Connected: ${devices[0].name} · iOS ${devices[0].ios_version}` };

  async function doPair() {
    const udid = devices[0]?.udid;
    if (!udid) return;
    setPairing(true);
    try {
      await api.pair(udid);
      await refresh();
    } finally {
      setPairing(false);
    }
  }

  // Each media view syncs its own folder; all default to the music folder.
  function dirFor(v: string): string {
    if (v === 'books') return booksDir;
    if (v === 'audiobooks') return audiobooksDir;
    return musicDir;
  }

  /** Restore every preference to its default (Settings → Reset calls this after clearing storage). */
  function resetPrefs() {
    setTheme('system');
    setAccent('blue');
    setBackground('aurora');
    setGlass('balanced');
    setDensity('comfortable');
    setReduceMotion(false);
    setReduceTransparency(false);
    setModelManual(false);
    setMusicDir('/home/aurelio/Music');
    setBooksDir('/home/aurelio/Music');
    setAudiobooksDir('/home/aurelio/Music');
    setMirrorDelete(false);
  }

  async function doPreview() {
    if (!target) return;
    setBusy(true);
    try {
      setPreview(await api.preview(target, dirFor(view), mirrorDelete));
    } finally {
      setBusy(false);
    }
  }

  async function doSync() {
    if (!target) return;
    setBusy(true);
    try {
      await api.run(target, dirFor(view), mirrorDelete, false);
      await doPreview();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`ft-shell${sidebarOpen ? '' : ' sidebar-hidden'}`}>
      <div className="ft-bg" aria-hidden="true"><i className="ft-bg-a" /><i className="ft-bg-b" /><i className="ft-bg-c" /><i className="ft-bg-d" /><i className="ft-bg-e" /><i className="ft-bg-f" />{background === 'matrix' && !reduceMotion && <MatrixRain />}{background === 'rain' && !reduceMotion && <RainWindow />}</div>
      {sidebarOpen && (
        <Sidebar view={view} setView={changeView} counts={counts} apps={apps}
          connectedName={devices[0]?.name} />
      )}
      {sidebarOpen && (
        <button className="ft-backdrop" aria-label="Close sidebar" onClick={() => setSidebarOpen(false)} />
      )}
      <main className="ft-main">
        <div className={`ft-devbanner ${banner.cls}`} role="status">
          <span>{banner.text}</span>
        </div>
        <DeviceHeader target={target} appName={appName} model={model} device={devices[0] ?? null} onSync={doSync} busy={busy}
          showTrust pairing={pairing} onPair={doPair} artPinned={modelManual} />
        <div className="ft-controls" role="toolbar" aria-label={
          isSyncView ? 'Sync options: library folder, search, and sync preview'
          : 'View options'}>
          <span className="ft-view-label">{viewLabel} · {model.blurb}</span>
          <span className="ft-controls-icons">
            <button
              className="ft-icon-btn"
              aria-expanded={sidebarOpen}
              aria-label="Toggle sidebar"
              onClick={() => setSidebarOpen((o) => !o)}
            >
              ☰
            </button>
            <button className="ft-icon-btn" aria-label="Refresh device status" onClick={refresh} title="Check again for your iPhone">
              ⟳
            </button>
          </span>
          {isSyncView ? (
            <>
              <div className="ft-field">
                <label htmlFor="ft-library">Library on this computer</label>
                <input id="ft-library" value={dirFor(view)} onChange={(e) => {
                  const v = e.target.value;
                  if (view === 'books') setBooksDir(v);
                  else if (view === 'audiobooks') setAudiobooksDir(v);
                  else setMusicDir(v);
                }} placeholder="/path/to/library" />
              </div>
              <div className="ft-field narrow">
                <label htmlFor="ft-sync-search">Search sync list</label>
                <input id="ft-sync-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search files" />
              </div>
              <button className="ft-sync-btn" disabled={busy || !target} onClick={doPreview}
                title={`Compare ${dirFor(view) || 'your library folder'} with ${appName || 'the app'} and list what would be copied`}>
                Preview sync
              </button>
            </>
          ) : null}
        </div>
        {view === 'device' ? (
          <DevicePanel device={devices[0] ?? null} />
        ) : view === 'backup' ? (
          <BackupView udid={devices[0]?.udid ?? ''} />
        ) : view === 'photos' ? (
          <PhotosView udid={devices[0]?.udid ?? ''} />
        ) : view === 'screen' ? (
          <ScreenView udid={devices[0]?.udid ?? ''} modelId={devices[0]?.model_id || storedLiveModel() || modelId} deviceName={devices[0]?.name} />
        ) : view === 'files' ? (
          <FilesView udid={devices[0]?.udid ?? ''} />
        ) : view === 'diagnostics' ? (
          <DiagnosticsView udid={devices[0]?.udid ?? ''} />
        ) : view === 'toolbox' ? (
          <ToolboxView musicDir={musicDir} udid={devices[0]?.udid ?? ''} />
        ) : view === 'firmware' ? (
          <FirmwareView udid={devices[0]?.udid ?? ''} productType={devices[0]?.product_type ?? ''} />
        ) : view === 'docs' ? (
          <DocsView />
        ) : view === 'settings' ? (
          <SettingsView
            theme={theme} setTheme={setTheme} accent={accent} setAccent={setAccent}
            background={background} setBackground={setBackground}
            glass={glass} setGlass={setGlass}
            density={density} setDensity={setDensity}
            reduceMotion={reduceMotion} setReduceMotion={setReduceMotion}
            reduceTransparency={reduceTransparency} setReduceTransparency={setReduceTransparency}
            modelId={modelId} modelAuto={!modelManual}
            onPickModel={(id) => {
              if (id === 'auto') setModelManual(false);
              else { setModelManual(true); setModelId(id); }
            }}
            detectedModelName={devices[0]?.model_id ? (DEVICE_MODELS.find((m) => m.id === devices[0].model_id)?.name ?? devices[0].model_id) : ''}
            musicDir={musicDir} setMusicDir={setMusicDir}
            booksDir={booksDir} setBooksDir={setBooksDir}
            audiobooksDir={audiobooksDir} setAudiobooksDir={setAudiobooksDir}
            mirrorDelete={mirrorDelete} setMirrorDelete={setMirrorDelete}
            backendUp={backendUp} backendUrl="http://127.0.0.1:8000"
            onReset={resetPrefs} />
        ) : (
          <SyncTable rows={rows} />
        )}
      </main>
    </div>
  );
}
