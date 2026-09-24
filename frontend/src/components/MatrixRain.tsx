import { useEffect, useRef, useState } from 'react';

const GLYPHS = 'アイウエオカキクケコサシスセソ0123456789ABCDEF$#*+=<>';

function motionReduced(): boolean {
  try {
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return true;
  } catch { /* noop */ }
  try {
    if (document.documentElement.getAttribute('data-reduce-motion') === '1') return true;
  } catch { /* noop */ }
  return false;
}

/**
 * Matrix glyph rain. Mounted only while the Matrix wallpaper is active;
 * unmounts (no rAF, no cost) otherwise. Honors Reduce Motion by rendering
 * nothing, and pauses when the tab is hidden.
 */
export default function MatrixRain() {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const [reduced] = useState(motionReduced);

  useEffect(() => {
    if (reduced) return;
    const canvas = ref.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let raf = 0;
    let w = 0;
    let h = 0;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const FONT = 15;
    const TAIL = 14;
    let drops: { x: number; y: number; speed: number }[] = [];

    function resize() {
      const parent = canvas!.parentElement;
      const pw = parent ? parent.clientWidth : window.innerWidth;
      const ph = parent ? parent.clientHeight : window.innerHeight;
      w = pw;
      h = ph;
      canvas!.width = Math.floor(pw * dpr);
      canvas!.height = Math.floor(ph * dpr);
      canvas!.style.width = `${pw}px`;
      canvas!.style.height = `${ph}px`;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      const cols = Math.min(90, Math.max(24, Math.floor(pw / (FONT + 6))));
      drops = Array.from({ length: cols }, (_, i) => ({
        x: (i + 0.5) * (pw / cols),
        y: Math.random() * ph,
        speed: 1.5 + Math.random() * 3
      }));
    }

    // Light-phosphor on dark surfaces, deep green on light ones.
    const t = document.documentElement.getAttribute('data-theme');
    const dark = t === 'dark' || t === 'midnight'
      || (!t && window.matchMedia('(prefers-color-scheme: dark)').matches);
    const head = dark ? '190,255,200' : '20,110,55';
    const tail = dark ? '48,209,88' : '31,157,68';

    let last = performance.now();
    function frame(now: number) {
      raf = requestAnimationFrame(frame);
      if (document.hidden) { last = now; return; }
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      ctx!.clearRect(0, 0, w, h);
      ctx!.font = `${FONT}px ui-monospace, Menlo, monospace`;
      ctx!.textAlign = 'center';
      for (const d of drops) {
        for (let t = 0; t < TAIL; t++) {
          const yy = d.y - t * (FONT + 2);
          if (yy < -FONT || yy > h + FONT) continue;
          const a = t === 0 ? 0.9 : Math.max(0, 0.45 * (1 - t / TAIL));
          ctx!.fillStyle = t === 0 ? `rgba(${head},${a})` : `rgba(${tail},${a})`;
          const g = GLYPHS[(Math.random() * GLYPHS.length) | 0];
          ctx!.fillText(g, d.x, yy);
        }
        d.y += d.speed * 60 * dt;
        if (d.y - TAIL * (FONT + 2) > h && Math.random() < 0.02) {
          d.y = -Math.random() * h * 0.3;
          d.speed = 1.5 + Math.random() * 3;
        }
      }
    }

    resize();
    window.addEventListener('resize', resize);
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
    };
  }, [reduced]);

  if (reduced) return null;
  return <canvas className="ft-matrix" aria-hidden="true" ref={ref} />;
}
