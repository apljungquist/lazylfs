from __future__ import annotations

import hashlib
import logging
import os
import pathlib
from typing import (
    Dict,
    Set,
)

_logger = logging.getLogger(__name__)

_INDEX_NAME = ".shasum"


class NotOkError(Exception):
    pass


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with path.resolve().open("rb", buffering=0) as f:
        for n in iter(lambda: f.readinto(mv), 0):  # type: ignore
            h.update(mv[:n])
    return h.hexdigest()


def _fingerprint_from_content(path):
    return _sha256(path)


def _fingerprint_from_location(path):
    index = _read_index(path.parent / _INDEX_NAME)
    return index.get(path.name)


def _should_be_indexed(path: pathlib.Path) -> bool:
    return path.is_symlink() and path.is_file() and os.path.isabs(os.readlink(path))


def _read_index(path: pathlib.Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    split_lines = [line.split() for line in path.read_text().splitlines()]
    result = {line[-1]: line[0] for line in split_lines}
    if len(result) != len(split_lines):
        raise RuntimeError("Index contains duplicate entries")
    return result


def _append_to_index(link_path: pathlib.Path) -> None:
    index_path = link_path.parent / _INDEX_NAME
    index = _read_index(index_path)

    if link_path.name in index:
        if index[link_path.name] == _fingerprint_from_content(link_path):
            return
        else:
            raise TypeError("Cannot reassign existing key")

    with index_path.open("a") as f:
        f.write(f"{_fingerprint_from_content(link_path)}  {link_path.name}\n")


def track(paths: Set[pathlib.Path]) -> None:
    for path in paths:
        if _should_be_indexed(path):
            _append_to_index(path)


def _check_index(path):
    index = _read_index(path)

    indexed_names = set(index)
    existing_names = set(
        path.name for path in path.parent.iterdir() if _should_be_indexed(path)
    )

    if indexed_names != existing_names:
        return False

    for name, key_from_location in index.items():
        if _fingerprint_from_content(path.parent / name) != key_from_location:
            return False

    return True


def check(paths: Set[pathlib.Path]) -> None:
    ok = True
    for path in paths:
        if path.name == _INDEX_NAME:
            if _check_index(path):
                continue
        elif _should_be_indexed(path):
            if _fingerprint_from_location(path) == _fingerprint_from_content(path):
                continue
        else:
            if _fingerprint_from_location(path) is None:
                continue

        ok &= False
        _logger.debug("NOK %s", path)

    if not ok:
        raise NotOkError
