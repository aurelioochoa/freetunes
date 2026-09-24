# Gates: Media metadata details

OWNS: backend/app/services/media_metadata.py, backend/app/routers/files.py, backend/tests/test_media_metadata.py, frontend/src/api.ts, frontend/src/components/MediaViews.tsx, frontend/src/apple.css, GATES.md

Scope: Extract available original image/video metadata on demand and display dates, location, camera/media properties and all extracted fields in the shared inspector, with honest unavailable states.

- [x] G1: Image/video extraction preserves embedded metadata and excludes temporary host file facts; endpoint validates paths and cleans pulled files.
  CHECK: backend/.venv/bin/python -m pytest -q backend/tests/test_media_metadata.py backend/tests/test_file_content.py
  EXPECT: /\d+ passed(?:, \d+ warnings?)? in/
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/aurelio/Repos/freetunes; path=0cf1d8d1e9cd/26 entries; EXPECT=matched; output-sha256=c13753e279fb3d663f05a28d3d0ec9e84b083f786674ddad4ea0da45eca93d3d; output-bytes=992

- [x] G2: The frontend metadata integration typechecks and builds.
  CHECK: npm run build --prefix frontend
  EXPECT: built in
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/aurelio/Repos/freetunes; path=0cf1d8d1e9cd/26 entries; EXPECT=matched; output-sha256=6e958fd9ab4a19822136a610290a67468791b1990e6a8a51d6c78cf132b1f32e; output-bytes=418
