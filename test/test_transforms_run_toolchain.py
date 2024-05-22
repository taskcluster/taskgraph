"""
Tests for the 'toolchain' transforms.
"""

from pprint import pprint

import pytest

from taskgraph.transforms.run import make_task_description
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
        "using": "toolchain-script",
        "script": "run.sh",
        "toolchain-artifact": "public/build/artifact.zip",
    },
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
        m = mocker.patch(
            "taskgraph.transforms.run.toolchain.configure_taskdesc_for_run"
        )
        run_transform(make_task_description, task)
        return m.call_args[0]

    return inner


def assert_docker_worker(task, taskdesc):
    assert task == {
        "description": "fake description",
        "label": "fake-task-label",
        "run": {
            "command": ["vcs/taskcluster/scripts/toolchain/run.sh"],
            "cwd": "{checkout}/..",
            "sparse-profile": "toolchain-build",
            "using": "run-task",
            "workdir": "/builds/worker",
        },
        "worker": {
            "artifacts": [
                {
                    "name": "public/build",
                    "path": "/builds/worker/artifacts/",
                    "type": "directory",
                }
            ],
            "chain-of-trust": True,
            "docker-image": {"in-tree": "toolchain-build"},
            "env": {
                "MOZ_BUILD_DATE": 0,
                "MOZ_SCM_LEVEL": "1",
                "UPLOAD_DIR": "/builds/worker/artifacts/",
            },
            "implementation": "docker-worker",
            "os": "linux",
        },
        "worker-type": "t-linux",
    }
    assert taskdesc == {
        "attributes": {
            "toolchain-alias": "foo",
            "toolchain-artifact": "public/build/artifact.zip",
            "toolchain-env": {"FOO": "1"},
        },
        "cache": {
            "digest-data": [
                "a81c34908c02a5b6a14607465397c0f82d5c406b3e2e73f2c29644016d7bb031",
                "public/build/artifact.zip",
                "toolchain-build",
            ],
            "name": "fake-task-label",
            "type": "toolchains.v3",
        },
        "dependencies": {},
        "description": "fake description",
        "extra": {},
        "label": "fake-task-label",
        "routes": [],
        "scopes": [],
        "soft-dependencies": [],
        "worker": {
            "artifacts": [
                {
                    "name": "public/build",
                    "path": "/builds/worker/artifacts/",
                    "type": "directory",
                }
            ],
            "chain-of-trust": True,
            "docker-image": {"in-tree": "toolchain-build"},
            "env": {
                "MOZ_BUILD_DATE": 0,
                "MOZ_SCM_LEVEL": "1",
                "UPLOAD_DIR": "/builds/worker/artifacts/",
            },
            "implementation": "docker-worker",
            "os": "linux",
        },
        "worker-type": "t-linux",
    }


def assert_generic_worker(task, taskdesc):
    assert task == {
        "description": "fake description",
        "label": "fake-task-label",
        "run": {
            "command": "src/taskcluster/scripts/toolchain/run.sh --foo bar",
            "cwd": "{checkout}/..",
            "sparse-profile": "toolchain-build",
            "using": "run-task",
            "workdir": "/builds/worker",
        },
        "worker": {
            "artifacts": [
                {"name": "public/build", "path": "public/build", "type": "directory"}
            ],
            "chain-of-trust": True,
            "env": {"MOZ_BUILD_DATE": 0, "MOZ_SCM_LEVEL": "1"},
            "implementation": "generic-worker",
            "os": "windows",
        },
        "worker-type": "b-win2012",
    }
    assert taskdesc == {
        "attributes": {"toolchain-artifact": "public/build/artifact.zip"},
        "cache": {
            "digest-data": [
                "a81c34908c02a5b6a14607465397c0f82d5c406b3e2e73f2c29644016d7bb031",
                "public/build/artifact.zip",
                "--foo",
                "bar",
            ],
            "name": "fake-task-label",
            "type": "toolchains.v3",
        },
        "dependencies": {},
        "description": "fake description",
        "extra": {},
        "label": "fake-task-label",
        "routes": [],
        "scopes": [],
        "soft-dependencies": [],
        "worker": {
            "artifacts": [
                {"name": "public/build", "path": "public/build", "type": "directory"}
            ],
            "chain-of-trust": True,
            "env": {"MOZ_BUILD_DATE": 0, "MOZ_SCM_LEVEL": "1"},
            "implementation": "generic-worker",
            "os": "windows",
        },
        "worker-type": "b-win2012",
    }


def assert_powershell(task, _):
    assert task["run"] == {
        "command": "src/taskcluster/scripts/toolchain/run.ps1",
        "cwd": "{checkout}/..",
        "exec-with": "powershell",
        "sparse-profile": "toolchain-build",
        "using": "run-task",
        "workdir": "/builds/worker",
    }


def assert_forward(task, _):
    """Assert unknown schema args are forwarded to run_task"""
    assert task["run"]["foo"] == "bar"


def assert_relative_script(task, taskdesc):
    """Assert that a relative script produces the same results"""
    assert_docker_worker(task, taskdesc)


@pytest.mark.parametrize(
    "task",
    (
        pytest.param(
            {
                "run": {
                    "toolchain-alias": "foo",
                    "toolchain-env": {
                        "FOO": "1",
                    },
                }
            },
            id="docker_worker",
        ),
        pytest.param(
            {
                "run": {
                    "arguments": ["--foo", "bar"],
                },
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
                "run": {"script": "run.ps1"},
                "worker-type": "b-win2012",
                "worker": {
                    "os": "windows",
                    "implementation": "generic-worker",
                },
            },
            id="powershell",
        ),
        pytest.param(
            {"run": {"foo": "bar"}},
            id="forward",
        ),
        pytest.param(
            {
                "run": {
                    "script": "../toolchain/run.sh",
                    "toolchain-alias": "foo",
                    "toolchain-env": {
                        "FOO": "1",
                    },
                }
            },
            id="relative_script",
        ),
    ),
)
def test_toolchain(request, run_task_using, task):
    _, task, taskdesc, _ = run_task_using(task)
    print("Task:")
    pprint(task)
    print("Task Description:")
    pprint(taskdesc)
    param_id = request.node.callspec.id
    assert_func = globals()[f"assert_{param_id}"]
    assert_func(task, taskdesc)
