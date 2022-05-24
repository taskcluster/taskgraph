from setuptools import setup, find_packages

with open("requirements/base.in", "r") as fp:
    requirements = fp.read().splitlines()

setup(
    name="taskcluster-taskgraph",
    version="1.6.0",
    description="Build taskcluster taskgraphs",
    url="https://github.com/taskcluster/taskgraph",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=requirements,
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
