import pathlib

import pytest

from lazylfs import pathutils

_SAMEFILE_ATTRS = {
    "st_ino",
    "st_dev",
}

# These should be stable, st_atime notably is not


class Link(str):
    pass


class File(str):
    pass


def create_tree(top: pathlib.Path, spec) -> None:
    for name, sub in spec.items():
        path = top / name
        if isinstance(sub, dict):
            path.mkdir()
            create_tree(path, sub)
        elif isinstance(sub, File):
            path.write_text(sub)
        elif isinstance(sub, Link):
            path.symlink_to(sub)
        else:
            raise ValueError


@pytest.mark.parametrize(
    "tree, start, nodes",
    [
        # normpath would fail om this because it works on pure paths
        (
            {
                "a": {"e": {"lb": Link("../../b")}},
                "le": Link("./a/e/"),
                "llb": Link("./le/lb"),
                "b": File("B"),
            },
            "llb",
            ["llb", "lb", "b"],
        ),
        (
            {
                "a": {"e": {"i": {"la": Link("../..")}}},
                "li": Link("./a/e/i/"),
                "lla": Link("./li/la"),
            },
            "lla",
            ["lla", "la", "a"],
        ),
        # Direct link
        ({"b": Link("./c"), "c": File("C")}, "b", ["b", "c"]),
    ],
)
def test_trace_symlink_by_example(tmp_path, tree, start, nodes):
    create_tree(tmp_path, tree)
    hops = list(pathutils.trace_symlink(tmp_path / start))
    assert [hop.name for hop in hops] == nodes[
        1:
    ], "Did not pass through expected nodes"
    for hop in hops:
        assert hop.samefile(tmp_path / start), "Did not resolve to correct file"
    assert not hops[-1].is_symlink(), "Some symlinks not resolved"


@pytest.mark.parametrize(
    "tree, start, nodes",
    [
        # Self reference
        ({"b": Link("./b")}, "b", ["b"]),
        # Short cycle
        ({"b": Link("./c"), "c": Link("./b")}, "b", ["b", "c"]),
        # Eventual cycle
        (
            {"b": Link("./c"), "c": Link("./d"), "d": Link("./f"), "f": Link("./c")},
            "b",
            ["b", "c", "d", "f"],
        ),
    ],
)
def test_trace_symlink_does_not_get_stuck_in_loops(tmp_path, tree, start, nodes):
    create_tree(tmp_path, tree)
    hops = pathutils.trace_symlink(tmp_path / start)
    for hop, node in zip(hops, nodes[1:]):
        assert hop.name == node
    with pytest.raises(StopIteration):
        next(hops)


@pytest.mark.parametrize(
    "ensure_file",
    [
        lambda p: pathutils.ensure_lnk(p, "foo"),
        lambda p: pathutils.ensure_reg(p, "foo"),
    ],
)
def test_ensure_file_raises_if_parent_does_not_exist(tmp_path, ensure_file):
    with pytest.raises(FileNotFoundError):
        ensure_file(tmp_path / "a/b")


def test_ensure_dir_raises_if_root_does_not_exist(tmp_path):
    path = tmp_path / "a/e"
    with pytest.raises(FileNotFoundError):
        pathutils.ensure_dir(path, path.parent)


@pytest.mark.parametrize(
    "ensure_file",
    [
        lambda p: pathutils.ensure_lnk(p, "foo"),
        lambda p: pathutils.ensure_reg(p, "foo"),
    ],
)
@pytest.mark.parametrize(
    "create_path",
    [
        lambda p: pathutils.ensure_dir(p, p.parent),
        lambda p: pathutils.ensure_lnk(p, "spanish_inquisition"),
        lambda p: pathutils.ensure_reg(p, "spanish_inquisition"),
    ],
)
def test_ensure_path_raises_if_path_exists_and_is_different(
    tmp_path, ensure_file, create_path
):
    path = tmp_path / "x"
    create_path(path)
    with pytest.raises(FileExistsError):
        ensure_file(path)


@pytest.mark.parametrize(
    "create_path",
    [
        lambda p: pathutils.ensure_lnk(p, "spanish_inquisition"),
        lambda p: pathutils.ensure_reg(p, "spanish_inquisition"),
    ],
)
def test_ensure_dir_raises_if_path_exists_and_is_different(tmp_path, create_path):
    path = tmp_path / "x"
    create_path(path)
    with pytest.raises(FileExistsError):
        pathutils.ensure_dir(path, path.parent)


@pytest.mark.parametrize(
    "ensure_path",
    [
        lambda p: pathutils.ensure_dir(p, p.parent),
        lambda p: pathutils.ensure_reg(p, "foo"),
        lambda p: pathutils.ensure_reg(p, "foo"),
    ],
)
def test_ensure_functions_are_idempotent(tmp_path, ensure_path):
    path = tmp_path / "x"
    ensure_path(path)

    with pathutils.assert_nullipotent(tmp_path):
        ensure_path(path)
