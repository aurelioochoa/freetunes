export interface Device {
  udid: string; name: string; ios_version: string; trusted: boolean;
  product_type: string; model_id: string; model_number: string; serial: string;
  hardware: string; build: string; storage_total: number; storage_available: number;
  battery_pct: number; battery_charging: boolean; battery_eta_min: number | null;
  device_color?: string; device_color_hex?: string;
}
export interface AppInfo { bundle_id: string; name: string; file_sharing: boolean; installed: boolean }
export interface SyncItem { filename: string; action: 'push' | 'skip' | 'delete'; reason: string; size: number }
export interface SyncPreview { app_bundle_id: string; to_push: SyncItem[]; to_skip: SyncItem[]; to_delete: SyncItem[] }
export interface BackupInfo { udid: string; last_backup: string | null; encrypted: boolean; backup_dir?: string | null; available?: boolean; size_bytes?: number; file_count?: number; has_manifest?: boolean }
export interface BackupRecord { name: string; path: string; size_bytes: number; mtime: string | null; is_key_file: boolean }
export interface FileEntry { name: string; path: string; is_dir: boolean; size: number }
export interface MediaMetadata {
  summary: { label: string; value: string }[];
  sections: { name: string; fields: { label: string; value: string }[] }[];
  notes: string[];
}
export interface PhotoItem { filename: string; path: string; size: number }
export interface PhotoDuplicateItem { filename: string; path: string; size: number }
export interface PhotoDuplicates {
  ok: boolean; udid: string; groups: PhotoDuplicateItem[][]; count: number;
  scanned: number; hashed: number; skipped: number; note?: string; reason?: string;
}
export interface StorageBreakdown { total: number; available: number; used: number; source: string }
export interface VerificationCheck { label: string; status: string; detail: string }
export interface Verification { udid: string; model_number: string; kind: string; refurbished_suspect: boolean; details: string[]; checks?: VerificationCheck[]; summary?: string }
export interface CrashItem {
  filename: string; size: number; app?: string; date?: string;
  mtime?: string; kind?: string; exception?: string; reason?: string; os_version?: string;
}
export interface CrashDetail { item: CrashItem; preview: string; truncated: boolean; live: boolean }
export interface SyslogEntry { text: string; level: 'error' | 'warn' | 'info'; proc?: string; /** Subtype keyword that decided the level ('' for info). */ match?: string }
export interface SyslogResult {
  udid: string; lines: string; live: boolean; total?: number; shown?: number;
  errors?: number; warnings?: number; filtered?: boolean; requested?: number;
  /** Structured rows for the colorized web log viewer (same order as `lines`). */
  entries?: SyslogEntry[];
  /** True when the backend re-filtered a fresh capture instead of re-running the relay. */
  cached?: boolean;
  /** Milliseconds the capture took (0 when cached or mock). */
  capture_ms?: number;
  /** Capture window in seconds the backend used. */
  window?: number;
}
export interface DiagSummary { udid: string; status: string; headline: string; verification: Verification; crash_count: number; top_crash_apps: { app: string; count: number }[]; crash_kinds?: Record<string, number>; log_errors: number; log_warnings: number; log_live: boolean }
export interface FirmwareBuild { version: string; buildid: string; signed: boolean; url: string; filesize: number }
export interface ScreenHd { running: boolean; udid: string; url: string }
export interface ScreenUsbmuxd {
  linux: boolean; ready: boolean; needs?: string[];
  fork_installed?: boolean; fork_version?: string; has_device_mode?: boolean;
  service_active?: boolean; service_binary?: string; env_mode2?: boolean;
  override_present?: boolean; setup_command?: string;
}
export interface ScreenValeria {
  running: boolean; udid: string; url: string;
  /** Which tool backs the server: 'screen-mirror' | 'qvh' | ''. */
  backend?: string;
  /** Tools present and startable. */
  ready?: boolean;
  /** What this host still needs, in plain words + exact commands. */
  needs?: string[];
  install_hint?: string; install_command?: string; install_running?: boolean;
  qvh_hint?: string; usbmux_hint?: string;
  /** Linux one-time usbmuxd-fork setup ("" on non-Linux hosts). */
  linux_hint?: string; linux_setup_url?: string;
  /** Host usbmuxd vs the QuickTime fork (Linux only). */
  usbmuxd?: ScreenUsbmuxd;
  /** Desktop photo importer holding the USB interface (gvfs gphoto2). */
  photo_hold?: { held: boolean; mounts?: string[]; gio?: boolean };
  /** `qvh` binary present (manual `qvh gstreamer` fallback). */
  qvh?: boolean;
  /** `pymobiledevice3 screen-mirror` subcommand advertised. */
  screen_mirror?: boolean;
  /** Tail of the server's own output. */
  log?: string;
}
export interface ScreenAirplay {
  running: boolean; name: string; howto: string;
  /** Receiver binary present on this computer. */
  uxplay?: boolean;
  /** mDNS daemon: 'running' | 'stopped' | 'unknown'. */
  avahi?: string;
  /** Both prerequisites satisfied. */
  ready?: boolean;
  /** What this host still needs, in plain words + exact commands. */
  needs?: string[];
  /** Receiver renders into this page instead of its own desktop window. */
  embedded?: boolean;
  /** MJPEG endpoint for the embedded mirror ('' when not embedded). */
  stream_url?: string;
  install_hint?: string; avahi_hint?: string;
  /** Tail of the receiver's own output. */
  log?: string;
}
export interface ScreenStatus {
  udid: string; available: boolean; mode: string; live: boolean;
  developer_mode: string;
  /** DeveloperDiskImage mount: 'mounted' | 'missing' | 'unknown'. */
  ddi: string;
  /** Developer tunnel (tunneld) for this iPhone: 'up' | 'missing' | 'unknown'. */
  tunneld?: string;
  needs: string[]; ios_version: string;
  backends: { pymobiledevice3: boolean; idevicescreenshot: boolean; uxplay: boolean; qvh?: boolean; valeria?: boolean };
  hd: ScreenHd; valeria: ScreenValeria; airplay: ScreenAirplay;
  hints: { pymobiledevice3: string; uxplay: string; valeria?: string };
}
export interface ScreenSetupResult { ok: boolean; note?: string; reason?: string }

const base = '';

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  apps: () => fetch(`${base}/apps`).then(j<AppInfo[]>),
  devices: () => fetch(`${base}/devices`).then(j<Device[]>),
  pair: (udid: string) =>
    fetch(`${base}/devices/${encodeURIComponent(udid)}/pair`, { method: 'POST' }).then(j<{ ok: boolean; trusted: boolean; message: string }>),
  preview: (app_bundle_id: string, music_dir: string, mirror_delete = false) =>
    fetch(`${base}/sync/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_bundle_id, music_dir, mirror_delete })
    }).then(j<SyncPreview>),
  run: (app_bundle_id: string, music_dir: string, mirror_delete = false, dry_run = false) =>
    fetch(`${base}/sync/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_bundle_id, music_dir, mirror_delete, dry_run })
    }).then(j<{ pushed: string[]; deleted: string[]; skipped: string[] }>),
  backupInfo: (udid: string) => fetch(`${base}/backup/${udid}`).then(j<BackupInfo>),
  backupRun: (udid: string, full = true) =>
    fetch(`${base}/backup/${udid}?full=${full}`, { method: 'POST' }).then(j<unknown>),
  backupFiles: (udid: string) => fetch(`${base}/backup/${udid}/files`).then(j<{ filename: string; size: string }[]>),
  backupHistory: (udid: string) => fetch(`${base}/backup/${udid}/history`).then(j<BackupRecord[]>),
  backupVerify: (udid: string) =>
    fetch(`${base}/backup/${udid}/verify`, { method: 'POST' }).then(j<{ ok: boolean; message?: string; problems?: string[]; size_bytes?: number; file_count?: number; has_manifest?: boolean }>),
  backupDelete: (udid: string) =>
    fetch(`${base}/backup/${udid}`, { method: 'DELETE' }).then(j<{ ok: boolean; message?: string }>),
  backupEncryption: (udid: string, enabled: boolean) =>
    fetch(`${base}/backup/${udid}/encryption?enabled=${enabled}`, { method: 'POST' }).then(j<{ ok: boolean; message?: string; hint?: string }>),
  backupRestore: (udid: string, opts: { system?: boolean; settings?: boolean; skip_apps?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (opts.system) q.set('system', 'true');
    if (opts.settings) q.set('settings', 'true');
    if (opts.skip_apps) q.set('skip_apps', 'true');
    const suffix = q.toString() ? `?${q}` : '';
    return fetch(`${base}/backup/${udid}/restore${suffix}`, { method: 'POST' }).then(j<unknown>);
  },
  browse: (udid: string, path = '/') =>
    fetch(`${base}/files/browse?udid=${encodeURIComponent(udid)}&path=${encodeURIComponent(path)}`).then(j<FileEntry[]>),
  photos: (udid: string) => fetch(`${base}/photos?udid=${encodeURIComponent(udid)}`).then(j<PhotoItem[]>),
  photoDuplicates: (udid: string) =>
    fetch(`${base}/photos/duplicates?udid=${encodeURIComponent(udid)}`).then(j<PhotoDuplicates>),
  deletePhoto: async (udid: string, path: string): Promise<{ ok: boolean; path?: string }> => {
    const res = await fetch(
      `${base}/photos?udid=${encodeURIComponent(udid)}&path=${encodeURIComponent(path)}`,
      { method: 'DELETE' });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json() as { detail?: string };
        if (body.detail) detail = body.detail;
      } catch { /* keep HTTP status */ }
      throw new Error(detail);
    }
    return res.json() as Promise<{ ok: boolean; path?: string }>;
  },
  mediaMetadata: async (udid: string, path: string, signal?: AbortSignal): Promise<MediaMetadata> => {
    const res = await fetch(`${base}/files/metadata?udid=${encodeURIComponent(udid)}&path=${encodeURIComponent(path)}`, { signal });
    if (!res.ok) {
      const body = await res.json().catch(() => null) as { detail?: string } | null;
      throw new Error(body?.detail || `Metadata unavailable (HTTP ${res.status})`);
    }
    return res.json() as Promise<MediaMetadata>;
  },
  /** Direct URL for <img>/<video> real-byte previews (GET /files/content). */
  fileContentUrl: (udid: string, path: string) =>
    `${base}/files/content?udid=${encodeURIComponent(udid)}&path=${encodeURIComponent(path)}`,
  /** Small cached JPEG for grid tiles (GET /files/thumb). 404 → keep placeholder. */
  thumbUrl: (udid: string, path: string, size = 512) =>
    `${base}/files/thumb?udid=${encodeURIComponent(udid)}&path=${encodeURIComponent(path)}&size=${size}`,
  storageBreakdown: (udid: string) =>
    fetch(`${base}/storage/breakdown?udid=${encodeURIComponent(udid)}`).then(j<StorageBreakdown>),
  verification: (udid: string) =>
    fetch(`${base}/diagnostics/verification?udid=${encodeURIComponent(udid)}`).then(j<Verification>),
  crashes: (udid: string) =>
    fetch(`${base}/diagnostics/crashes?udid=${encodeURIComponent(udid)}`).then(j<CrashItem[]>),
  crashDetail: (udid: string, filename: string) =>
    fetch(`${base}/diagnostics/crashes/${encodeURIComponent(filename)}?udid=${encodeURIComponent(udid)}`).then(j<CrashDetail>),
  syslog: (udid: string, lines = 200, q = '', level = 'all', window = 3, signal?: AbortSignal) => {
    const url = `${base}/diagnostics/syslog?udid=${encodeURIComponent(udid)}&lines=${lines}&q=${encodeURIComponent(q)}&level=${encodeURIComponent(level)}&window=${window}`;
    return fetch(url, { signal }).then(j<SyslogResult>);
  },
  /** SSE URL for the real-time log stream (EventSource in DiagnosticsView). */
  syslogStreamUrl: (udid: string, q = '', level = 'all') =>
    `${base}/diagnostics/syslog/stream?udid=${encodeURIComponent(udid)}&q=${encodeURIComponent(q)}&level=${encodeURIComponent(level)}`,
  diagSummary: (udid: string) =>
    fetch(`${base}/diagnostics/summary?udid=${encodeURIComponent(udid)}`).then(j<DiagSummary>),
  duplicates: (path: string) =>
    fetch(`${base}/tools/duplicates?path=${encodeURIComponent(path)}`).then(j<{ ok: boolean; groups: string[][]; count: number; reason?: string }>),
  editTags: (path: string, title?: string, artist?: string, album?: string) =>
    fetch(`${base}/tools/tags`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, title, artist, album })
    }).then(j<{ ok: boolean; reason?: string; path?: string }>),
  makeRingtone: (src: string, dest: string, start_s: number, end_s: number) =>
    fetch(`${base}/tools/ringtone`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ src, dest, start_s, end_s })
    }).then(j<{ ok: boolean; reason?: string; dest?: string; hint?: string }>),
  convertMedia: (src: string, dest: string) =>
    fetch(`${base}/tools/convert?src=${encodeURIComponent(src)}&dest=${encodeURIComponent(dest)}`, { method: 'POST' }).then(j<{ ok: boolean; reason?: string }>),
  compressPhoto: (src: string, dest: string) =>
    fetch(`${base}/tools/compress-photo?src=${encodeURIComponent(src)}&dest=${encodeURIComponent(dest)}`, { method: 'POST' }).then(j<{ ok: boolean; reason?: string }>),
  heicToJpg: (src: string, dest: string) =>
    fetch(`${base}/tools/heic-to-jpg?src=${encodeURIComponent(src)}&dest=${encodeURIComponent(dest)}`, { method: 'POST' }).then(j<{ ok: boolean; reason?: string }>),
  firmwareSigned: (product: string) =>
    fetch(`${base}/firmware/signed?product=${encodeURIComponent(product)}`).then(j<FirmwareBuild[]>),
  flashDryRun: (udid: string, ipsw: string, mode: string, confirm: boolean) =>
    fetch(`${base}/flash/dry-run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ udid, ipsw, mode, confirm })
    }).then(j<unknown>),
  upload: (file: File) => {
    const form = new FormData();
    form.append('file', file, file.name);
    return fetch(`${base}/tools/upload`, { method: 'POST', body: form })
      .then(j<{ ok: boolean; path?: string; filename?: string; size?: number; download?: string; reason?: string }>);
  },
  /** Direct URL for a toolbox result download (GET /tools/file). */
  toolFileUrl: (name: string) => `${base}/tools/file?name=${encodeURIComponent(name)}`,
  fromDevice: (req: {
    udid: string; remote_path: string; op: string; dest_ext?: string;
    start_s?: number; end_s?: number; title?: string; artist?: string; album?: string;
    max_dim?: number; quality?: number;
  }) =>
    fetch(`${base}/tools/from-device`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req)
    }).then(j<{ ok: boolean; reason?: string; hint?: string; download?: string; filename?: string }>),
  /* ---- Live screen (3uTools-style realtime view) ---- */
  screenStatus: (udid: string) =>
    fetch(`${base}/screen/status?udid=${encodeURIComponent(udid)}`).then(j<ScreenStatus>),
  /** Single live PNG frame (or a marked placeholder when nothing is live). */
  screenShotUrl: (udid: string) =>
    `${base}/screen/shot?udid=${encodeURIComponent(udid)}`,
  /** MJPEG polling stream for an <img> tag (1–5 fps, view-only). `width` caps the frame's long edge (default 720). */
  screenStreamUrl: (udid: string, fps = 2, quality = 70, width = 720) =>
    `${base}/screen/stream?udid=${encodeURIComponent(udid)}&fps=${fps}&quality=${quality}&width=${width}`,
  screenSnapshot: async (udid: string): Promise<void> => {
    const res = await fetch(`${base}/screen/shot?udid=${encodeURIComponent(udid)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = res.headers.get('X-Screen-Live') === '1' ? 'iphone-screen.png' : 'freetunes-screen-placeholder.png';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
  },
  screenHd: () => fetch(`${base}/screen/hd`).then(j<ScreenHd>),
  screenHdStart: (udid: string) =>
    fetch(`${base}/screen/hd/start?udid=${encodeURIComponent(udid)}`, { method: 'POST' })
      .then(j<{ ok: boolean; running: boolean; url?: string; udid?: string; reason?: string; note?: string }>),
  screenHdStop: () =>
    fetch(`${base}/screen/hd/stop`, { method: 'POST' }).then(j<{ ok: boolean; running: boolean }>),
  screenValeria: () => fetch(`${base}/screen/valeria`).then(j<ScreenValeria>),
  screenValeriaStart: (udid: string) =>
    fetch(`${base}/screen/valeria/start?udid=${encodeURIComponent(udid)}`, { method: 'POST' })
      .then(j<{ ok: boolean; running: boolean; url?: string; udid?: string; backend?: string; reason?: string; note?: string }>),
  screenValeriaStop: () =>
    fetch(`${base}/screen/valeria/stop`, { method: 'POST' }).then(j<{ ok: boolean; running: boolean }>),
  /** One-click pip install of the Valeria fork + aiohttp/av. */
  screenValeriaInstall: () =>
    fetch(`${base}/screen/valeria/install`, { method: 'POST' })
      .then(j<{ ok: boolean; installed: boolean; already?: boolean; install_running?: boolean; note?: string; reason?: string; log?: string; command?: string }>),
  /** One-click Linux USB setup (usbmuxd fork; needs root, may ask for a terminal). */
  screenValeriaUsbmuxSetup: () =>
    fetch(`${base}/screen/valeria/usbmux-setup`, { method: 'POST' })
      .then(j<{ ok: boolean; installed: boolean; install_running?: boolean; note?: string; reason?: string; log?: string; command?: string }>),
  screenAirplay: () => fetch(`${base}/screen/airplay`).then(j<ScreenAirplay>),
  /** Start the receiver. `embed` keeps the mirror inside the web UI. */
  screenAirplayStart: (embed = true) =>
    fetch(`${base}/screen/airplay/start?embed=${embed}`, { method: 'POST' })
      .then(j<{ ok: boolean; running: boolean; name?: string; howto?: string; reason?: string; embedded?: boolean }>),
  /** MJPEG mirror for an <img> tag (embedded mode only). */
  screenAirplayStreamUrl: () => `${base}/screen/airplay/stream`,
  screenAirplayStop: () =>
    fetch(`${base}/screen/airplay/stop`, { method: 'POST' }).then(j<{ ok: boolean; running: boolean }>),
  /* ---- One-click setup for the two things iOS demands ---- */
  /** Make the Developer Mode row appear in Settings (no reboot). */
  screenRevealDevMode: (udid: string) =>
    fetch(`${base}/screen/setup/reveal-developer-mode?udid=${encodeURIComponent(udid)}`,
      { method: 'POST' }).then(j<ScreenSetupResult>),
  /** Turn Developer Mode on — the iPhone restarts. */
  screenEnableDevMode: (udid: string) =>
    fetch(`${base}/screen/setup/enable-developer-mode?udid=${encodeURIComponent(udid)}`,
      { method: 'POST' }).then(j<ScreenSetupResult>),
  /** Mount the personalized developer image (iOS drops it on reboot). */
  screenMountDdi: (udid: string) =>
    fetch(`${base}/screen/setup/mount-ddi?udid=${encodeURIComponent(udid)}`,
      { method: 'POST' }).then(j<ScreenSetupResult>),
};
