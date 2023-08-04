"""
Tests for the 'fetch' transforms.
"""

from copy import deepcopy
from pprint import pprint

from taskgraph.transforms import chunking

TASK_DEFAULTS = {
    "description": "fake description {this_chunk}/{total_chunks}",
    "name": "fake-task-name",
    "chunk": {
        "total-chunks": 2,
        "substitution-fields": [
            "description",
        ],
    },
}


def assert_chunked_task(task, chunk):
    assert task["description"] == f"fake description {chunk}/2"


def test_transforms(request, run_transform):
    task = deepcopy(TASK_DEFAULTS)

    tasks = run_transform(chunking.transforms, task)
    print("Dumping tasks:")
    pprint(tasks, indent=2)

    assert len(tasks) == 2, "Chunking should've generated 2 tasks"
    assert_chunked_task(tasks[0], 1)
    assert_chunked_task(tasks[1], 2)
