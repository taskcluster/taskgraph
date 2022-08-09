# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os

import pytest

from taskgraph import morph
from taskgraph.config import load_graph_config
from taskgraph.graph import Graph
from taskgraph.parameters import Parameters
from taskgraph.task import Task
from taskgraph.taskgraph import TaskGraph


@pytest.fixture(scope="module")
def graph_config():
    return load_graph_config(os.path.join("taskcluster", "ci"))


@pytest.fixture
def make_taskgraph():
    def inner(tasks):
        label_to_taskid = {k: k + "-tid" for k in tasks}
        for label, task_id in label_to_taskid.items():
            tasks[label].task_id = task_id
        graph = Graph(nodes=set(tasks), edges=set())
        taskgraph = TaskGraph(tasks, graph)
        return taskgraph, label_to_taskid

    return inner


def test_make_index_tasks(make_taskgraph, graph_config):
    task_def = {
        "routes": [
            "index.gecko.v2.mozilla-central.*",
        ],
        "deadline": "soon",
        "metadata": {
            "description": "desc",
            "owner": "owner@foo.com",
            "source": "https://source",
        },
        "extra": {
            "index": {"rank": 1540722354},
        },
    }
    task = Task(kind="test", label="a", attributes={}, task=task_def)
    docker_task = Task(
        kind="docker-image",
        label="build-docker-image-index-task",
        attributes={},
        task={},
    )
    taskgraph, label_to_taskid = make_taskgraph(
        {
            task.label: task,
            docker_task.label: docker_task,
        }
    )

    index_task, _, _ = morph.make_index_task(
        task, taskgraph, label_to_taskid, Parameters(strict=False), graph_config
    )

    assert index_task.task["payload"]["command"][0] == "insert-indexes.js"
    assert index_task.task["payload"]["env"]["TARGET_TASKID"] == "a-tid"
    assert index_task.task["payload"]["env"]["INDEX_RANK"] == 1540722354

    # check the scope summary
    assert index_task.task["scopes"] == ["index:insert-task:gecko.v2.mozilla-central.*"]


def test_register_morph(monkeypatch, make_taskgraph):
    taskgraph, label_to_taskid = make_taskgraph({})
    monkeypatch.setattr(morph, "registered_morphs", [])

    @morph.register_morph
    def fake_morph(taskgraph, label_to_taskid, *args):
        label_to_taskid.setdefault("count", 0)
        label_to_taskid["count"] += 1
        return taskgraph, label_to_taskid

    assert label_to_taskid == {}
    morph.morph(taskgraph, label_to_taskid, None, None)
    assert label_to_taskid == {"count": 1}
