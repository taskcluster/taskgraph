# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os
import platform
import signal
import time
from concurrent.futures import ProcessPoolExecutor

import pytest
from pytest_taskgraph import WithFakeKind, fake_load_graph_config
from pytest_taskgraph.fixtures.gen import FakeKind

from taskgraph import generator, graph
from taskgraph.generator import Kind, load_tasks_for_kind, load_tasks_for_kinds
from taskgraph.loader.default import loader as default_loader
from taskgraph.util.schema import SchemaValidationError

linuxonly = pytest.mark.skipif(
    platform.system() != "Linux"
    or os.environ.get("TASKGRAPH_USE_THREADS")
    or os.environ.get("TASKGRAPH_SERIAL"),
    reason="requires Linux multiprocessing support",
)
threadsonly = pytest.mark.skipif(
    not os.environ.get("TASKGRAPH_USE_THREADS") or os.environ.get("TASKGRAPH_SERIAL"),
    reason="requires multithreading to be enabled",
)


class FakeTPE(ProcessPoolExecutor):
    loaded_kinds = []

    def submit(self, kind_load_tasks, *args):
        self.loaded_kinds.append(kind_load_tasks.__self__.name)
        return super().submit(kind_load_tasks, *args)


class RecordingKind(FakeKind):
    """Records which process loaded it, and the kinds of the dependency
    tasks it was given, in the file at `record_path`."""

    record_path = None

    def load_tasks(self, parameters, loaded_tasks, write_artifacts):
        dep_kinds = sorted({t.kind for t in loaded_tasks.values()})
        line = f"{self.name} {os.getpid()} {','.join(dep_kinds)}\n"
        fd = os.open(self.record_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
        try:
            os.write(fd, line.encode())
        finally:
            os.close(fd)
        return super().load_tasks(parameters, loaded_tasks, write_artifacts)


def use_kind_class(tgg, cls):
    """Make `tgg` load its kinds as instances of `cls`."""
    load_kinds = tgg._load_kinds

    def _load_kinds(graph_config, target_kinds=None):
        for kind in load_kinds(graph_config, target_kinds):
            yield cls(kind.name, kind.path, kind.config, kind.graph_config)

    tgg._load_kinds = _load_kinds


@linuxonly
def test_kind_ordering_forked(monkeypatch, tmp_path, maketgg):
    """Each kind is loaded in a child process, with its subclass' load_tasks,
    after the kinds it depends on, and is given their tasks."""
    monkeypatch.setattr(RecordingKind, "record_path", str(tmp_path / "record"))
    tgg = maketgg(
        kinds=[
            ("_fake3", {"kind-dependencies": ["_fake2", "_fake1"]}),
            ("_fake2", {"kind-dependencies": ["_fake1"]}),
            ("_fake1", {"kind-dependencies": []}),
        ]
    )
    use_kind_class(tgg, RecordingKind)
    tgg._run_until("full_task_set")
    assert len(tgg.full_task_set.tasks) == 9

    records = [
        line.split(" ") for line in (tmp_path / "record").read_text().splitlines()
    ]
    assert [(name, deps) for name, _, deps in records] == [
        ("_fake1", ""),
        ("_fake2", "_fake1"),
        ("_fake3", "_fake1,_fake2"),
    ]
    pids = {int(pid) for _, pid, _ in records}
    assert len(pids) == 3
    assert os.getpid() not in pids


@linuxonly
def test_forked_max_workers(mocker, monkeypatch, tmp_path, maketgg):
    "Independent kinds are all loaded when fewer can be loaded at once."
    mocker.patch.object(generator, "_max_workers", return_value=1)
    tgg = maketgg(kinds=[(f"_fake{i}", {}) for i in range(4)])
    assert len(tgg.full_task_set.tasks) == 12


class UnpicklableError(Exception):
    def __init__(self, a, b):
        super().__init__(f"{a} {b}")


@linuxonly
def test_forked_exception_traceback(mocker, caplog, maketgg):
    """An exception raised loading a kind in a child is raised in the parent,
    with the traceback from the child."""

    def fail_in_child(self, *args, **kwargs):
        raise UnpicklableError("not", "picklable")

    mocker.patch.object(Kind, "load_tasks", fail_in_child)
    tgg = maketgg()

    with caplog.at_level("ERROR"):
        with pytest.raises(Exception, match="UnpicklableError: not picklable") as e:
            tgg._run_until("full_task_set")

    assert "in fail_in_child" in str(e.value.__cause__)
    records = [r for r in caplog.records if "Error loading tasks" in r.message]
    assert len(records) == 1
    assert records[0].message == "Error loading tasks for kind _fake:"
    assert "in fail_in_child" in caplog.text


@linuxonly
@pytest.mark.parametrize(
    "exit,expected",
    (
        pytest.param(lambda: os._exit(3), "exited with status 3", id="exit"),
        pytest.param(
            lambda: os.kill(os.getpid(), signal.SIGKILL),
            "was killed by signal SIGKILL",
            id="killed",
        ),
    ),
)
def test_forked_child_dies(mocker, maketgg, exit, expected):
    "A child exiting without sending its tasks is reported as an error."

    def die(self, *args, **kwargs):
        exit()

    mocker.patch.object(Kind, "load_tasks", die)
    tgg = maketgg()
    with pytest.raises(
        Exception, match=f"Process loading tasks for kind _fake {expected}"
    ):
        tgg._run_until("full_task_set")


@linuxonly
def test_forked_unpicklable_result(mocker, maketgg):
    "Tasks that can't be sent back are reported as an error loading the kind."

    def unpicklable(self, *args, **kwargs):
        return [lambda: None]

    mocker.patch.object(Kind, "load_tasks", unpicklable)
    tgg = maketgg()
    with pytest.raises(
        Exception, match="Could not send the tasks of kind _fake to the parent"
    ):
        tgg._run_until("full_task_set")


@linuxonly
def test_forked_children_killed_on_error(mocker, tmp_path, maketgg):
    "When loading a kind fails, the children loading other kinds are killed."
    pid_file = tmp_path / "pid"
    load_tasks = Kind.load_tasks

    def fail_or_hang(self, *args, **kwargs):
        if self.name == "_fail":
            # Wait for the other child to be running.
            while not pid_file.exists():
                time.sleep(0.01)
            raise RuntimeError("failed")
        if self.name == "_hang":
            pid_file.write_text(str(os.getpid()))
            time.sleep(60)
        return load_tasks(self, *args, **kwargs)

    mocker.patch.object(Kind, "load_tasks", fail_or_hang)
    tgg = maketgg(kinds=[("_fail", {}), ("_hang", {})])
    start = time.monotonic()
    with pytest.raises(RuntimeError, match="failed"):
        tgg._run_until("full_task_set")
    assert time.monotonic() - start < 30
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


@threadsonly
def test_kind_ordering_multithread(mocker, maketgg):
    "When task kinds depend on each other, they are loaded in postorder"
    mocked_tpe = mocker.patch.object(generator, "ThreadPoolExecutor", new=FakeTPE)
    tgg = maketgg(
        kinds=[
            ("_fake3", {"kind-dependencies": ["_fake2", "_fake1"]}),
            ("_fake2", {"kind-dependencies": ["_fake1"]}),
            ("_fake1", {"kind-dependencies": []}),
        ]
    )
    tgg._run_until("full_task_set")
    assert mocked_tpe.loaded_kinds == ["_fake1", "_fake2", "_fake3"]


def test_schema_validation_error_logged_without_traceback(mocker, caplog, maketgg):
    """SchemaValidationError from a kind is logged at ERROR level with no
    traceback attached (it's user input, not a programmer bug)."""

    def fail_load_tasks(self, *args, **kwargs):
        raise SchemaValidationError("bad task data")

    mocker.patch.object(Kind, "load_tasks", fail_load_tasks)
    tgg = maketgg()

    with caplog.at_level("ERROR"):
        with pytest.raises(SchemaValidationError):
            tgg._run_until("full_task_set")

    schema_records = [r for r in caplog.records if "Error loading tasks" in r.message]
    assert len(schema_records) == 1
    # logger.error attaches no exc_info — that's the whole point.
    assert schema_records[0].exc_info is None
    assert "bad task data" in schema_records[0].message


def test_other_exceptions_still_log_traceback(mocker, caplog, maketgg):
    """Non-SchemaValidationError exceptions still go through logger.exception
    so real programmer bugs surface their traceback."""

    def fail_load_tasks(self, *args, **kwargs):
        raise RuntimeError("unexpected bug")

    mocker.patch.object(Kind, "load_tasks", fail_load_tasks)
    tgg = maketgg()

    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError):
            tgg._run_until("full_task_set")

    records = [r for r in caplog.records if "Error loading tasks" in r.message]
    assert len(records) == 1
    assert records[0].exc_info is not None


def test_full_task_set(maketgg):
    "The full_task_set property has all tasks"
    tgg = maketgg()
    assert tgg.full_task_set.graph == graph.Graph(
        {"_fake-t-0", "_fake-t-1", "_fake-t-2"}, set()
    )
    assert sorted(tgg.full_task_set.tasks.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_fake-t-2"]
    )


def test_full_task_graph(maketgg):
    "The full_task_graph property has all tasks, and links"
    tgg = maketgg()
    assert tgg.full_task_graph.graph == graph.Graph(
        {"_fake-t-0", "_fake-t-1", "_fake-t-2"},
        {
            ("_fake-t-1", "_fake-t-0", "prev"),
            ("_fake-t-2", "_fake-t-1", "prev"),
        },
    )
    assert sorted(tgg.full_task_graph.tasks.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_fake-t-2"]
    )


def test_target_task_set(maketgg):
    "The target_task_set property has the targeted tasks"
    tgg = maketgg(["_fake-t-1"])
    assert tgg.target_task_set.graph == graph.Graph({"_fake-t-1"}, set())
    assert set(tgg.target_task_set.tasks.keys()) == {"_fake-t-1"}


def test_target_task_graph(maketgg):
    "The target_task_graph property has the targeted tasks and deps"
    tgg = maketgg(["_fake-t-1"])
    assert tgg.target_task_graph.graph == graph.Graph(
        {"_fake-t-0", "_fake-t-1"}, {("_fake-t-1", "_fake-t-0", "prev")}
    )
    assert sorted(tgg.target_task_graph.tasks.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1"]
    )


def test_always_target_tasks(maketgg):
    "The target_task_graph includes tasks with 'always_target'"
    tgg_args = {
        "target_tasks": ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1"],
        "kinds": [
            ("_fake", {"task-defaults": {"optimization": {"odd": None}}}),
            (
                "_ignore",
                {
                    "task-defaults": {
                        "attributes": {"always_target": True},
                        "optimization": {"even": None},
                    }
                },
            ),
        ],
        "params": {"optimize_target_tasks": False},
    }
    tgg = maketgg(**tgg_args)
    assert sorted(tgg.target_task_set.tasks.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1"]
    )
    assert sorted(tgg.target_task_graph.tasks.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1", "_ignore-t-2"]
    )
    assert sorted(t.label for t in tgg.optimized_task_graph.tasks.values()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1"]
    )

    # Test `enable_always_target: False`
    tgg_args["params"]["enable_always_target"] = False
    tgg = maketgg(**tgg_args)
    assert sorted(tgg.target_task_set.tasks.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1"]
    )
    assert sorted(tgg.target_task_graph.tasks.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1"]
    )
    assert sorted(t.label for t in tgg.optimized_task_graph.tasks.values()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1"]
    )

    # Test `enable_always_target: ["_fake"]`
    tgg_args = {
        "target_tasks": ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1"],
        "kinds": [
            (
                "_fake",
                {
                    "task-defaults": {
                        "attributes": {"always_target": True},
                        "optimization": {"odd": None},
                    }
                },
            ),
            (
                "_ignore",
                {
                    "task-defaults": {
                        "attributes": {"always_target": True},
                        "optimization": {"even": None},
                    }
                },
            ),
        ],
        "params": {"enable_always_target": ["_fake"], "optimize_target_tasks": False},
    }
    tgg = maketgg(**tgg_args)
    assert sorted(tgg.target_task_set.tasks.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1"]
    )
    assert sorted(tgg.target_task_graph.tasks.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_fake-t-2", "_ignore-t-0", "_ignore-t-1"]
    )
    assert sorted(t.label for t in tgg.optimized_task_graph.tasks.values()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_fake-t-2", "_ignore-t-0", "_ignore-t-1"]
    )


def test_optimized_task_graph(maketgg):
    "The optimized task graph contains task ids"
    tgg = maketgg(["_fake-t-2"])
    tid = tgg.label_to_taskid
    assert tgg.optimized_task_graph.graph == graph.Graph(
        {tid["_fake-t-0"], tid["_fake-t-1"], tid["_fake-t-2"]},
        {
            (tid["_fake-t-1"], tid["_fake-t-0"], "prev"),
            (tid["_fake-t-2"], tid["_fake-t-1"], "prev"),
        },
    )


def test_verifications(mocker, maketgg):
    m = mocker.patch.object(generator, "verifications")
    tgg = maketgg(["_fake-t-2"], enable_verifications=True)
    tgg.morphed_task_graph
    assert m.call_count == 10

    m = mocker.patch.object(generator, "verifications")
    tgg = maketgg(["_fake-t-2"], enable_verifications=False)
    tgg.morphed_task_graph
    m.assert_not_called()


def test_load_tasks_for_kind(monkeypatch):
    """
    `load_tasks_for_kinds` will load the tasks for the provided kind
    """
    monkeypatch.setattr(generator, "TaskGraphGenerator", WithFakeKind)
    monkeypatch.setattr(generator, "load_graph_config", fake_load_graph_config)

    tasks = load_tasks_for_kind(
        {"_kinds": [("_example-kind", []), ("docker-image", [])]},
        "_example-kind",
        "/root/taskcluster",
    )
    assert "docker-image-t-1" not in tasks
    assert (
        "_example-kind-t-1" in tasks
        and tasks["_example-kind-t-1"].label == "_example-kind-t-1"
    )

    tasks = load_tasks_for_kinds(
        {"_kinds": [("_example-kind", []), ("docker-image", [])]},
        ["_example-kind", "docker-image"],
        "/root/taskcluster",
    )
    assert (
        "docker-image-t-1" in tasks
        and tasks["docker-image-t-0"].label == "docker-image-t-0"
    )
    assert (
        "_example-kind-t-1" in tasks
        and tasks["_example-kind-t-1"].label == "_example-kind-t-1"
    )

    # Test that **kwargs are forwarded to TaskGraphGenerator
    tasks_with_kwargs = load_tasks_for_kind(
        {"_kinds": [("_example-kind", []), ("docker-image", [])]},
        "_example-kind",
        "/root/taskcluster",
        write_artifacts=True,  # This should be forwarded to TaskGraphGenerator
    )
    assert isinstance(tasks_with_kwargs, dict)
    assert "_example-kind-t-1" in tasks_with_kwargs

    # Test graph_attr parameter
    tasks_with_graph_attr = load_tasks_for_kinds(
        {"_kinds": [("_example-kind", []), ("docker-image", [])]},
        ["_example-kind"],
        "/root/taskcluster",
        graph_attr="full_task_set",
    )
    assert isinstance(tasks_with_graph_attr, dict)
    assert "_example-kind-t-1" in tasks_with_graph_attr


def test_loader_backwards_compat_interface(graph_config):
    """Ensure loaders can be called even if they don't support a
    `write_artifacts` argument."""

    class OldLoaderKind(Kind):
        def _get_loader(self):
            return lambda kind, path, config, params, tasks: []

    kind = OldLoaderKind("", "", {"transforms": []}, graph_config)
    kind.load_tasks({}, {}, False)


@pytest.mark.parametrize(
    "config,expected_transforms",
    (
        pytest.param(
            {},
            [
                "taskgraph.transforms.run:transforms",
                "taskgraph.transforms.task:transforms",
            ],
            id="no_transforms",
        ),
        pytest.param(
            {"transforms": ["taskgraph.transforms.notify:transforms"]},
            [
                "taskgraph.transforms.notify:transforms",
                "taskgraph.transforms.run:transforms",
                "taskgraph.transforms.task:transforms",
            ],
            id="additional_transform_specified",
        ),
    ),
)
def test_default_loader(config, expected_transforms):
    loader = Kind("", "", config, {})._get_loader()
    assert loader is default_loader, (
        "Default Kind loader should be taskgraph.loader.default.loader"
    )
    loader("", "", config, {}, [], False)

    assert config["transforms"] == expected_transforms


@pytest.mark.parametrize(
    "config",
    (
        pytest.param(
            {
                "transforms": [
                    "taskgraph.transforms.run:transforms",
                    "taskgraph.transforms.task:transforms",
                ]
            },
            id="run_and_task_transforms_specified",
        ),
        pytest.param(
            {"transforms": ["taskgraph.transforms.run:transforms"]},
            id="only_run_transform_specified",
        ),
        pytest.param(
            {"transforms": ["taskgraph.transforms.task:transforms"]},
            id="only_task_transform_specified",
        ),
    ),
)
def test_default_loader_errors(config):
    loader = Kind("", "", config, {})._get_loader()
    try:
        loader("", "", config, {}, [], False)
    except KeyError:
        return

    assert False, "Should've raised a KeyError"


@pytest.mark.parametrize(
    "kind_config",
    (
        pytest.param(
            {
                "loader": "taskgraph.loader.transform:loader",
                "transforms": ["test_taskgraph.transforms.foo:transforms"],
            },
            id="load transform",
        ),
        pytest.param(
            {
                "loader": "taskgraph.loader.transform:loader",
                "transforms": ["test_taskgraph.transforms.foo"],
            },
            id="load transform no object",
        ),
    ),
)
def test_kind_load_tasks(monkeypatch, graph_config, parameters, datadir, kind_config):
    monkeypatch.syspath_prepend(datadir / "taskcluster")
    kind = Kind(
        name="fake", path="foo/bar", config=kind_config, graph_config=graph_config
    )
    tasks = kind.load_tasks(parameters, {}, False)
    assert tasks


def test_kind_graph(maketgg):
    "The kind_graph property has all kinds and their dependencies"
    tgg = maketgg(
        kinds=[
            ("_fake3", {"kind-dependencies": ["_fake2", "_fake1"]}),
            ("_fake2", {"kind-dependencies": ["_fake1"]}),
            ("_fake1", {"kind-dependencies": []}),
        ]
    )
    kind_graph = tgg.kind_graph
    assert isinstance(kind_graph, graph.Graph)
    assert kind_graph.nodes == {"_fake1", "_fake2", "_fake3"}
    assert kind_graph.edges == {
        ("_fake3", "_fake2", "kind-dependency"),
        ("_fake3", "_fake1", "kind-dependency"),
        ("_fake2", "_fake1", "kind-dependency"),
    }


def test_kind_graph_missing_kind(maketgg):
    "A dependency on a kind that doesn't exist is an error"
    tgg = maketgg(
        kinds=[
            ("_fake2", {"kind-dependencies": ["_missing"]}),
            ("_fake1", {"kind-dependencies": []}),
        ]
    )
    with pytest.raises(Exception, match='Could not find the kind "_missing"'):
        tgg.kind_graph


def test_kind_graph_dependency_loop(maketgg):
    "A dependency loop between kinds is an error"
    tgg = maketgg(
        kinds=[
            ("_fake3", {"kind-dependencies": ["_fake2"]}),
            ("_fake2", {"kind-dependencies": ["_fake3"]}),
            ("_fake1", {"kind-dependencies": []}),
        ]
    )
    with pytest.raises(Exception, match="Dependency loop detected"):
        tgg.kind_graph


def test_kind_graph_with_target_kinds(maketgg):
    "The kind_graph property respects target_kinds parameter"
    tgg = maketgg(
        kinds=[
            ("_fake3", {"kind-dependencies": ["_fake2"]}),
            ("_fake2", {"kind-dependencies": ["_fake1"]}),
            ("_fake1", {"kind-dependencies": []}),
            ("_other", {"kind-dependencies": []}),
            ("docker-image", {"kind-dependencies": []}),  # Add docker-image
        ],
        params={"target-kinds": ["_fake2"]},
    )
    kind_graph = tgg.kind_graph
    # Should only include _fake2, _fake1, and docker-image (implicit dependency)
    assert "_fake2" in kind_graph.nodes
    assert "_fake1" in kind_graph.nodes
    assert "docker-image" in kind_graph.nodes
    # _fake3 and _other should not be included
    assert "_fake3" not in kind_graph.nodes
    assert "_other" not in kind_graph.nodes
