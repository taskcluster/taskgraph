"""
Tests for the 'toolchain' transforms.
"""
from pprint import pprint

import pytest

from taskgraph.transforms.job import make_task_description
from taskgraph.util.templates import merge

TASK_DEFAULTS = {
    "description": "fake description",
    "label": "fake-task-label",
    "worker-type": "t-linux",
    "worker": {
        "implementation": "docker-worker",
        "os": "linux",
        "env": {},
    },
    "run": {
        "using": "run-task",
        "command": "echo hello world",
    },
}


@pytest.fixture
def run_job_using(mocker, run_transform):
    m = mocker.patch("taskgraph.util.hash._find_files")
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
                    "mount-point": "/builds/worker/checkouts",
                    "name": "checkouts-hg58",
                    "skip-untrusted": False,
                    "type": "persistent",
                }
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
                "CI_BASE_REPOSITORY": "http://hg.example.com",
                "CI_HEAD_REF": "default",
                "CI_HEAD_REPOSITORY": "http://hg.example.com",
                "CI_HEAD_REV": "abcdef",
                "CI_REPOSITORY_TYPE": "hg",
                "HG_STORE_PATH": "/builds/worker/checkouts/hg-store",
                "MOZ_SCM_LEVEL": "1",
                "REPOSITORIES": '{"ci": "Taskgraph"}',
                "VCS_PATH": "/builds/worker/checkouts/vcs",
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
                '--ci-checkout=./build/src/ -- bash -cx "echo hello '
                'world"'
            ],
            "env": {
                "CI_BASE_REPOSITORY": "http://hg.example.com",
                "CI_HEAD_REF": "default",
                "CI_HEAD_REPOSITORY": "http://hg.example.com",
                "CI_HEAD_REV": "abcdef",
                "CI_REPOSITORY_TYPE": "hg",
                "HG_STORE_PATH": "y:/hg-shared",
                "MOZ_SCM_LEVEL": "1",
                "REPOSITORIES": '{"ci": "Taskgraph"}',
                "VCS_PATH": "./build/src",
            },
            "implementation": "generic-worker",
            "mounts": [
                {"cache-name": "checkouts", "directory": "./build"},
                {
                    "content": {
                        "url": "https://tc-tests.localhost/api/queue/v1/task/<TASK_ID>/artifacts/public/run-task"  # noqa
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


@pytest.mark.parametrize(
    "task",
    (
        pytest.param(
            {},
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
    ),
)
def test_run_task(request, run_job_using, task):
    taskdesc = run_job_using(task)
    print("Task Description:")
    pprint(taskdesc)
    param_id = request.node.callspec.id
    assert_func = globals()[f"assert_{param_id}"]
    assert_func(taskdesc)
