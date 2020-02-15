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
        "brothers_brother0": Link("./brothers_brother1"),
        "brothers_brother1": Link("./brothers_brother0"),
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
                cli.link(legacy_path / "a", repo_path / "a")

        with _TmpFile(a / "g"):
            with pytest.raises(FileExistsError):
                cli.link(legacy_path / "a", repo_path / "a")

        with _TmpLink(a / "g", _mktemp(dir=tmp_path)) as g:
            with pytest.raises(FileExistsError):
                cli.link(legacy_path / "a", repo_path / "a")
            g.resolve().unlink()

            with pytest.raises(FileExistsError):
                cli.link(legacy_path / "a", repo_path / "a")

    # The above failures should have created no files
    # (It would probably fail before this point as `a` cannot be removed if it is not empty)
    assert not list(repo_path.rglob("*"))

    cli.link(legacy_path / "a", repo_path / "a")
    cli.track(repo_path)

    (repo_path / "a/x").write_text("xulu")

    cli.check(repo_path)
    cli.check(repo_path / "a/g")
    cli.check(repo_path / "a/.shasum")
    cli.check(repo_path / "a/does_not_exist")  # TODO: Should this fail?
    cli.check(repo_path / "a/x")

    # Tamper with data
    (legacy_path / "a/g").write_text("stone")
    # Run checks
    with pytest.raises(cli.NotOkError):
        cli.check(repo_path)
    with pytest.raises(cli.NotOkError):
        cli.check(repo_path / "a/g")
    with pytest.raises(cli.NotOkError):
        cli.check(repo_path / "a/.shasum")
    # Restore data
    (legacy_path / "a/g").write_text(_SAMPLE_TREE["a"]["g"])

    # Check that it is restored properly; refactor this test soon
    cli.check(repo_path)
    cli.check(repo_path / "a/g")
    cli.check(repo_path / "a/.shasum")

    # Tamper with data
    (legacy_path / "a/g").unlink()
    # Run checks
    cli.check(repo_path)  # TODO: Should this fail or pass?
    with pytest.raises(Exception):
        cli.check(repo_path / "a/g")
    cli.check(repo_path / "a/.shasum")  # TODO: Should this fail or pass?
    # Restore data
    (legacy_path / "a/g").write_text(_SAMPLE_TREE["a"]["g"])

    # Check that it is restored properly; refactor this test soon
    cli.check(repo_path)
    cli.check(repo_path / "a/g")
    cli.check(repo_path / "a/.shasum")

    # Tamper with data
    index = cli._read_shasum_index(repo_path / "a/.shasum")
    old = index[pathlib.Path("g")]
    new = old[:-1] + "0"
    if old == new:
        new = old[:-1] + "1"
    assert old != new
    index[pathlib.Path("g")] = new
    cli._write_shasum_index(repo_path / "a/.shasum", index)
    # Run checks
    with pytest.raises(cli.NotOkError):
        cli.check(repo_path)
    with pytest.raises(cli.NotOkError):
        cli.check(repo_path / "a/g")
    with pytest.raises(cli.NotOkError):
        cli.check(repo_path / "a/.shasum")
    # Restore data
    index[pathlib.Path("g")] = old
    cli._write_shasum_index(repo_path / "a/.shasum", index)

    # Check that it is restored properly; refactor this test soon
    cli.check(repo_path)
    cli.check(repo_path / "a/g")
    cli.check(repo_path / "a/.shasum")

    # Tamper with data
    del index[pathlib.Path("g")]
    cli._write_shasum_index(repo_path / "a/.shasum", index)
    # Run checks
    with pytest.raises(cli.NotOkError):
        cli.check(repo_path)
    with pytest.raises(cli.NotOkError):
        cli.check(repo_path / "a/g")
    with pytest.raises(cli.NotOkError):
        cli.check(repo_path / "a/.shasum")  # TODO: Should this fail or pass?
    # Restore data
    index[pathlib.Path("g")] = old
    cli._write_shasum_index(repo_path / "a/.shasum", index)


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
        base_cmd + ["link", str(legacy_path / "a"), str(repo_path / "a")]
    ).stdout
    assert not run(base_cmd + ["track", str(repo_path)]).stdout
    assert not run(base_cmd + ["check", str(repo_path)]).stdout

    (legacy_path / "a/g").write_text("stone")

    proc = subprocess.run(base_cmd + ["check", str(repo_path)], capture_output=True)
    assert not proc.stdout
    assert proc.returncode
