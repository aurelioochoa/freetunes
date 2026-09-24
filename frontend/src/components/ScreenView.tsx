import GlassSelect, { type GlassOption } from './GlassSelect';
import { useCallback, useEffect, useRef, useState, type ReactNode, type SyntheticEvent } from 'react';
import { api, type ScreenStatus } from '../api';
import { DEVICE_MODELS } from '../devices';
import DevModeControls from './DevModeControls';
import IPhoneFrame from './IPhoneFrame';
import ValeriaViewer, { type ValeriaConn } from './ValeriaViewer';

type Mode = 'preview' | 'valeria' | 'hd' | 'airplay';

const MODES: { id: Mode; label: string }[] = [
  { id: 'preview', label: 'Preview (USB)' },
  { id: 'valeria', label: 'QuickTime (USB)' },
  { id: 'hd', label: 'HD (USB)' },
  { id: 'airplay', label: 'AirPlay (Wi-Fi)' },
];

const QUALITIES = [
  { q: 60, label: 'Fast', title: 'Smaller, faster (480p long edge)', width: 480 },
  { q: 70, label: 'Balanced', title: 'Balanced (720p long edge)', width: 720 },
  { q: 85, label: 'Sharp', title: 'Sharper, slower (1080p long edge)', width: 1080 },
];

const FRAME_OPTIONS: GlassOption[] = [
  { value: 'iphone-1st', label: 'Original iPhone', hint: 'Home button' },
  { value: 'iphone-4', label: 'iPhone 4 / 4S', hint: 'Home button' },
  { value: 'iphone-6', label: '6 / 6s / 7 / 8 era', hint: 'Home button' },
  { value: 'iphone-se', label: 'SE · Home button', hint: 'Home button' },
  { value: 'iphone-se-2', label: 'SE (2nd / 3rd gen)', hint: 'Home button' },
  { value: 'iphone-x', label: 'X / XS · first notch', hint: 'Notch' },
  { value: 'iphone-11', label: '11 / XR · Wide notch', hint: 'Notch' },
  { value: 'iphone-11-pro', label: '11 Pro · Wide notch', hint: 'Notch' },
  { value: 'iphone-11-pro-max', label: '11 Pro Max · Wide notch', hint: 'Notch' },
  { value: 'iphone-13', label: 'Notch (12–14)', hint: 'Notch' },
  { value: 'iphone-16e', label: '16e / 17e · notch', hint: 'Notch' },
  { value: 'iphone-15', label: 'Dynamic Island', hint: 'Dynamic Island' },
  { value: 'iphone-17', label: '17 / Air', hint: 'Dynamic Island' },
  { value: 'iphone-16-pro', label: 'Pro · titanium', hint: 'Pro' },
  { value: 'iphone-18-pro', label: '18 Pro', hint: 'Pro' },
  { value: 'iphone-duo', label: 'Duo · open', hint: 'Foldable' },
  { value: 'iphone-duo-folded', label: 'Duo · folded', hint: 'Foldable' },
];

const FRAME_KEY = 'freetunes-frame';

function readStored(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback; // private mode
  }
}

/** Landscape when the mirror's real pixels are wider than tall. */
function isLandscape(img: HTMLImageElement | null): boolean | null {
  if (!img || !img.naturalWidth || !img.naturalHeight) return null;
  return img.naturalWidth > img.naturalHeight;
}

function Empty({ className = '', children }: { className?: string; children: ReactNode }) {
  return <div className="ft-table"><div className={`ft-empty ${className}`.trim()}>{children}</div></div>;
}

function RotateButton({ landscape, onToggle }: { landscape: boolean; onToggle: () => void }) {
  return (
    <button className="ft-icon-btn" onClick={onToggle} aria-pressed={landscape}
      title={landscape ? 'Phone is upright again — back to portrait' : 'Phone is sideways — flip the frame to landscape'}>
      {landscape ? '⤢ Portrait' : '⤢ Landscape'}
    </button>
  );
}

export default function ScreenView({ udid, modelId, deviceName }: { udid: string; modelId?: string; deviceName?: string }) {
  const [status, setStatus] = useState<ScreenStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const [mode, setMode] = useState<Mode>('preview');
  const [playing, setPlaying] = useState(true);
  const [fps, setFps] = useState(2);
  const [quality, setQuality] = useState(70);
  // One flag for every long-running button (start/stop/install/setup):
  // two of them at once would only fight over the same USB device.
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState('');
  const [installLog, setInstallLog] = useState('');
  const [copied, setCopied] = useState(false);
  // Flips once the first mirrored frame paints, so the placeholder only
  // says "waiting" while it really is waiting.
  const [airSeen, setAirSeen] = useState(false);
  // Live QuickTime readout from the native canvas viewer, shown in the
  // toolbar above the frame, never as a footer inside the phone cutout.
  const [valeriaFps, setValeriaFps] = useState<number | null>(null);
  const [valeriaConn, setValeriaConn] = useState<ValeriaConn>('connecting');
  // The shell follows the phone's rotation. MJPEG frames keep arriving on
  // the same <img>, so re-read its pixels on an interval; the HD iframe
  // and QuickTime canvas are opaque to that, hence a manual toggle there.
  const [landscape, setLandscape] = useState(false);
  const imgRef = useRef<HTMLImageElement | null>(null);
  // Jump to a running HD/QuickTime server once per iPhone — on the first
  // status only. Re-deciding on every poll (or ⟳) yanked the user back
  // to QuickTime whenever they opened another tab while it streamed.
  const autoPicked = useRef(false);

  // Which hardware contour to draw. 'auto' follows the connected iPhone
  // (or the last one seen); a manual pick wins — e.g. USB dropped but the
  // same phone keeps mirroring over AirPlay.
  const [contourPick, setContourPick] = useState(() => readStored(FRAME_KEY, 'auto'));
  const effModel = contourPick === 'auto' ? modelId : contourPick;
  const autoName = DEVICE_MODELS.find((m) => m.id === modelId)?.name ?? 'iPhone';
  function pickContour(v: string) {
    setContourPick(v);
    try {
      localStorage.setItem(FRAME_KEY, v);
    } catch { /* private mode */ }
  }

  const applyStatus = useCallback((s: ScreenStatus) => {
    setStatus(s);
    setFailed(false);
    if (!autoPicked.current) {
      autoPicked.current = true;
      if (s.hd.running) setMode('hd');
      else if (s.valeria.running) setMode('valeria');
    }
  }, []);

  // A refresh keeps the current view (and any live viewer) mounted; only
  // the very first load shows the skeleton.
  const load = useCallback(async () => {
    try {
      applyStatus(await api.screenStatus(udid));
    } catch {
      setFailed(true);
    }
  }, [udid, applyStatus]);

  useEffect(() => {
    autoPicked.current = false;
    setStatus(null);
    setPlaying(true);
    setMsg('');
    setValeriaFps(null);
    setValeriaConn('connecting');
    setLandscape(false);
    load();
    const poll = setInterval(() => {
      api.screenStatus(udid).then(applyStatus, () => { /* keep last good status */ });
    }, 10000);
    return () => clearInterval(poll);
  }, [udid, load, applyStatus]);

  useEffect(() => {
    setLandscape(false);
    if (mode !== 'preview' && mode !== 'airplay') return;
    const t = setInterval(() => {
      const l = isLandscape(imgRef.current);
      if (l !== null) setLandscape(l);
    }, 2500);
    return () => clearInterval(t);
  }, [mode]);

  /** Run one button's request with a pending message; always refreshes. */
  async function act(key: string, pending: string, fn: () => Promise<string>) {
    setBusy(key);
    setMsg(pending);
    try {
      setMsg(await fn());
    } catch (e) {
      setMsg(`That did not work: ${String(e)}`);
    } finally {
      setBusy(null);
      await load();
    }
  }

  const startServer = (which: 'hd' | 'valeria') => act(which,
    which === 'hd'
      ? 'Starting the HD server — tunnel + page take ~10–20 s the first time…'
      : 'Starting QuickTime over USB — claiming the device takes ~5–10 s the first time…',
    async () => {
      const r = which === 'hd' ? await api.screenHdStart(udid) : await api.screenValeriaStart(udid);
      if (!(r.ok && r.running)) return r.reason || `${which === 'hd' ? 'HD' : 'QuickTime'} did not start.`;
      setMode(which);
      return which === 'hd'
        ? 'HD is live — full-rate video inside the frame below.'
        : 'QuickTime is live — 30–60 fps video inside the frame below, no Developer Mode needed.';
    });

  const stopServer = (which: 'hd' | 'valeria') => act(which, 'Stopping…', async () => {
    await (which === 'hd' ? api.screenHdStop() : api.screenValeriaStop());
    return which === 'hd' ? 'HD server stopped.' : 'QuickTime server stopped.';
  });

  /** pip install of the fork, or the Linux usbmuxd build — same shape. */
  const runSetup = (which: 'install' | 'usbmux') => {
    setInstallLog('');
    const install = which === 'install';
    return act(which, install
      ? 'Installing QuickTime dependencies — pip takes ~1–3 min the first time…'
      : 'Running the Linux USB setup — first build takes ~5–10 min, then it needs root…',
    async () => {
      const r = install ? await api.screenValeriaInstall() : await api.screenValeriaUsbmuxSetup();
      if (r.ok && r.installed) {
        return r.note || `${install ? 'Installed' : 'USB setup done'} — replug the iPhone, tap Trust, then press Start QuickTime.`;
      }
      if (r.install_running) return r.reason || 'Already running — wait, then press Refresh.';
      if (r.log) setInstallLog(r.log.slice(-800));
      return r.reason || (install
        ? 'Install did not finish — try the manual command below.'
        : 'USB setup did not finish — try the command in a terminal (it needs sudo).');
    });
  };

  const airplay = (start: boolean, embed = true) => act('airplay', start ? 'Starting AirPlay…' : 'Stopping AirPlay…',
    async () => {
      setAirSeen(false);
      if (!start) {
        await api.screenAirplayStop();
        return 'AirPlay receiver stopped.';
      }
      const r = await api.screenAirplayStart(embed);
      if (!r.ok) return r.reason || 'AirPlay did not start.';
      return embed
        ? 'freetunes is an AirPlay target — mirror from Control Center and it appears right here.'
        : 'freetunes is an AirPlay target — the mirror opens in its own window.';
    });

  /** Restart the receiver in the other render mode (page ⇄ window). */
  const airplaySwitch = (embed: boolean) => act('airplay', 'Restarting AirPlay…', async () => {
    await api.screenAirplayStop();
    const r = await api.screenAirplayStart(embed);
    setAirSeen(false);
    return r.ok ? 'AirPlay receiver restarted.' : r.reason || 'AirPlay did not start.';
  });

  const snapshot = () => act('shot', 'Taking a screenshot…', async () => {
    await api.screenSnapshot(udid);
    return status?.live
      ? 'Screenshot saved — that is exactly what the iPhone shows.'
      : 'Saved the placeholder — plug in your iPhone for real pixels.';
  });

  async function copyInstallCommand(cmd: string) {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setMsg(`Copy this command and run it in a terminal: ${cmd}`);
    }
  }

  // Apple gates the CoreDevice media stream HD rides on to iOS 27+;
  // below that the phone answers "Remote control requires iOS 27.0 or
  // later", so offering Start HD is a promise the device will not keep.
  const iosMajor = parseInt(status?.ios_version?.split('.')[0] || '0', 10);
  const hdBlocked = iosMajor > 0 && iosMajor < 27;
  const live = !!status?.live;
  const valeria = status?.valeria;
  // The fork's screen-mirror server speaks raw H.264 on /ws next to its
  // viewer page; the native canvas viewer talks that socket directly, so
  // no page (and no footer/scrollbar) ever enters the frame.
  const valeriaWs = valeria?.url ? valeria.url.replace(/^http/, 'ws').replace(/\/+$/, '') + '/ws' : '';
  const valeriaRunning = !!valeria?.running;
  const valeriaReady = valeria?.ready ?? !!status?.backends.valeria;
  const qtUsbmuxReady = valeria?.usbmuxd?.ready ?? true;
  const air = status?.airplay;
  const airRunning = !!air?.running;
  const airEmbedded = !!air?.embedded;
  const airReady = air?.ready ?? !!status?.backends.uxplay;
  // uxplay + avahi-daemon are host prerequisites, not iPhone ones: name
  // them with the command for *this* distro rather than a button that
  // can only fail.
  const airNeeds = air?.needs ?? [];
  const frameLabel = deviceName ? `${deviceName} iPhone contour` : undefined;
  const width = QUALITIES.find((x) => x.q === quality)?.width ?? 720;
  const streamUrl = api.screenStreamUrl(udid, fps, quality, width);

  /** The phone contour around a live mirror, in the current rotation. */
  const phone = (children: ReactNode, caption?: ReactNode) => (
    <figure className={`ft-iphone-wrap${landscape ? ' is-landscape' : ''}`}>
      <IPhoneFrame modelId={effModel} label={frameLabel} orientation={landscape ? 'landscape' : 'portrait'}>
        {children}
      </IPhoneFrame>
      {caption && <figcaption className="ft-screen-cap">{caption}</figcaption>}
    </figure>
  );

  const onImg = (e: SyntheticEvent<HTMLImageElement>) => {
    const l = isLandscape(e.currentTarget);
    if (l !== null) setLandscape(l);
  };

  function body() {
    if (!status) {
      return failed ? (
        <Empty>
          <strong>Could not reach the screen service</strong>
          <p>Is the backend running? Start it with <span className="ft-mono">make dev-backend</span>, then press Refresh.</p>
          <button className="ft-sync-btn" onClick={load}>Retry</button>
        </Empty>
      ) : (
        <div className="ft-screen-stage" aria-busy="true" aria-label="Loading screen">
          {phone(<div className="ft-screen-frame skeleton" style={{ minHeight: 380, width: '100%' }} />)}
        </div>
      );
    }

    if (mode === 'valeria') {
      if (valeriaRunning && valeriaWs) {
        return (
          <div className="ft-screen-stage">
            <div className="ft-screen-toolbar">
              <span className="ft-livepill on">● QUICKTIME LIVE</span>
              <span className={valeriaFps !== null ? 'ft-livepill on' : 'ft-livepill'} role="status">
                {valeriaFps !== null ? `${valeriaFps} fps` : valeriaConn === 'error' ? '○ RECONNECTING' : '○ CONNECTING'}
              </span>
              <span className="ft-hint">H.264 over USB — the fast preview, no Developer Mode.</span>
              <button className="ft-icon-btn" disabled={!!busy} onClick={() => stopServer('valeria')}>Stop QuickTime</button>
              <RotateButton landscape={landscape} onToggle={() => setLandscape((v) => !v)} />
            </div>
            {phone(<ValeriaViewer wsUrl={valeriaWs} onFps={setValeriaFps} onConn={setValeriaConn} />)}
          </div>
        );
      }
      const needsInstall = !valeriaReady && !valeriaRunning;
      return (
        <Empty className="ft-qt">
          <strong>QuickTime over USB — the fast preview</strong>
          <p className="ft-qt-sub">Same protocol QuickTime Player uses: 30–60 fps H.264 over USB,
            any trusted iPhone, <strong>no Developer Mode</strong>. While streaming
            the phone shows a fake 9:41 clock with notifications hidden (presentation mode).</p>
          {!!valeria?.needs?.length && (
            <ol className="ft-needs ft-qt-needs">
              {valeria.needs.map((n) => <li key={n}>{n}</li>)}
            </ol>
          )}
          {needsInstall && valeria?.install_command && (
            <div className="ft-cmd-box" aria-label="Manual install command">
              <code>{valeria.install_command}</code>
              <button className="ft-icon-btn" onClick={() => copyInstallCommand(valeria.install_command || '')}
                title="Copy the manual pip command">
                {copied ? '✓ Copied' : '⧉ Copy'}
              </button>
            </div>
          )}
          <div className="ft-qt-actions" role="group" aria-label="QuickTime actions">
            {needsInstall && (
              <button className="ft-icon-btn" disabled={!!busy || !!valeria?.install_running}
                onClick={() => runSetup('install')}
                title="Run pip install in the backend — same command as above">
                {busy === 'install' || valeria?.install_running ? '⏳ Installing…' : '⬇ Install dependencies'}
              </button>
            )}
            {!qtUsbmuxReady && (
              <button className="ft-icon-btn" disabled={!!busy} onClick={() => runSetup('usbmux')}
                title="Build the usbmuxd fork and switch the USB service to it (needs root — may ask you to run it in a terminal instead)">
                {busy === 'usbmux' ? '⏳ Setting up USB…' : '🔌 Run Linux USB setup'}
              </button>
            )}
            <button className="ft-sync-btn" disabled={!!busy || !udid || needsInstall}
              onClick={() => startServer('valeria')}
              title={needsInstall ? 'Install the dependencies first (one click above)' : 'Start the QuickTime server'}>
              Start QuickTime
            </button>
          </div>
          {installLog && <p className="ft-mono ft-qt-log">{installLog}</p>}
          {valeria?.linux_hint && <p className="ft-hint ft-qt-note">{valeria.linux_hint}</p>}
          {valeria?.usbmux_hint && <p className="ft-hint ft-qt-note">{valeria.usbmux_hint}</p>}
        </Empty>
      );
    }

    if (mode === 'hd') {
      if (status.hd.running && status.hd.url) {
        return (
          <div className="ft-screen-stage">
            <div className="ft-screen-toolbar">
              <span className="ft-livepill on">● HD LIVE</span>
              <span className="ft-hint">Full-rate video + audio, straight from the iPhone over USB.</span>
              <button className="ft-icon-btn" disabled={!!busy} onClick={() => stopServer('hd')}>Stop HD</button>
              <RotateButton landscape={landscape} onToggle={() => setLandscape((v) => !v)} />
            </div>
            {phone(<iframe src={status.hd.url} title="Live iPhone screen in full quality"
              className="ft-screen-hd" allow="autoplay; fullscreen" />)}
          </div>
        );
      }
      const pmd3 = status.backends.pymobiledevice3;
      return (
        <Empty>
          <strong>{hdBlocked ? `HD needs iOS 27 — this iPhone runs ${status.ios_version}` : 'HD is off'}</strong>
          {hdBlocked ? (
            <p>Apple gates the screen-mirroring service HD uses to iOS 27 and newer;
              on iOS {status.ios_version} the phone answers “Remote control requires
              iOS 27.0 or later”. Use <strong>QuickTime (USB)</strong> for fast video,
              <strong> Preview (USB)</strong> for stills or
              <strong> AirPlay (Wi-Fi)</strong> for full-rate video with sound.</p>
          ) : (
            <p>Full-rate HEVC video over USB — needs <span className="ft-mono">pymobiledevice3</span>,
              a trusted iPhone with Developer Mode on (iOS 17.4+ needs no extra setup).</p>
          )}
          <button className="ft-sync-btn" disabled={!!busy || !udid || !pmd3 || hdBlocked}
            onClick={() => startServer('hd')}
            title={hdBlocked ? `HD needs iOS 27 or newer — this iPhone runs ${status.ios_version}`
              : !pmd3 ? 'Install pymobiledevice3 first (see checklist)' : 'Start the HD server'}>
            Start HD
          </button>
          {!pmd3 && <p className="ft-mono">{status.hints.pymobiledevice3}</p>}
        </Empty>
      );
    }

    if (mode === 'airplay') {
      return (
        <>
          {airRunning && airEmbedded && (
            <div className="ft-screen-stage">
              {phone(
                <img ref={imgRef} className="ft-screen-img" alt="Live AirPlay mirror of the iPhone"
                  src={api.screenAirplayStreamUrl()}
                  onLoad={(e) => { setAirSeen(true); onImg(e); }} />,
                <>
                  <span className={airSeen ? 'ft-livepill on' : 'ft-livepill'}>
                    {airSeen ? '● AIRPLAY LIVE' : '○ WAITING FOR IPHONE'}
                  </span>
                  <span className="ft-hint">
                    Wi-Fi mirror, view-only. Sound plays through this computer's speakers, not the browser.
                  </span>
                </>,
              )}
            </div>
          )}
          <Empty>
            <strong>AirPlay mirror (Wi-Fi)</strong>
            <p>{air?.howto}. Best quality with sound — freetunes pretends
              to be an Apple TV. Both devices must share one Wi-Fi network.</p>
            {airNeeds.length > 0 && !airRunning && (
              <>
                <p>This computer is missing {airNeeds.length === 1 ? 'one piece' : 'two pieces'} —
                  run {airNeeds.length === 1 ? 'this' : 'these'} once, then press Start:</p>
                <ol className="ft-needs">
                  {airNeeds.map((n) => {
                    const [label, ...rest] = n.split(': ');
                    return <li key={n}>{label}: <span className="ft-mono">{rest.join(': ')}</span></li>;
                  })}
                </ol>
              </>
            )}
            <div className="ft-media-tools" style={{ justifyContent: 'center' }}>
              <button className="ft-sync-btn" disabled={!!busy || (!airReady && !airRunning)}
                onClick={() => airplay(!airRunning)}
                title={!airReady && !airRunning
                  ? 'Install uxplay and start avahi-daemon first (commands above)'
                  : airRunning ? 'Stop the receiver' : 'Start the receiver'}>
                {airRunning ? 'Stop AirPlay receiver' : 'Start AirPlay receiver'}
              </button>
              {airRunning && (
                <button className="ft-icon-btn" disabled={!!busy} onClick={() => airplaySwitch(!airEmbedded)}
                  title={airEmbedded
                    ? "Restart the receiver with uxplay's own window (full resolution)"
                    : 'Restart the receiver so the mirror renders inside freetunes'}>
                  {airEmbedded ? 'Use a separate window' : 'Bring the mirror into this page'}
                </button>
              )}
            </div>
            {airRunning && !airEmbedded && (
              <p>The mirror is playing in uxplay's own desktop window —
                it is a GStreamer window, so it cannot be moved inside the page.
                Use the button above to restart it as an in-page stream.</p>
            )}
            {!!air?.log && <p className="ft-mono">{air.log}</p>}
          </Empty>
        </>
      );
    }

    if (!udid) {
      return (
        <Empty>
          <strong>No iPhone connected</strong>
          <p>Plug in your iPhone with a USB cable, unlock it, and tap Trust on the phone.
            The live preview appears here — inside the phone frame, like QuickTime, HD and AirPlay.</p>
        </Empty>
      );
    }
    return (
      <div className="ft-screen-stage">
        {phone(
          playing ? (
            <img ref={imgRef} key={streamUrl} className="ft-screen-img"
              alt="Live preview of the iPhone screen" src={streamUrl} onLoad={onImg} />
          ) : (
            <img ref={imgRef} className="ft-screen-img" alt="Last iPhone screenshot"
              src={api.screenShotUrl(udid)} onLoad={onImg} />
          ),
          <>
            <span className={live ? 'ft-livepill on' : 'ft-livepill'}>
              {live ? '● LIVE PREVIEW' : '○ PLACEHOLDER'}
            </span>
            <span className="ft-hint">
              {playing ? `${fps} fps polling — view-only, no remote control.` : 'Paused — showing one still frame.'}
              {' '}For full frame rate, use QuickTime (USB) or HD.
            </span>
          </>,
        )}
      </div>
    );
  }

  return (
    <div className="ft-media">
      <div className="ft-media-bar glass">
        <div className="ft-media-count" role="status">
          <strong>{status ? (live ? 'Live screen' : 'Screen (not live yet)') : 'Screen'}</strong>
          <span>
            {!udid ? 'No iPhone connected.' : live
              ? `Mirroring ${status?.ios_version ? `iOS ${status.ios_version} · ` : ''}view-only, like 3uTools`
              : 'Finish the checklist below to get real pixels.'}
          </span>
          {status && (
            <span className={live ? 'ft-livepill on' : 'ft-livepill'}>
              {live ? '● LIVE' : '○ OFFLINE'}
            </span>
          )}
        </div>
        <div className="ft-media-tools">
          <div className="ft-segment" role="tablist" aria-label="Screen mode">
            {MODES.map((m) => (
              <button key={m.id} role="tab" aria-selected={mode === m.id}
                className={mode === m.id ? 'on' : ''} onClick={() => setMode(m.id)}>
                {m.label}
              </button>
            ))}
          </div>
          <label className="ft-hint" htmlFor="ft-contour">Frame</label>
          <GlassSelect id="ft-contour" label="Frame" value={contourPick} onChange={pickContour}
            title="Match the frame to the iPhone that is sharing — Auto follows the connected iPhone"
            options={[{ value: 'auto', label: `Auto · ${autoName}` }, ...FRAME_OPTIONS]} />
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
                {QUALITIES.map((x) => (
                  <button key={x.q} role="tab" aria-selected={quality === x.q}
                    className={quality === x.q ? 'on' : ''} onClick={() => setQuality(x.q)} title={x.title}>
                    {x.label}
                  </button>
                ))}
              </div>
              <button className="ft-icon-btn" disabled={!udid}
                onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause preview' : 'Resume preview'}>
                {playing ? '❚❚ Pause' : '▶ Play'}
              </button>
              <button className="ft-icon-btn" disabled={!udid || !!busy} onClick={snapshot}>
                📷 Screenshot
              </button>
            </>
          )}
          <button className="ft-icon-btn" onClick={load} aria-label="Refresh screen status">⟳</button>
        </div>
        {msg && <div className="ft-opmsg" role="status">{msg}</div>}
      </div>

      {body()}

      {status && status.needs.length > 0 && (
        <div className="ft-media-bar glass" aria-label="Setup checklist">
          <span className="ft-section" style={{ padding: 0 }}>To get the live screen</span>
          <ol className="ft-needs">
            {status.needs.map((n) => <li key={n}>{n}</li>)}
          </ol>
          <DevModeControls udid={udid} showState={false} onChanged={load} />
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
