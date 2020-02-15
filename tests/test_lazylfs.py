"""
This is for pytest to find and stop being upset not finding any tests.

>>> 'Happy?'[:-1]
'Happy'
"""
import functools
import os
import pathlib
import subprocess
import tempfile
from typing import Union

import pytest

from lazylfs import cli


class File(str):
    pass


class Link(str):
    pass


_SAMPLE_TREE = {
    "a": {
        "e": {"f": File("foxtrot")},
        "g": File("golf"),
        "mother": Link("../a/"),
        "sister": Link("./e/"),
        "nephew": Link("./e/f"),
        "brother": Link("./g"),
        "aunt": Link("../i/"),
        "cousin": Link("../i/j"),
        "uncle": Link("../k"),
        "cousins_brother": Link("../i/brother"),
        "cousins_cousin": Link("../i/cousin"),
    },
    "i": {"j": File("julia"), "brother": Link("./j"), "cousin": Link("../a/g")},
    "k": File("kilo"),
}


def _create_tree(path, spec):
    if isinstance(spec, dict):
        path.mkdir()
        for name in spec:
            _create_tree(path / name, spec[name])
    elif isinstance(spec, File):
        path.write_text(spec)
    elif isinstance(spec, Link):
        path.symlink_to(spec)
    else:
        raise ValueError


def _mktemp(*args, **kwargs):
    # `tempfile.mktemp` is deprecated but I still want a way to create a new file
    # without having to find a unique name myself or worry about open file descriptors.
    fd, path = tempfile.mkstemp(*args, **kwargs)
    os.close(fd)
    return path


class _TmpDir:
    def __init__(self, path: pathlib.Path):
        self._path = path

    def __enter__(self):
        self._path.mkdir()
        return self._path

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._path.rmdir()


class _TmpLink:
    def __init__(self, path: pathlib.Path, tgt: Union[str, pathlib.Path]):
        self._path = path
        self._tgt = tgt

    def __enter__(self):
        self._path.symlink_to(self._tgt)
        return self._path

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._path.unlink()


class _TmpFile:
    def __init__(self, path: pathlib.Path):
        self._path = path

    def __enter__(self):
        self._path.touch()
        return self._path

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._path.unlink()


def test_workflow_lib(tmp_path):
    legacy_path = tmp_path / "legacy"
    _create_tree(legacy_path, _SAMPLE_TREE)

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    with _TmpDir(repo_path / "a") as a:
        with _TmpDir(a / "g"):
            with pytest.raises(FileExistsError):
                cli.link(legacy_path, repo_path, "a/**/*")

        with _TmpFile(a / "g"):
            with pytest.raises(FileExistsError):
                cli.link(legacy_path, repo_path, "a/**/*")

        with _TmpLink(a / "g", _mktemp(dir=tmp_path)) as g:
            with pytest.raises(FileExistsError):
                cli.link(legacy_path, repo_path, "a/**/*")
            g.resolve().unlink()

            with pytest.raises(FileExistsError):
                cli.link(legacy_path, repo_path, "a/**/*")

    # The above failures should have created no files
    # (It would probably fail before this point as `a` cannot be removed if it is not empty)
    assert not list(repo_path.rglob("*"))

    cli.link(legacy_path, repo_path, "a/**/*")
    cli.track(repo_path)
    cli.check(repo_path)

    (legacy_path / "a/g").write_text("stone")

    with pytest.raises(Exception):
        cli.check(repo_path)


def test_workflow_cli(tmp_path):
    legacy_path = tmp_path / "legacy"
    _create_tree(legacy_path, _SAMPLE_TREE)

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    # Skip some of the unhappy path tests because
    # * they should work the same as for lib,
    # * the subprocess calls are slow, and
    # * I am lazy

    run = functools.partial(subprocess.run, check=True, capture_output=True)
    base_cmd = ["lazylfs"]
    assert not run(
        base_cmd + ["link", str(legacy_path), str(repo_path), "a/**/*"]
    ).stdout
    assert not run(base_cmd + ["track", str(repo_path)]).stdout
    assert not run(base_cmd + ["check", str(repo_path)]).stdout

    (legacy_path / "a/g").write_text("stone")

    proc = subprocess.run(base_cmd + ["check", str(repo_path)], capture_output=True)
    assert not proc.stdout
    assert proc.returncode
