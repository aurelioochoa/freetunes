"""Dev-server logging: timestamped output with polling noise turned down.

The SPA polls ``GET /devices`` + ``GET /apps`` every 5s (``App.tsx``) and
``GET /screen/status`` every 10s (``ScreenView.tsx``), so a stock uvicorn
access log is a wall of ``200 OK`` that buries real errors. This module:

- configures a ``HH:MM:SS [LEVEL] name: message`` format once,
  with ANSI level colors on a terminal (off when piped, unless
  ``FORCE_COLOR``; ``NO_COLOR`` always wins),
- installs a filter on the ``uvicorn.access`` logger that drops *successful*
  polling hits to DEBUG (failures and every other route still log),
- honors ``FREETUNES_LOG_LEVEL`` (``debug|info|warning|error``).

Idempotent: safe to call on import and again under ``--reload``.
"""
from __future__ import annotations

import logging
import os
import sys

#: Polled on a timer by the UI; 2xx hits here are routine, not news.
#: The syslog SSE stream is long-lived by design — its access line is noise.
POLLING_PATH_PREFIXES = ("/health", "/devices", "/apps", "/screen/status",
                         "/diagnostics/syslog/stream")

_configured = False


def _coerce_level(raw: str | None) -> int:
    return getattr(logging, (raw or "info").upper(), logging.INFO)


#: ANSI colors per level; reset after the level token. Kept minimal so
#: piped/test output stays readable even if color leaks through.
_LEVEL_COLORS = {
    "DEBUG": "\x1b[36m",    # cyan: routine, fades into the background
    "INFO": "\x1b[32m",     # green: the happy path
    "WARNING": "\x1b[33m",  # yellow: look here
    "ERROR": "\x1b[31m",    # red: broken
    "CRITICAL": "\x1b[1;31m",  # bold red: very broken
}
_RESET = "\x1b[0m"
_DIM = "\x1b[2m"


def _use_color(stream=None) -> bool:
    """True when ANSI colors should be emitted.

    ``NO_COLOR`` always disables; ``FORCE_COLOR`` enables even when piped
    (``scripts/dev.sh`` sets it so colors survive the prefix pipe).
    Otherwise color follows the TTY, matching the Makefile's COLOR logic.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    try:
        return (stream if stream is not None else sys.stderr).isatty()
    except Exception:
        return False


class ColoredFormatter(logging.Formatter):
    """Level-colored ``HH:MM:SS [LEVEL] name: message`` formatter."""

    def __init__(self, use_color: bool | None = None, **kwargs):
        super().__init__(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
            **kwargs,
        )
        self.use_color = _use_color() if use_color is None else use_color

    def format(self, record: logging.LogRecord) -> str:
        if not self.use_color:
            return super().format(record)
        color = _LEVEL_COLORS.get(record.levelname, "")
        if not color:
            return super().format(record)
        saved = record.levelname
        try:
            # Dim the timestamp; color just the level token. Errors and
            # warnings also tint the message so failures stand out in a
            # scrolling dev-server terminal; info/debug stay plain.
            record.levelname = f"{color}{saved}{_RESET}"
            out = super().format(record)
            out = out.replace(record.asctime,
                              f"{_DIM}{record.asctime}{_RESET}", 1)
            if record.levelno >= logging.ERROR:
                out = f"{color}{out}{_RESET}"
            elif record.levelno >= logging.WARNING:
                # Only tint the message half, keeping the prefix readable.
                head, sep, tail = out.partition(f"{record.name}: ")
                if sep:
                    out = f"{head}{sep}{color}{tail}{_RESET}"
            return out
        finally:
            record.levelname = saved


class PollingQuietFilter(logging.Filter):
    """Drop successful polling access records; keep everything else.

    Uvicorn access records look like ``'127.0.0.1 - "GET /devices HTTP/1.1"
    200'`` with ``record.args = (client, method, path, version, status)``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            args = record.args
            if not isinstance(args, tuple) or len(args) < 5:
                return True
            _client, _method, path, _version, status = args[:5]
            if not isinstance(path, str) or not isinstance(status, int):
                return True
            if status < 200 or status >= 300:
                return True
            # Strip query strings before matching (e.g. /screen/status?udid=).
            route = path.split("?", 1)[0]
            return not route.startswith(POLLING_PATH_PREFIXES)
        except Exception:
            return True


def setup_logging(level: str | None = None) -> logging.Logger:
    """Configure root logging once; return the ``freetunes`` logger."""
    global _configured
    resolved = _coerce_level(level or os.environ.get("FREETUNES_LOG_LEVEL", "info"))
    if not _configured:
        handler = logging.StreamHandler()
        handler.setFormatter(ColoredFormatter())
        root = logging.getLogger()
        root.setLevel(resolved)
        # Avoid duplicate handlers across --reload worker re-imports.
        if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
            root.addHandler(handler)
        else:
            root.handlers[0].setFormatter(handler.formatter)
        access = logging.getLogger("uvicorn.access")
        if not any(isinstance(f, PollingQuietFilter) for f in access.filters):
            access.addFilter(PollingQuietFilter())
        _configured = True
    else:
        logging.getLogger().setLevel(resolved)
    return logging.getLogger("freetunes")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"freetunes.{name}" if not name.startswith("freetunes") else name)
