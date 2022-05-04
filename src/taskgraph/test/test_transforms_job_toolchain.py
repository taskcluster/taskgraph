"""
Tests for the 'toolchain' transforms.
"""
from pprint import pprint
from unittest.mock import patch

import pytest

from taskgraph.transforms.job import make_task_description
from taskgraph.util import hash
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
def run_job_using(monkeypatch, run_transform):
    def fake_find_files(_):
        return ["taskcluster/scripts/toolchain/run.sh"]

    monkeypatch.setattr(hash, "_find_files", fake_find_files)

    def inner(task):
        task = merge(TASK_DEFAULTS, task)
        with patch(
            "taskgraph.transforms.job.toolchain.configure_taskdesc_for_run"
        ) as m:
            run_transform(make_task_description, task)
            return m.call_args[0]

    return inner


def assert_basic(task):
    assert task == {
        "attributes": {
            "toolchain-alias": "foo",
            "toolchain-artifact": "public/build/artifact.zip",
        },
        "cache": {
            "digest-data": [
                "a81c34908c02a5b6a14607465397c0f82d5c406b3e2e73f2c29644016d7bb031",
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
                "MOZ_SCM_LEVEL": 1,
                "UPLOAD_DIR": "/builds/worker/artifacts/",
            },
            "implementation": "docker-worker",
            "os": "linux",
        },
        "worker-type": "t-linux",
    }


@pytest.mark.parametrize(
    "task",
    (
        pytest.param(
            {
                "run": {
                    "toolchain-alias": "foo",
                }
            },
            id="basic",
        ),
    ),
)
def test_toolchain(request, run_job_using, task):
    task = run_job_using(task)[2]
    pprint(task)
    param_id = request.node.callspec.id
    assert_func = globals()[f"assert_{param_id}"]
    assert_func(task)
