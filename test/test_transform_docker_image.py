"""
Tests for the 'docker_image' transforms.
"""

import unittest
from copy import deepcopy

import pytest

from taskgraph.transforms import docker_image

TASK_DEFAULTS = {
    "name": "fake-name",
    "index": {
        "product": "fake-prod",
        "job-name": "fake-job-name",
        "type": "fake-type",
        "rank": 1,
    },
}


@pytest.mark.parametrize(
    "task_input, extra_params, expected_task_output",
    (
        pytest.param({}, {}, {"always-target": True}, id="null"),
        pytest.param(
            {"parent": "fake-parent"},
            {},
            {"dependencies": {"parent": "build-docker-image-fake-parent"}},
            id="parent",
        ),
        pytest.param(
            {"symbol": "fake-symbol"},
            {},
            {
                "treeherder": {
                    "symbol": "fake-symbol",
                    "platform": "taskcluster-images/opt",
                    "kind": "other",
                    "tier": 1,
                }
            },
            id="symbol",
        ),
    ),
)
@unittest.mock.patch(
    "taskgraph.transforms.docker_image.generate_context_hash",
    unittest.mock.MagicMock(),
)
def test_transforms(
    make_transform_config, run_transform, task_input, extra_params, expected_task_output
):
    task = deepcopy(TASK_DEFAULTS)
    task.update(task_input)

    config = make_transform_config()
    config.params.update(extra_params)

    expected_task_output["label"] = "build-docker-image-" + task["name"]
    expected_task_output["index"] = task["index"]
    expected_task_output["description"] = (
        "Build the docker image {} for use by dependent tasks".format(task["name"])
    )
    assert (
        expected_task_output.items()
        <= run_transform(docker_image.transforms, task, config)[0].items()
    )
