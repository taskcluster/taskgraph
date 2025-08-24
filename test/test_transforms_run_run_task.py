"""
Tests for the 'toolchain' transforms.
"""

import os.path
from pprint import pprint

import pytest

from taskgraph.transforms.run import make_task_description
from taskgraph.transforms.task import payload_builders, set_defaults
from taskgraph.util.caches import CACHES
from taskgraph.util.schema import Schema, validate_schema
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
        "max-run-time": 0,
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

    def inner(task, **kwargs):
        task = merge(TASK_DEFAULTS, task)
        return run_transform(make_task_description, task, **kwargs)[0]

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
                    "name": "checkouts",
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
            "docker-image": {"in-tree": "image"},
            "env": {
                "CI_BASE_REPOSITORY": "http://hg.example.com",
                "CI_HEAD_REF": "default",
                "CI_HEAD_REPOSITORY": "http://hg.example.com",
                "CI_HEAD_REV": "abcdef",
                "CI_REPOSITORY_TYPE": "hg",
                "HG_STORE_PATH": "/builds/worker/checkouts/hg-store",
                "MOZ_SCM_LEVEL": "1",
                "REPOSITORIES": '{"ci":"Taskgraph"}',
                "VCS_PATH": "/builds/worker/checkouts/vcs",
            },
            "implementation": "docker-worker",
            "max-run-time": 0,
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
                "CI_BASE_REPOSITORY": "http://hg.example.com",
                "CI_HEAD_REF": "default",
                "CI_HEAD_REPOSITORY": "http://hg.example.com",
                "CI_HEAD_REV": "abcdef",
                "CI_REPOSITORY_TYPE": "hg",
                "HG_STORE_PATH": "y:/hg-shared",
                "MOZ_SCM_LEVEL": "1",
                "REPOSITORIES": '{"ci":"Taskgraph"}',
                "VCS_PATH": "build/src",
            },
            "implementation": "generic-worker",
            "max-run-time": 0,
            "mounts": [
                {"cache-name": "checkouts", "directory": "build"},
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
            {"worker": {"os": "linux", "docker-image": {"in-tree": "image"}}},
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
                "worker": {"docker-image": "powershell"},
            },
            id="exec_with",
        ),
        pytest.param(
            {
                "run": {"run-task-command": ["/foo/bar/python3", "run-task"]},
                "worker": {"docker-image": "python"},
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
    taskdesc = next(set_defaults({}, [taskdesc]))
    validate_schema(
        payload_builders[taskdesc["worker"]["implementation"]].schema,
        taskdesc["worker"],
        "validation error",
    )


@pytest.fixture
def run_caches(run_task_using):
    def inner(task, **kwargs):
        task.setdefault("run", {}).setdefault("using", "run-task")
        impl = task.setdefault("worker", {}).setdefault(
            "implementation", "generic-worker"
        )
        result = run_task_using(task, **kwargs)

        key = "mounts" if impl == "generic-worker" else "caches"

        caches = result["worker"][key]
        caches = [c for c in caches if "cache-name" in c]
        print("Dumping for copy/paste:")
        pprint(caches, indent=2)

        # Create a new schema object with just the part relevant to caches.
        partial_schema = Schema(payload_builders[impl].schema.schema[key])
        validate_schema(partial_schema, caches, "validation error")

        return caches

    return inner


def test_caches_enabled(run_caches):
    task = {
        "run": {
            "use-caches": True,
        }
    }
    caches = run_caches(task)
    assert len(caches) == len(CACHES)
    cache_names = {c["cache-name"] for c in caches}
    for name, cfg in CACHES.items():
        if "cache_name" in cfg:
            continue
        assert name in cache_names


def test_caches_disabled(run_caches):
    task = {
        "run": {
            "use-caches": False,
        }
    }
    assert run_caches(task) == []


def test_caches_explicit(run_caches):
    task = {
        "run": {
            "use-caches": ["cargo"],
        }
    }
    assert run_caches(task) == [
        {"cache-name": "cargo", "directory": ".task-cache/cargo"}
    ]


def test_caches_project_explicit(run_caches):
    caches = run_caches(
        {},
        extra_graph_config={"taskgraph": {"run": {"use-caches": ["cargo"]}}},
    )
    assert caches == [{"cache-name": "cargo", "directory": ".task-cache/cargo"}]
