#!/usr/bin/env python
import pathlib

import setuptools


def _read(rel_path: str) -> str:
    abs_path = pathlib.Path(__file__).parent / rel_path
    return abs_path.read_text()


def _read_tagline() -> str:
    lines = _read("README.md").splitlines(keepends=False)
    for line in lines:
        if line and line[0] == line[-1] == "*":
            return line[1:-1]


setuptools.setup(
    name="lazylfs",
    author="AP Ljungquist",
    author_email="ap@ljungquist.eu",
    description=_read_tagline(),
    long_description=_read("README.md"),
    long_description_content_type="text/markdown",
    url="https://github.com/apljungquist/lazylfs",
    packages=setuptools.find_packages("src"),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Unix",
    ],
    install_requires=["sprig"],
    extras_require={"cli": ["fire"]},
    package_dir={"": "src"},
    entry_points={"console_scripts": ["lazylfs = lazylfs.cli:main [cli]"],},
)
