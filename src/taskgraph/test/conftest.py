import os

import pytest
from responses import RequestsMock

from taskgraph import generator
from taskgraph import optimize as optimize_mod
from taskgraph import target_tasks as target_tasks_mod
from taskgraph.config import GraphConfig
from taskgraph.generator import Kind, TaskGraphGenerator
from taskgraph.optimize import OptimizationStrategy
from taskgraph.transforms.base import TransformConfig
from taskgraph.util.templates import merge

here = os.path.abspath(os.path.dirname(__file__))


@pytest.fixture
def responses():
    with RequestsMock() as rsps:
        yield rsps


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
                "metadata": {"name": f"t-{i}"},
                "deadline": "soon",
            },
            "dependencies": dependencies,
        }
        if "job-defaults" in config:
            task = merge(config["job-defaults"], task)
        yield task


class FakeKind(Kind):
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
                    "t-linux": {
                        "provisioners": "taskgraph-t",
                        "implementation": "docker-worker",
                        "os": "linux",
                        "worker-type": "linux",
                    }
                }
            },
        },
        root_dir,
    )
    graph_config.__dict__["register"] = lambda: None
    return graph_config


class FakeParameters(dict):
    strict = True


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
            "head_repository": "http://hg.example.com",
            "head_rev": "abcdef",
            "head_ref": "abcdef",
            "level": 1,
            "project": "",
            "repository_type": "hg",
            "target_tasks_method": "test_method",
            "tasks_for": "hg-push",
            "try_mode": None,
        }
    )


@pytest.fixture
def maketgg(monkeypatch, parameters):
    def inner(target_tasks=None, kinds=[("_fake", [])], params=None):
        params = params or {}
        FakeKind.loaded_kinds = []
        target_tasks = target_tasks or []

        def target_tasks_method(full_task_graph, parameters, graph_config):
            return target_tasks

        def make_fake_strategies():
            return {
                mode: FakeOptimization(mode)
                for mode in ("always", "never", "even", "odd")
            }

        target_tasks_mod._target_task_methods["test_method"] = target_tasks_method
        monkeypatch.setattr(
            optimize_mod, "_make_default_strategies", make_fake_strategies
        )

        parameters["_kinds"] = kinds
        parameters.update(params)

        monkeypatch.setattr(generator, "load_graph_config", fake_load_graph_config)

        return WithFakeKind("/root", parameters)

    return inner


@pytest.fixture
def transform_config(parameters):
    graph_config = fake_load_graph_config(os.path.join("taskcluster", "ci"))
    return TransformConfig(
        "test", here, {}, parameters, {}, graph_config, write_artifacts=False
    )


@pytest.fixture
def run_transform(transform_config):
    def inner(func, tasks):
        if not isinstance(tasks, list):
            tasks = [tasks]

        return list(func(transform_config, tasks))

    return inner
