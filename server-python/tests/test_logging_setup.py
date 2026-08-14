"""Log configuration.

The app logged to stdout only, which systemd captures into the journal — and the
cPanel user this deploys as isn't in `adm`, `systemd-journal` or `wheel`, so
`journalctl -u rankboard.service` refuses. Every traceback the server produced was
unreadable by the only person who needed it.

Two properties matter more than the rest, and both are about not making things
worse than stdout-only:

  * configuring twice must not duplicate handlers, or `uvicorn --reload` writes
    every line two, three, four times as the module is re-imported
  * an unwritable log directory must not stop the server booting
"""

import logging
from logging.handlers import RotatingFileHandler

import pytest

from app import logging_setup


@pytest.fixture
def clean_root():
    """Bare root logger, restored afterwards.

    conftest and other modules configure logging for the rest of the suite;
    mutating the root logger without putting it back leaks into every later test.
    """
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    root.handlers = []
    try:
        yield root
    finally:
        for h in root.handlers:
            try:
                h.close()
            except Exception:
                pass
        root.handlers, root.level = saved_handlers, saved_level


# Counted by the module's own marker, not by isinstance: pytest attaches its
# capture handler to the root logger and it is a StreamHandler subclass, so an
# isinstance check counts test scaffolding as application output.
def file_handlers(root):
    return [h for h in root.handlers if logging_setup._ours(h, "file")]


def stream_handlers(root):
    return [h for h in root.handlers if logging_setup._ours(h, "stream")]


# ── the file gets written ─────────────────────────────────────────────

def test_it_writes_to_a_file(clean_root, tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    path = logging_setup.configure()
    assert path == tmp_path / "app.log"

    logging.getLogger("demo").info("a message")
    assert "a message" in path.read_text(encoding="utf-8")


def test_a_traceback_reaches_the_file(clean_root, tmp_path, monkeypatch):
    # The whole point. logger.exception in main's unhandled handler has to land
    # somewhere readable, or a 500 is undiagnosable again.
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    path = logging_setup.configure()

    try:
        raise ValueError("the actual cause")
    except ValueError:
        logging.getLogger("demo").exception("Unhandled error on GET /api/projects")

    written = path.read_text(encoding="utf-8")
    assert "Traceback (most recent call last)" in written
    assert "ValueError: the actual cause" in written
    assert "GET /api/projects" in written


def test_the_directory_is_created(clean_root, tmp_path, monkeypatch):
    nested = tmp_path / "does" / "not" / "exist"
    monkeypatch.setenv("LOG_DIR", str(nested))
    assert logging_setup.configure() == nested / "app.log"
    assert nested.is_dir()


def test_stdout_is_kept_as_well(clean_root, tmp_path, monkeypatch):
    # Still the only output a local `uvicorn` run shows, and root's journal
    # capture is useful to whoever has journal access.
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    logging_setup.configure()
    assert len(stream_handlers(clean_root)) == 1
    assert len(file_handlers(clean_root)) == 1


# ── configuring twice ─────────────────────────────────────────────────

def test_configuring_twice_does_not_duplicate_handlers(clean_root, tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    first = logging_setup.configure()
    second = logging_setup.configure()

    assert first == second
    assert len(file_handlers(clean_root)) == 1
    assert len(stream_handlers(clean_root)) == 1


def test_a_line_is_not_written_twice_after_reconfiguring(clean_root, tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    path = logging_setup.configure()
    logging_setup.configure()

    logging.getLogger("demo").info("once please")
    assert path.read_text(encoding="utf-8").count("once please") == 1


# ── failure must not be fatal ─────────────────────────────────────────

def test_an_unwritable_directory_does_not_raise(clean_root, tmp_path, monkeypatch):
    # Refusing to boot because a log directory is read-only would turn a
    # diagnostics problem into an outage.
    blocker = tmp_path / "app-logs"
    blocker.write_text("I am a file, not a directory", encoding="utf-8")
    monkeypatch.setenv("LOG_DIR", str(blocker))

    assert logging_setup.configure() is None
    # stdout still works, so the server is no worse off than before.
    assert len(stream_handlers(clean_root)) == 1
    assert file_handlers(clean_root) == []


def test_rotation_is_bounded(clean_root, tmp_path, monkeypatch):
    # Nothing else prunes this directory, and filling a shared-hosting quota
    # would take the database connections down with it.
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    logging_setup.configure()
    handler = file_handlers(clean_root)[0]
    assert handler.maxBytes == logging_setup.MAX_BYTES > 0
    assert handler.backupCount == logging_setup.BACKUP_COUNT > 0
