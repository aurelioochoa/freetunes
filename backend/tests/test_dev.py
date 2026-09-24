"""Dev-loop contract tests: `make dev` must live-reload on file changes
and talk to the real iPhone by default (mock only when asked)."""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAKEFILE = os.path.join(ROOT, "Makefile")
DEV_SH = os.path.join(ROOT, "scripts", "dev.sh")
REQUIREMENTS = os.path.join(ROOT, "backend", "requirements.txt")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _uvicorn_line(text: str) -> str:
    return next(
        l for l in text.splitlines()
        if "uvicorn" in l and "app.main:app" in l
    )


def _make_target_recipe(text: str, target: str) -> str:
    # Recipe lines belong to the target named before them: collect the
    # indented block under `target:` up to the next non-indented line.
    # Needed because the standard Makefile also has a prod `run` target
    # whose uvicorn line must NOT carry --reload.
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(target + ":"))
    out = []
    for l in lines[start + 1:]:
        if l != "" and not l[0].isspace():
            break
        out.append(l)
    return "\n".join(out)


def _make_dev_backend_line(text: str) -> str:
    return next(
        l for l in _make_target_recipe(text, "dev-backend").splitlines()
        if "uvicorn" in l and "app.main:app" in l
    )


def test_makefile_dev_backend_live_reloads():
    line = _make_dev_backend_line(_read(MAKEFILE))
    assert "--reload" in line, "make dev-backend must run uvicorn with --reload"


def test_dev_sh_backend_live_reloads():
    line = _uvicorn_line(_read(DEV_SH))
    assert "--reload" in line, "scripts/dev.sh backend must run uvicorn with --reload"


def test_reload_dependency_present():
    reqs = _read(REQUIREMENTS)
    assert "uvicorn[standard]" in reqs, \
        "uvicorn[standard] ships watchfiles, which --reload needs"


def test_makefile_dev_backend_defaults_to_real_device():
    line = _make_dev_backend_line(_read(MAKEFILE))
    assert "FREETUNES_MOCK=1 " not in line, \
        "make dev must NOT force mock mode or a plugged iPhone stays invisible"


def test_dev_sh_backend_defaults_to_real_device():
    line = _uvicorn_line(_read(DEV_SH))
    assert "FREETUNES_MOCK=1 " not in line, \
        "scripts/dev.sh must NOT force mock mode or a plugged iPhone stays invisible"


def _access_record(path: str, status: int):
    import logging
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s %s" %d',
        ("127.0.0.1", "GET", path, "HTTP/1.1", status), None,
    )


def test_logging_setup_quietens_polling_successes():
    from app.logging_setup import PollingQuietFilter
    f = PollingQuietFilter()
    # The UI polls these every few seconds: 200s must not bury real logs.
    assert f.filter(_access_record("/health", 200)) is False
    assert f.filter(_access_record("/devices", 200)) is False
    assert f.filter(_access_record("/apps", 200)) is False
    assert f.filter(_access_record("/screen/status?udid=x", 200)) is False
    # Failures and real routes always stay visible.
    assert f.filter(_access_record("/devices", 500)) is True
    assert f.filter(_access_record("/sync/preview", 200)) is True


def test_main_wires_request_logging():
    src = _read(os.path.join(ROOT, "backend", "app", "main.py"))
    assert "setup_logging" in src, "main must configure logging on import"
    assert '@app.middleware("http")' in src, \
        "main must log requests with duration via HTTP middleware"
    assert "backend up" in src, "main must log the dev-server startup banner"


def test_dev_sh_tags_and_log_level():
    src = _read(DEV_SH)
    assert "--log-level" in _uvicorn_line(src), \
        "dev backend must forward FREETUNES_LOG_LEVEL to uvicorn"
    assert "backend" in src and "frontend" in src and "prefix" in src, \
        "dev.sh must tag each line so backend/frontend logs stay attributable"
    assert "trap" in src and "cleanup" in src, \
        "dev.sh must kill the sibling daemon on Ctrl-C instead of orphaning it"


def test_makefile_dev_backend_log_level():
    line = _make_dev_backend_line(_read(MAKEFILE))
    assert "--log-level" in line, \
        "make dev-backend must forward FREETUNES_LOG_LEVEL to uvicorn"
    assert "--reload" in line, "log flags must not drop --reload"


def test_logging_formatter_colors_levels():
    import logging
    from app.logging_setup import ColoredFormatter
    rec = logging.LogRecord(
        "freetunes.api", logging.ERROR, __file__, 1, "boom", (), None)
    out = ColoredFormatter(use_color=True).format(rec)
    assert "ERROR" in out and "\x1b[31mERROR\x1b[0m" in out, \
        "errors must stand out in red on a terminal"
    assert rec.levelname == "ERROR", "formatting must not mutate the record"
    plain = ColoredFormatter(use_color=False).format(rec)
    assert "\x1b[" not in plain, "piped/file output must stay plain"


def test_logging_color_env_overrides(monkeypatch):
    import io
    from app.logging_setup import _use_color

    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert _use_color(Tty()) is True
    assert _use_color(io.StringIO()) is False
    monkeypatch.setenv("NO_COLOR", "1")
    assert _use_color(Tty()) is False, "NO_COLOR must always win"
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert _use_color(io.StringIO()) is True, \
        "FORCE_COLOR keeps colors through the dev.sh prefix pipes"


def test_dev_sh_colors_tags():
    src = _read(DEV_SH)
    assert "NO_COLOR" in src and "FORCE_COLOR" in src, \
        "dev.sh must follow NO_COLOR/FORCE_COLOR like the Makefile"
    assert "033[" in src, "dev.sh must define ANSI colors for the tags"
    assert "C_BACKEND" in src and "C_FRONTEND" in src, \
        "backend/frontend tags must differ in color so scans stay instant"


def test_requirements_keep_the_quicktime_fork_installable():
    # The screen-mirror fork installs as pymobiledevice3 0.1.devN (no tags)
    # and needs construct-typing<0.8. A version floor on pymobiledevice3
    # made `make setup` swap the fork for stock PyPI (QuickTime tab gone);
    # pinning construct-typing<0.8 here made the file unresolvable, since
    # stock pymobiledevice3 11.x requires >=0.8. The fork's own installer
    # (VALERIA_INSTALL_PACKAGES) owns that pin.
    reqs = [line.split("#")[0].strip() for line in _read(REQUIREMENTS).splitlines()]
    pmd3 = [r for r in reqs if r.startswith("pymobiledevice3")]
    assert pmd3 == ["pymobiledevice3"], f"no version constraint allowed: {pmd3}"
    assert not any(r.startswith("construct-typing") for r in reqs)
