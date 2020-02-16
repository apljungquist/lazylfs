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

lazylfs track ./ --crud=cru

lazylfs check ./

git add .

git commit -m "Adds some data"

git diff-tree --no-commit-id --name-only -r HEAD \
| lazylfs check
```
