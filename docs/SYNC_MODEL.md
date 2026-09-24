# freetunes sync model

## In one sentence

freetunes copies files into third-party apps' File Sharing folders over AFC;
it never writes Apple's own Music/Books databases (that door is locked).

## Preview = pure function

`POST /sync/preview {app_bundle_id, music_dir, mirror_delete}`:

1. Scan local dir (`mutagen` tags for audio; filename titles for books).
2. Hash every file (SHA-256).
3. `list_docs(bundle_id)` → `{filename: sha256}` from the device.
4. Diff (`backend/app/services/sync_plan.py::plan_sync`):
   - remote hash missing → `push` (`new`)
   - hash differs → `push` (`changed`)
   - hash equal → `skip` (`identical`)
   - remote-only + `mirror_delete` → `delete` (`absent locally`)

`POST /sync/run` executes the plan via AFC `push`/`delete` (or dry-run).

## App mapping

| freetunes view | Bundle ID | Content |
|---|---|---|
| Music | `org.videolan.vlc-ios` | mp3/m4a/flac/opus/ogg/wav/aac + m3u |
| Books | `com.readest.readest` | epub/pdf/mobi/azw3/fb2/txt/cbz |
| Audiobooks | `com.tortugapower.BookPlayer` | m4b/mp3, `.zip` becomes a playlist |

Bundle IDs are discovered at runtime (`GET /apps`); the table is the
preferred default only.

## Roadmap

- P1: real AFC via pymobiledevice3, `idevicebackup2` backup UI, auto model
  detection (replaces the manual model picker).
- P2: transcode-on-push (ffmpeg), OPDS/Wi-Fi serving for Readest,
  AudiobookShelf/Jellyfin import for BookPlayer.
