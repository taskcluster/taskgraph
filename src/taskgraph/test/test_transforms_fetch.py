"""
Tests for the 'fetch' transforms.
"""

from copy import deepcopy
from pprint import pprint

import pytest

from taskgraph.transforms import fetch

TASK_DEFAULTS = {
    "description": "fake description",
    "name": "fake-task-name",
}


def assert_static_url(task):
    assert task["run"]["command"] == [
        "fetch-content",
        "static-url",
        "--sha256",
        "abcdef",
        "--size",
        "123",
        "-H",
        "User-Agent:Mozilla",
        "https://example.com/resource",
        "/builds/worker/artifacts/resource",
    ]
    assert task["attributes"]["fetch-artifact"] == "public/resource"


@pytest.mark.parametrize(
    "task_input",
    (
        pytest.param(
            {
                "fetch": {
                    "type": "static-url",
                    "url": "https://example.com/resource",
                    "sha256": "abcdef",
                    "size": 123,
                    "headers": {
                        "User-Agent": "Mozilla",
                    },
                },
            },
            id="static-url",
        ),
    ),
)
def test_transforms(request, run_transform, task_input):
    task = deepcopy(TASK_DEFAULTS)
    task.update(task_input)

    task = run_transform(fetch.transforms, task)[0]
    print("Dumping task:")
    pprint(task, indent=2)

    # Call the assertion function for the given test.
    param_id = request.node.callspec.id
    assertion_func = globals()[f"assert_{param_id.replace('-', '_')}"]
    assertion_func(task)
