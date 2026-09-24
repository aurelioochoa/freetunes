# freetunes developer guide

## Architecture

```
[iPhone USB] <-> [FastAPI daemon :8000, backend/] <-> [Vite+React SPA :5173, frontend/]
```

Browsers cannot speak usbmuxd/AFC, so all USB work lives in the local Python
daemon. The SPA only talks HTTP to it. `FREETUNES_MOCK=1` (default) uses an
in-memory AFC; unset it to hit real devices via `RealAFC`
(`backend/app/services/afc.py`, wired to pymobiledevice3 in P1).

## Commands (`make`)

| Target | What |
|---|---|
| `make setup` | venv + JS deps (approves esbuild build) |
| `make dev` / `dev-backend` / `dev-frontend` | run daemons |
| `make test` | backend pytest (includes UI contract tests) |
| `make build` / `typecheck` | vite build / tsc |
| `make verify` | test + build |
| `make clean` | remove artifacts |

## Contract tests

UI design is guarded by static contract tests in `backend/tests/`:

- `test_design.py` — glassmorphism tokens, iPhone render wiring
- `test_hig.py` — Apple HIG patterns (floating chrome, collapsible sidebar,
  badges, inset selection, focus, empty state)
- `test_polish.py` — themes, animation, model catalog, copy, icons, sources, docs

Rule: **tests first**. Add/adjust the contract, watch it fail, then implement.

## Frontend conventions

- `src/api.ts` mirrors `backend/app/models.py`; `shared/openapi-types.ts` is the
  hand-kept shared copy.
- `src/devices.ts` — iPhone model catalog + theme/accent catalogs.
- `src/sources.ts` — upstream GitHub repos rendered in the footer. Set
  `FREETUNES_REPO_URL` once this repo is pushed.
- Theming: `:root` tokens + `prefers-color-scheme`; explicit overrides via
  `document.documentElement.dataset.theme = light|dark` and
  `dataset.accent`. Choices persist in localStorage.
- Motion: `@keyframes ft-fade-up` / `ft-pop`, always under
  `prefers-reduced-motion: reduce` guard.

## Diagnostics backend (`backend/app/services/diagnostics.py`)

User-facing behavior is documented in [DIAGNOSTICS.md](DIAGNOSTICS.md).
Implementation notes that will bite you:

- `idevicesyslog` (1.4.0) has **no `-n LINES` flag** (`-n` = `--network`):
  run the plain relay and let the timeout stop it. `SubprocessRunner` keeps
  the partial capture on `TimeoutExpired` (success iff stdout non-empty), and
  `syslog()` tails/filters that window.
- `idevicecrashreport` must pass **`-k/--keep`** — without it, reading crash
  reports deletes them off the phone.
- The health gate counts only *actionable* errors (`BENIGN_NOISE_HINTS`
  excludes constant kernel spam like IOSurface `decode: mismatch`).

## Documentation tab (`src/components/DocsView.tsx`)

The Documentation tab is the user guide bundled as a static view (offline,
searchable, never drifts from the UI). Convention: **one section per app
tab**. Adding a tab means adding, in this order:

1. Contract tokens in `backend/tests/test_docs_settings.py`
   (`test_docs_view_covers_every_tab` + search index) — watch them fail.
2. A `SECTIONS` entry (id, title, search blurb, icon) + search `hay` entry +
   card in `DocsView.tsx`, plus a glossary row if you introduced jargon.
3. A matching plain-language section in `docs/USER_GUIDE.md` (the tab claims
   to *be* the guide, so the two must stay in sync).

## Adding a new iPhone model

1. Export a device render to `frontend/public/iphone-<name>.png` (>5 KB, portrait PNG).
2. Append an entry to `DEVICE_MODELS` in `src/devices.ts`.
3. `make verify` — `test_device_art_per_model` covers the wiring.
