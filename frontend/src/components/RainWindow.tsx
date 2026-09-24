import { useEffect, useRef, useState } from 'react';

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

interface Drop { x: number; y: number; r: number; a: number; ph: number }
interface TrailPt { x: number; y: number; age: number }
interface Runner { x: number; y: number; speed: number; r: number; w: number; ph: number; trail: TrailPt[] }

const rnd = (a: number, b: number) => a + Math.random() * (b - a);
const TRAIL_LIFE = 1.6;

/**
 * Realistic rainy window (in the spirit of lbebber's WebGL demo, done in
 * 2D canvas): a blurred night-city backdrop, condensation droplets that
 * refract a *focused* copy of the backdrop like tiny lenses, and heavy
 * drops that wobble down the pane leaving fading wet trails — absorbing
 * small droplets on their way. Only mounted while Rain is active.
 */
export default function RainWindow() {
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
    let drops: Drop[] = [];
    let runners: Runner[] = [];

    // Backdrop layers, repainted on resize only.
    const bgBlur = document.createElement('canvas');
    const bgSharp = document.createElement('canvas');
    let sheen: CanvasGradient | null = null;
    let vig: CanvasGradient | null = null;

    function paintScene(c: CanvasRenderingContext2D, sw: number, sh: number) {
      const g = c.createLinearGradient(0, 0, 0, sh);
      g.addColorStop(0, '#101b2e');
      g.addColorStop(0.55, '#0a1020');
      g.addColorStop(1, '#04060c');
      c.fillStyle = g;
      c.fillRect(0, 0, sw, sh);
      // City lights: warm windows below, cool neons above.
      for (let i = 0; i < 42; i++) {
        const warm = Math.random() < 0.55;
        const bx = rnd(0, sw);
        const by = warm ? rnd(sh * 0.45, sh) : rnd(0, sh * 0.6);
        const br = rnd(3, 16);
        const hue = warm ? rnd(20, 48) : rnd(180, 320);
        const rg = c.createRadialGradient(bx, by, 0, bx, by, br);
        rg.addColorStop(0, `hsla(${hue}, 90%, 68%, 0.85)`);
        rg.addColorStop(0.35, `hsla(${hue}, 90%, 60%, 0.35)`);
        rg.addColorStop(1, `hsla(${hue}, 90%, 60%, 0)`);
        c.fillStyle = rg;
        c.beginPath();
        c.arc(bx, by, br, 0, Math.PI * 2);
        c.fill();
      }
      // Distant window grid.
      c.fillStyle = 'rgba(255, 200, 130, 0.20)';
      for (let i = 0; i < 60; i++) {
        c.fillRect(rnd(0, sw), rnd(sh * 0.4, sh), rnd(1, 3), rnd(1, 2.5));
      }
    }

    function paintBackdrop() {
      // Sharp layer: what droplets refract (focused world).
      // Blurred layer: what the naked eye sees through the glass.
      const sw = Math.max(2, Math.floor(w / 2));
      const sh = Math.max(2, Math.floor(h / 2));
      bgSharp.width = sw;
      bgSharp.height = sh;
      const sctx = bgSharp.getContext('2d');
      if (sctx) paintScene(sctx, sw, sh);
      bgBlur.width = sw;
      bgBlur.height = sh;
      const bctx = bgBlur.getContext('2d');
      if (bctx) {
        try { bctx.filter = 'blur(9px)'; } catch { /* older canvas */ }
        bctx.drawImage(bgSharp, 0, 0);
        try { bctx.filter = 'none'; } catch { /* older canvas */ }
      }
    }

    function spawnRunner(anywhere: boolean): Runner {
      return {
        x: rnd(0, w),
        y: anywhere ? rnd(0, h) : rnd(-h * 0.2, 0),
        speed: rnd(110, 300),
        r: rnd(2.2, 3.6),
        w: rnd(1.2, 2),
        ph: rnd(0, Math.PI * 2),
        trail: []
      };
    }

    function resize() {
      const parent = canvas!.parentElement;
      const pw = parent ? parent.clientWidth : window.innerWidth;
      const ph = parent ? parent.clientHeight : window.innerHeight;
      w = Math.max(1, pw);
      h = Math.max(1, ph);
      canvas!.width = Math.floor(pw * dpr);
      canvas!.height = Math.floor(ph * dpr);
      canvas!.style.width = `${pw}px`;
      canvas!.style.height = `${ph}px`;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);

      paintBackdrop();
      sheen = ctx!.createLinearGradient(0, 0, w * 0.7, h);
      sheen.addColorStop(0, 'rgba(200,225,250,0.055)');
      sheen.addColorStop(0.5, 'rgba(200,225,250,0)');
      vig = ctx!.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.35, w / 2, h / 2, Math.max(w, h) * 0.75);
      vig.addColorStop(0, 'rgba(0,0,0,0)');
      vig.addColorStop(1, 'rgba(0,0,0,0.45)');

      const area = w * h;
      const nDrop = Math.min(200, Math.max(50, Math.floor(area / 11000)));
      drops = Array.from({ length: nDrop }, () => ({
        x: rnd(0, w), y: rnd(0, h), r: rnd(1, 3.4), a: rnd(0.5, 1), ph: rnd(0, Math.PI * 2)
      }));
      const nRun = Math.min(14, Math.max(5, Math.floor(area / 130000)));
      runners = Array.from({ length: nRun }, () => spawnRunner(true));
    }

    /** Lens refraction: sample the *focused* backdrop, magnified + shifted up. */
    function drawLens(x: number, y: number, r: number, alpha: number) {
      const z = 2.1;
      const sw = (r * 2) / z;
      const sh = (r * 2) / z;
      // Source lives on the half-scale sharp canvas.
      const sx = (x - sw / 2) / 2;
      const sy = (y - sh / 2 - r * 0.35) / 2;
      ctx!.save();
      ctx!.beginPath();
      ctx!.arc(x, y, r, 0, Math.PI * 2);
      ctx!.clip();
      ctx!.globalAlpha = alpha;
      ctx!.drawImage(bgSharp, sx, sy, sw / 2, sh / 2, x - r, y - r, r * 2, r * 2);
      ctx!.globalAlpha = 1;
      // Transmitted light pools at the bottom, dark crescent on top.
      const shade = ctx!.createLinearGradient(0, y - r, 0, y + r);
      shade.addColorStop(0, 'rgba(0,0,0,0.28)');
      shade.addColorStop(0.55, 'rgba(0,0,0,0)');
      shade.addColorStop(1, 'rgba(210,235,255,0.30)');
      ctx!.fillStyle = shade;
      ctx!.fillRect(x - r, y - r, r * 2, r * 2);
      ctx!.restore();
      // Bright rim + specular catchlight.
      ctx!.strokeStyle = 'rgba(205,232,252,0.55)';
      ctx!.lineWidth = 1;
      ctx!.beginPath();
      ctx!.arc(x, y, r - 0.5, 0, Math.PI * 2);
      ctx!.stroke();
      ctx!.fillStyle = 'rgba(235,248,255,0.9)';
      ctx!.beginPath();
      ctx!.arc(x - r * 0.34, y - r * 0.38, Math.max(0.6, r * 0.18), 0, Math.PI * 2);
      ctx!.fill();
    }

    let last = performance.now();
    function frame(now: number) {
      raf = requestAnimationFrame(frame);
      if (document.hidden) { last = now; return; }
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const t = now / 1000;

      // Blurred world behind the glass.
      ctx!.drawImage(bgBlur, 0, 0, bgBlur.width, bgBlur.height, 0, 0, w, h);

      // Condensation lenses, gently breathing.
      for (const d of drops) {
        const tw = d.a * (0.85 + 0.15 * Math.sin(t * 0.8 + d.ph));
        drawLens(d.x, d.y, d.r, tw);
      }

      // Sliding drops with fading wet trails.
      for (let i = 0; i < runners.length; i++) {
        const r = runners[i];
        r.y += r.speed * (0.65 + r.y / h) * dt;
        r.x += Math.sin(r.y * 0.03 + r.ph) * 0.5;
        r.trail.push({ x: r.x, y: r.y, age: 0 });
        if (r.trail.length > 36) r.trail.shift();
        if (r.y - 160 > h) {
          runners[i] = spawnRunner(false);
          continue;
        }
        // Wet trail: taper + fade with age (every 2nd segment: halves strokes).
        for (let k = 2; k < r.trail.length; k += 2) {
          const p = r.trail[k];
          p.age += dt * 2;
          if (p.age > TRAIL_LIFE) continue;
          const f = 1 - p.age / TRAIL_LIFE;
          ctx!.strokeStyle = `rgba(185,220,248,${0.22 * f})`;
          ctx!.lineWidth = r.w * f + 0.4;
          ctx!.lineCap = 'round';
          ctx!.beginPath();
          ctx!.moveTo(r.trail[k - 1].x, r.trail[k - 1].y);
          ctx!.lineTo(p.x, p.y);
          ctx!.stroke();
        }
        // Absorb condensation in the wiper's path.
        for (let di = drops.length - 1; di >= 0; di--) {
          const d = drops[di];
          const dx = d.x - r.x;
          const dy = d.y - r.y;
          if (dx * dx + dy * dy < (r.r + d.r) * (r.r + d.r)) {
            drops[di] = { x: rnd(0, w), y: rnd(0, h), r: rnd(1, 3), a: rnd(0.5, 1), ph: rnd(0, Math.PI * 2) };
            r.r = Math.min(4.2, r.r + 0.05);
          }
        }
        drawLens(r.x, r.y, r.r, 1);
      }

      // Glass sheen + vignette.
      ctx!.fillStyle = sheen!;
      ctx!.fillRect(0, 0, w, h);
      ctx!.fillStyle = vig!;
      ctx!.fillRect(0, 0, w, h);
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
  return <canvas className="ft-rain" aria-hidden="true" ref={ref} />;
}
