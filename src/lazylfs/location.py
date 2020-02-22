from __future__ import annotations

import logging
import pathlib

from lazylfs import pathutils

_logger = logging.getLogger(__name__)


def link(src: pathlib.Path, dst: pathlib.Path,) -> None:
    if not src.is_dir():
        raise ValueError("Expected src to be a directory")

    src_tails = {
        pathlib.Path(path).relative_to(src)
        for path in src.rglob("*")
        if path.is_file() and not path.is_symlink()
    }

    dst.mkdir(exist_ok=True)

    for tail in sorted(src_tails):
        src_path = src / tail
        dst_path = dst / tail
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        _logger.debug("Linking %s", str(tail))

        if not pathutils.ensure_lnk(dst_path, src_path):
            _logger.debug("Path exists and is equivalent, skipping")
