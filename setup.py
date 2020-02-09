#!/usr/bin/env python

import setuptools

setuptools.setup(
    name="lazylfs",
    version="0.0.0",
    packages=setuptools.find_packages("src"),
    package_dir={"": "src"},
)
