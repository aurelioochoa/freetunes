import { useState } from 'react';
import type { SyncItem } from '../api';

/** Plain words for everyone; the raw sync codes stay in the tooltip. */
const ACTION_LABEL: Record<SyncItem['action'], string> = {
  push: 'Copy to iPhone',
  skip: 'Already on iPhone',
  delete: 'Remove from iPhone'
};

export default function SyncTable({ rows }: { rows: SyncItem[] }) {
  const [selected, setSelected] = useState<string | null>(null);

  if (rows.length === 0) {
    return (
      <div className="ft-table">
        <div className="ft-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M9 18V6l10-2v11" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="6.5" cy="18" r="2.5" />
            <circle cx="16.5" cy="15" r="2.5" />
          </svg>
          <strong>No changes to show</strong>
          <p>Choose the folder with your music or books above, then press Preview. freetunes compares it with your iPhone and lists here what it would copy.</p>
        </div>
      </div>
    );
  }

  function toggle(name: string) {
    setSelected((s) => (s === name ? null : name));
  }

  return (
    <>
      <div className="ft-table" role="table" aria-label="What sync will do">
        <div className="ft-row head" role="row">
          <div>File</div><div>What happens</div><div>Why</div><div>Size</div><div>Status</div>
        </div>
        {rows.map((r) => {
          const key = r.action + r.filename;
          const isSel = selected === key;
          return (
            <div
              key={key}
              role="row"
              tabIndex={0}
              aria-selected={isSel}
              className={`ft-row${isSel ? ' selected' : ''}`}
              onClick={() => toggle(key)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(key); } }}
            >
              <div>{r.filename}</div>
              <div><span className={`pill ${r.action}`} title={`sync code: ${r.action}`}>{ACTION_LABEL[r.action]}</span></div>
              <div>{r.reason}</div>
              <div>{r.size}</div>
              <div>queued</div>
            </div>
          );
        })}
      </div>
      <details className="ft-tech">
        <summary>Technical details: what do these words mean?</summary>
        <p>
          Copy to iPhone (code <code>push</code>) = new or changed file, identified by its SHA-256 hash.
          Already on iPhone (code <code>skip</code>) = identical hash on both sides, nothing to do.
          Remove from iPhone (code <code>delete</code>) = only with mirror mode, file missing on this computer.
          Reasons <code>new</code> / <code>changed</code> / <code>identical</code> come straight from the freetunes API.
        </p>
      </details>
    </>
  );
}
