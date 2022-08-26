"""
Tests for the 'task' transforms.
"""

from copy import deepcopy
from pathlib import Path
from pprint import pprint

import pytest

from taskgraph.transforms import task
from taskgraph.transforms.base import TransformConfig

from .conftest import FakeParameters

TASK_DEFAULTS = {
    "description": "fake description",
    "name": "fake-task-name",
    "worker-type": "t-linux",
    "worker": {
        "docker-image": "fake-image-name",
        "max-run-time": 1800,
    },
    "treeherder": {
        "tier": 1,
        "symbol": "G",
        "platform": "some-th-platform/some-th-collection",
        "kind": "build",
    },
}
here = Path(__file__).parent


def assert_common(task_dict):
    assert task_dict["label"] == "test-fake-task-name"
    assert "task" in task_dict
    assert "extra" in task_dict["task"]
    assert "payload" in task_dict["task"]


def assert_hg_push(task_dict):
    assert_common(task_dict)


def assert_github_pull_request(task_dict):
    assert_common(task_dict)


def assert_github_pull_request_dot_git(task_dict):
    assert_common(task_dict)


@pytest.mark.parametrize(
    "task_params",
    (
        pytest.param(
            {
                "base_repository": "http://hg.example.com",
                "build_date": 0,
                "build_number": 1,
                "head_repository": "http://hg.example.com",
                "head_rev": "abcdef",
                "head_ref": "default",
                "level": "1",
                "moz_build_date": 0,
                "next_version": "1.0.1",
                "owner": "some-owner",
                "project": "some-project",
                "pushlog_id": 1,
                "repository_type": "hg",
                "target_tasks_method": "test_method",
                "tasks_for": "hg-push",
                "try_mode": None,
                "version": "1.0.0",
            },
            id="hg-push",
        ),
        pytest.param(
            {
                "base_repository": "http://github.com/mozilla/example",
                "build_date": 0,
                "build_number": 1,
                "head_repository": "http://github.com/mozilla/example",
                "head_rev": "abcdef",
                "head_ref": "default",
                "level": "1",
                "moz_build_date": 0,
                "next_version": "1.0.1",
                "owner": "some-owner",
                "project": "some-project",
                "pushlog_id": 1,
                "repository_type": "git",
                "target_tasks_method": "test_method",
                "tasks_for": "github-pull-request",
                "try_mode": None,
                "version": "1.0.0",
            },
            id="github-pull-request",
        ),
        pytest.param(
            {
                "base_repository": "git@github.com://github.com/mozilla/example.git",
                "build_date": 0,
                "build_number": 1,
                "head_repository": "git@github.com://github.com/mozilla/example.git",
                "head_rev": "abcdef",
                "head_ref": "default",
                "level": "1",
                "moz_build_date": 0,
                "next_version": "1.0.1",
                "owner": "some-owner",
                "project": "some-project",
                "pushlog_id": 1,
                "repository_type": "git",
                "target_tasks_method": "test_method",
                "tasks_for": "github-pull-request",
                "try_mode": None,
                "version": "1.0.0",
            },
            id="github-pull-request-dot-git",
        ),
    ),
)
def test_transforms(request, run_transform, graph_config, task_params):
    # instead of make_transform_config fixture, to get custom parameters
    params = FakeParameters(task_params)
    transform_config = TransformConfig(
        "test",
        str(here),
        {},
        params,
        {},
        graph_config,
        write_artifacts=False,
    )
    task_dict = deepcopy(TASK_DEFAULTS)

    task_dict = run_transform(task.transforms, task_dict, config=transform_config)[0]
    print("Dumping task:")
    pprint(task_dict, indent=2)

    # Call the assertion function for the given test.
    param_id = request.node.callspec.id
    assertion_func = globals()[f"assert_{param_id.replace('-', '_')}"]
    assertion_func(task_dict)
