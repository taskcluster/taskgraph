"""
Tests for the 'fetch' transforms.
"""

import os.path
from copy import deepcopy
from pprint import pprint

from taskgraph.transforms import task_context
from taskgraph.transforms.base import TransformConfig

from .conftest import FakeParameters

here = os.path.abspath(os.path.dirname(__file__))

TASK_DEFAULTS = {
    "description": "fake description {object} {file} {param} {object_and_file}"
    "{object_and_param} {file_and_param} {object_file_and_param} {param_fallback}",
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


def test_transforms(request, run_transform, graph_config):
    task = deepcopy(TASK_DEFAULTS)

    params = FakeParameters(
        {
            "param": "param",
            "object_and_param": "param-overrides-object",
            "file_and_param": "param-overrides-file",
            "object_file_and_param": "param-overrides-all",
            "default": "default",
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
        },
    )
    transform_config = TransformConfig(
        "test", str(here), {}, params, {}, graph_config, write_artifacts=False
    )

    task = run_transform(task_context.transforms, task, config=transform_config)[0]
    print("Dumping task:")
    pprint(task, indent=2)

    assert (
        task["description"]
        == "fake description object file param object-overrides-file"
        "param-overrides-object param-overrides-file param-overrides-all default"
    )
