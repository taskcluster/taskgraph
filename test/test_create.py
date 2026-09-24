# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import re
import time
import unittest
from concurrent import futures
from unittest import mock

import pytest
import responses

from taskgraph import create
from taskgraph.config import GraphConfig
from taskgraph.create import CreateTasksException
from taskgraph.graph import Graph
from taskgraph.task import Task
from taskgraph.taskgraph import TaskGraph
from taskgraph.util import taskcluster as tc_util

GRAPH_CONFIG = GraphConfig({"trust-domain": "domain"}, "/var/empty")


def mock_taskcluster_api(
    created_tasks=None, error_status=None, error_message=None, error_task_ids=None
):
    """Mock the Taskcluster Queue API for create task calls."""

    def request_callback(request):
        task_id = request.url.split("/")[-1]

        # Check if this task should error
        if error_status is not None:
            if error_task_ids is None or task_id in error_task_ids:
                # Support per-task error messages
                if isinstance(error_message, dict):
                    message = error_message.get(task_id, "error")
                else:
                    message = error_message or "error"
                return (error_status, {}, f'{{"message": "{message}"}}')

        # Success case - capture task definition if requested
        if created_tasks is not None:
            task_def = json.loads(request.body)
            created_tasks[task_id] = task_def

        return (200, {}, f'{{"status": {{"taskId": "{task_id}"}}}}')

    responses.add_callback(
        responses.PUT,
        re.compile(r"https://tc\.example\.com/api/queue/v1/task/.*"),
        callback=request_callback,
        content_type="application/json",
    )


class TestCreate(unittest.TestCase):
    def setUp(self):
        # Clear cached Taskcluster clients/sessions since we're mocking the environment
        tc_util.get_taskcluster_client.cache_clear()
        tc_util.get_session.cache_clear()

    @responses.activate
    @mock.patch.dict(
        "os.environ",
        {"TASKCLUSTER_ROOT_URL": "https://tc.example.com"},
        clear=True,
    )
    def test_create_tasks(self):
        created_tasks = {}
        mock_taskcluster_api(created_tasks=created_tasks)

        tasks = {
            "tid-a": Task(
                kind="test", label="a", attributes={}, task={"payload": "hello world"}
            ),
            "tid-b": Task(
                kind="test", label="b", attributes={}, task={"payload": "hello world"}
            ),
        }
        label_to_taskid = {"a": "tid-a", "b": "tid-b"}
        graph = Graph(nodes={"tid-a", "tid-b"}, edges={("tid-a", "tid-b", "edge")})
        taskgraph = TaskGraph(tasks, graph)

        create.create_tasks(
            GRAPH_CONFIG,
            taskgraph,
            label_to_taskid,
            {"level": "4"},
            decision_task_id="decisiontask",
        )

        assert created_tasks
        for tid, task in created_tasks.items():
            self.assertEqual(task["payload"], "hello world")
            self.assertEqual(task["schedulerId"], "domain-level-4")
            # make sure the dependencies exist, at least
            for depid in task.get("dependencies", []):
                if depid == "decisiontask":
                    # Don't look for decisiontask here
                    continue
                self.assertIn(depid, created_tasks)

    @responses.activate
    @mock.patch.dict(
        "os.environ",
        {"TASKCLUSTER_ROOT_URL": "https://tc.example.com"},
        clear=True,
    )
    def test_create_task_without_dependencies(self):
        "a task with no dependencies depends on the decision task"
        created_tasks = {}
        mock_taskcluster_api(created_tasks=created_tasks)

        tasks = {
            "tid-a": Task(
                kind="test", label="a", attributes={}, task={"payload": "hello world"}
            ),
        }
        label_to_taskid = {"a": "tid-a"}
        graph = Graph(nodes={"tid-a"}, edges=set())
        taskgraph = TaskGraph(tasks, graph)

        create.create_tasks(
            GRAPH_CONFIG,
            taskgraph,
            label_to_taskid,
            {"level": "4"},
            decision_task_id="decisiontask",
        )

        assert created_tasks
        for tid, task in created_tasks.items():
            self.assertEqual(task.get("dependencies"), ["decisiontask"])

    @responses.activate
    @mock.patch.dict(
        "os.environ",
        {"TASKCLUSTER_ROOT_URL": "https://tc.example.com"},
        clear=True,
    )
    def test_create_tasks_fails_if_create_fails(self):
        "create_tasks fails if a single create_task call fails"
        mock_taskcluster_api(error_status=403, error_message="oh no!")

        tasks = {
            "tid-a": Task(
                kind="test", label="a", attributes={}, task={"payload": "hello world"}
            ),
        }
        label_to_taskid = {"a": "tid-a"}
        graph = Graph(nodes={"tid-a"}, edges=set())
        taskgraph = TaskGraph(tasks, graph)

        with self.assertRaises(CreateTasksException):
            create.create_tasks(
                GRAPH_CONFIG,
                taskgraph,
                label_to_taskid,
                {"level": "4"},
                decision_task_id="decisiontask",
            )

    @responses.activate
    @mock.patch.dict(
        "os.environ",
        {"TASKCLUSTER_ROOT_URL": "https://tc.example.com"},
        clear=True,
    )
    def test_create_tasks_collects_multiple_errors(self):
        "create_tasks collects all errors from multiple failing tasks"
        mock_taskcluster_api(
            error_status=409,
            error_message={
                "tid-a": "scope error for task a",
                "tid-b": "scope error for task b",
            },
            error_task_ids={"tid-a", "tid-b"},
        )

        tasks = {
            "tid-a": Task(
                kind="test", label="a", attributes={}, task={"payload": "hello world"}
            ),
            "tid-b": Task(
                kind="test", label="b", attributes={}, task={"payload": "hello world"}
            ),
        }
        label_to_taskid = {"a": "tid-a", "b": "tid-b"}
        graph = Graph(nodes={"tid-a", "tid-b"}, edges=set())
        taskgraph = TaskGraph(tasks, graph)

        with self.assertRaises(CreateTasksException) as cm:
            create.create_tasks(
                GRAPH_CONFIG,
                taskgraph,
                label_to_taskid,
                {"level": "4"},
                decision_task_id="decisiontask",
            )

        # Verify both errors are in the exception message
        exception_message = str(cm.exception)
        self.assertIn("Could not create 'a'", exception_message)
        self.assertIn("Could not create 'b'", exception_message)

    @responses.activate
    @mock.patch.dict(
        "os.environ",
        {"TASKCLUSTER_ROOT_URL": "https://tc.example.com"},
        clear=True,
    )
    def test_create_tasks_fails_if_done_callback_is_slow(self):
        "create_tasks fails even if done-callbacks run after futures.wait() returns"
        mock_taskcluster_api(error_status=403, error_message="oh no!")

        tasks = {
            "tid-a": Task(
                kind="test", label="a", attributes={}, task={"payload": "hello world"}
            ),
        }
        label_to_taskid = {"a": "tid-a"}
        graph = Graph(nodes={"tid-a"}, edges=set())
        taskgraph = TaskGraph(tasks, graph)

        real_add_done_callback = futures.Future.add_done_callback

        def slow_add_done_callback(self, fn):
            def wrapper(fut):
                time.sleep(0.1)
                fn(fut)

            return real_add_done_callback(self, wrapper)

        with mock.patch.object(
            futures.Future, "add_done_callback", slow_add_done_callback
        ):
            with self.assertRaises(CreateTasksException):
                create.create_tasks(
                    GRAPH_CONFIG,
                    taskgraph,
                    label_to_taskid,
                    {"level": "4"},
                    decision_task_id="decisiontask",
                )


def _chain_taskgraph(n):
    """Build a taskgraph where tid-i depends on tid-(i-1)."""
    tasks = {}
    for i in range(n):
        deps = [f"tid-{i - 1}"] if i else []
        tasks[f"tid-{i}"] = Task(
            kind="test", label=f"t{i}", attributes={}, task={"dependencies": deps}
        )
    edges = {(f"tid-{i}", f"tid-{i - 1}", "dep") for i in range(1, n)}
    taskgraph = TaskGraph(tasks, Graph(nodes=set(tasks), edges=edges))
    label_to_taskid = {t.label: tid for tid, t in tasks.items()}
    return taskgraph, label_to_taskid


def test_create_tasks_long_chain(mocker):
    "tasks are created after their dependencies, even in very deep graphs"
    mocker.patch.object(create, "get_session")
    created = []
    mocker.patch.object(
        create,
        "create_task",
        side_effect=lambda session, task_id, label, task_def: created.append(task_id),
    )

    n = 3000
    taskgraph, label_to_taskid = _chain_taskgraph(n)
    create.create_tasks(
        GRAPH_CONFIG, taskgraph, label_to_taskid, {"level": "4"}, "decisiontask"
    )

    assert created == [f"tid-{i}" for i in range(n)]
    assert taskgraph.tasks["tid-0"].task["dependencies"] == ["decisiontask"]
    assert taskgraph.tasks["tid-1"].task["dependencies"] == ["tid-0"]


def test_create_tasks_skips_dependents_of_failed_tasks(mocker):
    "tasks depending on a task that failed to be created are not submitted"
    mocker.patch.object(create, "get_session")
    created = []

    def fake_create_task(session, task_id, label, task_def):
        if task_id == "tid-1":
            raise Exception("oh no!")
        created.append(task_id)

    mocker.patch.object(create, "create_task", side_effect=fake_create_task)

    taskgraph, label_to_taskid = _chain_taskgraph(4)
    with pytest.raises(CreateTasksException) as excinfo:
        create.create_tasks(
            GRAPH_CONFIG, taskgraph, label_to_taskid, {"level": "4"}, "decisiontask"
        )

    assert created == ["tid-0"]
    assert "Could not create 't1'" in str(excinfo.value)
    assert "'t2'" not in str(excinfo.value)


def test_create_tasks_duplicates(mocker):
    "tasks with the task_duplicates attribute are created multiple times"
    mocker.patch.object(create, "get_session")
    created = []
    mocker.patch.object(
        create,
        "create_task",
        side_effect=lambda session, task_id, label, task_def: created.append(
            (task_id, label)
        ),
    )

    taskgraph, label_to_taskid = _chain_taskgraph(2)
    taskgraph.tasks["tid-0"].attributes["task_duplicates"] = 3
    create.create_tasks(
        GRAPH_CONFIG, taskgraph, label_to_taskid, {"level": "4"}, "decisiontask"
    )

    labels = [label for _, label in created]
    assert labels.count("t0") == 3
    assert labels.count("t1") == 1
    assert len({task_id for task_id, _ in created}) == 4
    # t1 is only created once the primary t0 task was created.
    assert labels.index("t1") > created.index(("tid-0", "t0"))
