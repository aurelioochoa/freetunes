export interface DeviceModel {
  id: string;
  name: string;
  screen: string;
  unlock: string;
  svg: string;
  blurb: string;
}

/** Supported iPhone models. Header art is the real Rafael Fernandez
 *  CC BY-SA 4.0 device render per model (iPhone 17e art by Pncke, same
 *  license — see SOURCES); P1 selects the entry automatically once the
 *  real model arrives over usbmuxd/lockdownd.
 *  Names are the canonical marketing name for the art; blurbs note sharing. */
export const DEVICE_MODELS: DeviceModel[] = [
  {
    id: 'iphone-1st',
    name: 'iPhone (1st Gen)',
    screen: '3.5″ LCD',
    unlock: 'Home button',
    svg: '/iphone-1st-mini.png',
    blurb: 'The original 2007 iPhone. 30-pin dock, no App Store yet.'
  },
  {
    id: 'iphone-4',
    name: 'iPhone 4',
    screen: '3.5″ LCD · Retina',
    unlock: 'Home button',
    svg: '/iphone-4-mini.png',
    blurb: 'The 2010 glass-and-steel redesign. First Retina display, front camera.'
  },
  {
    id: 'iphone-6',
    name: 'iPhone 6',
    screen: '4.7″ LCD',
    unlock: 'Home button · Touch ID',
    svg: '/iphone-6-mini.png',
    blurb: 'The rounded 4.7″ one. iPhone 6 Plus shares this contour, bigger.'
  },
  {
    id: 'iphone-6s',
    name: 'iPhone 6s',
    screen: '4.7″ LCD · 3D Touch',
    unlock: 'Home button · Touch ID',
    svg: '/iphone-6s-mini.png',
    blurb: 'Same shell as the 6, second-gen Touch ID inside.'
  },
  {
    id: 'iphone-6s-plus',
    name: 'iPhone 6s Plus',
    screen: '5.5″ LCD · 3D Touch',
    unlock: 'Home button · Touch ID',
    svg: '/iphone-6s-plus-mini.png',
    blurb: 'The big 6s with optical image stabilization.'
  },
  {
    id: 'iphone-7',
    name: 'iPhone 7',
    screen: '4.7″ LCD',
    unlock: 'Home button · Touch ID',
    svg: '/iphone-7-mini.png',
    blurb: 'Solid-state Home button, first water resistance. 7 Plus shares this contour.'
  },
  {
    id: 'iphone-8',
    name: 'iPhone 8',
    screen: '4.7″ LCD · True Tone',
    unlock: 'Home button · Touch ID',
    svg: '/iphone-8-mini.png',
    blurb: 'Glass back, wireless charging. Last of the small Home-button line.'
  },
  {
    id: 'iphone-8-plus',
    name: 'iPhone 8 Plus',
    screen: '5.5″ LCD · True Tone',
    unlock: 'Home button · Touch ID',
    svg: '/iphone-8-plus-mini.png',
    blurb: 'The big 8 with dual camera and Portrait mode.'
  },
  {
    id: 'iphone-se',
    name: 'iPhone SE',
    screen: '4.7″ LCD',
    unlock: 'Home button · Touch ID',
    svg: '/iphone-se-mini.png',
    blurb: 'The small one with a Home button. Same sync steps as every iPhone.'
  },
  {
    id: 'iphone-se-2',
    name: 'iPhone SE (2nd gen)',
    screen: '4.7″ LCD',
    unlock: 'Home button · Touch ID',
    svg: '/iphone-se-2-mini.png',
    blurb: '2020 SE: iPhone 8 body with iPhone 11 chip.'
  },
  {
    id: 'iphone-se-3',
    name: 'iPhone SE (3rd gen)',
    screen: '4.7″ LCD',
    unlock: 'Home button · Touch ID',
    svg: '/iphone-se-3-mini.png',
    blurb: '2022 SE: same body again, first SE with 5G.'
  },
  {
    id: 'iphone-se-4',
    name: 'iPhone SE (4th gen)',
    screen: '6.1″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-se-4-mini.png',
    blurb: 'The SE goes edge-to-edge: notch, no more Home button.'
  },
  {
    id: 'iphone-x',
    name: 'iPhone X',
    screen: '5.8″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-x-mini.png',
    blurb: 'The 2017 redesign: first notch, first Face ID, stainless steel.'
  },
  {
    id: 'iphone-xs',
    name: 'iPhone XS',
    screen: '5.8″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-xs-mini.png',
    blurb: 'Faster Face ID in the same X shell.'
  },
  {
    id: 'iphone-xs-max',
    name: 'iPhone XS Max',
    screen: '6.5″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-xs-max-mini.png',
    blurb: 'The big XS — biggest screen of its year.'
  },
  {
    id: 'iphone-xr',
    name: 'iPhone XR',
    screen: '6.1″ LCD',
    unlock: 'Face ID · notch',
    svg: '/iphone-xr-mini.png',
    blurb: 'The colorful LCD one with a single camera.'
  },
  {
    id: 'iphone-11',
    name: 'iPhone 11',
    screen: '6.1″ LCD',
    unlock: 'Face ID · notch',
    svg: '/iphone-11.png',
    blurb: 'Notch, Lightning port. Dual camera.'
  },
  {
    id: 'iphone-11-pro',
    name: 'iPhone 11 Pro',
    screen: '5.8″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-11-pro.png',
    blurb: 'Notch, Lightning port. Triple camera, stainless steel.'
  },
  {
    id: 'iphone-11-pro-max',
    name: 'iPhone 11 Pro Max',
    screen: '6.5″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-11-pro-max.png',
    blurb: 'The big 11 with triple camera and stainless steel.'
  },
  {
    id: 'iphone-12-mini',
    name: 'iPhone 12 mini',
    screen: '5.4″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-12mini.png',
    blurb: 'The tiny flat-edge one. Full 12 in a small body.'
  },
  {
    id: 'iphone-12',
    name: 'iPhone 12',
    screen: '6.1″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-12-mini.png',
    blurb: 'Flat edges return, OLED for the base model, MagSafe.'
  },
  {
    id: 'iphone-12-pro',
    name: 'iPhone 12 Pro',
    screen: '6.1″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-12-pro-mini.png',
    blurb: 'Notch, Lightning port. Triple camera plus LiDAR. 12 Pro Max shares this contour.'
  },
  {
    id: 'iphone-13',
    name: 'iPhone 13',
    screen: '6.1″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-13-mini.png',
    blurb: 'Notch, Lightning port. Diagonal cameras, bigger battery.'
  },
  {
    id: 'iphone-13-pro',
    name: 'iPhone 13 Pro',
    screen: '6.1″ OLED · 120 Hz',
    unlock: 'Face ID · notch',
    svg: '/iphone-13-pro-mini.png',
    blurb: 'ProMotion screen, triple camera. 13 Pro Max shares this contour.'
  },
  {
    id: 'iphone-14',
    name: 'iPhone 14',
    screen: '6.1″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-14-mini.png',
    blurb: 'Notch screen, Lightning port. The safe middle of the lineup. 14 Plus shares this contour.'
  },
  {
    id: 'iphone-14-pro',
    name: 'iPhone 14 Pro',
    screen: '6.1″ OLED · 120 Hz',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-14-pro-mini.png',
    blurb: 'First Dynamic Island, always-on screen. 14 Pro Max shares this contour.'
  },
  {
    id: 'iphone-15',
    name: 'iPhone 15',
    screen: '6.1″ / 6.7″ OLED',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-island-mini.png',
    blurb: 'Dynamic Island, USB-C port. First iPhone without Lightning.'
  },
  {
    id: 'iphone-15-plus',
    name: 'iPhone 15 Plus',
    screen: '6.7″ OLED',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-15-plus-mini.png',
    blurb: 'The big 15 with Dynamic Island and USB-C.'
  },
  {
    id: 'iphone-15-pro',
    name: 'iPhone 15 Pro',
    screen: '6.1″ OLED · 120 Hz',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-15-pro-mini.png',
    blurb: 'Titanium, Action button, USB-C. First Pro without Lightning.'
  },
  {
    id: 'iphone-15-pro-max',
    name: 'iPhone 15 Pro Max',
    screen: '6.7″ OLED · 120 Hz',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-15-pro-max-mini.png',
    blurb: 'The big titanium one with 5× tetraprism zoom.'
  },
  {
    id: 'iphone-16e',
    name: 'iPhone 16e',
    screen: '6.1″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-16e-mini.png',
    blurb: 'The budget 16: single camera, notch instead of Island, Apple modem.'
  },
  {
    id: 'iphone-16',
    name: 'iPhone 16',
    screen: '6.1″ OLED',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-16-mini.png',
    blurb: 'Dynamic Island, Camera Control button, Apple Intelligence.'
  },
  {
    id: 'iphone-16-plus',
    name: 'iPhone 16 Plus',
    screen: '6.7″ OLED',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-16-plus-mini.png',
    blurb: 'The big 16 with Camera Control.'
  },
  {
    id: 'iphone-16-pro',
    name: 'iPhone 16 Pro / Max',
    screen: '6.3″ / 6.9″ OLED',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-pro-mini.png',
    blurb: 'The big titanium one with extra camera lenses.'
  },
  {
    id: 'iphone-16-pro-max',
    name: 'iPhone 16 Pro Max',
    screen: '6.9″ OLED · 120 Hz',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-16-pro-max-mini.png',
    blurb: 'The biggest iPhone of the 16 line, titanium.'
  },
  {
    id: 'iphone-air',
    name: 'iPhone Air',
    screen: '6.5″ OLED · 120 Hz',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-air-mini.png',
    blurb: 'The thinnest iPhone ever, titanium. eSIM only, single camera.'
  },
  {
    id: 'iphone-17',
    name: 'iPhone 17',
    screen: '6.3″ OLED · 120 Hz',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-17-mini.png',
    blurb: '120 Hz for the base model at last, upgraded selfie camera.'
  },
  {
    id: 'iphone-17e',
    name: 'iPhone 17e',
    screen: '6.1″ OLED',
    unlock: 'Face ID · notch',
    svg: '/iphone-17e-mini.png',
    blurb: 'The budget 17 keeps the notch and a single camera.'
  },
  {
    id: 'iphone-17-pro',
    name: 'iPhone 17 Pro',
    screen: '6.3″ OLED · 120 Hz',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-17-pro-mini.png',
    blurb: 'Aluminum unibody with full-width camera plateau, A19 Pro.'
  },
  {
    id: 'iphone-17-pro-max',
    name: 'iPhone 17 Pro Max',
    screen: '6.9″ OLED · 120 Hz',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-17-pro-max-mini.png',
    blurb: 'The biggest 17 with the camera plateau and best battery.'
  },
  {
    id: 'iphone-duo',
    name: 'iPhone Duo',
    screen: 'Foldable OLED · open',
    unlock: 'Touch ID · side button',
    svg: '/iphone-duo-mini.png',
    blurb: "Apple's first foldable, open like a book. Cover screen when folded."
  },
  {
    id: 'iphone-duo-folded',
    name: 'iPhone Duo (folded)',
    screen: 'Cover OLED · folded',
    unlock: 'Touch ID · side button',
    svg: '/iphone-duo-folded-mini.png',
    blurb: 'Duo folded shut: phone-sized cover screen on the outside.'
  },
  {
    id: 'iphone-18-pro',
    name: 'iPhone 18 Pro',
    screen: '6.3″ / 6.9″ OLED · 120 Hz',
    unlock: 'Face ID · Dynamic Island',
    svg: '/iphone-18-pro-mini.png',
    blurb: 'The newest Pro with Dynamic Island. 18 Pro Max shares this contour.'
  }
];

export type ThemeName = 'system' | 'light' | 'dark' | 'midnight' | 'paper' | 'forest' | 'ocean' | 'sunset' | 'lavender';
export type AccentName = 'blue' | 'purple' | 'green' | 'orange' | 'pink' | 'red' | 'yellow' | 'mint' | 'cyan';

export const THEMES: { id: ThemeName; label: string }[] = [
  { id: 'system', label: 'Automatic (follows system)' },
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
  { id: 'midnight', label: 'Midnight' },
  { id: 'paper', label: 'Paper' },
  { id: 'forest', label: 'Forest' },
  { id: 'ocean', label: 'Ocean' },
  { id: 'sunset', label: 'Sunset' },
  { id: 'lavender', label: 'Lavender' }
];

export const ACCENTS: { id: AccentName; label: string }[] = [
  { id: 'blue', label: 'Blue' },
  { id: 'purple', label: 'Purple' },
  { id: 'green', label: 'Green' },
  { id: 'orange', label: 'Orange' },
  { id: 'pink', label: 'Pink' },
  { id: 'red', label: 'Red' },
  { id: 'yellow', label: 'Yellow' },
  { id: 'mint', label: 'Mint' },
  { id: 'cyan', label: 'Cyan' }
];

export type BackgroundName = 'aurora' | 'orbs' | 'mesh' | 'static' | 'matrix' | 'starfield' | 'waves' | 'dusk' | 'confetti' | 'rain';

export const BACKGROUNDS: { id: BackgroundName; label: string; blurb: string }[] = [
  { id: 'aurora', label: 'Aurora', blurb: 'Slow northern-lights drift. Calm default.' },
  { id: 'orbs', label: 'Orbs', blurb: 'Three floating color orbs over the base tint.' },
  { id: 'mesh', label: 'Mesh', blurb: 'Shifting gradient mesh. Most colorful.' },
  { id: 'matrix', label: 'Matrix', blurb: 'Falling glyph rain. Green phosphor.' },
  { id: 'starfield', label: 'Starfield', blurb: 'Slow star drift and twinkle. Best in dark.' },
  { id: 'waves', label: 'Waves', blurb: 'Two translucent tides sliding past each other.' },
  { id: 'dusk', label: 'Dusk', blurb: 'Warm ember-to-violet shift. Slower than Mesh.' },
  { id: 'confetti', label: 'Confetti', blurb: 'Gentle falling paper. For celebratory moods.' },
  { id: 'rain', label: 'Rain', blurb: 'Rainy window. Droplets racing down the glass.' },
  { id: 'static', label: 'Static', blurb: 'No animation. Best for battery + focus.' }
];

export type GlassName = 'clear' | 'balanced' | 'tinted';

export const GLASSES: { id: GlassName; label: string; blurb: string }[] = [
  { id: 'clear', label: 'Ultra clear', blurb: 'Most see-through. Content shines through.' },
  { id: 'balanced', label: 'Balanced', blurb: 'Apple default. Legible over anything.' },
  { id: 'tinted', label: 'Fully tinted', blurb: 'Almost opaque. Maximum readability.' }
];

export type DensityName = 'comfortable' | 'compact';

export const DENSITIES: { id: DensityName; label: string }[] = [
  { id: 'comfortable', label: 'Comfortable' },
  { id: 'compact', label: 'Compact' }
];

/**
 * Apple ProductType (e.g. `iPhone14,5`) -> marketing name.
 * Apple's internal numbers do NOT match the box name:
 * the whole iPhone 13 family is `iPhone14,x`, the 14 family is
 * `iPhone15,x`, and so on. So `iPhone14,5` IS a regular iPhone 13.
 */
export const PRODUCT_FRIENDLY: Record<string, string> = {
  'iPhone3,1': 'iPhone 4',
  'iPhone3,2': 'iPhone 4',
  'iPhone3,3': 'iPhone 4',
  'iPhone4,1': 'iPhone 4S',
  'iPhone7,2': 'iPhone 6',
  'iPhone8,1': 'iPhone 6s',
  'iPhone8,2': 'iPhone 6s Plus',
  'iPhone8,4': 'iPhone SE (1st gen)',
  'iPhone9,1': 'iPhone 7',
  'iPhone9,3': 'iPhone 7',
  'iPhone9,2': 'iPhone 7 Plus',
  'iPhone9,4': 'iPhone 7 Plus',
  'iPhone10,1': 'iPhone 8',
  'iPhone10,4': 'iPhone 8',
  'iPhone10,2': 'iPhone 8 Plus',
  'iPhone10,5': 'iPhone 8 Plus',
  'iPhone10,3': 'iPhone X',
  'iPhone10,6': 'iPhone X',
  'iPhone11,2': 'iPhone XS',
  'iPhone11,4': 'iPhone XS Max',
  'iPhone11,6': 'iPhone XS Max',
  'iPhone11,8': 'iPhone XR',
  'iPhone12,1': 'iPhone 11',
  'iPhone12,3': 'iPhone 11 Pro',
  'iPhone12,5': 'iPhone 11 Pro Max',
  'iPhone12,8': 'iPhone SE (2nd gen)',
  'iPhone13,1': 'iPhone 12 mini',
  'iPhone13,2': 'iPhone 12',
  'iPhone13,3': 'iPhone 12 Pro',
  'iPhone13,4': 'iPhone 12 Pro Max',
  'iPhone14,2': 'iPhone 13 Pro',
  'iPhone14,3': 'iPhone 13 Pro Max',
  'iPhone14,4': 'iPhone 13 mini',
  'iPhone14,5': 'iPhone 13',
  'iPhone14,6': 'iPhone SE (3rd gen)',
  'iPhone14,7': 'iPhone 14',
  'iPhone14,8': 'iPhone 14 Plus',
  'iPhone15,2': 'iPhone 14 Pro',
  'iPhone15,3': 'iPhone 14 Pro Max',
  'iPhone15,4': 'iPhone 15',
  'iPhone15,5': 'iPhone 15 Plus',
  'iPhone16,1': 'iPhone 15 Pro',
  'iPhone16,2': 'iPhone 15 Pro Max',
  'iPhone17,1': 'iPhone 16 Pro',
  'iPhone17,2': 'iPhone 16 Pro Max',
  'iPhone17,3': 'iPhone 16',
  'iPhone17,4': 'iPhone 16 Plus',
  'iPhone17,5': 'iPhone 16e',
};

export function friendlyProductName(productType: string): string {
  if (!productType) return '';
  return PRODUCT_FRIENDLY[productType] ?? '';
}

/** `iPhone 13 · iPhone14,5` — friendly first, technical id kept for firmware lookups. */
export function describeProduct(productType: string): string {
  if (!productType) return '';
  const friendly = friendlyProductName(productType);
  return friendly ? `${friendly} · ${productType}` : productType;
}
