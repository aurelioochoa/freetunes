import { useState } from 'react';
import type { Device } from '../api';
import { describeProduct } from '../devices';
import DevModeControls from './DevModeControls';

function gb(bytes: number): string {
  return `${(bytes / 1e9).toFixed(1)} GB`;
}

export default function DevicePanel({ device }: { device: Device | null }) {
  const [copied, setCopied] = useState(false);

  if (!device) {
    return (
      <div className="ft-table">
        <div className="ft-empty">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <rect x="4" y="1.5" width="8" height="13" rx="2" />
            <path d="M7 12.5h2" strokeLinecap="round" />
          </svg>
          <strong>No iPhone connected</strong>
          <p>Plug in your iPhone with a USB cable, unlock it, and tap Trust on the phone. This panel fills in by itself.</p>
        </div>
      </div>
    );
  }

  const used = Math.max(0, device.storage_total - device.storage_available);
  const pct = device.storage_total
    ? Math.min(100, Math.round((used / device.storage_total) * 100)) : 0;

  async function copyUdid() {
    try {
      await navigator.clipboard.writeText(device!.udid);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard unavailable */ }
  }

  const modelLabel = device.product_type
    ? describeProduct(device.product_type)
    : device.model_number || '—';
  const rows: [string, string][] = [
    ['Name', device.name],
    ['iOS', `${device.ios_version} (${device.build || 'build unknown'})`],
    ['Model', modelLabel],
    ['Finish', device.device_color || device.device_color_hex || '—'],
    ['Serial', device.serial || '—'],
    ['Chip platform', device.hardware || '—']
  ];

  return (
    <div className="ft-panel">
      <div className="ft-specs">
        {rows.map(([k, v]) => (
          <div className="ft-spec" key={k}>
            <span>{k}</span><strong>{v}</strong>
          </div>
        ))}
        <div className="ft-spec">
          <span>UDID</span>
          <strong className="ft-mono">{device.udid || '—'}</strong>
          {device.udid && (
            <button className="ft-icon-btn" onClick={copyUdid}>
              {copied ? 'Copied ✓' : 'Copy'}
            </button>
          )}
        </div>
      </div>
      <div className="ft-gauges">
        <div className="ft-gauge">
          <span>Storage — {gb(used)} of {gb(device.storage_total)} used</span>
          <div className="ft-bar"><i style={{ width: `${pct}%`, background: '#0071e3' }} /></div>
        </div>
        <div className="ft-gauge">
          <span>
            Battery — {device.battery_pct >= 0 ? `${device.battery_pct}%` : 'unknown'}
            {device.battery_charging ? ' · charging ⚡' : ''}
          </span>
          <div className="ft-bar"><i style={{
            width: `${Math.max(0, device.battery_pct)}%`,
            background: device.battery_pct < 20 ? '#ff453a' : '#30d158'
          }} /></div>
        </div>
      </div>
      <DevModeControls udid={device.udid} />
    </div>
  );
}
