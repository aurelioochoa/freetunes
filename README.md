# freetunes — FOSS web iTunes clone (Finder + Music UI)

Web-based manager for iPhone media via File Sharing apps:
Music → VLC, Books → Readest, Audiobooks → BookPlayer. Backup via `idevicebackup2` (P1).

## Layout
- `backend/` FastAPI daemon on `http://127.0.0.1:8000` (USB/AFC lives here; browsers can't do usbmuxd)
- `frontend/` Vite + React Finder-style UI on `http://127.0.0.1:5173`
- `shared/openapi-types.ts` shared API shapes
- `scripts/dev.sh` dev runner

## Quickstart
```bash
make setup       # first time only
make dev         # backend :8000 + UI :5173, both live-reload on save
# open http://127.0.0.1:5173, set library path, Preview -> Sync
```

New here? Read **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** — plain-language
walkthrough with a jargon glossary. Contributing? See
**[docs/DEVELOPER.md](docs/DEVELOPER.md)** and **[docs/SYNC_MODEL.md](docs/SYNC_MODEL.md)**.
Will it work with your iPhone/iOS? See
**[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md)** — the honest,
sourced support list.

## Sources

Built on open source: [VLC for iOS](https://github.com/videolan/vlc-ios),
[Readest](https://github.com/readest/readest),
[BookPlayer](https://github.com/TortugaPower/BookPlayer),
[libimobiledevice](https://github.com/libimobiledevice/libimobiledevice),
[ifuse](https://github.com/libimobiledevice/ifuse). Full list in the app footer.

## API
- `GET /health`, `GET /devices`, `GET /apps`, `GET /apps/{bundle}/files`
- `GET /library/music?path=…`, `GET /library/books?path=…`
- `POST /sync/preview`, `POST /sync/run` `{app_bundle_id, music_dir, mirror_delete, dry_run}`
- `GET /backup/{udid}`, `POST /backup/{udid}`, `GET /backup/{udid}/files`, `POST /backup/{udid}/encryption`, `POST /backup/{udid}/restore` (idevicebackup2; mock-safe stub when tool missing)
- `GET /files/browse?udid=&path=/`, `GET /photos?udid=`, `GET /photos/duplicates?udid=`, `DELETE /photos?udid=&path=/DCIM/….JPG`, `GET /storage/breakdown?udid=`
- `GET /diagnostics/verification|crashes|syslog?udid=` (logs & crash reports — see [docs/DIAGNOSTICS.md](docs/DIAGNOSTICS.md))
- `POST /tools/tags`, `GET /tools/duplicates?path=`, `POST /tools/ringtone|convert|compress-photo|heic-to-jpg`
- `GET /firmware/signed?product=iPhone14,5`, `POST /flash/dry-run` (signed-only, never flashes)
- `GET /screen/status|shot|stream`, `POST /screen/hd/start|stop`, `GET /screen/valeria`, `POST /screen/valeria/start|stop|install|usbmux-setup`, `POST /screen/airplay/start|stop` (3uTools-style realtime screen: HD HEVC over USB via pymobiledevice3, QuickTime-USB Valeria H.264 30–60 fps with no Developer Mode, MJPEG preview fallback, managed uxplay AirPlay; Linux USB setup via `make setup-valeria-linux`)
- `POST /screen/setup/reveal-developer-mode|enable-developer-mode|mount-ddi` (the iOS 17–26 prerequisites, driven from the Screen tab and the device page)

## Tests
```bash
cd backend && .venv/bin/python -m pytest -q
cd ../frontend && pnpm install && pnpm build
```

## Roadmap
P0 scaffold ✅ → P1 real device layer (pymobiledevice3 AFC + idevicebackup2) → P2 music polish → P3 books OPDS → P4 audiobook chapters → P5 backup UI.
