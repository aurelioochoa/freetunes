import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { api, type ScreenStatus } from '../api';

/**
 * The two things iOS 17-26 demands before any screen capture works:
 * Developer Mode on the phone, and a mounted (personalized) developer
 * image. Both are driven from the host here, so the user never has to
 * hunt for a Settings row that is hidden until a dev tool asks for it.
 *
 * Self-contained on purpose: the device page and the Screen tab both
 * render it, and neither owns the setup flow.
 */
export default function DevModeControls({ udid, onChanged, showState = true, fallback }: {
  udid: string;
  /** Called after a step succeeds so the parent can refresh its own view. */
  onChanged?: () => void;
  showState?: boolean;
  /**
   * Shown in place of the controls when this computer has no
   * pymobiledevice3 to drive them. Callers that render inside a titled
   * card pass one so the card never sits visibly empty; the device page
   * and Screen tab pass nothing and keep collapsing to nothing.
   */
  fallback?: ReactNode;
}) {
  const [status, setStatus] = useState<ScreenStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  // Turning Developer Mode on restarts the iPhone, so that button arms on
  // the first click and only fires on the second.
  const [armReboot, setArmReboot] = useState(false);

  const load = useCallback(async () => {
    try {
      setStatus(await api.screenStatus(udid));
    } catch { /* keep the last good status */ }
  }, [udid]);

  useEffect(() => { setMsg(''); setArmReboot(false); load(); }, [udid, load]);

  async function run(kind: 'reveal' | 'enable' | 'ddi') {
    if (!udid) return;
    setBusy(true);
    setArmReboot(false);
    setMsg(kind === 'ddi'
      ? 'Downloading and mounting the developer image — this can take a minute…'
      : 'Asking the iPhone… unlock it if it prompts.');
    try {
      const r = kind === 'reveal' ? await api.screenRevealDevMode(udid)
        : kind === 'enable' ? await api.screenEnableDevMode(udid)
          : await api.screenMountDdi(udid);
      setMsg(r.ok ? (r.note || 'Done.') : (r.reason || 'The iPhone refused that.'));
      await load();
      onChanged?.();
    } catch (e) {
      setMsg(`Setup step failed: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  // No phone, or the first status round-trip is still in flight: collapse
  // rather than flash a "not supported" fallback that a moment later is wrong.
  if (!udid || !status) return null;
  if (!status.backends.pymobiledevice3) return <>{fallback ?? null}</>;

  const devmode = status.developer_mode;
  const ddi = status.ddi;
  const ready = devmode === 'on' && ddi !== 'missing';

  return (
    <div className="ft-devmode" aria-label="Developer Mode setup">
      {showState && (
        <div className="ft-spec">
          <span>Developer Mode</span>
          <strong>
            {devmode === 'on' ? 'On' : devmode === 'off' ? 'Off' : 'Unknown'}
            {' · developer image '}
            {ddi === 'mounted' ? 'mounted' : ddi === 'missing' ? 'not mounted' : 'unknown'}
          </strong>
          <span className={ready ? 'ft-livepill on' : 'ft-livepill'}>
            {ready ? '● SCREEN READY' : '○ SETUP NEEDED'}
          </span>
        </div>
      )}
      <div className="ft-media-tools">
        {devmode !== 'on' && (
          <>
            <button className="ft-icon-btn" disabled={busy}
              onClick={() => run('reveal')}
              title="Adds the Developer Mode row to Settings → Privacy & Security on the iPhone. Nothing else changes.">
              Show Developer Mode on iPhone
            </button>
            <button className={armReboot ? 'ft-sync-btn' : 'ft-icon-btn'} disabled={busy}
              onClick={() => (armReboot ? run('enable') : setArmReboot(true))}
              title="Turns Developer Mode on from here. The iPhone restarts and then asks you to confirm.">
              {armReboot ? 'Restart the iPhone now?' : 'Turn on Developer Mode (restarts iPhone)'}
            </button>
          </>
        )}
        {devmode !== 'off' && ddi === 'missing' && (
          <button className="ft-sync-btn" disabled={busy} onClick={() => run('ddi')}
            title="Downloads and mounts the personalized developer image iOS needs for screen capture. iOS drops it on every restart.">
            Mount developer image
          </button>
        )}
        {ready && <span className="ft-hint">Live screen is ready — open the Screen tab.</span>}
      </div>
      {msg && <div className="ft-opmsg" role="status">{msg}</div>}
    </div>
  );
}
