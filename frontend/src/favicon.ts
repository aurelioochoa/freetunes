/** Keep the tab icon in sync with the same CSS colors as the app. */
export function syncFavicon(): void {
  const icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!icon) return;
  const colors = getComputedStyle(document.documentElement);
  const accent = colors.getPropertyValue('--accent').trim() || '#0071e3';
  const surface = colors.getPropertyValue('--menu').trim() || '#ffffff';
  const ink = colors.getPropertyValue('--text').trim() || '#1d1d1f';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
    <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop stop-color="${accent}"/><stop offset="1" stop-color="${surface}"/>
    </linearGradient></defs>
    <rect x="2" y="2" width="60" height="60" rx="15" fill="url(#bg)"/>
    <g fill="none" stroke="${ink}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
      <path d="M26 44 V20 l18 -4 v22"/>
      <circle cx="21" cy="44" r="6" fill="${ink}" stroke="none"/>
      <circle cx="39" cy="38" r="6" fill="${ink}" stroke="none"/>
    </g>
  </svg>`;
  icon.href = `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

export function watchSystemFavicon(): () => void {
  const scheme = window.matchMedia('(prefers-color-scheme: dark)');
  syncFavicon();
  scheme.addEventListener('change', syncFavicon);
  return () => scheme.removeEventListener('change', syncFavicon);
}
