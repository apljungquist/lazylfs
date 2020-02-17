from __future__ import annotations

import enum
import hashlib
import logging
import os
import pathlib
import sys
from typing import (
    Union,
    TYPE_CHECKING,
    Dict,
    Set,
    Tuple,
    Iterator,
)

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    PathT = Union[str, os.PathLike[str], pathlib.Path]


class ConflictResolution(enum.Enum):
    THEIRS = "theirs"
    OURS = "ours"
    PANIC = "panic"


_INDEX_NAME = ".shasum"


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with path.resolve().open("rb", buffering=0) as f:
        for n in iter(lambda: f.readinto(mv), 0):  # type: ignore
            h.update(mv[:n])
    return h.hexdigest()


def _read_shasum_index(path: pathlib.Path) -> Dict[str, str]:
    split_lines = (line.split() for line in path.read_text().splitlines())
    return {line[-1]: line[0] for line in split_lines}


def _write_shasum_index(path: pathlib.Path, index: Dict[str, str]) -> None:
    path.write_text("".join(sorted(f"{v}  {k}\n" for k, v in index.items())))


def _update_shasum_index(link_path: pathlib.Path) -> None:
    if not _should_be_indexed(link_path):
        return

    if _is_indexed(link_path):
        if _matches_indexed(link_path):
            return
        else:
            raise PermissionError("Refusing cowardly to overwrite information")

    index_path = link_path.parent / _INDEX_NAME
    try:
        index = _read_shasum_index(index_path)
    except FileNotFoundError:
        index = {}

    index[link_path.name] = _sha256(link_path)
    _write_shasum_index(index_path, index)


def _check_link(link_path: pathlib.Path) -> bool:
    _logger.debug("Checking link %s", str(link_path))
    if _should_be_indexed(link_path):
        if _is_indexed(link_path):
            if _matches_indexed(link_path):
                return True
            else:
                _logger.debug("NOK because link does not match index")
                return False
        else:
            _logger.debug("NOK because link is not indexed")
            return False
    else:
        if _is_indexed(link_path):
            _logger.debug("NOK because should not be indexed")
            return False
        else:
            return True


def _should_be_indexed(link_path: pathlib.Path) -> bool:
    return link_path.is_symlink() and link_path.is_file()


def _is_indexed(link_path: pathlib.Path) -> bool:
    index_path = link_path.parent / _INDEX_NAME

    try:
        index = _read_shasum_index(index_path)
    except FileNotFoundError:
        return False
    return link_path.name in index


def _matches_indexed(link_path: pathlib.Path) -> bool:
    index_path = link_path.parent / _INDEX_NAME

    index = _read_shasum_index(index_path)
    expected = index[link_path.name]
    actual = _sha256(link_path)
    return actual == expected


def _check_index(index_path: pathlib.Path) -> bool:
    _logger.debug("Checking index %s", str(index_path))
    ok = True

    try:
        index = _read_shasum_index(index_path)
    except FileNotFoundError:
        index = {}

    for name, expected in index.items():
        link_path = index_path.parent / name
        try:
            actual = _sha256(link_path)
        except FileNotFoundError:
            _logger.info("NOK because link does not exist: %s", link_path.name)
            ok = False
            continue

        if actual != expected:
            _logger.info("NOK because link does not match: %s", link_path.name)
            ok = False

    for link_path in sorted(index_path.parent.iterdir()):
        if _should_be_indexed(link_path) and link_path.name not in index:
            _logger.info("NOK because link is not indexed")
            ok = False

    return ok


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


def link(
    src: PathT,
    dst: PathT,
    on_conflict: Union[str, ConflictResolution] = ConflictResolution.PANIC,
) -> None:
    """Create links in `dst` to the corresponding files in `src`

    :param src: Directory under which to look for files
    :param dst: Directory under which to create symlinks
    """
    on_conflict = ConflictResolution(on_conflict)
    if on_conflict is not ConflictResolution.PANIC:
        raise NotImplementedError("Only on_conflict=panic is implemented")

    src = pathlib.Path(src).resolve()
    dst = pathlib.Path(dst).resolve()

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

        if dst_path.is_symlink() and os.readlink(dst_path) == os.fspath(src_path):
            _logger.debug("Path exists and is equivalent, skipping")
            continue

        if dst_path.is_symlink() or dst_path.exists():
            raise FileExistsError

        dst_path.symlink_to(src_path)


def track(
    *includes: str,
    on_conflict: Union[str, ConflictResolution] = ConflictResolution.PANIC,
) -> None:
    """Track the checksum of files in the index"""
    on_conflict = ConflictResolution(on_conflict)
    if on_conflict is not ConflictResolution.PANIC:
        raise NotImplementedError("Only on_conflict=panic is implemented")

    _track(_collect_paths(includes))


def _track(paths: Set[pathlib.Path]) -> None:
    for path in paths:
        _update_shasum_index(path)


class NotOkError(Exception):
    pass


def check(
    *includes: str,
    on_conflict: Union[str, ConflictResolution] = ConflictResolution.PANIC,
) -> None:
    """Check the checksum of files against the index

    Exit with non-zero status if a difference is detected or a file could not be
    checked.
    """
    on_conflict = ConflictResolution(on_conflict)
    if on_conflict is not ConflictResolution.PANIC:
        raise NotImplementedError("Only on_conflict=panic is implemented")

    _check(_collect_paths(includes))


def _check(paths: Set[pathlib.Path]) -> None:
    ok = True

    for path in paths:
        if path.name == _INDEX_NAME:
            ok &= _check_index(path)
        else:
            ok &= _check_link(path)

    if not ok:
        raise NotOkError


def main():
    import fire  # type: ignore

    logging.basicConfig(level=getattr(logging, os.environ.get("LEVEL", "WARNING")))
    fire.Fire({func.__name__: func for func in [link, track, check]})
