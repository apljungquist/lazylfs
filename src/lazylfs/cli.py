from __future__ import annotations

import enum
import hashlib
import itertools
import logging
import os
import pathlib
import sys
from typing import Union, TYPE_CHECKING, Set, Tuple, Iterator

from lazylfs import pathutils

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    PathT = Union[str, os.PathLike[str], pathlib.Path]


class ConflictResolution(enum.Enum):
    THEIRS = "theirs"
    OURS = "ours"
    PANIC = "panic"


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with path.resolve().open("rb", buffering=0) as f:
        for n in iter(lambda: f.readinto(mv), 0):  # type: ignore
            h.update(mv[:n])
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode())
    return h.hexdigest()


def _ensure_path(path: pathlib.Path, root: pathlib.Path) -> None:
    rel_path = path.relative_to(root)  # Check that root in an ancestor
    for parent in rel_path.parents:
        parent.mkdir(exist_ok=True)
    path.mkdir(exist_ok=True)


def _relative_path(start, end) -> str:
    common = os.path.commonpath([start, end])
    up = os.path.join(*[os.pardir] * len(os.path.relpath(start, common).split(os.sep)))
    down = os.path.relpath(end, common)
    return os.path.join(up, down)


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


def _find_repo_root(start: pathlib.Path) -> pathlib.Path:
    if not start.is_dir():
        start = start.parent
    for parent in itertools.chain([start], start.parents):
        names = {path.name for path in parent.iterdir()}
        if ".git" in names:
            return parent
    raise FileNotFoundError


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
    cas = _find_repo_root(dst) / "cas"
    cas.mkdir(exist_ok=True)

    for tail in sorted(src_tails):
        src_path = src / tail
        dst_path = dst / tail
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        _logger.debug("Linking %s", str(tail))

        checksum = _sha256(src_path)
        cas_path = cas / checksum
        if cas_path.is_symlink():
            tgt = os.readlink(cas_path)
            if tgt != str(src_path):
                found_path = cas / "found" / _sha256_text(tgt)
                _ensure_path(found_path.parent, cas)
                found_path.symlink_to(dst_path)
        else:
            cas_path.symlink_to(src_path)

        if (
            dst_path.is_symlink()
            and os.path.split(os.readlink(dst_path))[1] == checksum
        ):
            _logger.debug("Path exists and is equivalent, skipping")
            continue

        if dst_path.is_symlink() or dst_path.exists():
            raise FileExistsError

        dst_path.symlink_to(_relative_path(dst_path.parent, cas_path))


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
    paths = _collect_paths(includes)
    _check(_find_repo_root(next(iter(paths))), paths)


def _find_brdige(root: pathlib.Path, path: pathlib.Path) -> pathlib.Path:
    src = path
    for tgt in pathutils.trace_symlink(path):
        try:
            path.relative_to(root)
        except ValueError:
            return src
        src = tgt
    raise FileNotFoundError


def _check(repo: pathlib.Path, paths: Set[pathlib.Path]) -> None:
    ok = True
    cas = repo / "cas"

    # Collect content. Factor out?
    cas_paths_to_check = set()
    for path in paths:
        if not path.is_symlink():
            continue

        try:
            path.relative_to(cas)
        except ValueError:
            pass
        else:
            continue
        for hop in pathutils.trace_symlink(path):
            try:
                hop.relative_to(repo)
            except ValueError:
                _logger.debug("NOK because link is not tracked %s", str(path))
                ok &= False
                break

            try:
                hop.relative_to(cas)
            except ValueError:
                continue

            cas_paths_to_check.add(hop)
            break

    # Check content. Factor out?
    for path in cas_paths_to_check:
        expected = path.name
        try:
            actual = _sha256(path)
        except FileNotFoundError as e:
            raise NotOkError from e
        if actual != expected:
            ok &= False
            _logger.debug("NOK %s", path)

    if not ok:
        raise NotOkError


def main():
    import fire  # type: ignore

    logging.basicConfig(level=getattr(logging, os.environ.get("LEVEL", "WARNING")))
    fire.Fire({func.__name__: func for func in [link, check]})
