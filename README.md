# LazyLFS

*A quick way to version control data stored remotely*

*Lazy* because
* it does not eagerly fetch the data, and
* it does not require a lot of work up front.


## Usage

Install like

```bash
pip install lazylfs
```

Use like

```bash
cd path/to/repo

git init .

lazylfs link path/to/data/ ./

lazylfs track ./

lazylfs check ./

git add .

git commit -m "Adds some data"

git diff-tree --no-commit-id --name-only -r HEAD \
| lazylfs check
```


## Alternatives

There are many existing ways to handle large files and large repositories in git.
This section explores these alternatives, their strengths, weaknesses and applicability to my use case.

Common to many of them is that they have a higher barrier to entry if when migrating from something like a NAS.

### Git LFS

Downloading a small part of files is cumbersome.
The best method I have found is to
1. `export GIT_LFS_SKIP_SMUDGE=1`,
2. `git-lfs fetch` files selectively using the `-I` and `-X` arguments,
3. `git-lfs` checkout files, explicitly if errors are to avoid.
4. repeat 2 and 3 after every git operation that add, remove or modify files tracked by lfs.

[Reportedly](https://stackoverflow.com/a/4327707), the footprint of a repo is likely to be much larger than just the files because they are stored once as objects in git and once as files in the working tree.

### git-annex

Seems like default behavior is to store a copy of every file in`.git/annex`.
I made a very brief attempt at replacing the files with symlinks which seemed to make it unhappy.

It also seems hard to learn and cumbersome to use in general due to its flexibility.
Admittedly this may be because I have not spent enough time with it, so that is definitely on my ToDo list.

### VFS for Git

> The short answer is that a Linux VFSForGit client is not yet available, but we're working on it!

[VFSForGIT issue #1226](https://github.com/microsoft/VFSForGit/issues/1226)
