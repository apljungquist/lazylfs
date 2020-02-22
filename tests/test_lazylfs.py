"""
This is for pytest to find and stop being upset not finding any tests.

>>> 'Happy?'[:-1]
'Happy'
"""
import contextlib
import functools
import logging
import os
import pathlib
import stat
import subprocess
from typing import Collection, Dict

import pytest

from lazylfs import cli, pathutils

_logger = logging.getLogger(__name__)


class File(str):
    pass


class Link(str):
    pass


_SAMPLE_TREE = {
    "a": {
        "e": {"f": File("foxtrot")},
        "g": File("golf"),
        "h": File("hotel"),
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


def _create_tree(path, spec, ignored_exceptions=()):
    try:
        if isinstance(spec, dict):
            path.mkdir(exist_ok=True)
            for name in spec:
                _create_tree(path / name, spec[name], ignored_exceptions)
        elif isinstance(spec, File):
            pathutils.ensure_reg(path, spec)
        elif isinstance(spec, Link):
            pathutils.ensure_lnk(path, spec)
        else:
            raise ValueError
    except ignored_exceptions as e:
        _logger.debug("Ignoring exception %s", str(e))


_SAMEFILE_ATTRS = {
    "st_ino",
    "st_dev",
}

# These should be stable, st_atime notably is not
_STABLE_ATTRS = {
    "st_mode",
    "st_uid",
    "st_gid",
    "st_mtime",
    "st_ctime",
}


def _calc_fingerprint(
    path: pathlib.Path, follow_symlinks: bool, attrs: Collection[str]
) -> Dict:
    if follow_symlinks:
        s = path.stat()
    else:
        s = path.lstat()
    if stat.S_ISDIR(s.st_mode):
        return {
            "content": [
                _calc_fingerprint(child, follow_symlinks, attrs)
                for child in path.iterdir()
            ],
            **{attr: getattr(s, attr) for attr in attrs},
        }
    elif stat.S_ISLNK(s.st_mode):
        return {
            "content": os.readlink(path),
            **{attr: getattr(s, attr) for attr in attrs},
        }
    elif stat.S_ISREG(s.st_mode):
        return {
            "content": path.read_text(),
            **{attr: getattr(s, attr) for attr in attrs},
        }
    else:
        raise ValueError


@contextlib.contextmanager
def assert_nullipotent(path):
    before = _calc_fingerprint(path, False, _STABLE_ATTRS)
    yield
    after = _calc_fingerprint(path, False, _STABLE_ATTRS)
    assert after == before


@pytest.fixture()
def base_legacy(tmp_path):
    legacy_path = tmp_path / "legacy"
    _create_tree(legacy_path, _SAMPLE_TREE)
    yield legacy_path


@pytest.fixture()
def base_repo(tmp_path, base_legacy):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    cli.link(base_legacy / "a", repo_path / "a")
    cli.track(repo_path)

    _create_tree(repo_path / "a", _SAMPLE_TREE["a"], FileExistsError)

    (repo_path / "a/reg").touch()
    (repo_path / "a/dir").mkdir()

    yield repo_path


@pytest.mark.parametrize(
    "create_path",
    [
        lambda path: path.parent.mkdir() or path.touch(),
        lambda path: path.parent.mkdir() or path.symlink_to("anything"),
    ],
)
def test_link_fails_if_existing_and_different(tmp_path, base_legacy, create_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    existing_path = repo_path / "a/g"
    create_path(existing_path)

    with assert_nullipotent(existing_path), pytest.raises(FileExistsError):
        cli.link(base_legacy / "a", repo_path / "a")

    with assert_nullipotent(repo_path), pytest.raises(FileExistsError):
        cli.link(base_legacy / "a", repo_path / "a")


def test_link_skips_if_existing_and_same(tmp_path, base_legacy):
    # This enables idempotency
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    cli.link(base_legacy / "a", repo_path / "a")

    with assert_nullipotent(repo_path):
        cli.link(base_legacy / "a", repo_path / "a")


def test_link_does_not_affect_src(tmp_path, base_legacy):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    with assert_nullipotent(base_legacy):
        cli.link(base_legacy / "a", repo_path / "a")


def test_common_paths_resolve_to_samefile_after_link(tmp_path, base_legacy):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    src = base_legacy / "a"
    dst = repo_path / "a"
    cli.link(src, dst)

    src_paths = {
        path.relative_to(src)
        for path in src.rglob("*")
        if not stat.S_ISDIR(path.lstat().st_mode)
    }
    dst_paths = {
        path.relative_to(dst)
        for path in dst.rglob("*")
        if not stat.S_ISDIR(path.lstat().st_mode)
    }
    common_paths = src_paths & dst_paths

    src_fingerprint = {
        path: _calc_fingerprint(src / path, True, _SAMEFILE_ATTRS)
        for path in common_paths
    }
    dst_fingerprint = {
        path: _calc_fingerprint(dst / path, True, _SAMEFILE_ATTRS)
        for path in common_paths
    }

    assert src_fingerprint == dst_fingerprint


def test_track_is_idempotent(tmp_path, base_legacy):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    cli.link(base_legacy / "a", repo_path / "a")
    cli.track(repo_path)

    with assert_nullipotent(repo_path):
        cli.track(repo_path)


def test_check_on_clean_repo(base_repo):
    with assert_nullipotent(base_repo):
        cli.check(base_repo)
        cli.check(base_repo / "a/g")
        cli.check(base_repo / "a/h")
        cli.check(base_repo / "a/.shasum")

        # Check should ignore paths that are not links
        # Will happen if not all paths in repo are links
        cli.check(base_repo / "a/reg")
        cli.check(base_repo / "a/dir")

        # Will happen if
        # * was link and has been deleted from repo and index,
        # * was other type and has been deleted (never in index)
        cli.check(base_repo / "a/dir/bad")
        cli.check(base_repo / "a/dir/.shasum")


def test_check_modified_tgt(base_repo):
    # Equivalent to modifying entry in index
    (base_repo / "a/g").resolve().write_text("stone")

    with assert_nullipotent(base_repo):
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo)
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo / "a/g")
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo / "a/.shasum")

        # One invalid link should not impact ability to validate on work on other files
        cli.check(base_repo / "a/reg")
        cli.check(base_repo / "a/dir")
        cli.check(base_repo / "a/dir/bad")
        cli.check(base_repo / "a/e/f")
        cli.check(base_repo / "a/e/.shasum")
        cli.check(base_repo / "a/h")


def test_check_deleted_tgt(base_repo):
    (base_repo / "a/g").resolve().unlink()

    with assert_nullipotent(base_repo):
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo)
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo / "a/g")
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo / "a/.shasum")

        # One invalid link should not impact ability to validate on work on other files
        cli.check(base_repo / "a/reg")
        cli.check(base_repo / "a/dir")
        cli.check(base_repo / "a/dir/bad")
        cli.check(base_repo / "a/e/f")
        cli.check(base_repo / "a/e/.shasum")
        cli.check(base_repo / "a/h")


def test_check_deleted_lnk(base_repo):
    # Equivalent to adding entry in index
    (base_repo / "a/g").unlink()

    with assert_nullipotent(base_repo):
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo)
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo / "a/g")
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo / "a/.shasum")

        # One invalid link should not impact ability to validate on work on other files
        cli.check(base_repo / "a/reg")
        cli.check(base_repo / "a/dir")
        cli.check(base_repo / "a/dir/bad")
        cli.check(base_repo / "a/e/f")
        cli.check(base_repo / "a/e/.shasum")
        cli.check(base_repo / "a/h")


def test_check_added_lnk(base_repo):
    # Equivalent to deleting entry in index
    g = base_repo / "a/g"
    x = base_repo / "a/x"
    x.symlink_to(g.resolve())

    with assert_nullipotent(base_repo):
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo)
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo / "a/x")
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo / "a/.shasum")

        # One invalid link should not impact ability to validate on work on other files
        cli.check(base_repo / "a/reg")
        cli.check(base_repo / "a/dir")
        cli.check(base_repo / "a/dir/bad")
        cli.check(base_repo / "a/e/f")
        cli.check(base_repo / "a/e/.shasum")
        cli.check(base_repo / "a/h")


def test_check_added_lnk_new_dir(base_repo):
    # Equivalent to deleting index

    # Removing index is easier to implement than adding a new dir with files but the
    # current test name makes it easier relating this test to other tests.
    (base_repo / "a/.shasum").unlink()

    with assert_nullipotent(base_repo):
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo)
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo / "a/g")
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo / "a/h")
        with pytest.raises(cli.NotOkError):
            cli.check(base_repo / "a/.shasum")

        # One invalid link should not impact ability to validate on work on other files
        cli.check(base_repo / "a/reg")
        cli.check(base_repo / "a/dir")
        cli.check(base_repo / "a/dir/bad")
        cli.check(base_repo / "a/e/f")
        cli.check(base_repo / "a/e/.shasum")


def test_workflow_cli(tmp_path):
    legacy_path = tmp_path / "legacy"
    _create_tree(legacy_path, _SAMPLE_TREE)

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    # Skip some of the unhappy path tests because
    # * they should work the same as for lib,
    # * the subprocess calls are slow, and
    # * I am lazy

    run = functools.partial(subprocess.run, check=True, text=True, capture_output=True)
    base_cmd = ["lazylfs"]
    assert not run(
        base_cmd + ["link", str(legacy_path / "a"), str(repo_path / "a")]
    ).stdout
    assert not run(base_cmd + ["track", str(repo_path)]).stdout
    assert not run(base_cmd + ["check", str(repo_path)]).stdout
    assert not run(
        base_cmd + ["check"],
        input="\n".join(map(str, (path for path in repo_path.rglob("*")))),
    ).stdout

    (legacy_path / "a/g").write_text("stone")

    proc = subprocess.run(
        base_cmd + ["check", str(repo_path)], capture_output=True, text=True
    )
    assert not proc.stdout
    assert proc.returncode

    proc = subprocess.run(
        base_cmd + ["check"],
        capture_output=True,
        text=True,
        input="\n".join(map(str, (path for path in repo_path.rglob("*")))),
    )
    assert not proc.stdout
    assert proc.returncode
