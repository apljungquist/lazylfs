from __future__ import annotations

import hashlib
import logging
import os
import pathlib
import sys
from typing import (
    Dict,
    Set,
    Tuple,
    Iterator,
)

_logger = logging.getLogger(__name__)


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


def track(paths: Set[pathlib.Path]) -> None:
    index = ShasumIntegrityIndex()
    for path in paths:
        if _should_be_indexed(path):
            index.add(path)


class NotOkError(Exception):
    pass


def check(paths: Set[pathlib.Path]) -> None:
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
