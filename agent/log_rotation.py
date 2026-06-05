r"""Rotating file logging setup for agent components.

Three call sites use this:
  - agent.py     (legacy single-process mode, ~CONFIG_DIR/agent.log)
  - service.py   (Session 0 coordinator, ~CONFIG_DIR/logs/service.log)
  - helper.py    (Session 1+ worker,      ~CONFIG_DIR/logs/helper.log)

Why a shared module
-------------------
Prior to this, each component had its own ad-hoc logging setup
(service.py and helper.py used `logging.basicConfig` which only
writes to stderr; agent.py used a plain `FileHandler` that grew
without bound). The dev scripts (`_rc_start_*.ps1`) had to
manually wire stdout/stderr to files via `Start-Process
-RedirectStandardOutput`, which is fragile:

  - nssm / Task Scheduler drop the redirected output on
    service restart, so log history is lost.
  - stdout / stderr share a file but get interleaved badly.
  - No rotation -> the disk fills up over months.

The new setup writes each component to its own file under
`%APPDATA%\RemoteControlAgent\logs\`, rotated by size. Existing
nssm-visible output (and so `python -m agent --mode=...` in a
terminal works).

Size limits
-----------
Each component gets 5 MB x 3 backups = 20 MB max on disk.
`agent.log` keeps the same shape (1 main + 3 rotated) so old
code/tools that read `agent.log` still find it. service.log and
helper.log get their own pair.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

# Configurable via env if you need bigger logs in dev, but capped
# to avoid filling the disk.
_MAX_BYTES_DEFAULT = int(os.environ.get('RC_LOG_MAX_BYTES', 5 * 1024 * 1024))  # 5 MB
_BACKUPS_DEFAULT = int(os.environ.get('RC_LOG_BACKUPS', 3))  # 5 MB * 4 = 20 MB

# Standard format shared across all three components so a single
# `grep`-style filter works across files.
_FMT = '%(asctime)s [%(name)s %(levelname)s] %(message)s'


def setup_rotating_log(
    name: str,
    log_path: str,
    level: int = logging.INFO,
    max_bytes: int = _MAX_BYTES_DEFAULT,
    backup_count: int = _BACKUPS_DEFAULT,
) -> logging.Logger:
    """Create a logger that writes to both a rotating file and stderr.

    Returns the named logger. Subsequent calls with the same name
    return the same logger (idempotent), so it's safe to call from
    multiple modules.

    File path layout (created on first call):
        <log_path>           <- current
        <log_path>.1         <- previous
        <log_path>.2         <- older
        <log_path>.3         <- oldest (oldest gets deleted on rotate)
    """
    logger = logging.getLogger(name)
    if getattr(logger, '_rc_rotating_initialized', False):
        return logger

    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # File handler: rotate when size exceeds max_bytes. encoding='utf-8'
    # matches the old agent.py setup so existing log viewers don't
    # choke on cp936 / GBK sequences from PyInstaller builds.
    fh = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8',
        mode='a',  # append on startup, don't truncate
    )
    fh.setFormatter(logging.Formatter(_FMT))
    fh.setLevel(level)

    # Stderr handler so dev scripts that capture stdout/stderr still
    # get a copy. Use the existing `basicConfig` root handlers if
    # present (don't double-configure).
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(_FMT))
    sh.setLevel(level)

    logger.setLevel(level)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.propagate = False  # avoid double-logging via root
    logger._rc_rotating_initialized = True  # type: ignore[attr-defined]
    return logger
