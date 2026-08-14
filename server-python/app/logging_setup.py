"""Logging that the person running the server can actually read.

The app configured a root logger writing to stdout, which systemd captures into
the journal. On this deployment that made every diagnostic unreachable: the cPanel
user isn't in `adm`, `systemd-journal` or `wheel`, so `journalctl -u
rankboard.service` answers "No journal files were opened due to insufficient
permissions." Diagnosing a 500 meant hand-writing a script to reproduce the
failing query.

So: a rotating file alongside stdout. stdout stays because it's what a local
`uvicorn` run shows, and because systemd's own capture is still useful to whoever
does have root.

    tail -50 ~/rankboard/logs/app.log
    grep -A 30 Traceback ~/rankboard/logs/app.log | tail -40
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

#: 5 MB × 5 files, so the log can't quietly consume a shared-hosting disk quota.
#: Rotation matters more than usual here: nothing else prunes this directory, and
#: filling the disk would take the database connections down with it.
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5

FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

#: Marker attribute set on handlers this module installs.
#:
#: Detection used to be `isinstance(h, StreamHandler)`, which is wrong in both
#: directions: RotatingFileHandler *is* a StreamHandler, and so is anything else
#: that attaches to the root logger — pytest's capture handler, for one. So a
#: foreign handler made configure() believe it had already added stdout and skip
#: it, and re-running under `uvicorn --reload` could then double up. An explicit
#: mark means we only ever count our own.
_MARK = "_rankboard_handler"


def _ours(handler, kind: str) -> bool:
    return getattr(handler, _MARK, None) == kind


def _mark(handler, kind: str):
    setattr(handler, _MARK, kind)
    return handler


def log_dir() -> Path:
    """Where to write. Override with LOG_DIR.

    Defaults to `logs/` beside the application package rather than somewhere in
    /var: the deploy target is shared hosting where the app owns its own tree and
    nothing else.
    """
    override = os.environ.get("LOG_DIR", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "logs"


def configure(level: int = logging.INFO) -> Path | None:
    """Attach the handlers. Returns the log file path, or None if unavailable.

    Called once from main, before anything else logs. Idempotent — a second call
    is a no-op rather than a second set of handlers, because under
    `uvicorn --reload` the module is re-imported and duplicate handlers would
    write every line twice.
    """
    root = logging.getLogger()
    root.setLevel(level)

    if not any(_ours(h, "stream") for h in root.handlers):
        stream = _mark(logging.StreamHandler(), "stream")
        stream.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(stream)

    existing = next((h for h in root.handlers if _ours(h, "file")), None)
    if existing is not None:
        return Path(existing.baseFilename)

    directory = log_dir()
    try:
        # exist_ok covers the directory; it does not cover the path already being
        # a *file*, which raises FileExistsError — an OSError, so the handler
        # below catches it and the server still starts.
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "app.log"
        handler = _mark(
            RotatingFileHandler(
                path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
            ),
            "file",
        )
        handler.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(handler)
    except OSError as exc:
        # A read-only or unwritable directory must not stop the server booting.
        # Losing the file log is a diagnostics problem; refusing to start over it
        # would be an outage, and stdout still works.
        root.warning("File logging unavailable (%s) — logging to stdout only.", exc)
        return None

    root.info("Logging to %s (max %d bytes x %d)", path, MAX_BYTES, BACKUP_COUNT)
    return path
