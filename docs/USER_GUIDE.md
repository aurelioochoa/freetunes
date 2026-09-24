# freetunes user guide

freetunes copies your music, ebooks and audiobooks from your computer to your
iPhone — without iTunes and without an Apple account. It is a website that
runs on your own computer; nothing is uploaded anywhere.

## What you need

1. An iPhone and its USB cable.
2. One free app on the iPhone, depending on what you want to copy:
   - **Music** → [VLC](https://github.com/videolan/vlc-ios) (free, open source)
   - **Ebooks** → [Readest](https://github.com/readest/readest) (free, open source)
   - **Audiobooks** → [BookPlayer](https://github.com/TortugaPower/BookPlayer) (free, open source)
3. freetunes running on your computer (see below).

Why these apps? Apple does not let other programs write into its own Music
and Books apps. But Apple does let programs hand files to other apps — that
open door is what freetunes uses.

## Start it (3 steps)

```bash
make setup     # first time only: installs everything
make dev       # start freetunes
```

Then open **http://127.0.0.1:5173** in your browser.

## Copy files (the normal flow)

1. Plug in your iPhone, unlock it, tap **Trust** on the phone screen.
2. Pick your iPhone model at the top (just changes the picture).
3. On the left, choose **Music**, **Books** or **Audiobooks**.
4. Type (or paste) the folder on your computer that holds the files.
5. Press **Preview**. Green rows (“Copy to iPhone”) are what would be copied.
   Grey rows (“Already on iPhone”) are skipped automatically.
6. Press **Sync**. Done — open VLC / Readest / BookPlayer on the phone.

Tip: use the search box to find one file in a long list. Click a row to
highlight it.

## Your iPhone at a glance (Device tab)

The top banner always states what is true right now: backend stopped, no
iPhone detected, phone not trusted, or connected with its iOS version. Below
it are the specs, the storage bar (used vs total) and the battery state.
The iPhone model picker only changes the artwork — the app auto-matches
your real phone until you pick one manually.

## Back up the whole iPhone (Backup tab)

The only undo button there is — back up before anything destructive.

1. Unlock the phone, tap **Trust**, enter the device passcode, keep the
   screen on with the cable plugged directly into the computer.
2. Run a **Full** backup first; later runs can be **Incremental** (only what
   changed).
3. Turn on **encryption** to include passwords and health data — without it
   those are skipped, and you need the password to restore.
4. Press **Verify** after big backups. **Restore** writes a backup back to
   the phone; **Delete** removes it from this computer.

## Files & photos

- **Files tab** — browse the iPhone's shared folders over the cable, like a
  Finder window.
- **Photos tab** — your camera roll (DCIM). **Export** downloads to this
  computer; deleting frees phone space. Import is best-effort.
- **Duplicates** groups byte-identical photos so you can keep one copy.

## Watch your iPhone screen live (like 3uTools)

Open the **Screen** tab on the left. It is view-only — you can watch and
take screenshots, but taps still happen on the phone itself.

- **Preview (USB)** — works everywhere once the phone is trusted. A still
  image refreshing 1–5 times per second. Press **📷 Screenshot** to save
  exactly what the phone shows.
- **QuickTime (USB)** — the fast preview: 30–60 fps H.264 over USB via the
  `screen-mirror` fork (`feature/screen-mirror-browser-viewer` branch) or
  `qvh gstreamer`, same protocol QuickTime Player uses. Any trusted iPhone,
  **no Developer Mode**. Press **Install dependencies** once (or run the
  shown pip command), then Start. On Linux the capture path also needs the
  usbmuxd fork (`dynamic-config-switch`, `USBMUXD_DEFAULT_DEVICE_MODE=2`).
  While streaming the phone shows a fake 9:41 clock with notifications
  hidden. If it fails to claim USB, check udev rules, stop competing
  usbmuxd clients, replug, and retry.
- **HD (USB)** — full-rate video with sound, but **only on iOS 27 or
  newer**: Apple refuses the screen-mirroring service on older iPhones
  ("Remote control requires iOS 27.0 or later"). On iOS 26 and below the
  tab says so and the button stays greyed out — use QuickTime, Preview or AirPlay.
- **AirPlay (Wi-Fi)** — best wireless quality with sound, and on iOS 26 the only
  full-rate option with audio. It needs two things on *this computer*, which the tab
  lists with the exact command for your distribution:
  1. the **uxplay** receiver (on Arch it lives in the AUR: `yay -S uxplay`;
     on Debian/Ubuntu: `sudo apt install uxplay`);
  2. a running **avahi-daemon** (`sudo systemctl enable --now avahi-daemon`)
     — this is the mDNS service your iPhone uses to *find* the receiver;
     without it uxplay runs but never shows up in Screen Mirroring.

  Then, with both devices on the same Wi-Fi: Control Center → Screen
  Mirroring → **freetunes**.

If the tab says OFFLINE, follow its checklist — it names the exact missing
piece (cable, Trust, Developer Mode, or the install command).

### The two buttons that do the iPhone setup for you

Modern iOS (17 and up, including iOS 26) hides screen capture behind two
switches. Both have buttons — in the **Screen** tab's checklist and on the
**Device** page — so you do not have to hunt for them:

- **Show Developer Mode on iPhone** — on a phone that has never been used
  with developer tools, the *Developer Mode* row is not in Settings at all.
  This puts it there (Settings → Privacy & Security → Developer Mode).
  Nothing else on the phone changes. Then turn it on yourself; the phone
  restarts and asks you to confirm.
- **Turn on Developer Mode (restarts iPhone)** — does the same from the
  computer. It **restarts your iPhone**, so it asks twice before acting.
- **Mount developer image** — iOS forgets this piece on every restart, so
  if the screen worked yesterday and is OFFLINE today, this is usually the
  one button you need. It downloads once and takes a few seconds.

The device page also shows the current state: *Developer Mode: On ·
developer image mounted*, with a **SCREEN READY** badge when both are done.

## Check your iPhone's health (Diagnostics)

Open the **Diagnostics** tab on the left. It reads three things from your
iPhone over the cable — nothing is changed or uploaded:

- **Verification** — is the model number retail-new, refurbished, or a
  service replacement, plus whether the serial is readable.
- **Crash reports** — every crash file (`.ips`) stored on the phone, newest
  first. Empty ("None found") is a healthy sign.
 - **Device log** — a live tail of what iOS is doing right now. Use the
   search box (try an app name like `SpringBoard`) and the All / Warnings+ /
   Errors / Info buttons to narrow it down. Hover any button for what it
   keeps; hover a red/amber badge to see which word (`timeout`, `thermal`,
   `denied`…) colored that line; open “How is each line classified?” for the
   full keyword guide (click a keyword to search it). **Copy** or
   **Download .log** saves what you see to this computer.

The headline at the top says **Healthy**, **Needs a look**, or **Waiting
for iPhone**. "Needs a look" just means something is worth opening — often
a few repeated log errors from one noisy app. Details for nerds:
[docs/DIAGNOSTICS.md](DIAGNOSTICS.md).

## Toolbox, firmware

- **Toolbox** — small jobs on files from your computer or the iPhone:
  duplicate finder, audio tags, ringtone maker (max 40 seconds), format
  conversion, photo compression, HEIC → JPG, and the Developer Mode helper.
  Audio/photo tools need `ffmpeg` / Pillow on this computer; leaving the
  destination empty downloads the result instead of saving it.
- **Firmware** — lists only iOS versions Apple still signs, always dry-runs
  first, and never flashes without you confirming twice.

## Appearance

In the **Settings** tab (left sidebar, under General) you can switch **Theme**
(Automatic follows your computer; Light and Dark force one) and the **Accent
color**. Your choice is remembered on this computer.

The **Documentation** tab next to it holds this same guide, built into the
app so it works offline.

## Safety notes

- **Preview never changes anything.** Sync only adds files; it never deletes
  from your iPhone unless you explicitly turn on mirror mode.
- Only copy files you own or that are freely licensed.
- Encrypted Apple purchases (DRM) will not play in VLC/Readest/BookPlayer.

## Glossary (jargon, translated)

- **bundle / bundle ID** — Apple's internal name for an app, e.g.
  `org.videolan.vlc-ios` means “the VLC app”. You never need to type these;
  freetunes finds them automatically.
- **AFC (Apple File Connection)** — the USB cable “language” freetunes speaks
  to exchange files with an app's folder on the iPhone.
- **usbmuxd** — a small helper program on your computer that lets many programs
  share one iPhone USB connection. Installed automatically with freetunes'
  dependencies.
- **SHA-256 hash** — a fingerprint of a file's contents. freetunes compares
  fingerprints to know “already there” vs “new or changed” without guessing
  from file names or dates.
- **mirror mode** — optional: also delete from the iPhone files you deleted on
  the computer. Off by default.
- **DRM** — copy protection. Protected store purchases only play in Apple's
  own apps.
- **OPDS** — a way for ebook apps to download books from your computer over
  Wi-Fi instead of cable (planned, see SYNC_MODEL.md).
- **syslog / device log** — the running commentary iOS writes about
  everything it does. The Diagnostics tab shows a live tail of it.
- **crash report (.ips)** — a file iOS writes when an app blows up. Listed
  newest-first in Diagnostics; an empty list is a healthy sign.
- **backup (idevicebackup2)** — a full copy of your iPhone on this computer
  (Backup tab). Encrypt it to include passwords and health data.
- **Developer Mode** — an iPhone switch (Settings → Privacy & Security) that
  unlocks screen capture and deep diagnostics. freetunes can reveal and
  enable it from the Screen tab; enabling restarts the phone.
- **signed firmware (IPSW)** — an iOS install file Apple still approves.
  The Firmware tab lists signed versions only and always dry-runs first.
