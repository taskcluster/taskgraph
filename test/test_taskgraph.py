# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import unittest

from taskgraph.graph import Graph
from taskgraph.task import Task
from taskgraph.taskgraph import TaskGraph


class TestTaskGraph(unittest.TestCase):
    maxDiff = None

    def test_taskgraph_to_json(self):
        tasks = {
            "a": Task(
                kind="test",
                label="a",
                attributes={"attr": "a-task"},
                task={"taskdef": True},
                dependencies={"edgelabel": "b"},
            ),
            "b": Task(
                kind="test",
                label="b",
                attributes={},
                task={"task": "def"},
                optimization={"seta": None},
                dependencies={"first": "a"},
            ),
        }
        graph = Graph(nodes=set("ab"), edges={("a", "b", "edgelabel")})
        taskgraph = TaskGraph(tasks, graph)

        res = taskgraph.to_json()

        self.assertEqual(
            res,
            {
                "a": {
                    "kind": "test",
                    "label": "a",
                    "attributes": {"attr": "a-task", "kind": "test"},
                    "task": {"taskdef": True},
                    "dependencies": {"edgelabel": "b"},
                    "description": "",
                    "soft_dependencies": [],
                    "if_dependencies": [],
                    "optimization": None,
                },
                "b": {
                    "kind": "test",
                    "label": "b",
                    "attributes": {"kind": "test"},
                    "task": {"task": "def"},
                    "dependencies": {"first": "a"},
                    "description": "",
                    "soft_dependencies": [],
                    "if_dependencies": [],
                    "optimization": {"seta": None},
                },
            },
        )

    def test_round_trip(self):
        graph = TaskGraph(
            tasks={
                "a": Task(
                    kind="fancy",
                    label="a",
                    attributes={},
                    dependencies={"prereq": "b"},  # must match edges, below
                    optimization={"seta": None},
                    task={"task": "def"},
                ),
                "b": Task(
                    kind="pre",
                    label="b",
                    attributes={},
                    dependencies={},
                    optimization={"seta": None},
                    task={"task": "def2"},
                ),
            },
            graph=Graph(nodes={"a", "b"}, edges={("a", "b", "prereq")}),
        )

        tasks, new_graph = TaskGraph.from_json(graph.to_json())
        self.assertEqual(graph, new_graph)

    def test_from_json_skips_external_dep_references(self):
        # Optimized/morphed graphs may carry Task.dependencies entries
        # pointing at taskIds of replaced or cached tasks that aren't part
        # of the graph itself. from_json must keep those references on the
        # Task while excluding them from the Graph's edge set.
        tasks_dict = {
            "a": {
                "kind": "fancy",
                "label": "a",
                "attributes": {},
                "task": {"task": "def"},
                "dependencies": {"prereq": "b", "external": "EXT_TASKID"},
                "soft_dependencies": [],
                "if_dependencies": [],
                "optimization": None,
                "description": "",
            },
            "b": {
                "kind": "pre",
                "label": "b",
                "attributes": {},
                "task": {"task": "def2"},
                "dependencies": {},
                "soft_dependencies": [],
                "if_dependencies": [],
                "optimization": None,
                "description": "",
            },
        }
        tasks, new_graph = TaskGraph.from_json(tasks_dict)
        self.assertEqual(new_graph.graph.nodes, frozenset({"a", "b"}))
        self.assertEqual(new_graph.graph.edges, {("a", "b", "prereq")})
        self.assertEqual(
            tasks["a"].dependencies, {"prereq": "b", "external": "EXT_TASKID"}
        )

    simple_graph = TaskGraph(
        tasks={
            "a": Task(
                kind="fancy",
                label="a",
                attributes={},
                dependencies={"prereq": "b"},  # must match edges, below
                optimization={"seta": None},
                task={"task": "def"},
            ),
            "b": Task(
                kind="pre",
                label="b",
                attributes={},
                dependencies={},
                optimization={"seta": None},
                task={"task": "def2"},
            ),
        },
        graph=Graph(nodes={"a", "b"}, edges={("a", "b", "prereq")}),
    )

    def test_contains(self):
        assert "a" in self.simple_graph
        assert "c" not in self.simple_graph
