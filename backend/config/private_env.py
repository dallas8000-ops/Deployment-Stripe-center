"""Load local-only env files from repo-root private_env/ (never committed to git)."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_private_env(repo_root: Path) -> list[str]:
    """
    Load every *.env file in private_env/ into os.environ.
    Later files do not override variables already set (override=False).
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return []

    private_dir = repo_root / "private_env"
    if not private_dir.is_dir():
        return []

    loaded: list[str] = []
    for path in sorted(private_dir.glob("*.env")):
        if path.is_file():
            load_dotenv(path, override=False)
            loaded.append(path.name)
            logger.debug("Loaded private env file %s", path)

    if loaded:
        logger.info("Loaded %d private env file(s) from %s", len(loaded), private_dir)
    return loaded
