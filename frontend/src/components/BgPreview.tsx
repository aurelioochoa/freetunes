import type { BackgroundName } from '../devices';
import MatrixRain from './MatrixRain';
import RainWindow from './RainWindow';

/**
 * Live miniature of a wallpaper, rendered inside its Settings tile.
 * Canvas wallpapers (Matrix, Rain) run the real thing auto-sized to
 * the tile; the rest use the same keyframes as the full-size
 * background. Returns null for Static.
 */
export default function BgPreview({ id }: { id: BackgroundName }) {
  if (id === 'static') return null;
  if (id === 'matrix') {
    return (
      <span className="ft-prev" data-prev="matrix" aria-hidden="true">
        <MatrixRain />
      </span>
    );
  }
  if (id === 'rain') {
    return (
      <span className="ft-prev" data-prev="rain" aria-hidden="true">
        <RainWindow />
      </span>
    );
  }
  return (
    <span className="ft-prev" data-prev={id} aria-hidden="true">
      <i /><i /><i />
    </span>
  );
}
