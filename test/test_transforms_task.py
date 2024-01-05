"""
Tests for the 'task' transforms.
"""

from contextlib import nullcontext as does_not_raise
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
    "index": {
        "rank": "by-tier",
        "product": "fake",
        "job-name": "fake-job",
    },
}
here = Path(__file__).parent


def assert_common(task_dict):
    assert task_dict["label"] == "test-fake-task-name"
    assert "task" in task_dict
    assert "extra" in task_dict["task"]
    assert "payload" in task_dict["task"]
    assert "routes" in task_dict["task"]
    assert (
        "index.test-domain.v2.some-project.latest.fake.fake-job"
        in task_dict["task"]["routes"]
    )
    assert (
        "index.test-domain.v2.some-project.pushdate.1970.01.01.19700101000000.fake.fake-job"
        in task_dict["task"]["routes"]
    )
    assert (
        "index.test-domain.v2.some-project.pushlog-id.1.fake.fake-job"
        in task_dict["task"]["routes"]
    )
    assert (
        "index.test-domain.v2.some-project.revision.abcdef.fake.fake-job"
        in task_dict["task"]["routes"]
    )


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


@pytest.mark.parametrize(
    "kind,task_def,expected_th",
    (
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "fake-task-name",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
            },
            {},
            id="no treeherder info",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "T",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="fully generated treeherder info",
        ),
        pytest.param(
            "special-test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "ST",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="multi character symbol",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": {
                    "symbol": "Test",
                },
            },
            {
                "symbol": "Test",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="explicit symbol",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": {
                    "symbol": "T(1)",
                },
            },
            {
                "symbol": "1",
                "groupSymbol": "T",
                "groupName": "tests",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="explicit group symbol",
        ),
        pytest.param(
            "build",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "b-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "B",
                "tier": 1,
                "jobKind": "build",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="build kind",
        ),
        pytest.param(
            "signing",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "S",
                "tier": 1,
                "jobKind": "other",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="non-build and non-test kind",
        ),
        pytest.param(
            "test-build",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": {
                    "kind": "build",
                },
            },
            {
                "symbol": "TB",
                "tier": 1,
                "jobKind": "build",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="explicit kind",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": {
                    "tier": 1,
                },
            },
            {
                "symbol": "T",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="explicit tier 1",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": {
                    "tier": 3,
                },
            },
            {
                "symbol": "T",
                "tier": 3,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="explicit tier 3",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": {
                    "platform": "linux/debug",
                },
            },
            {
                "symbol": "T",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "debug": True,
                },
                "machine": {
                    "platform": "linux",
                },
            },
            id="explicit platform",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "T",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="fully generated treeherder info",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "T",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="fully generated treeherder info",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "T",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="fully generated treeherder info",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "T",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="fully generated treeherder info",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "T",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="fully generated treeherder info",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "T",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="fully generated treeherder info",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "T",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="fully generated treeherder info",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "T",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="fully generated treeherder info",
        ),
        pytest.param(
            "test",
            {
                "description": "fake description",
                "name": "linux64/opt",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
                "treeherder": True,
            },
            {
                "symbol": "T",
                "tier": 1,
                "jobKind": "test",
                "collection": {
                    "opt": True,
                },
                "machine": {
                    "platform": "default",
                },
            },
            id="fully generated treeherder info",
        ),
    ),
)
def test_treeherder_defaults(run_transform, graph_config, kind, task_def, expected_th):
    params = FakeParameters(
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
    )
    transform_config = TransformConfig(
        kind,
        str(here),
        {},
        params,
        {},
        graph_config,
        write_artifacts=False,
    )
    task_dict = deepcopy(task_def)

    task_dict = run_transform(task.transforms, task_dict, config=transform_config)[0]
    print("Dumping task:")
    pprint(task_dict, indent=2)

    assert task_dict["task"].get("extra", {}).get("treeherder", {}) == expected_th


@pytest.mark.parametrize(
    "test_task, expectation",
    (
        (
            {
                "label": "task1",
                "dependencies": ["dependency"] * 2,
                "soft-dependencies": ["dependency"] * 1,
                "if-dependencies": ["dependency"] * 4,
            },
            does_not_raise(),
        ),
        (
            {
                "label": "task2",
                "dependencies": ["dependency"] * 97,
                "soft-dependencies": ["dependency"] * 1,
                "if-dependencies": ["dependency"] * 1,
            },
            does_not_raise(),
        ),
        (
            {
                "label": "task3",
                "dependencies": ["dependency"] * 98,
                "soft-dependencies": ["dependency"] * 1,
                "if-dependencies": ["dependency"] * 1,
            },
            pytest.raises(Exception),
        ),
        (
            {
                "label": "task3",
                "dependencies": ["dependency"] * 99,
                "soft-dependencies": ["dependency"],
                "if-dependencies": ["dependency"],
            },
            pytest.raises(Exception),
        ),
    ),
)
def test_check_task_dependencies(graph_config, test_task, expectation):
    params = FakeParameters(
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
    )

    transform_config = TransformConfig(
        "check_task_dependencies",
        str(here),
        {},
        params,
        {},
        graph_config,
        write_artifacts=False,
    )

    with expectation:
        assert (
            len(list(task.check_task_dependencies(transform_config, [test_task]))) == 1
        )


@pytest.mark.parametrize(
    "deadline_after, test_task",
    (
        (
            None,
            {
                "description": "fake description",
                "name": "fake-task-name",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
            },
        ),
        (
            "2 weeks",
            {
                "description": "fake description",
                "name": "fake-task-name",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
            },
        ),
    ),
)
def test_default_deadline_after(run_transform, graph_config, deadline_after, test_task):
    if deadline_after:
        graph_config._config["task-deadline-after"] = deadline_after

    params = FakeParameters(
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
    )

    transform_config = TransformConfig(
        "check_deadline",
        str(here),
        {},
        params,
        {},
        graph_config,
        write_artifacts=False,
    )

    task_dict = deepcopy(test_task)

    task_dict = run_transform(task.transforms, task_dict, config=transform_config)[0]
    if deadline_after:
        assert task_dict["task"]["deadline"] == {"relative-datestamp": deadline_after}
    else:
        assert task_dict["task"]["deadline"] == {"relative-datestamp": "1 day"}


@pytest.mark.parametrize(
    "expires_after, test_task",
    (
        (
            None,
            {
                "description": "fake description",
                "name": "fake-task-name",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
            },
        ),
        (
            "90 days",
            {
                "description": "fake description",
                "name": "fake-task-name",
                "worker-type": "t-linux",
                "worker": {
                    "docker-image": "fake-image-name",
                    "max-run-time": 1800,
                },
            },
        ),
    ),
)
def test_default_expires_after(run_transform, graph_config, expires_after, test_task):
    if expires_after:
        graph_config._config["task-expires-after"] = expires_after

    params = FakeParameters(
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
    )

    transform_config = TransformConfig(
        "check_expires",
        str(here),
        {},
        params,
        {},
        graph_config,
        write_artifacts=False,
    )

    task_dict = deepcopy(test_task)

    task_dict = run_transform(task.transforms, task_dict, config=transform_config)[0]
    if expires_after:
        assert task_dict["task"]["expires"] == {"relative-datestamp": expires_after}
    else:
        assert task_dict["task"]["expires"] == {"relative-datestamp": "28 days"}
