import GlassSelect from './GlassSelect';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, type MediaMetadata, type FileEntry, type PhotoDuplicateItem, type PhotoItem } from '../api';

function parentOf(path: string): string {
  if (!path || path === '/') return '/';
  const parts = path.replace(/\/+$/, '').split('/').filter(Boolean);
  parts.pop();
  return '/' + parts.join('/');
}

function fmtBytes(size: number): string {
  if (!size || size <= 0) return '—';
  if (size < 1024) return `${size} B`;
  const units = ['KB', 'MB', 'GB'];
  let v = size / 1024;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
  return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${units[u]}`;
}

function extOf(name: string): string {
  const i = name.lastIndexOf('.');
  return i >= 0 ? name.slice(i + 1).toLowerCase() : '';
}

const VIDEO_EXTS = new Set(['mov', 'mp4', 'm4v', 'avi', 'mkv']);
const PHOTO_EXTS = new Set(['jpg', 'jpeg', 'png', 'heic', 'heif', 'gif', 'webp', 'dng', 'raw']);
const AUDIO_EXTS = new Set(['mp3', 'm4a', 'wav', 'flac', 'aac', 'ogg']);
const BROWSER_BLIND_EXTS = new Set(['heic', 'heif']);

type Kind = 'video' | 'photo' | 'audio' | 'folder' | 'doc';

function kindOfPhoto(p: PhotoItem): Kind {
  const e = extOf(p.filename);
  return VIDEO_EXTS.has(e) ? 'video' : 'photo';
}

function kindOfFile(r: FileEntry): Kind {
  if (r.is_dir) return 'folder';
  const e = extOf(r.name);
  if (VIDEO_EXTS.has(e)) return 'video';
  if (PHOTO_EXTS.has(e)) return 'photo';
  if (AUDIO_EXTS.has(e)) return 'audio';
  return 'doc';
}

/** Stable subtle tint per filename so the grid feels like content, not chrome. */
function tintOf(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 360;
  return h;
}

function KindGlyph({ kind }: { kind: Kind }) {
  const common = { width: 26, height: 26, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, 'aria-hidden': true } as const;
  if (kind === 'folder')
    return (
      <svg {...common}><path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h5l2 2.5h7A1.5 1.5 0 0 1 20 9v8.5a1.5 1.5 0 0 1-1.5 1.5h-14A1.5 1.5 0 0 1 3 17.5Z" strokeLinejoin="round" /></svg>
    );
  if (kind === 'video')
    return (
      <svg {...common}><rect x="3" y="6" width="13" height="12" rx="2.5" /><path d="M16 10.5 21 7.5v9l-5-3Z" strokeLinejoin="round" /></svg>
    );
  if (kind === 'audio')
    return (
      <svg {...common}><circle cx="7.5" cy="17" r="2.8" /><circle cx="17" cy="15" r="2.8" /><path d="M10.3 17V6l9.5-2.5V15" strokeLinecap="round" /></svg>
    );
  if (kind === 'doc')
    return (
      <svg {...common}><path d="M6 3.5h7L18.5 9v11.5H6Z" strokeLinejoin="round" /><path d="M13 3.5V9h5.5" /></svg>
    );
  return (
    <svg {...common}><rect x="3.5" y="5" width="17" height="14" rx="2.5" /><circle cx="9" cy="10" r="1.6" /><path d="m5.5 17.5 4.5-4.5 3 3 2.5-2.5 3 3" strokeLinecap="round" strokeLinejoin="round" /></svg>
  );
}

function crumbs(path: string): { label: string; path: string }[] {
  const parts = (path || '/').split('/').filter(Boolean);
  const out = [{ label: 'iPhone', path: '/' }];
  let acc = '';
  for (const p of parts) {
    acc += '/' + p;
    out.push({ label: p, path: acc });
  }
  return out;
}
/** Real-byte preview served by GET /files/content (`afcclient get`). */
function previewable(kind: Kind, filename: string): boolean {
  if (kind !== 'photo' && kind !== 'video') return false;
  return !BROWSER_BLIND_EXTS.has(extOf(filename));
}

async function downloadBlob(url: string, filename: string): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
}

interface DeviceAction { op: string; label: string; title: string; extra?: Record<string, unknown> }

/** Toolbox ops that make sense for one iPhone file (pull → process → download). */
function deviceActions(kind: Kind, ext: string): DeviceAction[] {
  if (kind === 'photo' && !BROWSER_BLIND_EXTS.has(ext))
    return [{ op: 'compress-photo', label: 'Compress & download', title: 'Pull, shrink with Pillow, download the smaller copy' }];
  if (kind === 'photo' && BROWSER_BLIND_EXTS.has(ext))
    return [{ op: 'heic-to-jpg', label: 'Convert to JPG & download', title: 'Pull, convert HEIC to JPG, download' }];
  if (kind === 'video' && ext !== 'mp4')
    return [{ op: 'convert', label: 'Convert to MP4 & download', title: 'Pull, transcode with ffmpeg, download', extra: { dest_ext: 'mp4' } }];
  if (kind === 'audio')
    return [{ op: 'ringtone', label: 'First 30 s as ringtone', title: 'Pull, cut 0–30 s AAC, download .m4r', extra: { start_s: 0, end_s: 30 } }];
  return [];
}

/**
 * Lazy real thumbnail layered over the tile placeholder (GET /files/thumb).
 * Renders nothing until the tile scrolls near the viewport; on 404/error
 * the placeholder underneath simply stays visible.
 *
 * Fetches via JS + blob URL instead of <img src> so missing thumbnails
 * (large videos, unsupported types) don't spam the console with
 * "Failed to load resource: 404" — fetch 404s are silent, <img> 404s aren't.
 */
function ThumbImg({ udid, path, size = 384 }: { udid: string; path: string; size?: number }) {
  const sentry = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(false);
  const [failed, setFailed] = useState(false);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  useEffect(() => {
    const el = sentry.current;
    if (!el || !udid) return;
    if (!('IntersectionObserver' in window)) { setVisible(true); return; }
    const ob = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { setVisible(true); ob.disconnect(); }
    }, { rootMargin: '500px' });
    ob.observe(el);
    return () => ob.disconnect();
  }, [udid]);
  useEffect(() => { setFailed(false); setObjectUrl(null); }, [path, size, udid]);
  useEffect(() => {
    if (!udid || !visible || failed || objectUrl) return;
    let cancelled = false;
    const ctrl = new AbortController();
    fetch(api.thumbUrl(udid, path, size), { signal: ctrl.signal }).then(async (res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      if (cancelled) return;
      setObjectUrl(URL.createObjectURL(blob));
    }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; ctrl.abort(); };
  }, [udid, path, size, visible, failed, objectUrl]);
  useEffect(() => {
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [objectUrl]);
  return (
    <>
      <span ref={sentry} className="ft-thumb-sentry" aria-hidden="true" />
      {udid && visible && !failed && objectUrl && (
        <img className="ft-thumb-img" loading="lazy" alt="" src={objectUrl} />
      )}
    </>
  );
}

function PreviewArt({ udid, path, filename, kind }: {
  udid: string; path: string; filename: string; kind: Kind;
}) {
  const [failed, setFailed] = useState(false);
  const [thumbFailed, setThumbFailed] = useState(false);
  useEffect(() => { setFailed(false); setThumbFailed(false); }, [path, udid]);
  const hue = tintOf(filename);
  const artStyle = {
    background: `linear-gradient(135deg, hsl(${hue} 24% 86%), hsl(${(hue + 40) % 360} 26% 72%))`,
  };
  const ext = extOf(filename);

  if (!udid) {
    return (
      <div className="ft-inspector-art" style={artStyle}>
        <KindGlyph kind={kind} />
        <span className="ft-preview-note">Sample data — plug in your iPhone to see the real pixels.</span>
      </div>
    );
  }
  if (BROWSER_BLIND_EXTS.has(ext)) {
    // iPhone stills (HEIC/HEIF) browsers cannot decode: the server converts
    // one frame to JPEG for /files/thumb, so show that converted preview
    // instead of a blind placeholder. Full quality via Export / Convert.
    const converted = udid ? api.thumbUrl(udid, path, 1024) : '';
    if (!thumbFailed && converted) {
      return (
        <div className="ft-inspector-art real">
          <img key={converted} className="ft-real" src={converted}
            alt={`Converted preview of ${filename}`} onError={() => setThumbFailed(true)} />
        </div>
      );
    }
    return (
      <div className="ft-inspector-art" style={artStyle}>
        <KindGlyph kind={kind} />
        <span className="ft-preview-note">HEIC previews are not supported in this browser — export the file to view it.</span>
        <a className="ft-icon-btn" href={api.fileContentUrl(udid, path)} download={filename}>Export</a>
      </div>
    );
  }
  if (kind !== 'photo' && kind !== 'video') {
    return (
      <div className="ft-inspector-art" style={artStyle}>
        <KindGlyph kind={kind} />
        <span className="ft-preview-note">No inline preview for this file type — export it to open.</span>
        <a className="ft-icon-btn" href={api.fileContentUrl(udid, path)} download={filename}>Export</a>
      </div>
    );
  }
  if (failed) {
    const thumb = udid ? api.thumbUrl(udid, path, 640) : '';
    // Videos from iPhone are often HEVC-in-MOV, which desktop browsers
    // cannot decode in <video>. The server-side ffmpeg thumbnail usually
    // still exists, so show it as a static fallback instead of nothing.
    if (kind === 'video' && thumb && !thumbFailed) {
      return (
        <div className="ft-inspector-art real">
          <img key={thumb} className="ft-real" src={thumb}
            alt={`Thumbnail of ${filename}`} onError={() => setThumbFailed(true)} />
        </div>
      );
    }
    return (
      <div className="ft-inspector-art" style={artStyle}>
        <KindGlyph kind={kind} />
        <span className="ft-preview-note">
          {kind === 'video'
            ? 'This iPhone video uses a codec this browser cannot play (usually HEVC in MOV) — the thumbnail is shown when available. Convert to MP4 or export it to watch.'
            : 'Preview failed to load — the file may be unreachable. Export it instead.'}
        </span>
        <a className="ft-icon-btn" href={api.fileContentUrl(udid, path)} download={filename}>Export</a>
      </div>
    );
  }
  const url = api.fileContentUrl(udid, path);
  return (
    <div className="ft-inspector-art real">
      {kind === 'video' ? (
        <video key={url} className="ft-real" controls playsInline preload="metadata"
          poster={udid ? api.thumbUrl(udid, path, 640) : undefined}
          src={url} onError={() => setFailed(true)}
          aria-label={`Video preview of ${filename}`} />
      ) : (
        <img key={url} className="ft-real" src={url} alt={`Preview of ${filename}`}
          onError={() => setFailed(true)} />
      )}
    </div>
  );
}

/** Chevron in the project's icon language: 24px grid, 1.6 stroke, no fill. */
function Chevron({ dir }: { dir: 'prev' | 'next' }) {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={dir === 'prev' ? 'M14.5 5.5 8 12l6.5 6.5' : 'M9.5 5.5 16 12l-6.5 6.5'} />
    </svg>
  );
}

function CloseGlyph() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.6} strokeLinecap="round" aria-hidden="true">
      <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />
    </svg>
  );
}

/** The one shape both views select: a photo row and a file row reduce to this. */
interface InspectorItem {
  path: string;
  name: string;
  size: number;
  kind: Kind;
  isDir: boolean;
}

/**
 * Pull → process → download, shared by both views so a given file offers the
 * same operations wherever it is selected. Only `path`/`name` are needed, so
 * PhotoItem and FileEntry both qualify.
 */
function useDeviceOps(udid: string, onStart?: () => void) {
  const [opBusy, setOpBusy] = useState<string | null>(null);
  const [opMsg, setOpMsg] = useState('');

  const runDeviceOp = useCallback(async (
    op: string, target: { path: string; name: string }, extra: Record<string, unknown> = {},
  ) => {
    onStart?.();
    setOpBusy(target.path + op);
    setOpMsg(`Working on ${target.name} — pulling from the iPhone…`);
    try {
      const res = await api.fromDevice({ udid, remote_path: target.path, op, ...extra });
      if (res.ok && res.download) {
        await downloadBlob(res.download, res.filename || target.name);
        setOpMsg(`Done — downloaded ${res.filename || target.name}.`);
      } else {
        setOpMsg(`${target.name}: ${res.reason || 'failed'}`);
      }
    } catch (e) {
      setOpMsg(`${target.name}: ${String(e)}`);
    } finally {
      setOpBusy(null);
    }
  }, [udid, onStart]);

  return { opBusy, opMsg, runDeviceOp };
}

function MetadataDetails({ udid, path }: { udid: string; path: string }) {
  const [metadata, setMetadata] = useState<MediaMetadata | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!udid) return;
    const controller = new AbortController();
    setMetadata(null);
    setError('');
    api.mediaMetadata(udid, path, controller.signal).then((result) => {
      if (!controller.signal.aborted) setMetadata(result);
    }).catch((e: unknown) => {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Metadata could not be loaded.');
    });
    return () => controller.abort();
  }, [udid, path, attempt]);

  return (
    <section className="ft-media-metadata" aria-label="Media metadata" aria-busy={!!udid && !metadata && !error}>
      <h3>Details</h3>
      {!udid ? <p className="ft-hint">Connect your iPhone to read metadata from the original file.</p>
        : error ? <div role="status"><p className="ft-hint">{error}</p>
          <button className="ft-icon-btn" onClick={() => setAttempt((n) => n + 1)}>Retry metadata</button></div>
        : !metadata ? <p className="ft-hint" role="status">Reading metadata from the original…</p>
        : <>
          {metadata.summary.length > 0 && <dl className="ft-inspector-dl">
            {metadata.summary.map((field) => <div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}
          </dl>}
          {!metadata.summary.some((f) => f.label === 'Captured') && <p className="ft-hint">Capture date and time are not available in the extracted metadata.</p>}
          {!metadata.summary.some((f) => ['Location', 'Latitude', 'Longitude'].includes(f.label)) && <p className="ft-hint">Location is not available in the extracted metadata.</p>}
          <p className="ft-hint">Dates and times are shown as recorded in the file. A time zone is shown only when provided.</p>
          {metadata.sections.length > 0 ? <details className="ft-all-metadata">
            <summary>All metadata · {metadata.sections.reduce((n, section) => n + section.fields.length, 0)} fields</summary>
            {metadata.sections.map((section) => <details key={section.name}>
              <summary>{section.name} · {section.fields.length}</summary>
              <dl className="ft-inspector-dl">
                {section.fields.map((field) => <div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}
              </dl>
            </details>)}
          </details> : <p className="ft-hint">No readable embedded metadata was found.</p>}
          {metadata.notes.map((note) => <p className="ft-hint" key={note}>{note}</p>)}
        </>}
    </section>
  );
}

/**
 * The inspector for both Photos and Files. `variant` changes only the shell —
 * a wide panel pinned above the gallery, or the Finder sidebar column. Preview,
 * navigation, metadata and actions are identical, so the same file reads and
 * behaves the same way whichever view you found it in.
 */
function Inspector({
  variant, udid, item, index, total, grandTotal, onStep, onClose, opBusy, runDeviceOp,
}: {
  variant: 'panel' | 'sidebar';
  udid: string;
  item: InspectorItem;
  index: number;
  total: number;
  grandTotal?: number;
  onStep: (dir: 1 | -1) => void;
  onClose: () => void;
  opBusy: string | null;
  runDeviceOp: (op: string, target: { path: string; name: string }, extra?: Record<string, unknown>) => void;
}) {
  const ext = extOf(item.name);
  const canPreview = !item.isDir && previewable(item.kind, item.name);
  const isBlind = !item.isDir && BROWSER_BLIND_EXTS.has(ext);
  const ops = item.isDir ? [] : deviceActions(item.kind, ext);
  const kindLabel = item.isDir ? 'Folder'
    : `${item.kind === 'video' ? 'Video' : item.kind === 'photo' ? 'Photo'
      : item.kind === 'audio' ? 'Audio' : 'File'}${ext ? ` · ${ext.toUpperCase()}` : ''}`;

  return (
    <aside className={`ft-inspector glass ft-inspector-${variant}`} aria-label="Preview">
      <PreviewArt udid={udid} path={item.path} filename={item.name} kind={item.kind} />
      <div className="ft-inspector-body">
        <div className="ft-inspector-nav">
          <button className="ft-nav-btn" onClick={() => onStep(-1)} disabled={total < 2}
            aria-label="Previous item" title="Previous (←)"><Chevron dir="prev" /></button>
          <div className="ft-inspector-heading">
            <strong className="ft-inspector-title" title={item.name}>{item.name}</strong>
            <span className="ft-inspector-count" role="status">
              {index >= 0
                ? `${index + 1} of ${total}${grandTotal && grandTotal > total ? ` shown · ${grandTotal} total` : ''}`
                : 'Not in the current filter'}
            </span>
          </div>
          <button className="ft-nav-btn" onClick={() => onStep(1)} disabled={total < 2}
            aria-label="Next item" title="Next (→)"><Chevron dir="next" /></button>
          <button className="ft-nav-btn ft-nav-close" onClick={onClose}
            aria-label="Close preview" title="Close (Esc)"><CloseGlyph /></button>
        </div>

        <dl className="ft-inspector-dl">
          <div><dt>Kind</dt><dd>{kindLabel}</dd></div>
          {!item.isDir && <div><dt>Size</dt><dd className="ft-num">{fmtBytes(item.size)}</dd></div>}
          <div><dt>Where</dt><dd className="ft-mono">{item.path}</dd></div>
          {!item.isDir && (
            <div><dt>Transfer</dt><dd>
              <span className="pill skip">export-ready</span>{' '}
              <span className="ft-hint">import is best-effort</span>
            </dd></div>
          )}
        </dl>

        {!item.isDir && (item.kind === 'photo' || item.kind === 'video') && (
          <MetadataDetails key={`${udid}:${item.path}`} udid={udid} path={item.path} />
        )}

        {udid && !item.isDir && (
          <div className="ft-inspector-actions">
            <a className="ft-icon-btn primary" href={api.fileContentUrl(udid, item.path)}
              download={item.name}>{isBlind ? 'Export original' : 'Export'}</a>
            {canPreview && (
              <a className="ft-icon-btn" href={api.fileContentUrl(udid, item.path)}
                target="_blank" rel="noreferrer">Open full size</a>
            )}
            {ops.map((a) => (
              <button key={a.op} className="ft-icon-btn" title={a.title}
                disabled={opBusy === item.path + a.op}
                onClick={() => runDeviceOp(a.op, { path: item.path, name: item.name }, a.extra ?? {})}>
                {opBusy === item.path + a.op ? 'Working…' : a.label}
              </button>
            ))}
            <button className="ft-icon-btn" onClick={() => {
              try { navigator.clipboard.writeText(item.path); } catch { /* noop */ }
            }}>Copy path</button>
          </div>
        )}
      </div>
    </aside>
  );
}

/* ---------------- Photos ---------------- */

type PhotoFilter = 'all' | 'photo' | 'video';

export function PhotosView({ udid }: { udid: string }) {
  const [photos, setPhotos] = useState<PhotoItem[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<PhotoFilter>('all');
  const [mode, setMode] = useState<'grid' | 'list'>('grid');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [selected, setSelected] = useState<PhotoItem | null>(null);
  const { opBusy, opMsg, runDeviceOp } = useDeviceOps(udid);
  const [dupGroups, setDupGroups] = useState<PhotoDuplicateItem[][]>([]);
  const [dupMeta, setDupMeta] = useState<{ scanned: number; hashed: number; skipped: number } | null>(null);
  const [dupMsg, setDupMsg] = useState('');
  const [dupBusy, setDupBusy] = useState(false);
  const [dupOpen, setDupOpen] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState('loading');
    try {
      const list = await api.photos(udid);
      setPhotos(list);
      setState('ready');
      setSelected((s) => (s && list.some((p) => p.path === s.path) ? s : null));
    } catch {
      setPhotos([]);
      setState('error');
    }
  }, [udid]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    setDupGroups([]);
    setDupMeta(null);
    setDupMsg('');
    setDupOpen(false);
    setDeleting(null);
  }, [udid]);

  const scanDuplicates = useCallback(async () => {
    if (!udid) {
      setDupMsg('Plug in your iPhone first — sample data has no bytes to compare.');
      setDupOpen(true);
      return;
    }
    setDupBusy(true);
    setDupMsg('Scanning — pulling same-size photos to compare fingerprints…');
    setDupOpen(true);
    try {
      const r = await api.photoDuplicates(udid);
      setDupGroups(r.groups ?? []);
      setDupMeta({ scanned: r.scanned ?? 0, hashed: r.hashed ?? 0, skipped: r.skipped ?? 0 });
      if ((r.groups ?? []).length === 0) {
        setDupMsg(r.note
          || `No byte-identical duplicates — scanned ${r.scanned ?? 0}, compared ${r.hashed ?? 0}`
          + ((r.skipped ?? 0) > 0 ? `, skipped ${r.skipped}.` : '.'));
      } else {
        const extra = (r.skipped ?? 0) > 0 ? ` · skipped ${r.skipped}` : '';
        setDupMsg(`Found ${r.count} duplicate group${r.count === 1 ? '' : 's'}`
          + ` — scanned ${r.scanned}, compared ${r.hashed}${extra}. Keep one per group, delete the rest.`);
      }
    } catch (e) {
      setDupGroups([]);
      setDupMeta(null);
      setDupMsg(`Duplicate scan failed: ${String(e)}`);
    } finally {
      setDupBusy(false);
    }
  }, [udid]);

  const pruneDeleted = useCallback((paths: Set<string>) => {
    setPhotos((prev) => prev.filter((p) => !paths.has(p.path)));
    setDupGroups((prev) => prev
      .map((g) => g.filter((m) => !paths.has(m.path)))
      .filter((g) => g.length > 1));
    setSelected((s) => (s && paths.has(s.path) ? null : s));
  }, []);

  const deleteOne = useCallback(async (target: { path: string; filename: string }) => {
    if (!window.confirm(`Delete ${target.filename} from the iPhone? This cannot be undone.`)) return;
    setDeleting(target.path);
    try {
      await api.deletePhoto(udid, target.path);
      pruneDeleted(new Set([target.path]));
      setDupMsg(`Deleted ${target.filename}.`);
    } catch (e) {
      setDupMsg(`Could not delete ${target.filename}: ${String(e)}`);
    } finally {
      setDeleting(null);
    }
  }, [udid, pruneDeleted]);

  const keepFirst = useCallback(async (group: PhotoDuplicateItem[]) => {
    const [, ...rest] = group;
    if (rest.length === 0) return;
    if (!window.confirm(`Keep ${group[0].filename} and delete ${rest.length} duplicate${rest.length === 1 ? '' : 's'}? This cannot be undone.`)) return;
    setDeleting(group[0].path);
    const done: string[] = [];
    let failed = '';
    for (const m of rest) {
      try {
        await api.deletePhoto(udid, m.path);
        done.push(m.path);
      } catch (e) {
        failed = String(e);
        break;
      }
    }
    if (done.length) pruneDeleted(new Set(done));
    setDupMsg(failed
      ? `Deleted ${done.length} of ${rest.length}, then stopped: ${failed}`
      : `Deleted ${done.length} duplicate${done.length === 1 ? '' : 's'} — kept ${group[0].filename}.`);
    setDeleting(null);
  }, [udid, pruneDeleted]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return photos
      .filter((p) => (filter === 'all' ? true : kindOfPhoto(p) === filter))
      .filter((p) => (!q ? true : (p.filename + ' ' + p.path).toLowerCase().includes(q)))
      .slice()
      .sort((a, b) => a.filename.localeCompare(b.filename));
  }, [photos, query, filter]);

  const totalBytes = useMemo(() => photos.reduce((n, p) => n + (p.size || 0), 0), [photos]);
  const videos = photos.filter((p) => kindOfPhoto(p) === 'video').length;

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageStart = (currentPage - 1) * pageSize;
  const shown = useMemo(() => filtered.slice(pageStart, pageStart + pageSize), [filtered, pageStart, pageSize]);

  useEffect(() => {
    setPage(1);
    setSelected(null);
  }, [query, filter, pageSize, udid]);

  useEffect(() => { setPage((p) => Math.min(p, pageCount)); }, [pageCount]);
  useEffect(() => {
    setSelected((s) => s && shown.some((p) => p.path === s.path) ? s : null);
  }, [shown]);

  const changePage = (next: number) => {
    setPage(next);
    setSelected(null);
  };

  const pagination = (
    <nav className="ft-photo-pagination" aria-label="Photo pagination">
      <span role="status">{filtered.length ? `Showing ${pageStart + 1}–${pageStart + shown.length} of ${filtered.length} items` : '0 items'}</span>
      <div className="ft-photo-page-field"><span>Items per page</span>
        <GlassSelect label="Items per page" value={String(pageSize)}
          onChange={(value) => setPageSize(Number(value))}
          options={[25, 50, 100, 200].map((size) => ({ value: String(size), label: String(size) }))} />
      </div>
      <div className="ft-photo-pages">
        <button className="ft-icon-btn" disabled={currentPage === 1} onClick={() => changePage(currentPage - 1)}>Previous</button>
        <div className="ft-photo-page-field"><span>Page</span>
          <GlassSelect label="Page" value={String(currentPage)}
            onChange={(value) => changePage(Number(value))}
            options={Array.from({ length: pageCount }, (_, i) => ({ value: String(i + 1), label: String(i + 1) }))} />
          <span>of {pageCount}</span>
        </div>
        <button className="ft-icon-btn" disabled={currentPage === pageCount} onClick={() => changePage(currentPage + 1)}>Next</button>
      </div>
    </nav>
  );

  const selIndex = selected ? shown.findIndex((p) => p.path === selected.path) : -1;
  const step = useCallback((dir: 1 | -1) => {
    if (!shown.length) return;
    const next = selIndex < 0
      ? (dir > 0 ? 0 : shown.length - 1)
      : (selIndex + dir + shown.length) % shown.length;
    setSelected(shown[next]);
    requestAnimationFrame(() => {
      try { document.getElementById(`ph-${shown[next].path}`)?.scrollIntoView({ block: 'nearest' }); } catch { /* noop */ }
    });
  }, [shown, selIndex]);

  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.closest('.ft-pop') || t.isContentEditable)) return;
      if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
      else if (e.key === 'Escape') { setSelected(null); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected, step]);

  return (
    <div className="ft-media">
      <div className="ft-media-bar glass">
        <div className="ft-media-count" role="status">
          <strong>{state === 'ready' ? `${filtered.length} item${filtered.length === 1 ? '' : 's'}` : 'Photos'}</strong>
          <span>{!udid ? 'No iPhone — sample data.' : `${photos.length} in DCIM · ${videos} video${videos === 1 ? '' : 's'} · ${fmtBytes(totalBytes)}`}</span>
        </div>
        <div className="ft-media-tools">
          <input
            type="search" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Search photos" aria-label="Search photos" className="ft-search"
          />
          <div className="ft-segment" role="tablist" aria-label="Media type">
            {(['all', 'photo', 'video'] as PhotoFilter[]).map((f) => (
              <button key={f} role="tab" aria-selected={filter === f}
                className={filter === f ? 'on' : ''} onClick={() => setFilter(f)}>
                {f === 'all' ? 'All' : f === 'photo' ? 'Photos' : 'Videos'}
              </button>
            ))}
          </div>
          <div className="ft-segment" role="tablist" aria-label="Layout">
            <button role="tab" aria-selected={mode === 'grid'} className={mode === 'grid' ? 'on' : ''} onClick={() => setMode('grid')} title="Grid">▦</button>
            <button role="tab" aria-selected={mode === 'list'} className={mode === 'list' ? 'on' : ''} onClick={() => setMode('list')} title="List">☰</button>
          </div>
          <button className="ft-icon-btn" onClick={scanDuplicates} disabled={dupBusy}
            title="Compare fingerprints of same-size photos on this iPhone and group byte-identical ones">
            {dupBusy ? 'Scanning…' : 'Find duplicates'}
          </button>
          <button className="ft-icon-btn" onClick={load} aria-label="Refresh photos">⟳</button>
        </div>
        {state === 'ready' && pagination}
        {opMsg && <div className="ft-opmsg" role="status">{opBusy ? `${opMsg} (working…)` : opMsg}</div>}
        {dupMsg && <div className="ft-opmsg" role="status">{dupBusy ? `${dupMsg} (working…)` : dupMsg}</div>}
      </div>

      {dupOpen && (
        <section className="ft-table" aria-label="Duplicate photos on this iPhone">
          <div className="ft-row head" role="row">
            <div>Duplicate photos{dupMeta ? ` · ${dupGroups.length} group${dupGroups.length === 1 ? '' : 's'} · scanned ${dupMeta.scanned} · compared ${dupMeta.hashed}${dupMeta.skipped ? ` · skipped ${dupMeta.skipped}` : ''}` : ''}</div>
            <div>Size</div>
            <div>Keep</div>
            <div>Status</div>
            <div />
          </div>
          {dupBusy ? (
            <div className="ft-empty"><strong>Scanning photos…</strong>
              <p>Pulling same-size photos over USB to compare fingerprints. Large libraries take a while.</p></div>
          ) : dupGroups.length === 0 ? (
            <div className="ft-empty">
              <KindGlyph kind="photo" />
              <strong>No duplicates shown</strong>
              <p>{dupMsg || 'Press Find duplicates to compare the photos on this iPhone.'}</p>
              <span>
                <button className="ft-sync-btn" disabled={dupBusy} onClick={scanDuplicates}>
                  {dupBusy ? 'Scanning…' : 'Scan again'}
                </button>{' '}
                <button className="ft-icon-btn" onClick={() => setDupOpen(false)}>Hide</button>
              </span>
            </div>
          ) : (
            <>
              <ul className="ft-dup-list" style={{ padding: 12 }}>
                {dupGroups.map((g, i) => (
                  <li key={g[0]?.path ?? i} className="ft-dup-group" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                    <span style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                      <span className="ft-dup-badge">{g.length}× identical</span>
                      <span className="ft-hint">{fmtBytes(g[0]?.size ?? 0)} each</span>
                      <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                        <button className="ft-icon-btn sm" disabled={!!deleting}
                          title={`Delete every copy except ${g[0]?.filename} (cannot be undone)`}
                          onClick={() => keepFirst(g)}>
                          {deleting === g[0]?.path ? 'Working…' : `Keep first, delete ${g.length - 1}`}
                        </button>
                        <button className="ft-icon-btn sm" onClick={() => setDupOpen(false)}>Hide</button>
                      </span>
                    </span>
                    <span style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 8, width: '100%' }}>
                      {g.map((m, j) => {
                        const hue = tintOf(m.filename);
                        return (
                          <span key={m.path} className="ft-thumb" style={{ cursor: 'default' }}>
                            <span className="ft-thumb-art" style={{ background: `linear-gradient(135deg, hsl(${hue} 22% 88%), hsl(${(hue + 36) % 360} 24% 76%))` }}>
                              <KindGlyph kind={kindOfPhoto({ filename: m.filename, path: m.path, size: m.size } as PhotoItem)} />
                              <ThumbImg udid={udid} path={m.path} size={256} />
                            </span>
                            <span className="ft-thumb-meta">
                              <span className="ft-thumb-name" title={m.path}>
                                {j === 0 ? '★ ' : ''}{m.filename}
                              </span>
                              <span className="ft-thumb-sub ft-mono">{m.path}</span>
                              <span style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                                <a className="ft-icon-btn sm" href={api.fileContentUrl(udid, m.path)}
                                  download={m.filename} title={`Export ${m.filename} to this computer`}>Export</a>
                                <button className="ft-icon-btn sm" disabled={!!deleting}
                                  title={j === 0 ? 'Delete this copy from the iPhone (cannot be undone)' : 'Delete this duplicate from the iPhone (cannot be undone)'}
                                  onClick={() => deleteOne(m)}>
                                  {deleting === m.path ? 'Deleting…' : 'Delete'}
                                </button>
                              </span>
                            </span>
                          </span>
                        );
                      })}
                    </span>
                  </li>
                ))}
              </ul>
              <div className="ft-empty" style={{ padding: '12px 20px 16px' }}>
                <span className="ft-hint">★ marks the copy kept by “Keep first”. Deletion runs on the iPhone over USB — if iOS keeps DCIM read-only, export first and delete in the Photos app.</span>
              </div>
            </>
          )}
        </section>
      )}

      {selected && (
        <Inspector
          variant="panel" udid={udid}
          item={{ path: selected.path, name: selected.filename, size: selected.size,
            kind: kindOfPhoto(selected), isDir: false }}
          index={selIndex} total={shown.length} grandTotal={filtered.length}
          onStep={step} onClose={() => setSelected(null)}
          opBusy={opBusy} runDeviceOp={runDeviceOp} />
      )}

      {state === 'loading' ? (
        <div className="ft-gallery" aria-busy="true" aria-label="Loading photos">
          <span className="ft-sr-only">Loading photos…</span>
          {Array.from({ length: 8 }).map((_, i) => <div key={i} className="ft-thumb skeleton" style={{ minHeight: 150 }} />)}
        </div>
      ) : state === 'error' ? (
        <div className="ft-table"><div className="ft-empty">
          <strong>Could not load photos</strong>
          <p>Check the cable, tap Trust on the phone, then press Refresh.</p>
          <button className="ft-sync-btn" onClick={load}>Retry</button>
        </div></div>
      ) : filtered.length === 0 ? (
        <div className="ft-table"><div className="ft-empty">
          <KindGlyph kind="photo" />
          <strong>{photos.length === 0 ? 'No photos found' : 'No matches'}</strong>
          <p>{photos.length === 0
            ? 'Plug in your iPhone and trust it. Export (iPhone → PC) always works; import to Camera Roll is best-effort on modern iOS.'
            : 'Try a different search or filter.'}</p>
        </div></div>
      ) : mode === 'grid' ? (
        <div className="ft-gallery" role="listbox" aria-label="Photos on iPhone" aria-activedescendant={selected ? `ph-${selected.path}` : undefined}>
          {shown.map((p) => {
            const kind = kindOfPhoto(p);
            const hue = tintOf(p.filename);
            const active = selected?.path === p.path;
            return (
              <button key={p.path} id={`ph-${p.path}`} role="option" aria-selected={active}
                className={`ft-thumb${active ? ' active' : ''}`}
                onClick={() => setSelected(active ? null : p)}
                title={`${p.filename} · ${fmtBytes(p.size)}`}>
                <span className="ft-thumb-art" style={{ background: `linear-gradient(135deg, hsl(${hue} 22% 88%), hsl(${(hue + 36) % 360} 24% 76%))` }}>
                  <KindGlyph kind={kind} />
                  {kind === 'video' && <span className="ft-play" aria-hidden="true">▶</span>}
                  <ThumbImg udid={udid} path={p.path} />
                </span>
                <span className="ft-thumb-meta">
                  <span className="ft-thumb-name">{p.filename}</span>
                  <span className="ft-thumb-sub">{fmtBytes(p.size)} · {kind === 'video' ? 'Video' : extOf(p.filename).toUpperCase() || 'Photo'}</span>
                </span>
                <span className="ft-ext">{extOf(p.filename).toUpperCase() || '—'}</span>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="ft-table" role="table" aria-label="Photos on iPhone">
          <div className="ft-row head" role="row"><div>Photo / video</div><div>Kind</div><div>Size</div><div>Status</div><div /></div>
          {shown.map((p) => {
            const kind = kindOfPhoto(p);
            return (
              <div key={p.path} role="row" tabIndex={0}
                className={`ft-row${selected?.path === p.path ? ' selected' : ''}`}
                onClick={() => setSelected(p)} onKeyDown={(e) => { if (e.key === 'Enter') setSelected(p); }}>
                <div className="ft-cell-main"><KindGlyph kind={kind} /><span>{p.filename}</span></div>
                <div>{kind === 'video' ? 'Video' : 'Photo'}</div>
                <div className="ft-mono">{fmtBytes(p.size)}</div>
                <div><span className="pill skip">export-ready</span></div>
                <div />
              </div>
            );
          })}
        </div>
      )}
      {state === 'ready' && filtered.length > 0 && (
        <div className="ft-media-bar glass">{pagination}</div>
      )}
    </div>
  );
}

/* ---------------- Files ---------------- */

export function FilesView({ udid }: { udid: string }) {
  const [path, setPath] = useState('/');
  const [rows, setRows] = useState<FileEntry[]>([]);
  const [photos, setPhotos] = useState<PhotoItem[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<'list' | 'grid'>('list');
  const [selected, setSelected] = useState<FileEntry | null>(null);
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const closeMenu = useCallback(() => setOpenMenu(null), []);
  const { opBusy, opMsg, runDeviceOp } = useDeviceOps(udid, closeMenu);

  const load = useCallback(async (p: string) => {
    setState('loading');
    try {
      const [files, pics] = await Promise.all([api.browse(udid, p), api.photos(udid)]);
      setRows(files);
      setPhotos(pics);
      setState('ready');
      setSelected((s) => (s && files.some((f) => f.path === s.path) ? s : null));
    } catch {
      setRows([]);
      setState('error');
    }
  }, [udid]);

  useEffect(() => { load(path); }, [load, path]);
  useEffect(() => { setPath('/'); setQuery(''); setSelected(null); }, [udid]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q ? rows.filter((r) => (r.name + ' ' + r.path).toLowerCase().includes(q)) : rows;
    return list.slice().sort((a, b) =>
      a.is_dir === b.is_dir ? a.name.localeCompare(b.name) : a.is_dir ? -1 : 1);
  }, [rows, query]);

  /** Files that can be previewed/stepped through — folders are not part of it. */
  const stepable = useMemo(() => visible.filter((r) => !r.is_dir), [visible]);
  const selIndex = selected ? stepable.findIndex((r) => r.path === selected.path) : -1;
  const step = useCallback((dir: 1 | -1) => {
    if (!stepable.length) return;
    const next = selIndex < 0
      ? (dir > 0 ? 0 : stepable.length - 1)
      : (selIndex + dir + stepable.length) % stepable.length;
    setSelected(stepable[next]);
    requestAnimationFrame(() => {
      try { document.getElementById(`fr-${stepable[next].path}`)?.scrollIntoView({ block: 'nearest' }); } catch { /* noop */ }
    });
  }, [stepable, selIndex]);

  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.closest('.ft-pop') || t.isContentEditable)) return;
      if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
      else if (e.key === 'Escape') { setSelected(null); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected, step]);

  const folders = rows.filter((r) => r.is_dir).length;
  const atRoot = !path || path === '/';

  return (
    <div className="ft-media">
      <div className="ft-media-bar glass">
        <nav className="ft-crumbs" aria-label="Location">
          {crumbs(path).map((c, i, all) => (
            <span key={c.path} className="ft-crumb">
              {i > 0 && <span className="ft-crumb-sep" aria-hidden="true">›</span>}
              {i === all.length - 1
                ? <strong aria-current="page">{c.label}</strong>
                : <button className="ft-link" onClick={() => setPath(c.path)}>{c.label}</button>}
            </span>
          ))}
        </nav>
        <div className="ft-media-tools">
          <button className="ft-icon-btn" disabled={atRoot} onClick={() => setPath(parentOf(path))} aria-label="Go up one folder" title="Up one folder">↑</button>
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter this folder" aria-label="Filter files" className="ft-search" />
          <input value={path} onChange={(e) => setPath(e.target.value || '/')} placeholder="/" aria-label="Path on iPhone" className="ft-path" />
          <div className="ft-segment" role="tablist" aria-label="Layout">
            <button role="tab" aria-selected={mode === 'list'} className={mode === 'list' ? 'on' : ''} onClick={() => setMode('list')} title="List">☰</button>
            <button role="tab" aria-selected={mode === 'grid'} className={mode === 'grid' ? 'on' : ''} onClick={() => setMode('grid')} title="Icons">▦</button>
          </div>
          <button className="ft-icon-btn" onClick={() => load(path)} aria-label="Refresh files">⟳</button>
        </div>
        <div className="ft-media-count" role="status">
          <span>{state === 'ready' ? `${visible.length} item${visible.length === 1 ? '' : 's'} · ${folders} folder${folders === 1 ? '' : 's'}` : 'Browsing…'}</span>
          {!udid && <span> · no iPhone — sample data</span>}
        </div>
        {opMsg && <div className="ft-opmsg" role="status">{opBusy ? `${opMsg} (working…)` : opMsg}</div>}
      </div>

      <div className={`ft-finder${selected ? ' has-selection' : ''}`}>
        <div className="ft-finder-main">
          {state === 'loading' ? (
            <div className="ft-table" aria-busy="true"><div className="ft-row ft-row-files"><div>Loading files…</div><div /><div /></div></div>
          ) : state === 'error' ? (
            <div className="ft-table"><div className="ft-empty">
              <strong>Could not list files</strong>
              <p>Check the cable, tap Trust on the phone, then press Refresh.</p>
              <button className="ft-sync-btn" onClick={() => load(path)}>Retry</button>
            </div></div>
          ) : visible.length === 0 ? (
            <div className="ft-table"><div className="ft-empty">
              <KindGlyph kind="folder" />
              <strong>{query ? 'No matches in this folder' : 'Folder is empty'}</strong>
              <p>{query ? 'Clear the filter to see everything here.' : `Nothing at ${path} on the iPhone.`}</p>
            </div></div>
          ) : mode === 'list' ? (
            <div className="ft-table" role="table" aria-label="Files on iPhone">
              <div className="ft-row head ft-row-files" role="row"><div>Name</div><div>Kind</div><div>Size</div><div /></div>
              {visible.map((r) => {
                const kind = kindOfFile(r);
                const menuOpen = openMenu === r.path;
                const actions = r.is_dir ? [] : deviceActions(kind, extOf(r.name));
                return (
                  <div key={r.path} id={`fr-${r.path}`} role="row" tabIndex={0}
                    className={`ft-row ft-row-files${selected?.path === r.path ? ' selected' : ''}${r.is_dir ? ' is-dir' : ''}`}
                    onClick={() => (r.is_dir ? setPath(r.path) : setSelected(r))}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') { if (r.is_dir) setPath(r.path); else setSelected(r); }
                      if (e.key === 'Escape') setOpenMenu(null);
                    }}>
                    <div className="ft-cell-main"><KindGlyph kind={kind} /><span>{r.name}</span>{r.is_dir && <span className="ft-hint">›</span>}</div>
                    <div>{r.is_dir ? 'Folder' : extOf(r.name).toUpperCase() || 'File'}</div>
                    <div className="ft-mono">{fmtBytes(r.size)}</div>
                    <div className="ft-menu-cell">
                      {!r.is_dir && (
                        <button className="ft-icon-btn sm" aria-haspopup="menu" aria-expanded={menuOpen}
                          aria-label={`Actions for ${r.name}`} title="Tools for this file"
                          onClick={(e) => { e.stopPropagation(); setOpenMenu(menuOpen ? null : r.path); }}>
                          ⋯
                        </button>
                      )}
                      {menuOpen && (
                        <div className="ft-menu" role="menu" aria-label={`Actions for ${r.name}`}
                          onClick={(e) => e.stopPropagation()}>
                          <a role="menuitem" className="ft-menu-item"
                            href={api.fileContentUrl(udid, r.path)} download={r.name}>Export original</a>
                          {actions.map((a) => (
                            <button key={a.op} role="menuitem" className="ft-menu-item"
                              title={a.title} disabled={!!opBusy}
                              onClick={() => runDeviceOp(a.op, { path: r.path, name: r.name }, a.extra ?? {})}>
                              {a.label}
                            </button>
                          ))}
                          <button role="menuitem" className="ft-menu-item"
                            onClick={() => { try { navigator.clipboard.writeText(r.path); } catch { /* noop */ } setOpenMenu(null); }}>
                            Copy path
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="ft-gallery small" role="listbox" aria-label="Files on iPhone">
              {visible.map((r) => {
                const kind = kindOfFile(r);
                const active = selected?.path === r.path;
                return (
                  <button key={r.path} role="option" aria-selected={!!active}
                    className={`ft-thumb${active ? ' active' : ''}`}
                    onClick={() => (r.is_dir ? setPath(r.path) : setSelected(active ? null : r))}
                    onDoubleClick={() => r.is_dir && setPath(r.path)}
                    title={r.path}>
                    <span className="ft-thumb-art mini">
                      <KindGlyph kind={kind} />
                      {(kind === 'photo' || kind === 'video') && previewable(kind, r.name) && (
                        <ThumbImg udid={udid} path={r.path} size={256} />
                      )}
                    </span>
                    <span className="ft-thumb-meta">
                      <span className="ft-thumb-name">{r.name}</span>
                      <span className="ft-thumb-sub">{r.is_dir ? 'Folder' : fmtBytes(r.size)}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {photos.length > 0 && (
            <section aria-label="Photos strip">
              <div className="ft-strip-head">
                <span className="ft-section" style={{ padding: 0 }}>Photos on this iPhone · {photos.length}</span>
                <span className="ft-hint">export works · import is best-effort</span>
              </div>
              <div className="ft-strip">
                {photos.slice(0, 24).map((p) => (
                  <div key={p.path} className="ft-strip-item" title={`${p.filename} · ${fmtBytes(p.size)}`}>
                    <span className="ft-strip-art" style={{ background: `linear-gradient(135deg, hsl(${tintOf(p.filename)} 22% 88%), hsl(${(tintOf(p.filename) + 36) % 360} 24% 76%))` }}>
                      <KindGlyph kind={kindOfPhoto(p)} />
                      <ThumbImg udid={udid} path={p.path} size={256} />
                    </span>
                    <span className="ft-strip-name">{p.filename}</span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        {selected && (
          <Inspector
            variant="sidebar" udid={udid}
            item={{ path: selected.path, name: selected.name, size: selected.size,
              kind: kindOfFile(selected), isDir: selected.is_dir }}
            index={selIndex} total={stepable.length}
            onStep={step} onClose={() => setSelected(null)}
            opBusy={opBusy} runDeviceOp={runDeviceOp} />
        )}
      </div>
    </div>
  );
}
