from __future__ import annotations

import hashlib
import logging
import os
import pathlib
import sys
from typing import (
    Union,
    TYPE_CHECKING,
    Collection,
    Dict,
    Set,
    Tuple,
    Iterator,
)

from sprig import dictutils  # type: ignore

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    PathT = Union[str, os.PathLike[str], pathlib.Path]

_INDEX_NAME = ".shasum"


# Aliases for file mode combinations to allow filters to be expressed as easy to read
# disjunctions. More to come when needed, primarily is_dir and is_lnk_dir.


def _is_bad(path: pathlib.Path) -> bool:
    return not path.exists() and not path.is_symlink()


def _is_reg(path: pathlib.Path) -> bool:
    """Path is regular file"""
    return path.is_file() and not path.is_symlink()


def _is_lnk_bad(path: pathlib.Path) -> bool:
    """Path is dangling symlink"""
    return path.is_symlink() and not path.exists()


def _is_lnk_reg(path: pathlib.Path) -> bool:
    """"Path symlink to regular file"""
    return path.is_symlink() and path.is_file()


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with path.resolve().open("rb", buffering=0) as f:
        for n in iter(lambda: f.readinto(mv), 0):  # type: ignore
            h.update(mv[:n])
    return h.hexdigest()


def _read_shasum_index(path: pathlib.Path) -> Dict[pathlib.Path, str]:
    split_lines = (line.split() for line in path.read_text().splitlines())
    return {pathlib.Path(line[-1]): line[0] for line in split_lines}


def _write_shasum_index(path: pathlib.Path, index: Dict[pathlib.Path, str]) -> None:
    path.write_text("".join(sorted(f"{v}  {k}\n" for k, v in index.items())))


def _update_shasum_index(path: pathlib.Path, files: Collection[pathlib.Path]) -> None:
    top = path.parent
    try:
        previous_index = _read_shasum_index(path)
    except FileNotFoundError:
        previous_index = {}
    previous_tails = set(previous_index)

    current_tails = {file.relative_to(top) for file in files}

    if previous_tails & current_tails:
        _logger.info("Some files are already indexed, skipping")

    if previous_tails - current_tails:
        _logger.info("Some indexed files are gone, preserving")

    marginal_tails = current_tails - previous_tails
    if not marginal_tails:
        _logger.info("No files need to be indexed")
        return

    _logger.debug("Indexing %s files", len(marginal_tails))
    marginal_index = {tail: _sha256(top / tail) for tail in marginal_tails}

    _write_shasum_index(path, {**previous_index, **marginal_index})


def _check_link(link_path: pathlib.Path) -> bool:
    _logger.debug("Checking link %s", str(link_path))

    top = link_path.parent
    index_path = top / _INDEX_NAME

    try:
        index = _read_shasum_index(index_path)
    except FileNotFoundError:
        if link_path.exists():
            _logger.info("NOK because no index for link")
            return False
        else:
            return True

    try:
        expected = index[link_path.relative_to(top)]
    except KeyError:
        if link_path.exists():
            _logger.info("NOK because link not in index")
            return False
        else:
            return True

    try:
        actual = _sha256(link_path)
    except FileNotFoundError:
        _logger.info("NOK because link does not exist")
        return False

    if actual != expected:
        _logger.info("NOK because checksum mismatch for link")
        return False

    return True


def _check_index(index_path: pathlib.Path) -> bool:
    _logger.debug("Checking index %s", str(index_path))

    ok = True
    top = index_path.parent

    try:
        index = _read_shasum_index(index_path)
    except FileNotFoundError:
        index = {}

    for name, expected in index.items():
        link_path = top / name
        try:
            actual = _sha256(link_path)
        except FileNotFoundError:
            _logger.info("NOK because link does not exist")
            ok = False
            continue

        if actual != expected:
            _logger.info("NOK because checksum mismatch for link")
            ok = False

    existing = set(
        path.relative_to(top)
        for path in top.iterdir()
        if _is_lnk_reg(path) or _is_lnk_bad(path)
    )
    untracked = existing - set(index)
    if untracked:
        _logger.info("NOK because untracked links")
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


def link(src: PathT, dst: PathT) -> None:
    """Create links in `dst` to the corresponding files in `src`

    :param src: Directory under which to look for files
    :param dst: Directory under which to create symlinks
    """
    src = pathlib.Path(src).resolve()
    dst = pathlib.Path(dst).resolve()

    if not src.is_dir():
        raise ValueError("Expected src to be a directory")

    src_tails = {
        pathlib.Path(path).relative_to(src) for path in src.rglob("*") if _is_reg(path)
    }
    dst_tails = {path.relative_to(dst) for path in dst.rglob("*")}

    conflicts = src_tails & dst_tails
    if conflicts:
        for tail in conflicts:
            _logger.debug("Path already exist in the destination: %s", str(tail))
        raise FileExistsError("Some paths already exist in the destination")

    dst.mkdir(exist_ok=True)

    new = src_tails - dst_tails
    for tail in sorted(new):
        src_path = src / tail
        dst_path = dst / tail
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        _logger.debug("Linking %s", str(tail))
        dst_path.symlink_to(src_path)


def track(*includes: str) -> None:
    """Track the checksum of files in the index"""
    _track(_collect_paths(includes))


def _track(paths: Set[pathlib.Path]) -> None:
    batches = dictutils.group_by(
        (path for path in paths if _is_lnk_reg(path)), lambda path: path.parent,
    )
    for dir, files in batches.items():
        _update_shasum_index(dir / _INDEX_NAME, files)


class NotOkError(Exception):
    pass


def check(*includes: str) -> None:
    """Check the checksum of files against the index

    Exit with non-zero status if a difference is detected or a file could not be
    checked.
    """
    _check(_collect_paths(includes))


def _check(paths: Set[pathlib.Path]) -> None:
    ok = True

    for path in paths:
        if path.name == _INDEX_NAME:
            if _is_reg(path) or _is_bad(path):
                ok &= _check_index(path)
            else:
                raise ValueError("Non-regular file named like index file")
        elif _is_lnk_reg(path) or _is_lnk_bad(path) or _is_bad(path):
            ok &= _check_link(path)
        else:
            _logger.debug("Ignoring path %s", str(path))

    if not ok:
        raise NotOkError


def main():
    import fire  # type: ignore

    logging.basicConfig(level=getattr(logging, os.environ.get("LEVEL", "WARNING")))
    fire.Fire({func.__name__: func for func in [link, track, check]})
