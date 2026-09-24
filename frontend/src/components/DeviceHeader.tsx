import { useEffect, useState, type CSSProperties } from 'react';
import type { Device } from '../api';
import { DEVICE_MODELS, friendlyProductName } from '../devices';
import type { DeviceModel } from '../devices';
import { CONTOUR_MINI, contourForModel } from './IPhoneFrame';

type TrustState = 'trusted' | 'untrusted' | 'absent';

function trustState(device: Device | null): TrustState {
  if (!device || !device.udid) return 'absent';
  return device.trusted ? 'trusted' : 'untrusted';
}

function batteryLabel(device: Device | null): string | null {
  if (!device || device.battery_pct < 0) return null;
  if (device.battery_pct >= 100) return 'Full';
  const base = `${device.battery_pct}%`;
  if (!device.battery_charging) return `${base} · not charging`;
  if (device.battery_eta_min == null) return `${base} · charging…`;
  return `${base} · ~${device.battery_eta_min} min to full`;
}

function storageLabel(device: Device | null): { text: string; pct: number } | null {
  if (!device || !device.storage_total) return null;
  const used = Math.max(0, device.storage_total - device.storage_available);
  const pct = Math.min(100, Math.round((used / device.storage_total) * 100));
  return { text: `${(device.storage_available / 1e9).toFixed(1)} GB free`, pct };
}

/** Backend-normalized `#rrggbb`, or '' when unknown. Validated here too so
 *  a stray lockdown string can never become an arbitrary CSS value. */
function colorHex(device: Device | null): string {
  const raw = device?.device_color_hex?.trim() ?? '';
  return /^#[0-9a-f]{6}$/i.test(raw) ? raw.toLowerCase() : '';
}

/** Carousel slides: one per model, except Duo open + folded which share
 *  a single wider slide rendered side by side. */
export const CAROUSEL_SLIDES: { id: string; models: DeviceModel[] }[] = (() => {
  const slides: { id: string; models: DeviceModel[] }[] = [];
  for (const m of DEVICE_MODELS) {
    if (m.id === 'iphone-duo-folded') continue; // merged into the Duo slide
    if (m.id === 'iphone-duo') {
      const folded = DEVICE_MODELS.find((x) => x.id === 'iphone-duo-folded');
      slides.push({ id: 'iphone-duo', models: folded ? [m, folded] : [m] });
    } else {
      slides.push({ id: m.id, models: [m] });
    }
  }
  return slides;
})();

export default function DeviceHeader({ target, appName, model, device, onSync, busy, showTrust, pairing, onPair, artPinned }: {
  target: string;
  appName: string;
  model: DeviceModel;
  device: Device | null;
  onSync: () => void;
  busy: boolean;
  showTrust?: boolean;
  pairing?: boolean;
  onPair?: () => void;
  /** True when the user pinned a model in Settings → Device Art. Stops the idle carousel. */
  artPinned?: boolean;
}) {
  const trust = trustState(device);
  const batt = batteryLabel(device);
  const charging = !!device && device.battery_charging && device.battery_pct < 100;
  const storage = storageLabel(device);
  const friendly = device?.product_type ? friendlyProductName(device.product_type) : '';
  const finishHex = colorHex(device);
  const finishName = device?.device_color?.trim() || '';
  // No cable → idle carousel: loop the real device renders so the header
  // never sits on one static image. Starts on the picked model, then
  // advances on a timer (paused when a real iPhone shows up, and off
  // entirely for prefers-reduced-motion).
  // A manual pick in Settings → Device Art pins the render: no cycling.
  // iPhone Duo open + folded share one wider slide, side by side —
  // each is too narrow on its own to read at 52px, together they fill
  // a double-width slot.
  const absent = trust === 'absent';
  const showCarousel = absent && !artPinned;
  const [carousel, setCarousel] = useState(() => {
    const i = CAROUSEL_SLIDES.findIndex((s) => s.models.some((m) => m.id === model.id));
    return i >= 0 ? i : 0;
  });
  useEffect(() => {
    if (!showCarousel) return;
    const i = CAROUSEL_SLIDES.findIndex((s) => s.models.some((m) => m.id === model.id));
    if (i >= 0) setCarousel((cur) => (cur === i ? cur : i));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model.id, showCarousel]);
  useEffect(() => {
    if (!showCarousel) return;
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const t = window.setInterval(() => {
      setCarousel((i) => (i + 1) % CAROUSEL_SLIDES.length);
    }, 2800);
    return () => window.clearInterval(t);
  }, [showCarousel]);
  const activeSlide = CAROUSEL_SLIDES[carousel % CAROUSEL_SLIDES.length] ?? CAROUSEL_SLIDES[0];
  const displayModel = showCarousel ? activeSlide.models[0] : model;
  const isDuoSlide = showCarousel && activeSlide.id === 'iphone-duo';
  const modelName = friendly || device?.model_number || displayModel.name;
  // Connected: show the exact model render (e.g. /iphone-11.png for iPhone 11),
  // falling back to the generic contour mini for unknown future hardware.
  // The mini mockup draws the same hardware contour as the Screen tab
  // frame, following the live iPhone when one is connected.
  const miniContour = contourForModel(device?.model_id || model.id);
  const miniSrc = CONTOUR_MINI[miniContour];
  const connectedModel = !absent
    ? DEVICE_MODELS.find((m) => m.id === device?.model_id)
    : undefined;
  const connectedSrc = connectedModel?.svg ?? miniSrc;
  // Pinned but unplugged: show the exact picked render, never the carousel.
  const staticSrc = absent ? (model.svg || miniSrc) : connectedSrc;
  const staticModelId = absent ? model.id : (connectedModel?.id ?? device?.model_id ?? model.id);
  const subtitle = device && device.udid
    ? `${modelName}${device.ios_version !== 'unknown' ? ` · iOS ${device.ios_version}` : ''}${appName ? ` · Plays in ${appName}` : ''}`
    : `${displayModel.screen} · ${displayModel.unlock}${appName ? ` · Plays in: ${appName}` : ''}`;

  return (
    <div className="ft-header" data-color={finishHex ? '1' : undefined}
      style={finishHex ? ({ '--device-color': finishHex } as CSSProperties) : undefined}>
      <div className={`ft-device${showCarousel ? ' is-carousel' : ''}${isDuoSlide ? ' is-duo' : ''}`} data-trust={trust} title={
        trust === 'trusted' ? 'iPhone connected and trusted'
        : trust === 'untrusted' ? 'iPhone found — tap Trust on the phone'
        : artPinned ? `Pinned to ${model.name} — change in Settings → Device Art`
        : 'No iPhone detected — showing the supported lineup'
      }>
        {showCarousel ? (
          <div className="ft-carousel" role="img" aria-roledescription="carousel"
            aria-label={`iPhone lineup — ${activeSlide.models.map((m) => m.name).join(' + ')}`}
            title="No iPhone detected — showing the supported lineup">
            {CAROUSEL_SLIDES.map((s, i) => {
              const active = i === carousel % CAROUSEL_SLIDES.length;
              return (
                <div key={s.id}
                  className={`ft-slide${s.models.length > 1 ? ' is-duo-pair' : ''}${active ? ' is-active' : ''}`}
                  aria-hidden={!active}>
                  {s.models.map((m) => (
                    <img key={m.id} src={m.svg} alt={active ? `${m.name} contour` : ''}
                      aria-hidden={!active} data-model={m.id} data-contour={contourForModel(m.id)}
                      draggable={false} loading={active ? 'eager' : 'lazy'} />
                  ))}
                </div>
              );
            })}
          </div>
        ) : (
          <img src={staticSrc} alt={`${modelName} contour`}
            data-model={staticModelId}
            data-contour={miniContour} />
        )}
        {!absent && <span className={`ft-status-dot ${trust}`} aria-hidden="true" />}
        <span className="ft-sr-only" aria-live="polite">{showCarousel ? activeSlide.models.map((m) => m.name).join(' + ') : ''}</span>
      </div>
      <div className="ft-titleblock">
        <h1>{device?.name || displayModel.name}</h1>
        <p>{subtitle}</p>
        <div className="ft-chips">
          {trust === 'trusted' && (
            <span className="ft-chip is-trusted" title="This computer is paired — sync and file access work">Trusted ✓</span>
          )}
          {trust === 'untrusted' && (
            <span className="ft-chip is-untrusted" title="Pairing missing — tap Trust on the phone">Not trusted</span>
          )}
          {device?.product_type && (
            <>
              {friendly && (
                <span className="ft-chip is-model" title="The name on the box — what Apple sells it as">{friendly}</span>
              )}
              <span className="ft-chip is-techid"
                title="Apple's internal hardware ID for this exact model. Firmware sites list builds under this ID — e.g. iPhone14,5 is the regular iPhone 13.">
                {device.product_type}
              </span>
            </>
          )}
          {finishHex && (
            <span className="ft-chip is-color"
              title={finishName
                ? `Hardware finish, live from your iPhone: ${finishName}`
                : 'Hardware finish, live from your iPhone'}
              aria-label={finishName ? `iPhone color: ${finishName}` : 'iPhone color'}>
              <i className="ft-color-dot" style={{ background: finishHex }} aria-hidden="true" />
              {finishName || 'iPhone color'}
            </span>
          )}
          {batt && device && (
            <span className={`ft-chip${charging ? ' charging' : ''}`} title="Battery status, live from your iPhone">
              <span aria-hidden="true">{charging ? '⚡' : '🔋'}</span> {batt}
              <span className="ft-meter" aria-hidden="true">
                <i style={{ width: `${Math.max(0, Math.min(100, device.battery_pct))}%` }} />
              </span>
            </span>
          )}
          {storage && (
            <span className="ft-chip" title="Free space, live from your iPhone">
              💾 {storage.text}
              <span className="ft-meter" aria-hidden="true">
                <i style={{ width: `${storage.pct}%` }} />
              </span>
            </span>
          )}
        </div>
      </div>
      {!absent && (
      <div className="ft-actions">
        {showTrust && (
          <button
            className="ft-trust-btn"
            disabled={pairing || !device || trust === 'trusted'}
            onClick={onPair}
            title={trust === 'trusted'
              ? 'This iPhone already trusts this computer — nothing to do'
              : device
                ? "Ask the iPhone to show the 'Trust This Computer?' prompt"
                : 'Plug in your iPhone first — then this asks it to show the Trust prompt'}
            aria-label="Ask iPhone to trust this computer"
            aria-disabled={pairing || !device || trust === 'trusted'}
          >
            {pairing ? 'Waiting for Trust…' : trust === 'trusted' ? 'Trusted ✓' : 'Ask iPhone to Trust'}
          </button>
        )}
        <button className="ft-sync-btn" disabled={busy} onClick={onSync}>
          {busy ? 'Syncing…' : 'Sync'}
        </button>
      </div>
      )}
    </div>
  );
}
