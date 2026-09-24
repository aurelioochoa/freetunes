import GlassSelect from './GlassSelect';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, type ScreenStatus } from '../api';
import { DEVICE_MODELS } from '../devices';
import DevModeControls from './DevModeControls';
import IPhoneFrame from './IPhoneFrame';
import ValeriaViewer, { type ValeriaConn } from './ValeriaViewer';

type Mode = 'preview' | 'valeria' | 'hd' | 'airplay';

function widthForQuality(quality: number): number {
  // Fast means fewer pixels to encode, ship, and decode — not just a
  // lower JPEG quality on the same 1170x2532 frame.
  if (quality <= 60) return 480;
  if (quality >= 85) return 1080;
  return 720;
}

function streamKey(udid: string, fps: number, quality: number): string {
  const width = widthForQuality(quality);
  return `${api.screenStreamUrl(udid, fps, quality, width)}&t=${fps}x${quality}x${width}`;
}

export default function ScreenView({ udid, modelId, deviceName }: { udid: string; modelId?: string; deviceName?: string }) {
  const [status, setStatus] = useState<ScreenStatus | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [mode, setMode] = useState<Mode>('preview');
  const [playing, setPlaying] = useState(true);
  const [fps, setFps] = useState(2);
  const [quality, setQuality] = useState(70);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  // Flips once the first mirrored frame paints, so the placeholder only
  // says "waiting" while it really is waiting.
  const [airSeen, setAirSeen] = useState(false);
  // The shell follows the phone's rotation: read each mirror's real pixels
  // (landscape video is wider than tall). MJPEG frames keep arriving on the
  // same <img>, so re-read on an interval — rotation mid-stream flips the
  // frame without a reload. The HD iframe is opaque, hence a manual toggle.
  const [previewLandscape, setPreviewLandscape] = useState(false);
  const [airLandscape, setAirLandscape] = useState(false);
  const [hdLandscape, setHdLandscape] = useState(false);
  const [valeriaLandscape, setValeriaLandscape] = useState(false);
  const previewRef = useRef<HTMLImageElement | null>(null);
  const airRef = useRef<HTMLImageElement | null>(null);
  // Which hardware contour to draw. 'auto' follows the connected iPhone
  // (or the last one seen); a manual pick wins — e.g. USB dropped but the
  // same phone keeps mirroring over AirPlay.
  const [contourPick, setContourPick] = useState(() => {
    try {
      return localStorage.getItem('freetunes-frame') || 'auto';
    } catch {
      return 'auto';
    }
  });
  const effModel = contourPick === 'auto' ? modelId : contourPick;
  const autoName = DEVICE_MODELS.find((m) => m.id === modelId)?.name
    ?? DEVICE_MODELS.find((m) => m.id === contourPick)?.name ?? 'iPhone';
  function pickContour(v: string) {
    setContourPick(v);
    try {
      localStorage.setItem('freetunes-frame', v);
    } catch { /* private mode */ }
  }

  function readOrientation(img: HTMLImageElement | null, set: (v: boolean) => void) {
    if (!img || !img.naturalWidth || !img.naturalHeight) return;
    set(img.naturalWidth > img.naturalHeight);
  }

  useEffect(() => {
    const t = setInterval(() => {
      readOrientation(previewRef.current, setPreviewLandscape);
      readOrientation(airRef.current, setAirLandscape);
    }, 2500);
    return () => clearInterval(t);
  }, []);

  const load = useCallback(async () => {
    setState('loading');
    try {
      const s = await api.screenStatus(udid);
      setStatus(s);
      setState('ready');
      if (s.hd.running) setMode('hd');
      else if (s.valeria.running) setMode('valeria');
    } catch {
      setStatus(null);
      setState('error');
    }
  }, [udid]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const s = await api.screenStatus(udid);
        setStatus(s);
        if (s.hd.running) setMode((m) => (m === 'preview' && !s.live ? 'hd' : m));
        else if (s.valeria.running) setMode((m) => (m === 'preview' ? 'valeria' : m));
      } catch { /* keep last good status */ }
    }, 10000);
    return () => clearInterval(t);
  }, [udid]);
  useEffect(() => { setPlaying(true); setMsg(''); setValeriaFps(null); setValeriaConn('connecting'); }, [udid]);
  useEffect(() => {
    setPreviewLandscape(false);
    setAirLandscape(false);
    setHdLandscape(false);
    setValeriaLandscape(false);
    previewRef.current = null;
    airRef.current = null;
  }, [udid]);

  async function snapshot() {
    if (!udid) return;
    setBusy(true);
    try {
      await api.screenSnapshot(udid);
      setMsg(status?.live
        ? 'Screenshot saved — that is exactly what the iPhone shows.'
        : 'Saved the placeholder — plug in your iPhone for real pixels.');
    } catch (e) {
      setMsg(`Screenshot failed: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function hdStart() {
    setBusy(true);
    setMsg('Starting the HD server — tunnel + page take ~10–20 s the first time…');
    try {
      const r = await api.screenHdStart(udid);
      if (r.ok && r.running) {
        setMsg('HD is live — full-rate video inside the frame below.');
        setMode('hd');
      } else {
        setMsg(r.reason || 'HD did not start.');
      }
      setStatus(await api.screenStatus(udid));
    } catch (e) {
      setMsg(`HD start failed: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function hdStop() {
    setBusy(true);
    try {
      await api.screenHdStop();
      setStatus(await api.screenStatus(udid));
      setMsg('HD server stopped.');
    } finally {
      setBusy(false);
    }
  }

  async function valeriaStart() {
    setBusy(true);
    setMsg('Starting QuickTime over USB — claiming the device takes ~5–10 s the first time…');
    try {
      const r = await api.screenValeriaStart(udid);
      if (r.ok && r.running) {
        setMsg('QuickTime is live — 30–60 fps video inside the frame below, no Developer Mode needed.');
        setMode('valeria');
      } else {
        setMsg(r.reason || 'QuickTime did not start.');
      }
      setStatus(await api.screenStatus(udid));
    } catch (e) {
      setMsg(`QuickTime start failed: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function valeriaStop() {
    setBusy(true);
    try {
      await api.screenValeriaStop();
      setStatus(await api.screenStatus(udid));
      setMsg('QuickTime server stopped.');
    } finally {
      setBusy(false);
    }
  }

  const [installing, setInstalling] = useState(false);
  const [usbmuxing, setUsbmuxing] = useState(false);
  const [installLog, setInstallLog] = useState('');
  const [copied, setCopied] = useState(false);
  // Live QuickTime readout from the native viewer (canvas, not the fork's
  // page): fps stays visible in the toolbar above the frame, never as a
  // footer inside the phone cutout.
  const [valeriaFps, setValeriaFps] = useState<number | null>(null);
  const [valeriaConn, setValeriaConn] = useState<ValeriaConn>('connecting');

  async function valeriaInstall() {
    setInstalling(true);
    setInstallLog('');
    setMsg('Installing QuickTime dependencies — pip takes ~1–3 min the first time…');
    try {
      const r = await api.screenValeriaInstall();
      if (r.ok && r.installed) {
        setMsg(r.note || 'Installed — replug the iPhone, tap Trust, then press Start QuickTime.');
      } else if (r.install_running) {
        setMsg(r.reason || 'Install already running — wait, then press Refresh.');
      } else {
        setMsg(r.reason || 'Install did not finish — try the manual command below.');
        if (r.log) setInstallLog(r.log.slice(-800));
      }
      setStatus(await api.screenStatus(udid));
    } catch (e) {
      setMsg(`Install failed: ${String(e)}`);
    } finally {
      setInstalling(false);
    }
  }

  async function usbmuxSetup() {
    setUsbmuxing(true);
    setInstallLog('');
    setMsg('Running the Linux USB setup — first build takes ~5–10 min, then it needs root…');
    try {
      const r = await api.screenValeriaUsbmuxSetup();
      if (r.ok && r.installed) {
        setMsg(r.note || 'USB setup done — replug the iPhone, tap Trust, then press Start QuickTime.');
      } else if (r.install_running) {
        setMsg(r.reason || 'USB setup already running — wait, then press Refresh.');
      } else {
        setMsg(r.reason || 'USB setup did not finish — try the command in a terminal (it needs sudo).');
        if (r.log) setInstallLog(r.log.slice(-800));
      }
      setStatus(await api.screenStatus(udid));
    } catch (e) {
      setMsg(`USB setup failed: ${String(e)}`);
    } finally {
      setUsbmuxing(false);
    }
  }

  async function copyInstallCommand(cmd: string) {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setMsg(`Copy this command and run it in a terminal: ${cmd}`);
    }
  }

  async function airplayToggle(running: boolean, embed = true) {
    setBusy(true);
    try {
      const r = running ? await api.screenAirplayStop() : await api.screenAirplayStart(embed);
      setStatus(await api.screenStatus(udid));
      setAirSeen(false);
      setMsg(running ? 'AirPlay receiver stopped.'
        : (r.ok ? (embed
          ? 'freetunes is an AirPlay target — mirror from Control Center and it appears right here.'
          : 'freetunes is an AirPlay target — the mirror opens in its own window.')
          : (r as { reason?: string }).reason || 'AirPlay did not start.'));
    } catch (e) {
      setMsg(`AirPlay failed: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  // Apple gates the CoreDevice media stream HD rides on to iOS 27+;
  // below that the phone answers "Remote control requires iOS 27.0 or
  // later", so offering Start HD is a promise the device will not keep.
  const iosMajor = parseInt(status?.ios_version?.split('.')[0] || '0', 10);
  const hdBlocked = iosMajor > 0 && iosMajor < 27;
  const live = !!status?.live;
  const hdUrl = status?.hd.url || '';
  const valeriaUrl = status?.valeria.url || '';
  // The fork's screen-mirror server speaks raw H.264 on /ws next to its
  // viewer page; the native canvas viewer below talks that socket
  // directly, so no page (and no footer/scrollbar) ever enters the frame.
  const valeriaWs = valeriaUrl
    ? valeriaUrl.replace(/^http/, 'ws').replace(/\/+$/, '') + '/ws'
    : '';
  const valeriaRunning = !!status?.valeria.running;
  const valeriaReady = status?.valeria.ready ?? !!status?.backends.valeria;
  const valeriaNeeds = status?.valeria.needs ?? [];
  const qtUsbmux = status?.valeria.usbmuxd;
  const qtUsbmuxReady = qtUsbmux?.ready ?? true;
  const airRunning = !!status?.airplay.running;
  const frameLabel = deviceName ? `${deviceName} iPhone contour` : undefined;
  // uxplay + avahi-daemon are host prerequisites, not iPhone ones: name
  // them with the command for *this* distro rather than offering a
  // button that can only fail.
  const airNeeds = status?.airplay.needs ?? [];
  const airEmbedded = !!status?.airplay.embedded;
  const airReady = status?.airplay.ready ?? !!status?.backends.uxplay;

  return (
    <div className="ft-media">
      <div className="ft-media-bar glass">
        <div className="ft-media-count" role="status">
          <strong>
            {state === 'ready'
              ? (live ? 'Live screen' : 'Screen (not live yet)')
              : 'Screen'}
          </strong>
          <span>
            {!udid ? 'No iPhone — sample frame.' : live
              ? `Mirroring ${status?.ios_version ? `iOS ${status.ios_version} · ` : ''}view-only, like 3uTools`
              : 'Finish the checklist below to get real pixels.'}
          </span>
          {state === 'ready' && (
            <span className={live ? 'ft-livepill on' : 'ft-livepill'}>
              {live ? '● LIVE' : '○ OFFLINE'}
            </span>
          )}
        </div>
        <div className="ft-media-tools">
          <div className="ft-segment" role="tablist" aria-label="Screen mode">
            {(['preview', 'valeria', 'hd', 'airplay'] as Mode[]).map((m) => (
              <button key={m} role="tab" aria-selected={mode === m}
                className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>
                {m === 'preview' ? 'Preview (USB)' : m === 'valeria' ? 'QuickTime (USB)' : m === 'hd' ? 'HD (USB)' : 'AirPlay (Wi-Fi)'}
              </button>
            ))}
          </div>
          <label className="ft-hint" htmlFor="ft-contour">Frame</label>
          <GlassSelect id="ft-contour" label="Frame" value={contourPick}
            onChange={pickContour}
            title="Match the frame to the iPhone that is sharing — Auto follows the connected iPhone"
            options={[
              { value: 'auto', label: `Auto · ${autoName}` },
              {'value': 'iphone-1st', 'label': 'Original iPhone', 'hint': 'Home button'},
              {'value': 'iphone-4', 'label': 'iPhone 4 / 4S', 'hint': 'Home button'},
              {'value': 'iphone-6', 'label': '6 / 6s / 7 / 8 era', 'hint': 'Home button'},
              {'value': 'iphone-se', 'label': 'SE · Home button', 'hint': 'Home button'},
              {'value': 'iphone-se-2', 'label': 'SE (2nd / 3rd gen)', 'hint': 'Home button'},
              {'value': 'iphone-x', 'label': 'X / XS · first notch', 'hint': 'Notch'},
              {'value': 'iphone-11', 'label': '11 / XR · Wide notch', 'hint': 'Notch'},
              {'value': 'iphone-11-pro', 'label': '11 Pro · Wide notch', 'hint': 'Notch'},
              {'value': 'iphone-11-pro-max', 'label': '11 Pro Max · Wide notch', 'hint': 'Notch'},
              {'value': 'iphone-13', 'label': 'Notch (12–14)', 'hint': 'Notch'},
              {'value': 'iphone-16e', 'label': '16e / 17e · notch', 'hint': 'Notch'},
              {'value': 'iphone-15', 'label': 'Dynamic Island', 'hint': 'Dynamic Island'},
              {'value': 'iphone-17', 'label': '17 / Air', 'hint': 'Dynamic Island'},
              {'value': 'iphone-16-pro', 'label': 'Pro · titanium', 'hint': 'Pro'},
              {'value': 'iphone-18-pro', 'label': '18 Pro', 'hint': 'Pro'},
              {'value': 'iphone-duo', 'label': 'Duo · open', 'hint': 'Foldable'},
              {'value': 'iphone-duo-folded', 'label': 'Duo · folded', 'hint': 'Foldable'},
            ]} />
          {mode === 'preview' && (
            <>
              <div className="ft-segment" role="tablist" aria-label="Preview frame rate">
                {[1, 2, 5].map((f) => (
                  <button key={f} role="tab" aria-selected={fps === f}
                    className={fps === f ? 'on' : ''} onClick={() => setFps(f)}
                    title={`${f} frame${f === 1 ? '' : 's'} per second`}>
                    {f} fps
                  </button>
                ))}
              </div>
              <div className="ft-segment" role="tablist" aria-label="Preview quality">
                {[60, 70, 85].map((q) => (
                  <button key={q} role="tab" aria-selected={quality === q}
                    className={quality === q ? 'on' : ''} onClick={() => setQuality(q)}
                    title={q === 60 ? 'Smaller, faster (480p long edge)' : q === 85 ? 'Sharper, slower (1080p long edge)' : 'Balanced (720p long edge)'}>
                    {q === 60 ? 'Fast' : q === 85 ? 'Sharp' : 'Balanced'}
                  </button>
                ))}
              </div>
              <button className="ft-icon-btn" disabled={!udid || busy}
                onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause preview' : 'Resume preview'}>
                {playing ? '❚❚ Pause' : '▶ Play'}
              </button>
              <button className="ft-icon-btn" disabled={!udid || busy} onClick={snapshot}>
                📷 Screenshot
              </button>
            </>
          )}
          <button className="ft-icon-btn" onClick={load} aria-label="Refresh screen status">⟳</button>
        </div>
        {msg && <div className="ft-opmsg" role="status">{msg}</div>}
      </div>

      {state === 'loading' ? (
        <div className="ft-screen-stage" aria-busy="true" aria-label="Loading screen">
          <figure className="ft-iphone-wrap">
            <IPhoneFrame modelId={effModel} label={frameLabel}>
              <div className="ft-screen-frame skeleton" style={{ minHeight: 380, width: '100%' }} />
            </IPhoneFrame>
          </figure>
        </div>
      ) : state === 'error' ? (
        <div className="ft-table"><div className="ft-empty">
          <strong>Could not reach the screen service</strong>
          <p>Is the backend running? Start it with <span className="ft-mono">make dev-backend</span>, then press Refresh.</p>
          <button className="ft-sync-btn" onClick={load}>Retry</button>
        </div></div>
      ) : mode === 'valeria' ? (
        valeriaUrl ? (
        <div className="ft-screen-stage">
          <>
            <div className="ft-screen-toolbar">
                <span className="ft-livepill on">● QUICKTIME LIVE</span>
                <span className={valeriaFps !== null ? 'ft-livepill on' : 'ft-livepill'} role="status">
                  {valeriaFps !== null ? `${valeriaFps} fps` : valeriaConn === 'error' ? '○ RECONNECTING' : '○ CONNECTING'}
                </span>
                <span className="ft-hint">H.264 over USB — the fast preview, no Developer Mode.</span>
                <button className="ft-icon-btn" disabled={busy} onClick={valeriaStop}>Stop QuickTime</button>
                <button className="ft-icon-btn" onClick={() => setValeriaLandscape((v) => !v)}
                  aria-pressed={valeriaLandscape}
                  title={valeriaLandscape ? 'Phone is upright again — back to portrait' : 'Phone is sideways — flip the frame to landscape'}>
                  {valeriaLandscape ? '⤢ Portrait' : '⤢ Landscape'}
                </button>
              </div>
              <figure className={`ft-iphone-wrap${valeriaLandscape ? ' is-landscape' : ''}`}>
                <IPhoneFrame modelId={effModel} label={frameLabel}
                  orientation={valeriaLandscape ? 'landscape' : 'portrait'}>
                  <ValeriaViewer wsUrl={valeriaWs}
                    onFps={setValeriaFps} onConn={setValeriaConn} />
                </IPhoneFrame>
              </figure>
            </>
        </div>
        ) : (
            <div className="ft-table"><div className="ft-empty ft-qt">
              <strong>QuickTime over USB — the fast preview</strong>
              <p className="ft-qt-sub">Same protocol QuickTime Player uses: 30–60 fps H.264 over USB,
                any trusted iPhone, <strong>no Developer Mode</strong>. While streaming
                the phone shows a fake 9:41 clock with notifications hidden (presentation mode).</p>
              {valeriaNeeds.length > 0 && !valeriaRunning && (
                <ol className="ft-needs ft-qt-needs">
                  {valeriaNeeds.map((n) => <li key={n}>{n}</li>)}
                </ol>
              )}
              {!valeriaReady && !valeriaRunning && status?.valeria.install_command && (
                <div className="ft-cmd-box" aria-label="Manual install command">
                  <code>{status.valeria.install_command}</code>
                  <button className="ft-icon-btn" disabled={busy || installing}
                    onClick={() => copyInstallCommand(status.valeria.install_command || '')}
                    title="Copy the manual pip command">
                    {copied ? '✓ Copied' : '⧉ Copy'}
                  </button>
                </div>
              )}
              <div className="ft-qt-actions" role="group" aria-label="QuickTime actions">
                {!valeriaReady && !valeriaRunning && (
                  <button className="ft-icon-btn" disabled={busy || installing || !!status?.valeria.install_running}
                    onClick={valeriaInstall}
                    title="Run pip install in the backend — same command as above">
                    {installing || status?.valeria.install_running ? '⏳ Installing…' : '⬇ Install dependencies'}
                  </button>
                )}
                {!qtUsbmuxReady && !valeriaRunning && (
                  <button className="ft-icon-btn" disabled={busy || usbmuxing}
                    onClick={usbmuxSetup}
                    title="Build the usbmuxd fork and switch the USB service to it (needs root — may ask you to run it in a terminal instead)">
                    {usbmuxing ? '⏳ Setting up USB…' : '🔌 Run Linux USB setup'}
                  </button>
                )}
                <button className="ft-sync-btn"
                  disabled={busy || installing || usbmuxing || !udid || (!valeriaReady && !valeriaRunning)}
                  onClick={valeriaStart} title={!valeriaReady && !valeriaRunning
                    ? 'Install the dependencies first (one click above)' : 'Start the QuickTime server'}>
                  Start QuickTime
                </button>
              </div>
              {installLog && (
                <p className="ft-mono ft-qt-log">{installLog}</p>
              )}
              {!!status?.valeria.log && (
                <p className="ft-mono ft-qt-log">{status.valeria.log}</p>
              )}
              {status?.valeria.linux_hint && (
                <p className="ft-hint ft-qt-note">{status.valeria.linux_hint}</p>
              )}
              {status?.valeria.usbmux_hint && (
                <p className="ft-hint ft-qt-note">{status.valeria.usbmux_hint}</p>
              )}
            </div></div>
        )
        ) : mode === 'hd' ? (
        hdUrl ? (
        <div className="ft-screen-stage">
          <>
            <div className="ft-screen-toolbar">
                <span className="ft-livepill on">● HD LIVE</span>
                <span className="ft-hint">Full-rate video + audio, straight from the iPhone over USB.</span>
                <button className="ft-icon-btn" disabled={busy} onClick={hdStop}>Stop HD</button>
                <button className="ft-icon-btn" onClick={() => setHdLandscape((v) => !v)}
                  aria-pressed={hdLandscape}
                  title={hdLandscape ? 'Phone is upright again — back to portrait' : 'Phone is sideways — flip the frame to landscape'}>
                  {hdLandscape ? '⤢ Portrait' : '⤢ Landscape'}
                </button>
              </div>
              <figure className={`ft-iphone-wrap${hdLandscape ? ' is-landscape' : ''}`}>
                <IPhoneFrame modelId={effModel} label={frameLabel}
                  orientation={hdLandscape ? 'landscape' : 'portrait'}>
                  <iframe src={hdUrl} title="Live iPhone screen in full quality"
                    className="ft-screen-hd" allow="autoplay; fullscreen" />
                </IPhoneFrame>
              </figure>
            </>
        </div>
        ) : (
            <div className="ft-table"><div className="ft-empty">
              <strong>{hdBlocked ? `HD needs iOS 27 — this iPhone runs ${status?.ios_version}` : 'HD is off'}</strong>
              {hdBlocked ? (
                <p>Apple gates the screen-mirroring service HD uses to iOS 27 and newer;
                  on iOS {status?.ios_version} the phone answers “Remote control requires
                  iOS 27.0 or later”. Use <strong>QuickTime (USB)</strong> for fast video,
                  <strong> Preview (USB)</strong> for stills or
                  <strong> AirPlay (Wi-Fi)</strong> for full-rate video with sound.</p>
              ) : (
                <p>Full-rate HEVC video over USB — needs <span className="ft-mono">pymobiledevice3</span>,
                  a trusted iPhone with Developer Mode on (iOS 17.4+ needs no extra setup).</p>
              )}
              <button className="ft-sync-btn"
                disabled={busy || !udid || !status?.backends.pymobiledevice3 || hdBlocked}
                onClick={hdStart} title={hdBlocked
                  ? `HD needs iOS 27 or newer — this iPhone runs ${status?.ios_version}`
                  : !status?.backends.pymobiledevice3
                    ? 'Install pymobiledevice3 first (see checklist)' : 'Start the HD server'}>
                Start HD
              </button>
              {!status?.backends.pymobiledevice3 && (
                <p className="ft-mono">{status?.hints.pymobiledevice3}</p>
              )}
            </div></div>
        )
        ) : mode === 'airplay' ? (
        <>
          {airRunning && airEmbedded && (
        <div className="ft-screen-stage">
            <figure className={`ft-iphone-wrap${airLandscape ? ' is-landscape' : ''}`}>
              <IPhoneFrame modelId={effModel} label={frameLabel}
                orientation={airLandscape ? 'landscape' : 'portrait'}>
                <img ref={airRef} className="ft-screen-img" alt="Live AirPlay mirror of the iPhone"
                  src={api.screenAirplayStreamUrl()}
                  onLoad={(e) => {
                    setAirSeen(true);
                    readOrientation(e.currentTarget, setAirLandscape);
                  }} />
              </IPhoneFrame>
              <figcaption className="ft-screen-cap">
                <span className={airSeen ? 'ft-livepill on' : 'ft-livepill'}>
                  {airSeen ? '● AIRPLAY LIVE' : '○ WAITING FOR IPHONE'}
                </span>
                <span className="ft-hint">
                  Wi-Fi mirror, view-only. Sound plays through this computer's speakers,
                  not the browser.
                </span>
              </figcaption>
            </figure>
        </div>
          )}
          <div className="ft-table"><div className="ft-empty">
            <strong>AirPlay mirror (Wi-Fi)</strong>
            <p>{status?.airplay.howto}. Best quality with sound — freetunes pretends
              to be an Apple TV. Both devices must share one Wi-Fi network.</p>
            {airNeeds.length > 0 && !airRunning && (
              <>
                <p>This computer is missing {airNeeds.length === 1 ? 'one piece' : 'two pieces'} —
                  run {airNeeds.length === 1 ? 'this' : 'these'} once, then press Start:</p>
                <ol className="ft-needs">
                  {airNeeds.map((n) => {
                    const [label, ...rest] = n.split(': ');
                    return (
                      <li key={n}>
                        {label}:{' '}
                        <span className="ft-mono">{rest.join(': ')}</span>
                      </li>
                    );
                  })}
                </ol>
              </>
            )}
            <div className="ft-media-tools" style={{ justifyContent: 'center' }}>
              <button className="ft-sync-btn" disabled={busy || (!airReady && !airRunning)}
                onClick={() => airplayToggle(airRunning)}
                title={!airReady && !airRunning
                  ? 'Install uxplay and start avahi-daemon first (commands above)'
                  : airRunning ? 'Stop the receiver' : 'Start the receiver'}>
                {airRunning ? 'Stop AirPlay receiver' : 'Start AirPlay receiver'}
              </button>
              {airRunning && !airEmbedded && (
                <button className="ft-icon-btn" disabled={busy}
                  onClick={async () => { await api.screenAirplayStop(); await airplayToggle(false, true); }}
                  title="Restart the receiver so the mirror renders inside freetunes">
                  Bring the mirror into this page
                </button>
              )}
              {airRunning && airEmbedded && (
                <button className="ft-icon-btn" disabled={busy}
                  onClick={async () => { await api.screenAirplayStop(); await airplayToggle(false, false); }}
                  title="Restart the receiver with uxplay's own window (full resolution)">
                  Use a separate window
                </button>
              )}
            </div>
            {airRunning && !airEmbedded && (
              <p>The mirror is playing in uxplay's own desktop window —
                it is a GStreamer window, so it cannot be moved inside the page.
                Use the button above to restart it as an in-page stream.</p>
            )}
            {airRunning && !airSeen && (
              <p><span className="ft-livepill on">● WAITING FOR IPHONE</span></p>
            )}
            {!!status?.airplay.log && (
              <p className="ft-mono">{status.airplay.log}</p>
            )}
          </div></div>
        </>
      ) : !udid ? (
        <div className="ft-table"><div className="ft-empty">
          <strong>No iPhone connected</strong>
          <p>Plug in your iPhone with a USB cable, unlock it, and tap Trust on the phone.
            The live preview appears here — inside the phone frame, like QuickTime, HD and AirPlay.</p>
        </div></div>
      ) : (
        <div className="ft-screen-stage">
          <figure className={`ft-iphone-wrap${previewLandscape ? ' is-landscape' : ''}`}>
            <IPhoneFrame modelId={effModel} label={frameLabel}
              orientation={previewLandscape ? 'landscape' : 'portrait'}>
              {udid && playing ? (
                <img ref={previewRef} key={streamKey(udid, fps, quality)}
                  className="ft-screen-img" alt="Live preview of the iPhone screen"
                  src={streamKey(udid, fps, quality)}
                  onLoad={(e) => readOrientation(e.currentTarget, setPreviewLandscape)} />
              ) : (
                <img ref={previewRef} className="ft-screen-img" alt="Last iPhone screenshot"
                  src={api.screenShotUrl(udid || 'mock-udid')}
                  onLoad={(e) => readOrientation(e.currentTarget, setPreviewLandscape)} />
              )}
            </IPhoneFrame>
            <figcaption className="ft-screen-cap">
              <span className={live ? 'ft-livepill on' : 'ft-livepill'}>
                {live ? '● LIVE PREVIEW' : '○ PLACEHOLDER'}
              </span>
              <span className="ft-hint">
                {playing ? `${fps} fps polling — view-only, no remote control.` : 'Paused — showing one still frame.'}
                {' '}For full frame rate, use QuickTime (USB) or HD.
              </span>
            </figcaption>
          </figure>
        </div>
      )}

      {state === 'ready' && status && status.needs.length > 0 && (
        <div className="ft-media-bar glass" aria-label="Setup checklist">
          <span className="ft-section" style={{ padding: 0 }}>To get the live screen</span>
          <ol className="ft-needs">
            {status.needs.map((n) => <li key={n}>{n}</li>)}
          </ol>
          <DevModeControls udid={udid} showState={false}
            onChanged={load} />
          <span className="ft-hint">
            Background: classic screenshot tools broke on iOS 17+ (Apple moved developer
            services behind a tunnel). freetunes speaks the new protocol via pymobiledevice3;
            full history in Compatibility → Live screen.
          </span>
        </div>
      )}
    </div>
  );
}
