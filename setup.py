#!/usr/bin/env python
import pathlib
from typing import List

import setuptools


def _read(rel_path: str) -> str:
    abs_path = pathlib.Path(__file__).parent / rel_path
    return abs_path.read_text()


def _read_tagline() -> str:
    lines = _read("README.md").splitlines(keepends=False)
    for line in lines:
        if line and line[0] == line[-1] == "*":
            return line[1:-1]


def _read_requirements(name: str) -> List[str]:
    return list(_read(f"requirements/{name}.txt").splitlines())


setuptools.setup(
    name="lazylfs",
    author="AP Ljungquist",
    author_email="ap@ljungquist.eu",
    description=_read_tagline(),
    long_description=_read("README.md"),
    long_description_content_type="text/markdown",
    url="https://github.com/apljungquist/lazylfs",
    packages=setuptools.find_packages("src"),
    package_data={"lazylfs": ["py.typed"]},
    zip_safe=False,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Unix",
    ],
    install_requires=_read_requirements("install_requires"),
    extras_require={"cli": _read_requirements("extras_require-cli")},
    package_dir={"": "src"},
    entry_points={"console_scripts": ["lazylfs = lazylfs.cli:main [cli]"]},
)
