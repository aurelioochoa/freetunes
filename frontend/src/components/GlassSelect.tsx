import { useEffect, useId, useRef, useState } from 'react';

export interface GlassOption {
  value: string;
  label: string;
  hint?: string;
}

interface GlassSelectProps {
  id?: string;
  value: string;
  options: GlassOption[];
  onChange: (v: string) => void;
  label: string;
  title?: string;
}

/**
 * Global Apple HIG pop-up button replacement.
 * Button shows the current selection; menu is a solid glass popover
 * with checkmark, keyboard nav (Esc / arrows / Enter) and click-outside.
 * Keeps a visually-hidden native select for forms / AT fallback.
 */
export default function GlassSelect({ id, value, options, onChange, label, title }: GlassSelectProps) {
  const [open, setOpen] = useState(false);
  const [focusIdx, setFocusIdx] = useState(() => Math.max(0, options.findIndex((o) => o.value === value)));
  const rootRef = useRef<HTMLDivElement | null>(null);
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const autoId = useId();
  const selectId = id ?? `gs-${autoId}`;
  const current = options.find((o) => o.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    setFocusIdx(Math.max(0, options.findIndex((o) => o.value === value)));
    function onDoc(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        setOpen(false);
        btnRef.current?.focus();
      }
    }
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, options, value]);

  useEffect(() => {
    if (open) menuRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (open) menuRef.current?.querySelector<HTMLElement>(`[data-option-index="${focusIdx}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [open, focusIdx]);

  function choose(v: string) {
    onChange(v);
    setOpen(false);
    btnRef.current?.focus();
  }

  function onBtnKey(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setOpen((o) => !o);
    }
  }

  function onListKey(e: React.KeyboardEvent) {
    if (!options.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocusIdx((i) => (i + 1) % options.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocusIdx((i) => (i - 1 + options.length) % options.length);
    } else if (e.key === 'Home' || e.key === 'End') {
      e.preventDefault();
      setFocusIdx(e.key === 'Home' ? 0 : options.length - 1);
    } else if (e.key === 'Tab') {
      setOpen(false);
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      choose(options[focusIdx]?.value ?? value);
    }
  }

  return (
    <div className="ft-pop" ref={rootRef}>
      <span id={`${selectId}-label`} className="ft-sr-only">{label}</span>
      {/* AT / no-JS fallback */}
      <select
        className="ft-sr-only"
        aria-hidden="true"
        tabIndex={-1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <button
        ref={btnRef}
        id={selectId}
        type="button"
        className={`ft-pop-btn${open ? ' open' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? `${selectId}-menu` : undefined}
        aria-labelledby={`${selectId}-label ${selectId}`}
        title={title ?? label}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onBtnKey}
      >
        <span className="ft-pop-value">{current?.label}</span>
        {current?.hint && <span className="ft-pop-hint">{current.hint}</span>}
        <svg className="ft-pop-chev" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div
          ref={menuRef}
          id={`${selectId}-menu`}
          className="ft-pop-menu"
          role="listbox"
          aria-activedescendant={options.length ? `${selectId}-option-${focusIdx}` : undefined}
          aria-labelledby={`${selectId}-label`}
          tabIndex={-1}
          onKeyDown={onListKey}
        >
          {options.map((o, i) => {
            const selected = o.value === value;
            return (
              <button
                key={o.value}
                type="button"
                role="option"
                id={`${selectId}-option-${i}`}
                data-option-index={i}
                tabIndex={-1}
                aria-selected={selected}
                className={`ft-pop-item${selected ? ' selected' : ''}${i === focusIdx ? ' focused' : ''}`}
                onClick={() => choose(o.value)}
                onMouseEnter={() => setFocusIdx(i)}
              >
                <span className="ft-pop-check" aria-hidden="true">{selected ? '✓' : ''}</span>
                <span className="ft-pop-text">
                  <span className="ft-pop-label">{o.label}</span>
                  {o.hint && <span className="ft-pop-sub">{o.hint}</span>}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
