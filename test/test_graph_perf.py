# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Benchmarks for taskgraph core operations on graphs with ~1000 tasks."""

import copy

import pytest

from taskgraph.graph import Graph
from taskgraph.task import Task
from taskgraph.taskgraph import TaskGraph
from taskgraph.transforms.base import TransformSequence

# ---------------------------------------------------------------------------
# Graph builders – each returns (tasks_dict, Graph, TaskGraph) for 1000 nodes
# ---------------------------------------------------------------------------

N = 1000


def _make_task(i):
    return Task(
        kind="test",
        label=f"task-{i}",
        attributes={"idx": i},
        task={"metadata": {"name": f"task-{i}"}},
    )


def _build_linear():
    """Chain: task-0 <- task-1 <- ... <- task-999."""
    tasks = {f"task-{i}": _make_task(i) for i in range(N)}
    edges = {(f"task-{i}", f"task-{i - 1}", "dep") for i in range(1, N)}
    g = Graph(set(tasks), edges)
    return tasks, g, TaskGraph(tasks, g)


def _build_fan_out_fan_in():
    """One root fans out to 998 middle tasks, which all feed into one sink.

    task-0 (root)
       |---> task-1 --+
       |---> task-2 --+--> task-999 (sink)
       ...            |
       `---> task-998 +
    """
    tasks = {f"task-{i}": _make_task(i) for i in range(N)}
    edges = set()
    for i in range(1, N - 1):
        edges.add((f"task-{i}", "task-0", "root"))
    for i in range(1, N - 1):
        edges.add((f"task-{N - 1}", f"task-{i}", "mid"))
    g = Graph(set(tasks), edges)
    return tasks, g, TaskGraph(tasks, g)


def _build_binary_tree():
    """Complete-ish binary tree with ~1000 nodes (children depend on parent)."""
    tasks = {f"task-{i}": _make_task(i) for i in range(N)}
    edges = set()
    for i in range(1, N):
        parent = (i - 1) // 2
        edges.add((f"task-{i}", f"task-{parent}", "parent"))
    g = Graph(set(tasks), edges)
    return tasks, g, TaskGraph(tasks, g)


def _build_diamond_layers():
    """Layered diamond: 10 layers of 100 tasks each; every task in layer L
    depends on every task in layer L-1 (100x100 edges between adjacent layers).

    This is 1000 tasks with 9 * 100 * 100 = 90 000 edges - a dense graph.
    """
    layer_size = 100
    num_layers = N // layer_size
    tasks = {f"task-{i}": _make_task(i) for i in range(N)}
    edges = set()
    for layer in range(1, num_layers):
        for i in range(layer_size):
            node = layer * layer_size + i
            for j in range(layer_size):
                dep = (layer - 1) * layer_size + j
                edges.add((f"task-{node}", f"task-{dep}", f"l{layer}-{j}"))
    g = Graph(set(tasks), edges)
    return tasks, g, TaskGraph(tasks, g)


# Pre-build the fixtures so construction cost isn't part of every benchmark
LINEAR = _build_linear()
FAN = _build_fan_out_fan_in()
BTREE = _build_binary_tree()
DIAMOND = _build_diamond_layers()

GEOMETRIES = {
    "linear": LINEAR,
    "fan": FAN,
    "btree": BTREE,
    "diamond": DIAMOND,
}


# ---------------------------------------------------------------------------
# Benchmarks – Graph.transitive_closure
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.parametrize("geometry", ["linear", "fan", "btree", "diamond"])
def test_transitive_closure(geometry):
    _, graph, _ = GEOMETRIES[geometry]
    # Pick a node roughly in the middle so the closure is non-trivial
    result = graph.transitive_closure({f"task-{N // 2}"})
    assert len(result.nodes) > 0


# ---------------------------------------------------------------------------
# Benchmarks – Graph.visit_postorder / visit_preorder
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.parametrize("geometry", ["linear", "fan", "btree", "diamond"])
def test_visit_postorder(geometry):
    _, graph, _ = GEOMETRIES[geometry]
    order = list(graph.visit_postorder())
    assert len(order) == N


@pytest.mark.benchmark
@pytest.mark.parametrize("geometry", ["linear", "fan", "btree", "diamond"])
def test_visit_preorder(geometry):
    _, graph, _ = GEOMETRIES[geometry]
    order = list(graph.visit_preorder())
    assert len(order) == N


# ---------------------------------------------------------------------------
# Benchmarks – Graph link dictionaries
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.parametrize("geometry", ["linear", "fan", "btree", "diamond"])
def test_links_dict(geometry):
    _, graph, _ = GEOMETRIES[geometry]
    # Clear the functools.cache to measure actual computation each time
    graph.links_and_reverse_links_dict.cache_clear()
    fwd, rev = graph.links_and_reverse_links_dict()
    assert len(fwd) == N
    assert len(rev) == N


# ---------------------------------------------------------------------------
# Benchmarks – TaskGraph.for_each_task
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.parametrize("geometry", ["linear", "fan", "btree", "diamond"])
def test_for_each_task(geometry):
    _, _, tg = GEOMETRIES[geometry]
    visited = []
    tg.for_each_task(lambda task, _tg: visited.append(task.label))
    assert len(visited) == N


# ---------------------------------------------------------------------------
# Benchmarks – TaskGraph JSON round-trip
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.parametrize("geometry", ["linear", "fan", "btree"])
def test_taskgraph_to_json(geometry):
    _, _, tg = GEOMETRIES[geometry]
    data = tg.to_json()
    assert len(data) == N


# ---------------------------------------------------------------------------
# Benchmarks – TransformSequence with a simple transform
# ---------------------------------------------------------------------------


transforms = TransformSequence()


@transforms.add
def add_worker_type(config, tasks):
    """A small transform that adds a field to every task dict."""
    for task in tasks:
        task = copy.copy(task)
        task["worker-type"] = f"b-linux-{task.get('idx', 0) % 4}"
        yield task


@transforms.add
def add_env_vars(config, tasks):
    """Another small transform that adds environment variables."""
    for task in tasks:
        task.setdefault("env", {})
        task["env"]["TASK_ID"] = task.get("name", "unknown")
        task["env"]["PRIORITY"] = "high" if task.get("idx", 0) % 10 == 0 else "low"
        yield task


@pytest.mark.benchmark
def test_transform_sequence():
    task_dicts = [
        {"name": f"task-{i}", "idx": i, "payload": {"command": f"echo {i}"}}
        for i in range(N)
    ]
    result = list(transforms(None, task_dicts))
    assert len(result) == N
    assert "worker-type" in result[0]
    assert "env" in result[0]
