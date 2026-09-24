import type { ReactNode } from 'react';

export type IPhoneContour = 'se' | 'notch' | 'island' | 'pro' | 'iphone11'
  | 'first' | 'x' | 'duo' | 'duo-folded' | 'eighteen';

/** Map the freetunes model catalog id (devices.ts) to a hardware contour. */
export function contourForModel(modelId?: string): IPhoneContour {
  if (modelId === 'iphone-1st' || modelId === 'iphone-4') return 'first';
  if (modelId === 'iphone-x' || modelId === 'iphone-xs' || modelId === 'iphone-xs-max')
    return 'x';
  if (modelId === 'iphone-duo') return 'duo';
  if (modelId === 'iphone-duo-folded') return 'duo-folded';
  if (modelId === 'iphone-18-pro') return 'eighteen';
  if (modelId === 'iphone-se') return 'se';
  if (
    modelId === 'iphone-6' ||
    modelId === 'iphone-6s' ||
    modelId === 'iphone-6s-plus' ||
    modelId === 'iphone-7' ||
    modelId === 'iphone-8' ||
    modelId === 'iphone-8-plus' ||
    modelId === 'iphone-se-2' ||
    modelId === 'iphone-se-3'
  )
    return 'se';
  if (
    modelId === 'iphone-11' ||
    modelId === 'iphone-11-pro' ||
    modelId === 'iphone-11-pro-max' ||
    modelId === 'iphone-xr'
  )
    return 'iphone11';
  if (
    modelId === 'iphone-12-mini' ||
    modelId === 'iphone-12' ||
    modelId === 'iphone-12-pro' ||
    modelId === 'iphone-13' ||
    modelId === 'iphone-13-pro' ||
    modelId === 'iphone-14' ||
    modelId === 'iphone-16e' ||
    modelId === 'iphone-17e' ||
    modelId === 'iphone-se-4'
  )
    return 'notch';
  if (
    modelId === 'iphone-15-pro' ||
    modelId === 'iphone-15-pro-max' ||
    modelId === 'iphone-16-pro' ||
    modelId === 'iphone-16-pro-max' ||
    modelId === 'iphone-17-pro' ||
    modelId === 'iphone-17-pro-max'
  )
    return 'pro';
  return 'island';
}

const CONTOUR_LABEL: Record<IPhoneContour, string> = {
  se: 'iPhone SE contour — Home button and Touch ID',
  notch: 'iPhone notch contour — Face ID notch',
  island: 'iPhone Dynamic Island contour',
  pro: 'iPhone Pro contour — titanium with Camera Control',
  iphone11: 'iPhone 11 contour — wide Face ID notch',
  first: 'Original iPhone contour — small screen, big chin and forehead',
  x: 'iPhone X contour — first Face ID notch, stainless steel',
  duo: 'iPhone Duo contour — foldable, open',
  'duo-folded': 'iPhone Duo contour — folded shut, cover screen',
  eighteen: 'iPhone 18 Pro contour — Dynamic Island',
};

/**
 * Portrait + landscape frame artwork per contour. All contours are
 * Rafael Fernandez CC BY-SA 4.0 vectors (see SOURCES) with the screen cut
 * out so the live mirror shows through pixel-aligned; notch / island stay
 * opaque and draw over the mirror. Landscape frames are the portrait art
 * rotated 90° CCW, so the notch / island sit on the left edge and the side
 * keys run along the top — the same contour, just rotated with the phone.
 */
const CONTOUR_ART: Record<IPhoneContour, { portrait: string; landscape: string }> = {
  se: { portrait: '/iphone-se-frame.png', landscape: '/iphone-se-frame-landscape.png' },
  notch: { portrait: '/iphone-13-frame.png', landscape: '/iphone-13-frame-landscape.png' },
  island: { portrait: '/iphone-island-frame.png', landscape: '/iphone-island-frame-landscape.png' },
  pro: { portrait: '/iphone-pro-frame.png', landscape: '/iphone-pro-frame-landscape.png' },
  iphone11: { portrait: '/iphone-11-frame.png', landscape: '/iphone-11-frame-landscape.png' },
  first: { portrait: '/iphone-first-frame.png', landscape: '/iphone-first-frame-landscape.png' },
  x: { portrait: '/iphone-x-frame.png', landscape: '/iphone-x-frame-landscape.png' },
  duo: { portrait: '/iphone-duo-frame.png', landscape: '/iphone-duo-frame-landscape.png' },
  'duo-folded': { portrait: '/iphone-duo-folded-frame.png', landscape: '/iphone-duo-folded-frame-landscape.png' },
  eighteen: { portrait: '/iphone-eighteen-frame.png', landscape: '/iphone-eighteen-frame-landscape.png' },
};

/** Header mini mockup per contour (full art, screen intact — no live pixels). */
export const CONTOUR_MINI: Record<IPhoneContour, string> = {
  se: '/iphone-se-mini.png',
  notch: '/iphone-notch-mini.png',
  island: '/iphone-island-mini.png',
  pro: '/iphone-pro-mini.png',
  iphone11: '/iphone-11-mini.png',
  first: '/iphone-1st-mini.png',
  x: '/iphone-x-mini.png',
  duo: '/iphone-duo-mini.png',
  'duo-folded': '/iphone-duo-folded-mini.png',
  eighteen: '/iphone-18-pro-mini.png',
};

export type IPhoneOrientation = 'portrait' | 'landscape';

/**
 * iPhone hardware contour. The live mirror (`children`) paints inside
 * `.ft-iphone-screen` so it is clipped by the phone's rounded screen,
 * with the Dynamic Island / notch / Home button drawn over it —
 * exactly where it sits on the real phone being shared.
 * `orientation="landscape"` uses the same contour art rotated horizontal
 * (island / notch on the left edge, keys along the top edge).
 *
 * All frames are Rafael Fernandez's CC BY-SA 4.0 iPhone vectors
 * (see SOURCES), with their screens cut out so the live mirror shows
 * through pixel-aligned.
 */
export default function IPhoneFrame({
  modelId,
  label,
  orientation = 'portrait',
  children,
}: {
  modelId?: string;
  label?: string;
  orientation?: IPhoneOrientation;
  children: ReactNode;
}) {
  const contour = contourForModel(modelId);
  const a11y = label || CONTOUR_LABEL[contour];
  const landscape = orientation === 'landscape';
  const art = landscape ? CONTOUR_ART[contour].landscape : CONTOUR_ART[contour].portrait;
  return (
    <div
      className={`ft-iphone is-${contour} has-art${landscape ? ' is-landscape' : ''}`}
      data-model={modelId ?? 'iphone-15'}
      data-contour={contour}
      data-orientation={orientation}
      role="img"
      aria-label={a11y}
      title={a11y}
    >
      <div className="ft-iphone-screen">
        {children}
        <img className="ft-iphone-art" src={art}
          alt="" aria-hidden="true" draggable={false} />
      </div>
    </div>
  );
}
