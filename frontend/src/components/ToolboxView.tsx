import { useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from '../api';
import DevModeControls from './DevModeControls';

type Result = { ok: boolean; reason?: string; hint?: string; download?: string; filename?: string } | null;

function ToolIcon({ d }: { d: string }) {
  return (
    <span className="ft-tool-icon" aria-hidden="true">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
        <path d={d} />
      </svg>
    </span>
  );
}

function BentoCard({ area, icon, title, sub, children, footer }: {
  area: string; icon: ReactNode; title: string; sub: string; children: ReactNode; footer?: ReactNode;
}) {
  return (
    <section className={`ft-bento-card glass bento-${area}`} aria-label={title}>
      <header className="ft-bento-head">
        {icon}
        <div>
          <h3>{title}</h3>
          <p>{sub}</p>
        </div>
      </header>
      <div className="ft-bento-body">{children}</div>
      {footer && <div className="ft-bento-foot">{footer}</div>}
    </section>
  );
}

function ResultLine({ r }: { r: Result }) {
  if (!r) return null;
  return (
    <p className={`ft-result${r.ok ? ' ok' : ' err'}`} role="status">
      <span aria-hidden="true">{r.ok ? '✓' : '!'}</span>
      {' '}{r.ok ? 'Done' : `Not done: ${r.reason ?? 'unknown error'}`}
      {r.hint ? ` — ${r.hint}` : ''}
      {r.ok && r.download && (
        <> — <a className="ft-link" href={r.download} download={r.filename || true}>
          Download {r.filename || 'result'}
        </a></>
      )}
    </p>
  );
}

/**
 * Source picker: type a server path, browse local files, or drop them in.
 * Dropped files upload to the backend; the returned server path fills in.
 */
function SourceField({ value, onChange, label, placeholder, accept }: {
  value: string; onChange: (v: string) => void;
  label: string; placeholder: string; accept?: string;
}) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  async function take(files: FileList | null) {
    const f = files?.[0];
    if (!f) return;
    setErr('');
    setUploading(true);
    try {
      const r = await api.upload(f);
      if (r.ok && r.path) onChange(r.path);
      else setErr(r.reason || 'Upload failed.');
    } catch (e) {
      setErr(`Upload failed: ${String(e)}`);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  return (
    <div
      className={`ft-drop${dragOver ? ' over' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => { e.preventDefault(); setDragOver(false); take(e.dataTransfer.files); }}
    >
      <div className="ft-field-row">
        <input value={value} onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder} aria-label={label} />
        <button className="ft-icon-btn" disabled={uploading} onClick={() => fileRef.current?.click()}
          title="Pick a file from this computer (uploads it for the tool)">
          {uploading ? 'Uploading…' : 'Browse…'}
        </button>
      </div>
      <input ref={fileRef} type="file" accept={accept} className="ft-sr-only" tabIndex={-1}
        aria-hidden="true" onChange={(e) => take(e.target.files)} />
      <span className="ft-hint">Type a path, Browse, or drop a file here.</span>
      {err && <span className="ft-result err" role="alert">{err}</span>}
    </div>
  );
}

export default function ToolboxView({ musicDir, udid }: { musicDir: string; udid: string }) {
  const [dupPath, setDupPath] = useState(musicDir);
  const [dups, setDups] = useState<string[][]>([]);
  const [dupMsg, setDupMsg] = useState('Find byte-identical duplicates before syncing.');
  const [dupBusy, setDupBusy] = useState(false);

  const [tagPath, setTagPath] = useState('');
  const [tagTitle, setTagTitle] = useState('');
  const [tagArtist, setTagArtist] = useState('');
  const [tagAlbum, setTagAlbum] = useState('');
  const [tagRes, setTagRes] = useState<Result>(null);
  const [tagBusy, setTagBusy] = useState(false);

  const [ringSrc, setRingSrc] = useState('');
  const [ringDest, setRingDest] = useState('');
  const [ringStart, setRingStart] = useState('0');
  const [ringEnd, setRingEnd] = useState('30');
  const [ringRes, setRingRes] = useState<Result>(null);
  const [ringBusy, setRingBusy] = useState(false);

  const [convSrc, setConvSrc] = useState('');
  const [convDest, setConvDest] = useState('');
  const [convRes, setConvRes] = useState<Result>(null);
  const [convBusy, setConvBusy] = useState(false);

  const [imgSrc, setImgSrc] = useState('');
  const [imgDest, setImgDest] = useState('');
  const [imgRes, setImgRes] = useState<Result>(null);
  const [imgBusy, setImgBusy] = useState(false);

  const [heicSrc, setHeicSrc] = useState('');
  const [heicDest, setHeicDest] = useState('');
  const [heicRes, setHeicRes] = useState<Result>(null);
  const [heicBusy, setHeicBusy] = useState(false);

  useEffect(() => { setDupPath(musicDir); }, [musicDir]);

  async function findDups() {
    setDupBusy(true);
    try {
      const r = await api.duplicates(dupPath || musicDir);
      if (!r.ok && (r as { reason?: string }).reason) setDupMsg(`${(r as { reason?: string }).reason}`);
      else { setDups(r.groups ?? []); setDupMsg(`Found ${r.count ?? 0} duplicate group${(r.count ?? 0) === 1 ? '' : 's'}.`); }
    } catch (e) { setDupMsg(`Scan failed: ${String(e)}`); }
    finally { setDupBusy(false); }
  }

  async function saveTags() {
    if (!tagPath.trim()) { setTagRes({ ok: false, reason: 'Pick an audio file first.' }); return; }
    setTagBusy(true);
    try {
      setTagRes(await api.editTags(tagPath.trim(), tagTitle || undefined, tagArtist || undefined, tagAlbum || undefined));
    } catch (e) { setTagRes({ ok: false, reason: String(e) }); }
    finally { setTagBusy(false); }
  }

  async function makeRing() {
    setRingBusy(true);
    try {
      const s = parseFloat(ringStart), e = parseFloat(ringEnd);
      setRingRes(await api.makeRingtone(ringSrc.trim(), ringDest.trim(), s, e));
    } catch (err) { setRingRes({ ok: false, reason: String(err) }); }
    finally { setRingBusy(false); }
  }

  async function convert() {
    if (!convSrc.trim()) { setConvRes({ ok: false, reason: 'Pick a source file first (type, Browse, or drop).' }); return; }
    setConvBusy(true);
    try { setConvRes(await api.convertMedia(convSrc.trim(), convDest.trim())); }
    catch (e) { setConvRes({ ok: false, reason: String(e) }); }
    finally { setConvBusy(false); }
  }

  async function compress() {
    if (!imgSrc.trim()) { setImgRes({ ok: false, reason: 'Pick a source file first (type, Browse, or drop).' }); return; }
    setImgBusy(true);
    try { setImgRes(await api.compressPhoto(imgSrc.trim(), imgDest.trim())); }
    catch (e) { setImgRes({ ok: false, reason: String(e) }); }
    finally { setImgBusy(false); }
  }

  async function heic() {
    if (!heicSrc.trim()) { setHeicRes({ ok: false, reason: 'Pick a source file first (type, Browse, or drop).' }); return; }
    setHeicBusy(true);
    try { setHeicRes(await api.heicToJpg(heicSrc.trim(), heicDest.trim())); }
    catch (e) { setHeicRes({ ok: false, reason: String(e) }); }
    finally { setHeicBusy(false); }
  }

  return (
    <div className="ft-bento-wrap">
      <p className="ft-footer" style={{ padding: '0 4px 4px' }}>
        Six local tools that never touch the iPhone until you sync, plus
        Developer Mode — the one card here that does talk to the phone.
      </p>

      <div className="ft-bento">
        <BentoCard area="devmode"
          icon={<ToolIcon d="M8 6l-5 6 5 6 M16 6l5 6-5 6" />}
          title="Developer Mode" sub="iOS 16+ · unlocks live screen and deep diagnostics"
          footer={<span className="ft-hint">
            Showing the row changes nothing else on the phone. Turning Developer
            Mode on restarts it, so that button asks twice.
          </span>}>
          {udid ? (
            <DevModeControls udid={udid} fallback={
              <p className="ft-hint">
                Install pymobiledevice3 on this computer to drive Developer Mode
                from here. Until then: Settings → Privacy &amp; Security on the iPhone.
              </p>
            } />
          ) : (
            <p className="ft-hint">
              Connect and trust an iPhone to reveal or turn on Developer Mode.
            </p>
          )}
        </BentoCard>

        <BentoCard area="dup"
          icon={<ToolIcon d="M4 6h16M4 12h16M4 18h10" />}
          title="Duplicate finder" sub="Byte-identical files in your library"
          footer={<span className="ft-hint" role="status">{dupMsg}</span>}>
          <div className="ft-field-row">
            <input value={dupPath} onChange={(e) => setDupPath(e.target.value)} placeholder="/path/to/scan" aria-label="Folder to scan for duplicates" />
            <button className="ft-sync-btn" disabled={dupBusy} onClick={findDups}>{dupBusy ? 'Scanning…' : 'Scan'}</button>
          </div>
          <ul className="ft-dup-list" aria-label="Duplicate files">
            {dups.length === 0 ? (
              <li className="ft-dup-empty">No duplicates yet — pick a folder and scan.</li>
            ) : dups.slice(0, 8).map((g, i) => (
              <li key={i} className="ft-dup-group">
                <span className="ft-dup-badge">{g.length}×</span>
                <span className="ft-mono">{g.join('  ↔  ')}</span>
              </li>
            ))}
          </ul>
          {dups.length > 8 && <span className="ft-hint">+ {dups.length - 8} more group(s)</span>}
        </BentoCard>

        <BentoCard area="tags"
          icon={<ToolIcon d="M4 5h7l9 9-7 7-9-9Z M8.5 9.5h.01" />}
          title="Audio tags" sub="MP3 / M4A title, artist, album"
          footer={<ResultLine r={tagRes} />}>
          <SourceField value={tagPath} onChange={setTagPath} label="Audio file to tag"
            placeholder="/path/to/song.mp3 or drop a file" accept="audio/*" />
          <div className="ft-field-grid3">
            <input value={tagTitle} onChange={(e) => setTagTitle(e.target.value)} placeholder="Title" aria-label="Title" />
            <input value={tagArtist} onChange={(e) => setTagArtist(e.target.value)} placeholder="Artist" aria-label="Artist" />
            <input value={tagAlbum} onChange={(e) => setTagAlbum(e.target.value)} placeholder="Album" aria-label="Album" />
          </div>
          <button className="ft-sync-btn block" disabled={tagBusy} onClick={saveTags}>{tagBusy ? 'Saving…' : 'Save tags'}</button>
        </BentoCard>

        <BentoCard area="ring"
          icon={<ToolIcon d="M9 18V6l10-2v12 M6 18a3 3 0 1 0 0 .01 M19 16a3 3 0 1 0 0 .01" />}
          title="Ringtone maker" sub="≤ 40 s · needs ffmpeg · empty dest downloads"
          footer={<ResultLine r={ringRes} />}>
          <SourceField value={ringSrc} onChange={setRingSrc} label="Ringtone source audio"
            placeholder="/path/to/song.mp3 or drop a file" accept="audio/*" />
          <div className="ft-field-grid2">
            <input value={ringStart} onChange={(e) => setRingStart(e.target.value)} placeholder="Start (s)" aria-label="Start seconds" inputMode="decimal" />
            <input value={ringEnd} onChange={(e) => setRingEnd(e.target.value)} placeholder="End (s)" aria-label="End seconds" inputMode="decimal" />
          </div>
          <input value={ringDest} onChange={(e) => setRingDest(e.target.value)} placeholder="Auto — download .m4r" aria-label="Ringtone destination (optional)" />
          <button className="ft-sync-btn block" disabled={ringBusy} onClick={makeRing}>{ringBusy ? 'Cutting…' : 'Make ringtone'}</button>
        </BentoCard>

        <BentoCard area="convert"
          icon={<ToolIcon d="M4 8h13l-3-3 M20 16H7l3 3" />}
          title="Format conversion" sub="ffmpeg · WAV ↔ MP3 ↔ M4A · empty dest downloads"
          footer={<ResultLine r={convRes} />}>
          <SourceField value={convSrc} onChange={setConvSrc} label="Convert source"
            placeholder="/path/to/in.wav or drop a file" accept="audio/*,video/*" />
          <input value={convDest} onChange={(e) => setConvDest(e.target.value)} placeholder="Auto — download result" aria-label="Convert destination (optional)" />
          <button className="ft-sync-btn block" disabled={convBusy} onClick={convert}>{convBusy ? 'Converting…' : 'Convert'}</button>
        </BentoCard>

        <BentoCard area="compress"
          icon={<ToolIcon d="M4 12a8 8 0 0 1 16 0 M12 4v8 M9 9l3 3 3-3" />}
          title="Compress photo" sub="Pillow · smaller JPG · empty dest downloads"
          footer={<ResultLine r={imgRes} />}>
          <SourceField value={imgSrc} onChange={setImgSrc} label="Photo to compress"
            placeholder="/path/to/photo.jpg or drop a file" accept="image/*" />
          <input value={imgDest} onChange={(e) => setImgDest(e.target.value)} placeholder="Auto — download result" aria-label="Compressed destination (optional)" />
          <button className="ft-sync-btn block" disabled={imgBusy} onClick={compress}>{imgBusy ? 'Compressing…' : 'Compress'}</button>
        </BentoCard>

        <BentoCard area="heic"
          icon={<ToolIcon d="M4 5h16v14H4Z M4 15l4-4 3 3 3-3 6 6" />}
          title="HEIC → JPG" sub="pillow-heif · iPhone photos · empty dest downloads"
          footer={<ResultLine r={heicRes} />}>
          <SourceField value={heicSrc} onChange={setHeicSrc} label="HEIC source"
            placeholder="/path/to/photo.heic or drop a file" accept=".heic,.heif,image/*" />
          <input value={heicDest} onChange={(e) => setHeicDest(e.target.value)} placeholder="Auto — download result" aria-label="JPG destination (optional)" />
          <button className="ft-sync-btn block" disabled={heicBusy} onClick={heic}>{heicBusy ? 'Converting…' : 'Convert HEIC'}</button>
        </BentoCard>
      </div>
    </div>
  );
}
