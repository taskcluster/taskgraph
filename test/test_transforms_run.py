# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Tests for the 'run' transform subsystem.
"""

import json
import os
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
