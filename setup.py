from setuptools import setup, find_packages

with open("requirements/base.in", "r") as fp:
    requirements = fp.read().splitlines()

setup(
    name="taskcluster-taskgraph",
    version="1.1.0",
    description="Build taskcluster taskgraphs",
    url="https://hg.mozilla.org/ci/taskgraph",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=requirements,
    classifiers=[
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
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
