"""
This is for pytest to find and stop being upset not finding any tests.

>>> 'Happy?'[:-1]
'Happy'
"""
import functools
import subprocess

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


def test_workflow_lib(tmp_path):
    legacy_path = tmp_path / "legacy"
    _create_tree(legacy_path, _SAMPLE_TREE)

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

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
