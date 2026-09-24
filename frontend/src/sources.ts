export interface Source {
  name: string;
  what: string;
  url: string;
  license: string;
}

/** Open-source building blocks freetunes stands on. Shown in the user guide. */
export const SOURCES: Source[] = [
  {
    name: 'VLC for iOS',
    what: 'Plays the music you sync (File Sharing inbox)',
    url: 'https://github.com/videolan/vlc-ios',
    license: 'GPL-2.0 / MPL-2.0'
  },
  {
    name: 'Readest',
    what: 'Reads the ebooks you sync',
    url: 'https://github.com/readest/readest',
    license: 'AGPL-3.0'
  },
  {
    name: 'BookPlayer',
    what: 'Plays the audiobooks you sync',
    url: 'https://github.com/TortugaPower/BookPlayer',
    license: 'GPL-3.0'
  },
  {
    name: 'libimobiledevice',
    what: 'USB talk + backup/restore engine',
    url: 'https://github.com/libimobiledevice/libimobiledevice',
    license: 'LGPL-2.1'
  },
  {
    name: 'ifuse',
    what: 'Mounts iPhone folders on Linux',
    url: 'https://github.com/libimobiledevice/ifuse',
    license: 'LGPL-2.1'
  },
  {
    name: 'iPhone 4 mock (Justin14)',
    what: 'Header/carousel art for iPhone 4 (front view, screen off)',
    url: 'https://commons.wikimedia.org/wiki/File:IPhone_4_Mock_No_Shadow_PSD.png',
    license: 'CC BY-SA 3.0'
  },
  {
    name: 'iPhone 11 vector (Rafael Fernandez)',
    what: 'Placeholder art for iPhone 11 (notch, dual camera)',
    url: 'https://commons.wikimedia.org/wiki/File:IPhone_11_White.svg',
    license: 'CC BY-SA 4.0'
  },
  {
    name: 'iPhone 11 Pro vector (Rafael Fernandez)',
    what: 'Placeholder art for iPhone 11 Pro (notch, triple camera)',
    url: 'https://commons.wikimedia.org/wiki/File:IPhone_11_Pro_Midnight_Green.svg',
    license: 'CC BY-SA 4.0'
  },
  {
    name: 'iPhone 11 Pro Max vector (Rafael Fernandez)',
    what: 'Placeholder art for iPhone 11 Pro Max (notch, triple camera)',
    url: 'https://commons.wikimedia.org/wiki/File:IPhone_11_Pro_Max_Midnight_Green.svg',
    license: 'CC BY-SA 4.0'
  },
  {
    name: 'iPhone 13 Pro vector (Rafael Fernandez)',
    what: 'Screen-frame artwork for notch iPhones 12–14 (screen cut out)',
    url: 'https://commons.wikimedia.org/wiki/File:IPhone_13_Pro_vector.svg',
    license: 'CC BY-SA 4.0'
  },
  {
    name: 'iPhone 11 vector (Rafael Fernandez)',
    what: 'Screen-frame artwork for iPhone 11 (screen cut out)',
    url: 'https://commons.wikimedia.org/wiki/File:IPhone_11_White.svg',
    license: 'CC BY-SA 4.0'
  },
  {
    name: 'iPhone 8 vector (Rafael Fernandez)',
    what: 'Screen-frame artwork for Home-button iPhones (screen cut out)',
    url: 'https://commons.wikimedia.org/wiki/File:IPhone_8_vector.svg',
    license: 'CC BY-SA 4.0'
  },
  {
    name: 'iPhone 15 vector (Rafael Fernandez)',
    what: 'Screen-frame artwork for Dynamic Island iPhones (screen cut out)',
    url: 'https://commons.wikimedia.org/wiki/File:IPhone_15_Vector.svg',
    license: 'CC BY-SA 4.0'
  },
  {
    name: 'iPhone 16 Pro vector (Rafael Fernandez)',
    what: 'Screen-frame artwork for Pro iPhones (screen cut out)',
    url: 'https://commons.wikimedia.org/wiki/File:IPhone_16_Pro_Vector.svg',
    license: 'CC BY-SA 4.0'
  },
];

/** Set this to the freetunes repo URL once it is pushed to GitHub. */
export const FREETUNES_REPO_URL = '';
