import { useEffect, useRef, useState } from 'react';

export type ValeriaConn = 'connecting' | 'stream' | 'error';

/** Stream config pushed by screen-mirror over the socket (`config:{...}`). */
interface StreamConfig {
  width: number;
  height: number;
  codec: string;
}

/** Scan an Annex-B byte sequence for an IDR NAL unit (type 5). */
function hasIdr(bytes: Uint8Array): boolean {
  for (let i = 0; i + 4 < bytes.length; i++) {
    if (bytes[i] === 0 && bytes[i + 1] === 0 && bytes[i + 2] === 0 && bytes[i + 3] === 1) {
      if ((bytes[i + 4] & 0x1f) === 5) return true;
    }
  }
  return false;
}

/**
 * QuickTime-over-USB viewer without the fork's browser page.
 *
 * screen-mirror serves a full web page (canvas + status footer) that was
 * built for its own window: embedded in the phone cutout its body padding
 * letterboxes the video, its stream/fps/backend footer lands inside the
 * viewport — a scrollbar inside the phone. The video itself arrives over
 * `/ws` (config JSON, backend name, raw H.264 Annex-B), so this component
 * speaks that protocol directly onto a bare canvas: the canvas is the only
 * thing in the cutout, there is nothing to scroll, and fps is reported up
 * to the freetunes toolbar instead of a footer under the screen.
 */
export default function ValeriaViewer({ wsUrl, onFps, onConn }: {
  wsUrl: string;
  onFps: (fps: number | null) => void;
  onConn: (c: ValeriaConn) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [unsupported, setUnsupported] = useState(false);
  const cb = useRef({ onFps, onConn });
  cb.current = { onFps, onConn };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (typeof VideoDecoder === 'undefined') {
      setUnsupported(true);
      cb.current.onConn('error');
      return;
    }
    let dead = false;
    let ws: WebSocket | null = null;
    let decoder: VideoDecoder | null = null;
    let configured = false;
    let ts = 0;
    let frames = 0;
    let fpsTimer: ReturnType<typeof setInterval> | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    const ctx = canvas.getContext('2d');

    function closeDecoder() {
      if (decoder) {
        try { decoder.close(); } catch { /* already closed */ }
        decoder = null;
      }
      configured = false;
    }

    function setupDecoder(cfg: StreamConfig) {
      closeDecoder();
      canvas!.width = cfg.width;
      canvas!.height = cfg.height;
      decoder = new VideoDecoder({
        output(frame) {
          try {
            ctx?.drawImage(frame, 0, 0, cfg.width, cfg.height);
          } finally {
            frame.close();
          }
          frames++;
        },
        error() {
          if (!dead) cb.current.onConn('error');
        },
      });
      decoder.configure({ codec: cfg.codec, optimizeForLatency: true });
      configured = true;
    }

    function feed(bytes: Uint8Array) {
      if (!configured || !decoder) return; // discarding pre-config bytes
      try {
        decoder.decode(new EncodedVideoChunk({
          type: hasIdr(bytes) ? 'key' : 'delta',
          timestamp: ts,
          data: bytes,
        }));
      } catch {
        // a torn chunk mid-GOP: the next keyframe resyncs by itself
      }
      ts += 16667; // microseconds; fake monotonic clock at ~60 fps
    }

    function connect() {
      if (dead) return;
      cb.current.onConn('connecting');
      let sock: WebSocket;
      try {
        sock = new WebSocket(wsUrl);
      } catch {
        if (!dead) retryTimer = setTimeout(connect, 2000);
        return;
      }
      ws = sock;
      sock.binaryType = 'arraybuffer';
      sock.onopen = () => { if (!dead) cb.current.onConn('stream'); };
      sock.onclose = () => {
        closeDecoder();
        if (dead) return;
        cb.current.onConn('error');
        cb.current.onFps(null);
        retryTimer = setTimeout(connect, 2000);
      };
      sock.onerror = () => {
        if (!dead) cb.current.onConn('error');
      };
      sock.onmessage = (e) => {
        if (dead) return;
        if (typeof e.data === 'string') {
          if (e.data.startsWith('config:')) {
            try {
              setupDecoder(JSON.parse(e.data.slice(7)) as StreamConfig);
            } catch {
              cb.current.onConn('error');
            }
          }
          return; // `backend:...` needs no UI of its own
        }
        feed(new Uint8Array(e.data as ArrayBuffer));
      };
    }

    fpsTimer = setInterval(() => {
      if (dead) return;
      cb.current.onFps(frames);
      frames = 0;
    }, 1000);
    connect();
    return () => {
      dead = true;
      if (fpsTimer) clearInterval(fpsTimer);
      if (retryTimer) clearTimeout(retryTimer);
      try { ws?.close(); } catch { /* gone already */ }
      closeDecoder();
    };
  }, [wsUrl]);

  if (unsupported) {
    return (
      <div className="ft-screen-hd ft-valeria-fallback" role="status">
        WebCodecs is unavailable — open freetunes in Chrome 94+, Edge 94+,
        Safari 16.4+, or Firefox 130+ for the QuickTime picture.
      </div>
    );
  }
  return <canvas ref={canvasRef} className="ft-screen-hd" aria-label="Live iPhone screen over QuickTime USB" />;
}
