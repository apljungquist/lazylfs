import os
import pathlib
from typing import Iterator


def _resolve_symlink(src: pathlib.Path) -> pathlib.Path:
    """Resolve the immediate target of a symlink

    Contrast this with :py:meth:`pathlib.Path.resolve` that resolves the final target
    of a symlink, possibly resolving many immediate targets along the way, and with
    :py:func:`os.path.normpath` that will not properly resolve parents when the path
    goes through a symlink to a directory.
    """
    tgt = os.readlink(src)
    if os.path.isabs(tgt):
        return pathlib.Path(tgt)

    head, tail = os.path.split(tgt)
    if tail == "..":
        return (src.parent / tgt).resolve()
    else:
        return (src.parent / head).resolve() / tail


def trace_symlink(path: os.PathLike) -> Iterator[pathlib.Path]:
    """Follow symlink to its final target and yield all hops along the way

    The final target is yielded last, this is the only element yielded that is not
    guaranteed to be a symlink.

    The given symlink is not included in the result (subject to change).

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     pathlib.Path(tmp, "b").touch()
    ...     pathlib.Path(tmp, "lb").symlink_to("./b")
    ...     pathlib.Path(tmp, "llb").symlink_to("./lb")
    ...     [hop.name for hop in trace_symlink(pathlib.Path(tmp, "llb"))]
    ['lb', 'b']
    """
    path = pathlib.Path(path)
    visited = {path}
    while path.is_symlink():
        path = _resolve_symlink(path)
        if path in visited:
            return
        visited.add(path)
        yield path
