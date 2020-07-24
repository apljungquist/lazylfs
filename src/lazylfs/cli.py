from __future__ import annotations

import logging
import os
import pathlib
import sys
from typing import (
    Union,
    TYPE_CHECKING,
    Set,
    Tuple,
    Iterator,
)

from lazylfs import content, location

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    PathT = Union[str, os.PathLike[str], pathlib.Path]


def _collect_paths(includes: Tuple[str, ...]) -> Set[pathlib.Path]:
    if not includes:
        includes = tuple([line.rstrip() for line in sys.stdin.readlines()])

    included: Set[pathlib.Path] = set()
    for top in includes:
        included.update(_find(pathlib.Path(top)))
    return included


def _find(top: pathlib.Path) -> Iterator[pathlib.Path]:
    yield top
    yield from top.rglob("*")


def link(src: PathT, dst: PathT, includes: Tuple[str, ...] = ("**/*",)) -> None:
    """Create links in `dst` to the corresponding files in `src`

    :param src: Directory under which to look for files
    :param dst: Directory under which to create symlinks
    :param includes: List of glob patterns specifying what files to link.
        The default is to include everything.
        Files matched by none of the patterns will not be linked.
    """
    src = pathlib.Path(src).resolve()
    dst = pathlib.Path(dst).resolve()
    location.link(src, dst, includes)


def track(*includes: str,) -> None:
    """Track the checksum of files in the index"""
    content.track(_collect_paths(includes))


NotOkError = content.NotOkError


def check(*includes: str,) -> None:
    """Check the checksum of files against the index

    Exit with non-zero status if a difference is detected or a file could not be
    checked.
    """
    content.check(_collect_paths(includes))


def main():
    import fire  # type: ignore

    logging.basicConfig(level=getattr(logging, os.environ.get("LEVEL", "WARNING")))
    fire.Fire({func.__name__: func for func in [link, track, check]})
