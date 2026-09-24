"""AFC abstraction: Mock (tests/dev) + pymobiledevice3 adapter stub (real device).

Web browsers cannot speak usbmuxd/AFC, so all USB work lives here in the
local Python daemon. Frontend only talks HTTP/WS to this layer.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field


@dataclass
class RemoteFile:
    filename: str
    size: int = 0
    sha256: str = ""


class AFCInterface:
    def list_apps(self) -> list[dict]:
        raise NotImplementedError

    def list_docs(self, bundle_id: str) -> list[RemoteFile]:
        raise NotImplementedError

    def push(self, bundle_id: str, local_path: str, filename: str) -> None:
        raise NotImplementedError

    def pull(self, bundle_id: str, filename: str, dest_path: str) -> None:
        raise NotImplementedError

    def delete(self, bundle_id: str, filename: str) -> None:
        raise NotImplementedError


# Well-known File Sharing targets. Bundle IDs are resolved at runtime via
# list_apps(); these are preferred defaults only.
PREFERRED_APPS = {
    "music": ["org.videolan.vlc-ios"],
    "books": ["com.readest.readest"],
    "audiobooks": ["com.tortugapower.BookPlayer"],
}


class MockAFC(AFCInterface):
    """In-memory AFC used for dev/tests without a device."""

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, bytes]] = {
            "org.videolan.vlc-ios": {},
            "com.readest.readest": {},
            "com.tortugapower.BookPlayer": {},
        }

    def list_apps(self) -> list[dict]:
        names = {
            "org.videolan.vlc-ios": "VLC",
            "com.readest.readest": "Readest",
            "com.tortugapower.BookPlayer": "BookPlayer",
        }
        return [
            {"bundle_id": bid, "name": names[bid], "file_sharing": True}
            for bid in self.docs
        ]

    def list_docs(self, bundle_id: str) -> list[RemoteFile]:
        out = []
        for name, data in self.docs.get(bundle_id, {}).items():
            out.append(
                RemoteFile(
                    filename=name,
                    size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            )
        return out

    def push(self, bundle_id: str, local_path: str, filename: str) -> None:
        with open(local_path, "rb") as f:
            self.docs.setdefault(bundle_id, {})[filename] = f.read()

    def pull(self, bundle_id: str, filename: str, dest_path: str) -> None:
        data = self.docs.get(bundle_id, {}).get(filename)
        if data is None:
            raise FileNotFoundError(filename)
        with open(dest_path, "wb") as f:
            f.write(data)

    def delete(self, bundle_id: str, filename: str) -> None:
        self.docs.get(bundle_id, {}).pop(filename, None)


class RealAFC(AFCInterface):
    """Real-device adapter backed by pymobiledevice3 / idevice tools.

    Kept as an explicit stub so imports never fail in CI without a device.
    Wire `pymobiledevice3` AFC client here in P1 (device layer).
    """

    def __init__(self, udid: str | None = None) -> None:
        self.udid = udid

    def _missing(self) -> RuntimeError:
        return RuntimeError(
            "No device connected or pymobiledevice3 not wired yet. "
            "Use MockAFC for dev/tests; connect + trust a device for real sync."
        )

    def list_apps(self) -> list[dict]:
        raise self._missing()

    def list_docs(self, bundle_id: str) -> list[RemoteFile]:
        raise self._missing()

    def push(self, bundle_id: str, local_path: str, filename: str) -> None:
        raise self._missing()

    def pull(self, bundle_id: str, filename: str, dest_path: str) -> None:
        raise self._missing()

    def delete(self, bundle_id: str, filename: str) -> None:
        raise self._missing()


# Process-wide mock singleton so API tests + dev server share state.
_mock = MockAFC()


def get_afc(use_mock: bool = True, udid: str | None = None) -> AFCInterface:
    if use_mock or os.environ.get("FREETUNES_MOCK", "1") == "1":
        return _mock
    return RealAFC(udid=udid)


def reset_mock() -> MockAFC:
    global _mock
    _mock = MockAFC()
    return _mock
