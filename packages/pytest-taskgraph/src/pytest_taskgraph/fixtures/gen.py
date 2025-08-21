from pathlib import Path

import pytest

from taskgraph import generator
from taskgraph import target_tasks as target_tasks_mod
from taskgraph.config import GraphConfig
from taskgraph.generator import Kind, TaskGraphGenerator
from taskgraph.graph import Graph
from taskgraph.optimize import OptimizationStrategy
from taskgraph.optimize import base as optimize_mod
from taskgraph.task import Task
from taskgraph.taskgraph import TaskGraph
from taskgraph.transforms.base import TransformConfig
from taskgraph.util.templates import merge

here = Path(__file__).parent


def fake_loader(kind, path, config, parameters, loaded_tasks):
    for i in range(3):
        dependencies = {}
        if i >= 1:
            dependencies["prev"] = f"{kind}-t-{i - 1}"

        task = {
            "kind": kind,
            "label": f"{kind}-t-{i}",
            "description": f"{kind} task {i}",
            "attributes": {"_tasknum": str(i)},
            "task": {
                "i": i,
                "metadata": {"name": f"{kind}-t-{i}"},
                "deadline": "soon",
            },
            "dependencies": dependencies,
        }
        if "task-defaults" in config:
            task = merge(config["task-defaults"], task)
        yield task


class FakeKind(Kind):
    loaded_kinds = []

    def _get_loader(self):
        return fake_loader

    def load_tasks(self, parameters, loaded_tasks, write_artifacts):
        FakeKind.loaded_kinds.append(self.name)
        return super().load_tasks(parameters, loaded_tasks, write_artifacts)


class WithFakeKind(TaskGraphGenerator):
    def _load_kinds(self, graph_config, target_kind=None):
        for kind_name, cfg in self.parameters["_kinds"]:
            config = {
                "transforms": [],
            }
            if cfg:
                config.update(cfg)
            yield FakeKind(kind_name, "/fake", config, graph_config)


def fake_load_graph_config(root_dir):
    graph_config = GraphConfig(
        {
            "trust-domain": "test-domain",
            "taskgraph": {
                "repositories": {
                    "ci": {"name": "Taskgraph"},
                }
            },
            "workers": {
                "aliases": {
                    "b-linux": {
                        "provisioner": "taskgraph-b",
                        "implementation": "docker-worker",
                        "os": "linux",
                        "worker-type": "linux",
                    },
                    "t-linux": {
                        "provisioner": "taskgraph-t",
                        "implementation": "docker-worker",
                        "os": "linux",
                        "worker-type": "linux",
                    },
                    "t-win": {
                        "provisioner": "taskgraph-t",
                        "implementation": "generic-worker",
                        "os": "windows",
                        "worker-type": "win",
                    },
                }
            },
            "task-priority": "low",
            "treeherder": {"group-names": {"T": "tests"}},
            "index": {
                "products": [
                    "fake",
                ],
            },
        },
        root_dir,
    )
    graph_config.__dict__["register"] = lambda: None
    return graph_config


@pytest.fixture
def graph_config(datadir):
    return fake_load_graph_config(str(datadir / "taskcluster"))


class FakeParameters(dict):
    strict = True

    def is_try(self):
        return self["level"] != 3

    def file_url(self, path, pretty=False):
        return path


class FakeOptimization(OptimizationStrategy):
    def __init__(self, mode, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode

    def should_remove_task(self, task, params, arg):
        if self.mode == "always":
            return True
        if self.mode == "even":
            return task.task["i"] % 2 == 0
        if self.mode == "odd":
            return task.task["i"] % 2 != 0
        return False


@pytest.fixture
def parameters():
    return FakeParameters(
        {
            "base_repository": "http://hg.example.com",
            "build_date": 0,
            "build_number": 1,
            "enable_always_target": True,
            "files_changed": [],
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
    )


@pytest.fixture
def maketgg(monkeypatch, parameters):
    def inner(target_tasks=None, kinds=None, params=None, enable_verifications=True):
        kinds = kinds or [("_fake", [])]
        params = params or {}
        FakeKind.loaded_kinds = []
        target_tasks = target_tasks or []

        def target_tasks_method(full_task_graph, parameters, graph_config):
            return target_tasks

        fake_strategies = {
            mode: FakeOptimization(mode) for mode in ("always", "never", "even", "odd")
        }

        target_tasks_mod._target_task_methods["test_method"] = target_tasks_method
        monkeypatch.setattr(optimize_mod, "registry", fake_strategies)

        parameters["_kinds"] = kinds
        parameters.update(params)

        monkeypatch.setattr(generator, "load_graph_config", fake_load_graph_config)

        return WithFakeKind(
            "/root", parameters, enable_verifications=enable_verifications
        )

    return inner


@pytest.fixture
def make_transform_config(parameters, graph_config):
    def inner(
        kind_config=None,
        kind_dependencies_tasks=None,
        extra_params=None,
        extra_graph_config=None,
    ):
        kind_config = kind_config or {}
        kind_dependencies_tasks = kind_dependencies_tasks or {}
        if extra_params:
            parameters.update(extra_params)
        if extra_graph_config:
            # We need this intermediate variable because `GraphConfig` is
            # frozen and we can't set attributes on it.
            new_graph_config = merge(graph_config._config, extra_graph_config)
            graph_config._config.update(new_graph_config)

        return TransformConfig(
            "test",
            str(here),
            kind_config,
            parameters,
            kind_dependencies_tasks,
            graph_config,
            write_artifacts=False,
        )

    return inner


@pytest.fixture
def run_transform(make_transform_config):
    def inner(func, tasks, config=None, **kwargs):
        if not isinstance(tasks, list):
            tasks = [tasks]

        if not config:
            config = make_transform_config(**kwargs)
        return list(func(config, tasks))

    return inner


def make_task(
    label,
    kind="test",
    optimization=None,
    task_def=None,
    task_id=None,
    dependencies=None,
    if_dependencies=None,
    attributes=None,
):
    task_def = task_def or {
        "sample": "task-def",
        "deadline": {"relative-datestamp": "1 hour"},
    }
    task = Task(
        attributes=attributes or {},
        if_dependencies=if_dependencies or [],
        kind=kind,
        label=label,
        task=task_def,
    )
    task.optimization = optimization
    task.task_id = task_id
    if dependencies is not None:
        task.task["dependencies"] = sorted(dependencies)
    return task


def make_graph(*tasks_and_edges, **kwargs):
    tasks = {t.label: t for t in tasks_and_edges if isinstance(t, Task)}
    edges = {e for e in tasks_and_edges if not isinstance(e, Task)}
    tg = TaskGraph(tasks, Graph(set(tasks), edges))

    if kwargs.get("deps", True):
        # set dependencies based on edges
        for l, r, name in tg.graph.edges:
            tg.tasks[l].dependencies[name] = r

    return tg
