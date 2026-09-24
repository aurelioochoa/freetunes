# freetunes compatibility list

Honest, sourced, updated 2026-09. Key point up front: **freetunes only uses
the safest FOSS surface — AFC File Sharing + backup — which works on every
iPhone below.** The limits come from iOS versions and library builds, not
from phone models.

**How to read the certainty labels:**

- ✅ **Verified** — confirmed by upstream reports / releases (linked).
- ➖ **Expected** — same code path as a verified neighbor, no contrary report.
- ❌ **Untested** — nobody (including us) has proven it on real hardware yet.

> freetunes' own backend is still **mock** (`FREETUNES_MOCK=1`). End-to-end
> sync on a real device is ❌ **Untested** until P1 lands. Everything below
> describes what the underlying FOSS libraries can do, so the doc stays true.

## 1. FOSS libraries × iOS versions (the part that actually matters)

| iOS | libimobiledevice (distro 1.3.0) | libimobiledevice 1.4.0 / git HEAD | pymobiledevice3 9.x | freetunes mechanism (AFC File Sharing) |
|---|---|---|---|---|
| 12 – 15 | ✅ pair, AFC, backup, info | ✅ | ✅ lockdown USB | ✅ |
| 16 | ✅; ⚠️ **passcode required before backup** (16.1+) | ✅ | ✅ | ✅ |
| 17 | ✅ core (pair, AFC, backup, info, sync) — [issue #1490](https://github.com/libimobiledevice/libimobiledevice/issues/1490); ⚠️ Wi-Fi discovery flaky on some 17.x; dev/debug needs HEAD | ✅ incl. iOS 17+ developer disk mounting | ✅ USB lockdown; dev services via RSD tunnel | ✅ |
| 18 | ➖ USB core; ⚠️ Wi-Fi on Linux needs usbmuxd2/netmuxd; keep screen on during backup ([issue #1601](https://github.com/libimobiledevice/libimobiledevice/issues/1601)) | ✅ USB core | ✅ incl. tunnel backup (user-confirmed on 18.3) | ✅ |
| 26 | ❌ old distro builds (segfaults / symbol errors) | ✅ backup **and** restore user-confirmed on 26.x with a clean git stack ([#1413](https://github.com/libimobiledevice/libimobiledevice/issues/1413), [r/linuxquestions](https://www.reddit.com/r/linuxquestions/comments/1qzaj4n/libimobiledevice_usage_with_ios_26/)) | ➖ same lockdown path as 18 | ✅ |

Notes:

- **1.4.0** (2025-10-10) is the first release with iOS 17+ support and
  `idevicebackup2` fixes ([releases](https://github.com/libimobiledevice/libimobiledevice/releases)).
  Anything older than that on iOS 17+ → build from git.
- **One matching stack or nothing.** Mixing distro packages with git-built
  libs causes `undefined symbol: afc_get_file_info_plist` / segfaults
  ([issue #1699](https://github.com/libimobiledevice/libimobiledevice/issues/1699)).
  Fix: purge all libimobiledevice packages and rebuild the full dependency
  chain (libtatsu → libplist → libusbmuxd → glue → libimobiledevice) from one source.
- **Big libraries time out.** 100 GB+ backups (photos, WhatsApp) can exceed
  the 30 s default receive timeout (`mobilebackup2 (-4)`). Retry, keep the
  screen on, or use a build with the 90 s timeout (PR #1705).
- **TLS backend matters.** If backups fail with SSL errors, rebuild with
  OpenSSL instead of GnuTLS.
- **Storage numbers: trust AFC, not lockdown.** Since iOS 17, lockdown
  `TotalDataAvailable` overshoots what Settings shows (e.g. 107 GB reported
  vs 1.04 GB real on a 128 GB iPhone 13 — upstream
  [issue #1572](https://github.com/libimobiledevice/libimobiledevice/issues/1572)).
  freetunes reads AFC `FSFreeBytes` (matches Settings) and only falls back to
  the lockdown value when AFC is unreachable (locked/asleep phone — AFC hangs
  instead of refusing, so the probe fails fast after 8 s and listings are
  cached 20 s to avoid piling up hung probes).
- **Wi-Fi is a bonus, USB is the truth.** Stock Linux usbmuxd has no Wi-Fi;
  on iOS 18 use usbmuxd2/netmuxd; first-time pairing is always over cable.

## 2. iPhone models (hardware is the easy part)

Any iPhone that runs the target app (section 3) syncs identically — AFC does
not care about chips, ports or camera bumps. Cable note: iPhone 15+ use
USB-C, iPhone 14 and older use Lightning; any data cable works.

| Model | Max iOS | VLC (9+) | Readest (15+) | BookPlayer (18+) |
|---|---|---|---|---|
| SE (2016), 6s, 7 | 15 | ✅ | ✅ (15.0 exactly) | ❌ needs 18 |
| 8, X | 16 | ✅ | ✅ | ❌ needs 18 |
| XR, XS | 18 | ✅ | ✅ | ✅ (18.0 exactly) |
| 11, 12, 13, 14, SE (2020/2022) | 26 | ✅ | ✅ | ✅ |
| 15, 16, 17 | 26 | ✅ | ✅ | ✅ |

freetunes ships real device renders per contour — SE, wide-notch (11 family),
notch (13/12, 14), Dynamic Island (15) and Pro (16 Pro) — as
`frontend/public/iphone-*.png` (Rafael Fernandez CC BY-SA 4.0, catalog in
`frontend/src/devices.ts`). When no iPhone is plugged the header cycles
through them; the picker is cosmetic until P1 auto-detects the real model
over lockdown.

## 3. Target apps (App Store minimums, checked 2026-09)

- **VLC** — Requires **iOS 9** or later. Free, open source
  ([vlc-ios](https://github.com/videolan/vlc-ios), GPL-2.0/MPL-2.0).
- **Readest** — Requires **iOS 15.0** or later. Free, open source
  ([readest](https://github.com/readest/readest), AGPL-3.0).
- **BookPlayer** — Requires **iOS 18.0** or later. Free, open source
  ([BookPlayer](https://github.com/TortugaPower/BookPlayer), GPL-3.0).

Consequence: audiobooks need an iPhone XR/XS or newer; ebooks need iPhone
6s or newer; music works on anything from the last decade.

## 4. Before you press Sync (operational checklist)

1. iPhone **unlocked**, tap **Trust**, enter the device **passcode** (iOS 16.1+).
2. Cable plugged directly into the computer; **screen stays on** during backup.
3. VLC / Readest / BookPlayer installed and opened at least once.
4. `idevicepair pair` succeeds before anything else.
5. On iOS 17+: use libimobiledevice **1.4.0+ or git** (never distro 1.3.0).
6. On iOS 26: clean single-source dependency stack (see pitfalls above).

## 5. What freetunes itself has proven
- ✅ Unit + contract tests, `make verify` green, production build ships.
- ✅ Real-device **detection** verified 2026-09: iPhone 13 (iPhone14,5),
  iOS 26.0.1 over USB — `GET /devices` returns name, iOS, trusted state and
  auto-matches the picker art. Distro libimobiledevice tools + active usbmuxd.
- ❌ **Not yet verified**: real-device preview → push → pull sync (AFC writes
  still go to MockAFC), and target-app presence detection. That is P1's exit
  criteria.
- ⚠️ Known on this exact phone today: none of VLC / Readest / BookPlayer is
  installed (`ApplicationLookupFailed`), so sync has nowhere to deliver yet —
  install one from the App Store first.

## 6. Live screen (3uTools-style realtime view)

| Path | What | Needs | iOS | Status |
|---|---|---|---|---|
| Preview (USB, MJPEG 1–5 fps) | screenshot polling in the browser | `pymobiledevice3` (17+) or `idevicescreenshot` (≤16 + dev image) | 12 – 26 | ✅ Verified on iPhone 13 / iOS 26.0.1 (2026-09-18): 1170×2532 live PNG in ~2 s per shot via `developer dvt screenshot`, after Developer Mode + `mounter auto-mount` |
| QuickTime (USB, Valeria H.264 30–60 fps) | supervised `pymobiledevice3 screen-mirror` (screen-mirror fork, `feature/screen-mirror-browser-viewer` branch) or `qvh gstreamer`, embedded as an iframe — the fast preview | trusted phone, **no Developer Mode**; one-click `POST /screen/valeria/install` or `pip install -U "git+https://github.com/renegadelink/pymobiledevice3.git@feature/screen-mirror-browser-viewer" aiohttp av` ([fork discussion](https://github.com/doronz88/pymobiledevice3/discussions/1668)) or [quicktime_video_hack](https://github.com/danielpaulus/quicktime_video_hack). **On Linux also**: the usbmuxd fork — one command: `make setup-valeria-linux` (or `POST /screen/valeria/usbmux-setup`, or the button in the QuickTime tab); distro usbmuxd fails every start as `no QT-capable config` | 9 – 26 | ➖ Expected, ❌ Untested here — implemented as `GET /screen/valeria`, `POST /screen/valeria/start|stop|install|usbmux-setup` (port 8081); fails honest when the fork is missing or usbmuxd wins the USB claim |
| HD (USB, HEVC full rate) | supervised `pymobiledevice3 developer core-device display serve-web`, embedded as an iframe | Developer Mode on, trusted, `pip install pymobiledevice3`; iOS 17.4+ needs no root ([tunnel guide](https://doronz88.github.io/pymobiledevice3/guides/ios17-tunnels/), [CLI recipes](https://doronz88.github.io/pymobiledevice3/guides/cli-recipes/)) | **27+ only** | ❌ Refused on iPhone 13 / iOS 26.0.1 (2026-09-18): the viewer page serves, but the phone answers `CoreDeviceError 9021 — Remote control requires iOS 27.0 or later`, and `display get-media-support-info` reports `supportedFeatures: 0`. freetunes now checks that first and says so instead of starting a server that never paints ([same gate in go-ios](https://github.com/danielpaulus/go-ios/pull/849)) |
| AirPlay (Wi-Fi, video + audio) | managed `uxplay` receiver, Control Center → Screen Mirroring → freetunes | **two host prerequisites**: the `uxplay` binary *and* a running `avahi-daemon` (mDNS is how the phone finds it), same Wi-Fi ([UxPlay](https://github.com/FDH2/UxPlay)) | 9 – 26 (Legacy Protocol; iOS 17 confirmed) | ➖ Expected, ❌ Untested here — no `uxplay` on this host (AUR-only on Arch) and `avahi-daemon` disabled |

### Developer Mode is only needed for Preview + HD

Preview and HD need **both** below; QuickTime (USB) and AirPlay need
neither — any trusted phone works, which is why QuickTime is the fast
preview on iOS 26 and below.

### The two things iOS demands first

Nothing above can produce a pixel until **both** are true on the phone,
and the Screen tab plus the device page now drive both from the host
(`POST /screen/setup/…`):

1. **Developer Mode on.** On a phone that never met a developer tool the
   row is not even in Settings → Privacy & Security; `amfi
   reveal-developer-mode` puts it there, `amfi enable-developer-mode`
   turns it on (the phone restarts).
2. **The developer image mounted.** iOS 17+ uses a *personalized* image
   fetched per boot, so it is gone after every restart —
   `mounter auto-mount` refetches it. `/screen/status` reports this as
   `ddi: mounted | missing | unknown`; with it missing the mode stays
   `setup` instead of claiming to be live.

The no-root userspace RSD tunnel (pmd3 ≥ 11 on Linux, iOS 17.4+) comes up
by itself — on iOS 26.0.1 no `sudo remote tunneld` was needed.

AirPlay note: the install hint is derived from `/etc/os-release`, because
a Debian command on an Arch box is worse than none — uxplay is not in
Arch's official repositories at all, only the AUR. freetunes also checks
`avahi-daemon` before starting the receiver: without mDNS, uxplay runs
happily and never appears in Screen Mirroring, which is indistinguishable
from "AirPlay is broken". uxplay's own stdout/stderr is kept (it used to
go to `DEVNULL`) and surfaced as the failure reason.

HD note: on iOS 26 and below, QuickTime (USB), Preview (USB) and AirPlay
(Wi-Fi) are the live paths — the HD tab now says that up front and leaves
**Start HD** disabled instead of failing after a 25 s wait. Earlier builds could
never start HD on *any* iOS: they passed `--udid` to `serve-web`, which
pmd3 v11 rejects outright ("No such option"), so the server aborted at
launch. Both that flag and the port flag are now gated on the CLI's own
`--help` text (same gating for Valeria's `screen-mirror`).

Capture-path note: `developer dvt screenshot` is tried first because it
is the one verified here *and* the only one that accepts `--udid`; pmd3
v11's `developer core-device screen-capture screenshot` rejects that flag
("No such option") and picks the first USB device, so freetunes only
falls back to it when a single phone is attached.

Why not just `idevicescreenshot` everywhere: on iOS 17+ the
`com.apple.mobile.screenshotr` service is gone from the old lockdown path
([issue #1465](https://github.com/libimobiledevice/libimobiledevice/issues/1465))
— developer services moved behind an RSD tunnel, which is exactly what
pymobiledevice3 speaks. The Screen tab's checklist tells the user which of
the four rows above applies to their phone.

## 7. Live screen alternatives (researched 2026-09)

Every screenshot path (screenshotr, DVT, CoreDevice `screencaptureservice`,
Xcode screenshot instrument) needs **Developer Mode on** (+ a mounted
developer image for DVT). Even JaviSoto's Device Hub reference app
([device-hub-ios](https://github.com/JaviSoto/device-hub-ios), live HEVC +
remote control over the same `idevice` stack) requires it. Paths that
dodge Developer Mode entirely:

- **QuickTime-USB (Valeria), no Developer Mode, 30–60 fps H.264** — now
  implemented as the **QuickTime (USB)** tab (`GET /screen/valeria`,
  `POST /screen/valeria/start|stop|install`, port 8081): the same protocol
  QuickTime Player uses; any trusted phone works. On Linux via
  [quicktime_video_hack](https://github.com/danielpaulus/quicktime_video_hack)
  (`qvh gstreamer`) or the unmerged
  [pmd3 screen-mirror fork](https://github.com/doronz88/pymobiledevice3/discussions/1668)
  (`feature/screen-mirror-browser-viewer` branch). Caveats: on Linux the
  capture path needs the usbmuxd fork's `dynamic-config-switch` branch with
  `USBMUXD_DEFAULT_DEVICE_MODE=2`
  ([setup guide](https://github.com/renegadelink/pymobiledevice3/blob/feature/screen-mirror-browser-viewer/docs/guides/valeria-linux-setup.md))
  — distro usbmuxd cannot drive the QuickTime alt-config. Apple puts the
  phone in presentation mode (fake 9:41 clock, notifications hidden), and
  practitioners report it as flaky for long sessions.
- **ReplayKit Broadcast Upload Extension** — a tiny custom iOS app whose
  extension encodes the screen (720p practical, 50 MB extension memory cap)
  and ships it over usbmuxd TCP to the desktop (see LensLink's OBS plugin
  PR for the pattern). The only officially supported reliable method, but
  needs Xcode + Apple signing (free Apple ID sideloading works, extension
  provisioning is the snag) and the user starts the broadcast from Control
  Center every time.
- **`idevice_mirror`** ([jkcoxson/idevice_mirror](https://github.com/jkcoxson/idevice_mirror))
  — Xcode screenshot-instrument streaming, cross-platform, but ~1 fps over
  USB and an 18-star 3-commit project. Not worth it over Developer Mode +
  DVT for stills.
- **AirPlay via uxplay** — already managed from the Screen tab; needs the
  same Wi-Fi on both ends, no phone changes at all.
