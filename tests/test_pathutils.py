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
