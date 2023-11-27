# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Tests for the 'run' transform subsystem.
"""

import os
from copy import deepcopy
from pprint import pprint
from unittest.mock import patch

import pytest

# prevent pytest thinking this is a test
from taskgraph.task import Task
from taskgraph.transforms import run
from taskgraph.transforms.run import run_task  # noqa: F401
from taskgraph.transforms.run.common import add_cache
from taskgraph.transforms.task import payload_builders
from taskgraph.util.schema import Schema, validate_schema
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

    def inner(task_input):
        task = deepcopy(TASK_DEFAULTS)
        task.update(task_input)

        with patch("taskgraph.transforms.run.configure_taskdesc_for_run") as m:
            # This forces the generator to be evaluated
            run_transform(run.transforms, task)
            return m.call_args[0]

    return inner


@pytest.mark.parametrize(
    "task",
    [
        {"worker-type": "t-linux"},
        pytest.param(
            {"worker-type": "releng-hardware/gecko-t-win10-64-hw"},
            marks=pytest.mark.xfail,
        ),
    ],
    ids=["docker-worker", "generic-worker"],
)
def test_worker_caches(task, transform):
    config, task, taskdesc, impl = transform(task)
    add_cache(task, taskdesc, "cache1", "/cache1")
    add_cache(task, taskdesc, "cache2", "/cache2", skip_untrusted=True)

    if impl not in ("docker-worker", "generic-worker"):
        pytest.xfail(f"caches not implemented for '{impl}'")

    key = "caches" if impl == "docker-worker" else "mounts"
    assert key in taskdesc["worker"]
    assert len(taskdesc["worker"][key]) == 2

    # Create a new schema object with just the part relevant to caches.
    partial_schema = Schema(payload_builders[impl].schema.schema[key])
    validate_schema(partial_schema, taskdesc["worker"][key], "validation error")


def assert_use_fetches_toolchain_env(task):
    assert task["worker"]["env"]["FOO"] == "1"


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
