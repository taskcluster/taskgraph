# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Tests for the 'run' transform subsystem.
"""

import json
import os
import re
from copy import deepcopy
from pprint import pprint
from unittest.mock import patch

import pytest

# prevent pytest thinking this is a test
from taskgraph.task import Task
from taskgraph.transforms import run
from taskgraph.transforms.run import run_task  # noqa: F401
from taskgraph.util.templates import merge

here = os.path.abspath(os.path.dirname(__file__))


TASK_DEFAULTS = {
    "description": "fake description",
    "label": "fake-task-label",
    "run": {
        "using": "run-task",
    },
}


@pytest.fixture
def transform(monkeypatch, run_transform):
    """Run the run transforms on the specified task but return the inputs to
    `configure_taskdesc_for_run` without executing it.

    This gives test functions an easy way to generate the inputs required for
    many of the `run_using` subsystems.
    """
    # Needed by 'generic_worker_run_task'
    monkeypatch.setenv("TASK_ID", "fakeid")

    def inner(task_input, **kwargs):
        defaults = deepcopy(TASK_DEFAULTS)
        task = merge(defaults, task_input)

        with patch("taskgraph.transforms.run.configure_taskdesc_for_run") as m:
            # This forces the generator to be evaluated
            run_transform(run.transforms, task, **kwargs)
            return m.call_args[0]

    return inner


def test_rewrite_when_to_optimization(run_transform, make_transform_config):
    config = make_transform_config()

    task = {"foo": "bar"}
    result = run_transform(run.rewrite_when_to_optimization, task)
    assert list(result) == [{"foo": "bar"}]

    task = {"foo": "bar", "when": {"files-changed": ["README.md"]}}
    result = run_transform(run.rewrite_when_to_optimization, task)
    assert list(result) == [
        {
            "foo": "bar",
            "optimization": {
                "skip-unless-changed": ["README.md", f"{config.path}/kind.yml"]
            },
        }
    ]

    task = {
        "foo": "bar",
        "when": {"files-changed": ["README.md"]},
        "task-from": "foo.yml",
    }
    result = run_transform(run.rewrite_when_to_optimization, task)
    assert list(result) == [
        {
            "foo": "bar",
            "optimization": {
                "skip-unless-changed": [
                    "README.md",
                    f"{config.path}/kind.yml",
                    f"{config.path}/foo.yml",
                ]
            },
            "task-from": "foo.yml",
        }
    ]


def assert_use_fetches_toolchain_env(task):
    assert task["worker"]["env"]["FOO"] == "1"


def assert_use_fetches_toolchain_extract_false(task):
    fetches = json.loads(task["worker"]["env"]["MOZ_FETCHES"]["task-reference"])
    assert len(fetches) == 1
    assert fetches[0]["extract"] is False


def assert_use_fetches_toolchain_mixed(task):
    fetches = json.loads(task["worker"]["env"]["MOZ_FETCHES"]["task-reference"])
    assert len(fetches) == 2
    assert fetches == [
        {
            "artifact": "bar.zip",
            "extract": True,
            "task": "<toolchain-bar>",
        },
        {
            "artifact": "target.whl",
            "extract": False,
            "task": "<toolchain-foo>",
        },
    ]


@pytest.mark.parametrize(
    "task,kind_dependencies_tasks",
    (
        pytest.param(
            {"fetches": {"toolchain": ["foo"]}},
            [
                Task(
                    kind="toolchain",
                    label="toolchain-foo",
                    attributes={
                        "toolchain-artifact": "target.zip",
                        "toolchain-env": {"FOO": "1"},
                    },
                    task={},
                )
            ],
            id="toolchain_env",
        ),
        pytest.param(
            {"fetches": {"toolchain": [{"artifact": "foo", "extract": False}]}},
            [
                Task(
                    kind="toolchain",
                    label="toolchain-foo",
                    attributes={
                        "toolchain-artifact": "target.whl",
                    },
                    task={},
                )
            ],
            id="toolchain_extract_false",
        ),
        pytest.param(
            {"fetches": {"toolchain": [{"artifact": "foo", "extract": False}, "bar"]}},
            [
                Task(
                    kind="toolchain",
                    label="toolchain-foo",
                    attributes={
                        "toolchain-artifact": "target.whl",
                    },
                    task={},
                ),
                Task(
                    kind="toolchain",
                    label="toolchain-bar",
                    attributes={
                        "toolchain-artifact": "bar.zip",
                    },
                    task={},
                ),
            ],
            id="toolchain_mixed",
        ),
    ),
)
def test_use_fetches(
    request,
    make_transform_config,
    run_transform,
    task,
    kind_dependencies_tasks,
):
    transform_config = make_transform_config(
        kind_dependencies_tasks={t.label: t for t in kind_dependencies_tasks}
    )
    task = merge(TASK_DEFAULTS, task)
    result = run_transform(run.use_fetches, task, config=transform_config)[0]
    pprint(result)

    param_id = request.node.callspec.id
    assert_func = globals()[f"assert_use_fetches_{param_id}"]
    assert_func(result)


GITHUB_PARAMS = {"base_repository": "https://github.com/Owner/Repo"}


def test_use_secrets(run_transform):
    task = merge(
        TASK_DEFAULTS,
        {
            "scopes": ["secrets:get:project/foo"],
            "worker": {"env": {"FOO": "1"}},
            "secrets": [
                {"type": "github-repo-token", "app": "read"},
                {
                    "type": "github-repo-token",
                    "app": "write",
                    "repo": "git@github.com:owner/other.git",
                    "permissions": {"pull_requests": "write", "contents": "read"},
                    "env": "OTHER_TOKEN",
                },
                {"type": "secret", "name": "project/foo", "env": "FOO_SECRET"},
                {
                    "type": "secret",
                    "name": "project/bar",
                    "key": "token",
                    "env": "BAR_TOKEN",
                },
                # Neither an env nor a file collides with a namesake of the other.
                {"type": "secret", "name": "project/foo", "file": "FOO_SECRET"},
            ],
        },
    )
    result = run_transform(run.use_secrets, task, extra_params=GITHUB_PARAMS)[0]

    assert "secrets" not in result
    assert result["worker"]["taskcluster-proxy"] is True
    assert result["scopes"] == [
        "secrets:get:project/foo",
        "auth:github-repo-token:read/Owner/Repo:contents:read",
        "auth:github-repo-token:write/owner/other:contents:read",
        "auth:github-repo-token:write/owner/other:pull_requests:write",
        "secrets:get:project/bar",
    ]
    env = result["worker"]["env"]
    assert env["FOO"] == "1"
    assert json.loads(env["RUN_TASK_SECRETS"]) == [
        {
            "type": "github-repo-token",
            "app": "read",
            "repo": "https://github.com/Owner/Repo",
        },
        {
            "type": "github-repo-token",
            "app": "write",
            "repo": "git@github.com:owner/other.git",
            "permissions": {"pull_requests": "write", "contents": "read"},
            "env": "OTHER_TOKEN",
        },
        {"type": "secret", "name": "project/foo", "env": "FOO_SECRET"},
        {"type": "secret", "name": "project/bar", "key": "token", "env": "BAR_TOKEN"},
        {"type": "secret", "name": "project/foo", "file": "FOO_SECRET"},
    ]


def test_use_secrets_none(run_transform):
    task = deepcopy(TASK_DEFAULTS)
    assert run_transform(run.use_secrets, task)[0] == TASK_DEFAULTS


@pytest.mark.parametrize(
    "task,error",
    (
        pytest.param(
            {
                "secrets": [{"type": "secret", "name": "a", "env": "FOO"}],
                "worker": {"env": {"RUN_TASK_SECRETS": "[]"}},
            },
            "not both",
            id="explicit_env",
        ),
        pytest.param(
            {"secrets": [{"type": "github-repo-token", "app": "read"}]},
            "is not a GitHub repository",
            id="not_github",
        ),
        pytest.param(
            {
                "secrets": [
                    {"type": "secret", "name": "a", "env": "GITHUB_TOKEN"},
                    {
                        "type": "github-repo-token",
                        "app": "read",
                        "repo": "https://github.com/o/r",
                    },
                ]
            },
            "more than one secret is exported to env GITHUB_TOKEN",
            id="duplicate_env",
        ),
        pytest.param(
            {
                "secrets": [
                    {"type": "secret", "name": "a", "file": "a.json"},
                    {"type": "secret", "name": "b", "file": "a.json"},
                ]
            },
            "more than one secret is exported to file a.json",
            id="duplicate_file",
        ),
    ),
)
def test_use_secrets_invalid(run_transform, task, error):
    task = merge(TASK_DEFAULTS, task)
    with pytest.raises(Exception, match=error):
        run_transform(run.use_secrets, task)


@pytest.mark.parametrize(
    "secret,error",
    (
        pytest.param({"type": "bogus"}, "", id="unknown_type"),
        pytest.param(
            {"type": "secret", "name": "a"},
            "exactly one of 'env' or 'file'",
            id="missing_env_and_file",
        ),
        pytest.param(
            {"type": "secret", "name": "a", "env": "A", "file": "a"},
            "exactly one of 'env' or 'file'",
            id="env_and_file",
        ),
        pytest.param({"type": "github-repo-token"}, "", id="missing_app"),
        pytest.param(
            {"type": "github-repo-token", "app": "read", "file": "a"},
            "",
            id="github_file",
        ),
        pytest.param(
            {"type": "secret", "name": "a", "env": "A", "app": "read"},
            "",
            id="unknown_key",
        ),
    ),
)
def test_use_secrets_schema(transform, secret, error):
    with pytest.raises(Exception, match=rf"(?s){re.escape(error)}.*\$\.secrets\[0\]"):
        transform({"worker-type": "t-linux", "secrets": [secret]})


def test_use_secrets_run_transforms(transform):
    taskdesc = transform(
        {
            "worker-type": "t-linux",
            "secrets": [{"type": "secret", "name": "project/foo", "env": "FOO"}],
        },
    )[2]
    assert "secrets" not in taskdesc
    assert "secrets:get:project/foo" in taskdesc["scopes"]
    assert json.loads(taskdesc["worker"]["env"]["RUN_TASK_SECRETS"]) == [
        {"type": "secret", "name": "project/foo", "env": "FOO"}
    ]
