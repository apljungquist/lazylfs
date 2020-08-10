import contextlib
import itertools
import os
import pathlib
import stat
from typing import Iterator, Union, Collection, Dict


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


def ensure_dir(path: os.PathLike, root: os.PathLike) -> bool:
    """Ensure that the specified directory exists

    Avoids creating paths in unintended locations by refusing to create directories
    outside of :param root:.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     path = pathlib.Path(tmp, "a", "e")
    ...     assert ensure_dir(path, path.parents[1]) is True
    ...     assert ensure_dir(path, path.parents[1]) is False

    :param path: location of directory
    :param root: an existing ancestor of the directory
    :return: ``True`` if path was created, ``False`` otherwise
    :raises FileExistsError: if the path exists and is different than what would be
        created by this function.
    """
    path = pathlib.Path(path)
    root = pathlib.Path(root)
    root.lstat()  # Raise early if root does not exist
    path.relative_to(root)  # Raise if not ancestor/descendant

    try:
        st_mode = os.lstat(path).st_mode
    except FileNotFoundError:
        parents = itertools.takewhile(lambda p: p != root, path.parents)
        for parent in reversed(list(parents)):
            parent.mkdir(exist_ok=True)
        path.mkdir(exist_ok=True)
        return True

    if not stat.S_ISDIR(st_mode):
        raise FileExistsError(f"File exists (wrong type): {path}")

    return False


def ensure_lnk(path: os.PathLike, tgt: os.PathLike) -> bool:
    """Ensure that the specified symlink exists

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     path = pathlib.Path(tmp, "b")
    ...     assert ensure_lnk(path, "./foo") is True
    ...     assert ensure_lnk(path, "./foo") is False

    :param path: location of symlink
    :param tgt: desired target of the symlink
    :return: ``True`` if path was created, ``False`` otherwise
    :raises FileExistsError: if the path exists and is different than what would be
        created by this function.
    """
    try:
        st_mode = os.lstat(path).st_mode
    except FileNotFoundError:
        os.symlink(tgt, path)
        return True

    if not stat.S_ISLNK(st_mode):
        raise FileExistsError(f"File exists (wrong type): {path}")

    if os.readlink(path) != os.fspath(tgt):
        raise FileExistsError(f"File exists (wrong content): {path}")

    return False


def ensure_reg(path: os.PathLike, content: Union[bytes, str]) -> bool:
    """Ensure that the specified file exists

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     path = pathlib.Path(tmp, "b")
    ...     assert ensure_reg(path, "Bravo") is True
    ...     assert ensure_reg(path, "Bravo") is False

    :param path: location of file
    :param content: desired content of given file
    :return: ``True`` if path was created, ``False`` otherwise
    :raises FileExistsError: if the path exists and is different than what would be
        created by this function.
    """
    if isinstance(content, str):
        content = content.encode()

    try:
        st_mode = os.lstat(path).st_mode
    except FileNotFoundError:
        with open(path, "xb") as f:
            f.write(content)
        return True

    if not stat.S_ISREG(st_mode):
        raise FileExistsError(f"File exists (wrong type): {path}")

    with open(path, "rb") as f:
        if f.read() != content:
            raise FileExistsError(f"File exists (wrong content): {path}")

    return False


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
