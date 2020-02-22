import pathlib

import pytest

from lazylfs import pathutils


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
    "tree, start, expected",
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
            ["lb", "b"],
        ),
        # Direct link
        ({"b": Link("./c"), "c": File("C")}, "b", ["c"]),
        # Self reference
        ({"b": Link("./b")}, "b", []),
        # Short cycle
        ({"b": Link("./c"), "c": Link("./b")}, "b", ["c"]),
        # Eventual cycle
        (
            {"b": Link("./c"), "c": Link("./d"), "d": Link("./f"), "f": Link("./c")},
            "b",
            ["c", "d", "f"],
        ),
    ],
)
def test_trace_symlink_by_example(tmp_path, tree, start, expected):
    create_tree(tmp_path, tree)
    hops = pathutils.trace_symlink(tmp_path / start)
    for l, r in zip(hops, expected):
        assert l.name == r
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
