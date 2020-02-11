#!/usr/bin/env python

import setuptools

setuptools.setup(
    name="lazylfs",
    install_requires=["sprig"],
    extras_require={"cli": ["fire"]},
    version="0.0.0",
    packages=setuptools.find_packages("src"),
    package_dir={"": "src"},
    entry_points={"console_scripts": ["lazylfs = lazylfs.cli:main [cli]"],},
)
