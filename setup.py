#!/usr/bin/env python

import setuptools

setuptools.setup(
    name="lazylfs",
    version="0.1.0",
    author="AP Ljungquist",
    author_email="ap@ljungquist.eu",
    description="A quick way to version control data",
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
