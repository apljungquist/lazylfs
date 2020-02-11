from __future__ import annotations
import logging
import os
import pathlib
from typing import Union, TYPE_CHECKING

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    PathT = Union[str, os.PathLike[str]]


def link(src: PathT, dst: PathT, include: str) -> None:
    """Create links in `dst` to the corresponding file in `src`

    :param src: Directory under which to look for files
    :param dst: Directory under which to create symlinks
    :param include: Glob pattern specifying which files to include
    """
    src = pathlib.Path(src).resolve()
    dst = pathlib.Path(dst).resolve()

    src_tails = {path.relative_to(src) for path in src.glob(include) if path.is_file()}
    dst_tails = {path.relative_to(dst) for path in dst.glob(include) if path.is_file()}

    conflicts = src_tails & dst_tails
    if conflicts:
        _logger.debug("%s paths already exist in the destination", len(conflicts))
        raise FileExistsError("Some paths already exist in the destination")

    dst.mkdir(exist_ok=True)

    new = src_tails - dst_tails
    for tail in sorted(new):
        src_path = src / tail
        dst_path = dst / tail
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        _logger.debug("Linking %s", str(tail))
        dst_path.symlink_to(src_path)


def main():
    import fire  # type: ignore

    logging.basicConfig(level=getattr(logging, os.environ.get("LEVEL", "WARNING")))
    fire.Fire({func.__name__: func for func in [link]})
