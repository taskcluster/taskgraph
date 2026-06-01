"""
Tests for the 'task_context' transforms.
"""

import os.path
from copy import deepcopy
from pprint import pprint

import pytest
from pytest_taskgraph import FakeParameters

from taskgraph.transforms import task_context
from taskgraph.transforms.base import TransformConfig

here = os.path.abspath(os.path.dirname(__file__))

BASE_PARAMS = {
    "base_repository": "http://hg.example.com",
    "build_date": 0,
    "build_number": 1,
    "enable_always_target": True,
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
}


def make_config(graph_config, extra_params=None):
    params_data = dict(BASE_PARAMS)
    if extra_params:
        params_data.update(extra_params)
    params = FakeParameters(params_data)
    return TransformConfig(
        "test", str(here), {}, params, {}, graph_config, write_artifacts=False
    )


TASK_DEFAULTS = {
    "description": "fake description {object} {file} {param} {object_and_file} "
    "{object_and_param} {file_and_param} {object_file_and_param} {param_fallback} {name}",
    "name": "fake-task-name",
    "task-context": {
        "from-parameters": {
            "param": "param",
            "object_and_param": "object_and_param",
            "file_and_param": "file_and_param",
            "object_file_and_param": "object_file_and_param",
            "param_fallback": ["missing-param", "default"],
        },
        "from-file": f"{here}/data/task_context.yml",
        "from-object": {
            "object": "object",
            "object_and_param": "shouldn't be used",
            "object_and_file": "object-overrides-file",
            "object_file_and_param": "shouldn't be used",
        },
        "substitution-fields": [
            "description",
        ],
    },
}
EXPECTED_DESCRIPTION = (
    "fake description object file param object-overrides-file "
    "param-overrides-object param-overrides-file param-overrides-all default fake-task-name"
)
NO_CONTEXT = deepcopy(TASK_DEFAULTS)
del NO_CONTEXT["task-context"]


@pytest.mark.parametrize(
    "task,description",
    (
        pytest.param(deepcopy(TASK_DEFAULTS), EXPECTED_DESCRIPTION, id="with-context"),
        pytest.param(
            deepcopy(NO_CONTEXT), TASK_DEFAULTS["description"], id="no-context"
        ),
    ),
)
def test_transforms(request, run_transform, graph_config, task, description):
    config = make_config(
        graph_config,
        {
            "param": "param",
            "object_and_param": "param-overrides-object",
            "file_and_param": "param-overrides-file",
            "object_file_and_param": "param-overrides-all",
            "default": "default",
        },
    )

    task = run_transform(task_context.transforms, task, config=config)[0]
    print("Dumping task:")
    pprint(task, indent=2)

    assert task["description"] == description


def test_resolve_keyed_by_from_parameters(run_transform, graph_config):
    task = {
        "name": "fake-task-name",
        "description": {
            "by-platform": {
                "linux": "resolved-from-parameters",
                "default": "default-value",
            },
        },
        "task-context": {
            "from-parameters": {"platform": "platform"},
            "substitution-fields": ["description"],
        },
    }
    config = make_config(graph_config, {"platform": "linux"})

    task = run_transform(task_context.transforms, task, config=config)[0]
    pprint(task, indent=2)

    assert task["description"] == "resolved-from-parameters"


def test_resolve_keyed_by_from_file(run_transform, graph_config):
    task = {
        "name": "fake-task-name",
        "description": {
            "by-file": {
                "file": "resolved-from-file",
                "default": "default-value",
            },
        },
        "task-context": {
            "from-file": f"{here}/data/task_context.yml",
            "substitution-fields": ["description"],
        },
    }
    config = make_config(graph_config)

    task = run_transform(task_context.transforms, task, config=config)[0]
    pprint(task, indent=2)

    assert task["description"] == "resolved-from-file"


def test_resolve_keyed_by_from_object(run_transform, graph_config):
    task = {
        "name": "fake-task-name",
        "description": {
            "by-flavor": {
                "chocolate": "resolved-from-object",
                "default": "default-value",
            },
        },
        "task-context": {
            "from-object": {"flavor": "chocolate"},
            "substitution-fields": ["description"],
        },
    }
    config = make_config(graph_config)

    task = run_transform(task_context.transforms, task, config=config)[0]
    pprint(task, indent=2)

    assert task["description"] == "resolved-from-object"


def test_resolve_keyed_by_missing_context_no_defer(run_transform, graph_config):
    task = {
        "name": "fake-task-name",
        "description": {
            "by-missing": {
                "linux": "should-not-resolve",
            },
        },
        "task-context": {
            "substitution-fields": ["description"],
        },
    }
    config = make_config(graph_config)

    with pytest.raises(Exception):
        run_transform(task_context.transforms, task, config=config)


def test_resolve_keyed_by_missing_context_with_defer(run_transform, graph_config):
    task = {
        "name": "fake-task-name",
        "description": {
            "by-flavor": {
                "chocolate": {
                    "by-missing": {
                        "linux": "should-not-resolve",
                        "default": "also-should-not-resolve",
                    },
                },
            },
        },
        "task-context": {
            "from-object": {"flavor": "chocolate"},
            "resolve-keyed-by-options": {"defer": ["missing"]},
            "substitution-fields": ["description"],
        },
    }
    config = make_config(graph_config)

    task = run_transform(task_context.transforms, task, config=config)[0]
    pprint(task, indent=2)

    assert task["description"] == {
        "by-missing": {
            "linux": "should-not-resolve",
            "default": "also-should-not-resolve",
        },
    }
