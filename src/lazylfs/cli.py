from __future__ import annotations

import glob
import hashlib
import logging
import os
import pathlib
from typing import Union, TYPE_CHECKING, Collection, Dict, Set

from sprig import dictutils  # type: ignore

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    PathT = Union[str, os.PathLike[str], pathlib.Path]

_INDEX_NAME = ".shasum"


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


def _check_shasum_index(path: pathlib.Path, files: Collection[pathlib.Path]) -> bool:
    ok = True
    top = path.parent
    previous_index = _read_shasum_index(path)
    previous_tails = set(previous_index)

    current_tails = {file.relative_to(top) for file in files}

    unchecked_tails = previous_tails - current_tails
    if unchecked_tails:
        _logger.info("%s tracked file(s) not included", len(unchecked_tails))
        for tail in sorted(unchecked_tails):
            _logger.debug("Not checked for %s", str(tail))

    untracked_tails = current_tails - previous_tails
    if untracked_tails:
        _logger.info("%s included file(s) not tracked", len(untracked_tails))
        ok = False
        for tail in sorted(untracked_tails):
            _logger.debug("Not tracked for %s", str(tail))

    common_tails = previous_tails & current_tails
    for tail in common_tails:
        expected = previous_index[tail]
        try:
            actual = _sha256(top / tail)
        except FileNotFoundError:
            _logger.warning("Could not check %s", str(top / tail))
            ok = False
            continue

        if actual != expected:
            _logger.info("Checksum mismatch for %s", str(top / tail))
            _logger.info("Actual:   %s", actual)
            _logger.info("Expected: %s", expected)
            ok = False

    return ok


def _find_links(includes: Collection[PathT]) -> Set[pathlib.Path]:
    included: Set[pathlib.Path] = set()
    for include in includes:
        for path in glob.glob(str(include)):
            if os.path.isdir(path):
                # `glob.glob("**", recursive=True)` does not play nice with symlink loops
                files = filter(os.path.isfile, pathlib.Path(path).rglob("*"))
            elif os.path.isfile(path):
                files = iter([pathlib.Path(path)])
            else:
                raise RuntimeError("Unexpected path type")

            included.update(file for file in files if os.path.islink(file))
    return included


def _find_paths(include: pathlib.Path) -> Set[pathlib.Path]:
    included: Set[pathlib.Path] = set()
    for path in glob.glob(str(include)):
        if os.path.isdir(path):
            included.add(pathlib.Path(path))
            included.update(pathlib.Path(path).rglob("*"))
        else:
            included.add(pathlib.Path(path))
    return included


def link(src: PathT, dst: PathT, include: str = "*") -> None:
    """Create links in `dst` to the corresponding file in `src`

    :param src: Directory under which to look for files
    :param dst: Directory under which to create symlinks
    :param include: Glob pattern specifying which files to include
    """
    src = pathlib.Path(src).resolve()
    dst = pathlib.Path(dst).resolve()

    src_tails = {
        pathlib.Path(path).relative_to(src)
        for path in _find_paths(src / include)
        if path.is_file() and not path.is_symlink()
    }
    dst_tails = {path.relative_to(dst) for path in _find_paths(dst / include)}

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


def track(*includes: PathT) -> None:
    """Track the checksum of files in the index"""
    batches = dictutils.group_by(_find_links(includes), lambda path: path.parent)
    for dir, files in batches.items():
        _update_shasum_index(dir / _INDEX_NAME, files)


class NotOkError(Exception):
    pass


def check(*includes: PathT) -> None:
    """Check the checksum of files against the index

    Exit with non-zero status if a difference is detected or a file could not be
    checked.
    """
    batches = dictutils.group_by(_find_links(includes), lambda path: path.parent)
    ok = True
    for dir, files in batches.items():
        ok &= _check_shasum_index(dir / _INDEX_NAME, files)

    if not ok:
        raise NotOkError


def main():
    import fire  # type: ignore

    logging.basicConfig(level=getattr(logging, os.environ.get("LEVEL", "WARNING")))
    fire.Fire({func.__name__: func for func in [link, track, check]})
