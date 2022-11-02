import os

from setuptools import find_packages, setup

project_dir = os.path.abspath(os.path.dirname(__file__))


with open(os.path.join(project_dir, "requirements/base.in")) as fp:
    requirements = fp.read().splitlines()

with open(os.path.join(project_dir, "version.txt")) as f:
    version = f.read().rstrip()

setup(
    name="taskcluster-taskgraph",
    version=version,
    description="Build taskcluster taskgraphs",
    url="https://github.com/taskcluster/taskgraph",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=requirements,
    extras_require={
        "load-image": ["zstandard"],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Software Development",
    ],
    entry_points={"console_scripts": ["taskgraph = taskgraph.main:main"]},
    package_data={
        "taskgraph": [
            "run-task/run-task",
            "run-task/fetch-content",
            "run-task/hgrc",
            "run-task/robustcheckout.py",
        ],
        "taskgraph.test": ["automationrelevance.json"],
    },
)
