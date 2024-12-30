"""
Tests for the 'toolchain' transforms.
"""

import os.path
from pprint import pprint

import pytest

from taskgraph.transforms.run import make_task_description
from taskgraph.util.templates import merge

here = os.path.abspath(os.path.dirname(__file__))

TASK_DEFAULTS = {
    "description": "fake description",
    "label": "fake-task-label",
    "worker-type": "t-linux",
    "worker": {
        "implementation": "docker-worker",
        "os": "linux",
        "env": {},
    },
    "run": {"using": "run-task", "command": "echo hello world"},
}


@pytest.fixture
def run_task_using(mocker, run_transform):
    m = mocker.patch("taskgraph.util.hash._get_all_files")
    m.return_value = [
        "taskcluster/scripts/toolchain/run.sh",
        "taskcluster/scripts/toolchain/run.ps1",
    ]

    def inner(task):
        task = merge(TASK_DEFAULTS, task)
        return run_transform(make_task_description, task)[0]

    return inner


def assert_docker_worker(task):
    assert task == {
        "attributes": {},
        "dependencies": {},
        "description": "fake description",
        "extra": {},
        "label": "fake-task-label",
        "routes": [],
        "scopes": [],
        "soft-dependencies": [],
        "worker": {
            "caches": [
                {
                    "mount-point": "/builds/worker/.task-cache/cargo",
                    "name": "cargo",
                    "skip-untrusted": False,
                    "type": "persistent",
                },
                {
                    "mount-point": "/builds/worker/checkouts",
                    "name": "checkouts",
                    "skip-untrusted": False,
                    "type": "persistent",
                },
                {
                    "mount-point": "/builds/worker/.task-cache/npm",
                    "name": "npm",
                    "skip-untrusted": False,
                    "type": "persistent",
                },
                {
                    "mount-point": "/builds/worker/.task-cache/pip",
                    "name": "pip",
                    "skip-untrusted": False,
                    "type": "persistent",
                },
                {
                    "mount-point": "/builds/worker/.task-cache/uv",
                    "name": "uv",
                    "skip-untrusted": False,
                    "type": "persistent",
                },
            ],
            "command": [
                "/usr/local/bin/run-task",
                "--ci-checkout=/builds/worker/checkouts/vcs/",
                "--",
                "bash",
                "-cx",
                "echo hello world",
            ],
            "env": {
                "CARGO_HOME": "/builds/worker/.task-cache/cargo",
                "CI_BASE_REPOSITORY": "http://hg.example.com",
                "CI_HEAD_REF": "default",
                "CI_HEAD_REPOSITORY": "http://hg.example.com",
                "CI_HEAD_REV": "abcdef",
                "CI_REPOSITORY_TYPE": "hg",
                "HG_STORE_PATH": "/builds/worker/checkouts/hg-store",
                "MOZ_SCM_LEVEL": "1",
                "PIP_CACHE_DIR": "/builds/worker/.task-cache/pip",
                "REPOSITORIES": '{"ci": "Taskgraph"}',
                "UV_CACHE_DIR": "/builds/worker/.task-cache/uv",
                "VCS_PATH": "/builds/worker/checkouts/vcs",
                "npm_config_cache": "/builds/worker/.task-cache/npm",
            },
            "implementation": "docker-worker",
            "os": "linux",
            "taskcluster-proxy": True,
        },
        "worker-type": "t-linux",
    }


def assert_generic_worker(task):
    assert task == {
        "attributes": {},
        "dependencies": {},
        "description": "fake description",
        "extra": {},
        "label": "fake-task-label",
        "routes": [],
        "scopes": [],
        "soft-dependencies": [],
        "worker": {
            "command": [
                "C:/mozilla-build/python3/python3.exe run-task "
                '--ci-checkout=build/src/ -- bash -cx "echo hello '
                'world"'
            ],
            "env": {
                "CARGO_HOME": "{task_workdir}/.task-cache/cargo",
                "CI_BASE_REPOSITORY": "http://hg.example.com",
                "CI_HEAD_REF": "default",
                "CI_HEAD_REPOSITORY": "http://hg.example.com",
                "CI_HEAD_REV": "abcdef",
                "CI_REPOSITORY_TYPE": "hg",
                "HG_STORE_PATH": "y:/hg-shared",
                "MOZ_SCM_LEVEL": "1",
                "PIP_CACHE_DIR": "{task_workdir}/.task-cache/pip",
                "REPOSITORIES": '{"ci": "Taskgraph"}',
                "UV_CACHE_DIR": "{task_workdir}/.task-cache/uv",
                "VCS_PATH": "{task_workdir}/build/src",
                "npm_config_cache": "{task_workdir}/.task-cache/npm",
            },
            "implementation": "generic-worker",
            "mounts": [
                {
                    "cache-name": "cargo",
                    "directory": ".task-cache/cargo",
                },
                {
                    "cache-name": "checkouts",
                    "directory": "build",
                },
                {
                    "cache-name": "npm",
                    "directory": ".task-cache/npm",
                },
                {
                    "cache-name": "pip",
                    "directory": ".task-cache/pip",
                },
                {
                    "cache-name": "uv",
                    "directory": ".task-cache/uv",
                },
                {
                    "content": {
                        "url": "https://tc-tests.localhost/api/queue/v1/task/<TASK_ID>/artifacts/public/run-task"
                    },
                    "file": "./run-task",
                },
            ],
            "os": "windows",
        },
        "worker-type": "b-win2012",
    }


def assert_exec_with(task):
    assert task["worker"]["command"] == [
        "/usr/local/bin/run-task",
        "--ci-checkout=/builds/worker/checkouts/vcs/",
        "--",
        "powershell.exe",
        "-ExecutionPolicy",
        "Bypass",
        "echo hello world",
    ]


def assert_run_task_command_docker_worker(task):
    assert task["worker"]["command"] == [
        "/foo/bar/python3",
        "run-task",
        "--ci-checkout=/builds/worker/checkouts/vcs/",
        "--",
        "bash",
        "-cx",
        "echo hello world",
    ]


def assert_run_task_command_generic_worker(task):
    assert task["worker"]["command"] == [
        ["chmod", "+x", "run-task"],
        [
            "/foo/bar/python3",
            "run-task",
            "--ci-checkout=checkouts/vcs/",
            "--",
            "bash",
            "-cx",
            "echo hello world",
        ],
    ]


@pytest.mark.parametrize(
    "task",
    (
        pytest.param(
            {"worker": {"os": "linux"}},
            id="docker_worker",
        ),
        pytest.param(
            {
                "worker-type": "b-win2012",
                "worker": {
                    "os": "windows",
                    "implementation": "generic-worker",
                },
            },
            id="generic_worker",
        ),
        pytest.param(
            {
                "run": {
                    "exec-with": "powershell",
                },
            },
            id="exec_with",
        ),
        pytest.param(
            {
                "run": {"run-task-command": ["/foo/bar/python3", "run-task"]},
            },
            id="run_task_command_docker_worker",
        ),
        pytest.param(
            {
                "run": {"run-task-command": ["/foo/bar/python3", "run-task"]},
                "worker": {
                    "implementation": "generic-worker",
                },
            },
            id="run_task_command_generic_worker",
        ),
    ),
)
def test_run_task(monkeypatch, request, run_task_using, task):
    monkeypatch.setenv("TASK_ID", "<TASK_ID>")
    taskdesc = run_task_using(task)
    print("Task Description:")
    pprint(taskdesc)
    param_id = request.node.callspec.id
    assert_func = globals()[f"assert_{param_id}"]
    assert_func(taskdesc)
