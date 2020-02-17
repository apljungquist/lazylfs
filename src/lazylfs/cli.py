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


class ShasumIntegrityIndex:
    def __contains__(self, link_path: pathlib.Path) -> bool:
        try:
            self[link_path]
        except KeyError:
            return False
        return True

    def __getitem__(self, link_path: pathlib.Path) -> str:
        try:
            index = _read_shasum_index(link_path.parent / _INDEX_NAME)
        except FileNotFoundError as e:
            raise KeyError from e
        return index[link_path.name]

    def __setitem__(self, link_path: pathlib.Path, new: str) -> None:
        index_filepath = link_path.parent / _INDEX_NAME
        key = link_path.name
        try:
            index = _read_shasum_index(index_filepath)
        except FileNotFoundError:
            index = {}

        if key in index:
            if index[key] == new:
                return
            else:
                raise PermissionError

        index[key] = self.calc_checksum(link_path)
        _write_shasum_index(index_filepath, index)

    def calc_checksum(self, link_path: pathlib.Path) -> str:
        return _sha256(link_path)

    def add(self, link_path: pathlib.Path) -> None:
        checksum = self.calc_checksum(link_path)
        self[link_path] = checksum

    def check(self, index_filepath: pathlib.Path) -> bool:
        try:
            index = _read_shasum_index(index_filepath)
        except FileNotFoundError:
            index = {}

        actual_keys = set(index)
        expected_keys = set(
            path.name
            for path in index_filepath.parent.iterdir()
            if _should_be_indexed(path)
        )

        if actual_keys != expected_keys:
            return False

        for key, expected_checksum in index.items():
            link_path = index_filepath.parent / key
            actual_checksum = self.calc_checksum(link_path)
            if actual_checksum != expected_checksum:
                return False

        return True


def _should_be_indexed(link_path: pathlib.Path) -> bool:
    return (
        link_path.is_symlink()
        and link_path.is_file()
        and os.path.isabs(os.readlink(link_path))
    )


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
    index = ShasumIntegrityIndex()
    for path in paths:
        if _should_be_indexed(path):
            index.add(path)


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
    index = ShasumIntegrityIndex()
    for path in paths:
        if path.name == _INDEX_NAME:
            if index.check(path):
                continue
        elif _should_be_indexed(path):
            if path in index:
                if index[path] == index.calc_checksum(path):
                    continue
        else:
            if path not in index:
                continue

        ok &= False
        _logger.debug("NOK %s", path)

    if not ok:
        raise NotOkError


def main():
    import fire  # type: ignore

    logging.basicConfig(level=getattr(logging, os.environ.get("LEVEL", "WARNING")))
    fire.Fire({func.__name__: func for func in [link, track, check]})
