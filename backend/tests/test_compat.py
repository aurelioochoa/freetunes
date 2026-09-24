"""Compatibility contract tests (TDD): every iPhone model has its own entry
with correct notch/island hardware, and docs/COMPATIBILITY.md tells the
honest, sourced truth about FOSS library × iOS support.
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "frontend", "src")
PUBLIC = os.path.join(ROOT, "frontend", "public")
DEVICES = os.path.join(SRC, "devices.ts")
DOC = os.path.join(ROOT, "docs", "COMPATIBILITY.md")
README = os.path.join(ROOT, "README.md")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def test_iphone_14_and_15_are_separate_models():
    catalog = _read(DEVICES)
    assert "iphone-14" in catalog, "iPhone 14 (notch+Lightning) needs its own entry"
    assert "iphone-15" in catalog, "iPhone 15 (island+USB-C) needs its own entry"
    art14 = re.search(r"id:\s*'iphone-14'.*?svg:\s*'(/[\w-]+\.(?:svg|png))'", catalog, re.S)
    art15 = re.search(r"id:\s*'iphone-15'.*?svg:\s*'(/[\w-]+\.(?:svg|png))'", catalog, re.S)
    assert art14 and art15 and art14.group(1) != art15.group(1), \
        "14 and 15 must use different art (notch vs Dynamic Island)"
    for art in (art14.group(1), art15.group(1)):
        assert os.path.isfile(os.path.join(PUBLIC, art.lstrip("/"))), \
            f"missing public{art}"


def test_no_combined_14_15_entry():
    catalog = _read(DEVICES)
    assert "15 / 14" not in catalog and "14 / 15" not in catalog, \
        "14 and 15 differ in port and screen cutout — never merge them"


def test_compat_doc_exists_and_linked():
    assert os.path.isfile(DOC), "missing docs/COMPATIBILITY.md"
    assert "docs/COMPATIBILITY.md" in _read(README)


def test_compat_doc_ios_version_rows():
    doc = _read(DOC)
    for row in ("iOS 15", "iOS 16", "iOS 17", "iOS 18", "iOS 26"):
        assert row in doc, f"compat doc must cover {row}"


def test_compat_doc_library_versions():
    doc = _read(DOC).lower()
    assert "1.4.0" in doc, "must name the libimobiledevice release with iOS 17+ support"
    assert "pymobiledevice3" in doc


def test_compat_doc_app_requirements():
    doc = _read(DOC)
    assert "iOS 9" in doc, "VLC needs iOS 9+"
    assert "iOS 15" in doc, "Readest needs iOS 15+"
    assert "iOS 18" in doc, "BookPlayer needs iOS 18+"


def test_compat_doc_operational_caveats():
    doc = _read(DOC).lower()
    assert "passcode" in doc, "iOS 16.1+ demands the passcode before backup"
    assert "unlock" in doc, "device must be unlocked / screen on"
    assert "mock" in doc, "must admit the backend is still mock until P1"


def test_compat_doc_marks_certainty():
    doc = _read(DOC).lower()
    assert "FSFreeBytes" in _read(DOC), "doc must name the trustworthy source"
    assert "verified" in doc or "confirmed" in doc, "must say what is verified"
    assert "untested" in doc or "not yet verified" in doc, \
        "must say what is NOT yet verified on a real device"
