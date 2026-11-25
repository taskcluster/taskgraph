# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime, timedelta, timezone
from functools import partial

import pytest
from pytest_taskgraph import make_graph, make_task

from taskgraph.graph import Graph
from taskgraph.optimize import base as optimize_mod
from taskgraph.optimize.base import (
    Alias,
    All,
    Any,
    Not,
    OptimizationStrategy,
    register_strategy,
)
from taskgraph.task import Task
from taskgraph.taskgraph import TaskGraph


class Remove(OptimizationStrategy):
    def should_remove_task(self, task, params, arg):
        return True


class Replace(OptimizationStrategy):
    def should_replace_task(self, task, params, deadline, taskid):
        expires = datetime.now(timezone.utc) + timedelta(days=1)
        if deadline and expires.replace(tzinfo=None) < datetime.strptime(
            deadline, "%Y-%m-%dT%H:%M:%S.%fZ"
        ):
            return False
        return taskid


def default_strategies():
    return {
        "never": OptimizationStrategy(),
        "remove": Remove(),
        "replace": Replace(),
    }


def make_opt_graph(*tasks_and_edges):
    tasks = {t.task_id: t for t in tasks_and_edges if isinstance(t, Task)}
    edges = {e for e in tasks_and_edges if not isinstance(e, Task)}
    return TaskGraph(tasks, Graph(set(tasks), edges))


def make_triangle(deps=True, **opts):
    """
    Make a "triangle" graph like this:

      t1 <-------- t3
       `---- t2 --'
    """
    return make_graph(
        make_task("t1", optimization=opts.get("t1")),
        make_task("t2", optimization=opts.get("t2")),
        make_task("t3", optimization=opts.get("t3")),
        ("t3", "t2", "dep"),
        ("t3", "t1", "dep2"),
        ("t2", "t1", "dep"),
        deps=deps,
    )


@pytest.mark.parametrize(
    "graph,kwargs,exp_removed",
    (
        # A graph full of optimization=never has nothing removed
        pytest.param(
            make_triangle(),
            {},
            # expectations
            set(),
            id="never",
        ),
        # A graph full of optimization=remove removes everything
        pytest.param(
            make_triangle(
                t1={"remove": None},
                t2={"remove": None},
                t3={"remove": None},
            ),
            {},
            # expectations
            {"t1", "t2", "t3"},
            id="all",
        ),
        # Tasks with the 'any' composite strategy are removed when any substrategy says to
        pytest.param(
            make_triangle(
                t1={"any": None},
                t2={"any": None},
                t3={"any": None},
            ),
            {"strategies": lambda: {"any": Any("never", "remove")}},
            # expectations
            {"t1", "t2", "t3"},
            id="composite_strategies_any",
        ),
        # Tasks with the 'all' composite strategy are removed when all substrategies say to
        pytest.param(
            make_triangle(
                t1={"all": None},
                t2={"all": None},
                t3={"all": None},
            ),
            {"strategies": lambda: {"all": All("never", "remove")}},
            # expectations
            set(),
            id="composite_strategies_all",
        ),
        # Tasks with the 'not' composite strategy are removed when the substrategy says not to
        pytest.param(
            make_graph(
                make_task("t1", optimization={"not-never": None}),
                make_task("t2", optimization={"not-remove": None}),
            ),
            {
                "strategies": lambda: {
                    "not-never": Not("never"),
                    "not-remove": Not("remove"),
                }
            },
            # expectations
            {"t1"},
            id="composite_strategies_not",
        ),
        # Removable tasks that are depended on by non-removable tasks are not removed
        pytest.param(
            make_triangle(
                t1={"remove": None},
                t3={"remove": None},
            ),
            {},
            # expectations
            {"t3"},
            id="blocked",
        ),
        # Removable tasks that are marked do_not_optimize are not removed
        pytest.param(
            make_triangle(
                t1={"remove": None},
                t2={"remove": None},  # but do_not_optimize
                t3={"remove": None},
            ),
            {"do_not_optimize": {"t2"}},
            # expectations
            {"t3"},
            id="do_not_optimize",
        ),
        # Tasks with 'if_dependencies' are removed when deps are not run
        pytest.param(
            make_graph(
                make_task("t1", optimization={"remove": None}),
                make_task("t2", optimization={"remove": None}),
                make_task(
                    "t3", optimization={"never": None}, if_dependencies=["t1", "t2"]
                ),
                make_task("t4", optimization={"never": None}, if_dependencies=["t1"]),
                ("t3", "t2", "dep"),
                ("t3", "t1", "dep2"),
                ("t2", "t1", "dep"),
                ("t4", "t1", "dep3"),
            ),
            {"requested_tasks": {"t3", "t4"}},
            # expectations
            {"t1", "t2", "t3", "t4"},
            id="if_deps_removed",
        ),
        # Parents of tasks with 'if_dependencies' are also removed even if requested
        pytest.param(
            make_graph(
                make_task("t1", optimization={"remove": None}),
                make_task("t2", optimization={"remove": None}),
                make_task(
                    "t3", optimization={"never": None}, if_dependencies=["t1", "t2"]
                ),
                make_task("t4", optimization={"never": None}, if_dependencies=["t1"]),
                ("t3", "t2", "dep"),
                ("t3", "t1", "dep2"),
                ("t2", "t1", "dep"),
                ("t4", "t1", "dep3"),
            ),
            {},
            # expectations
            {"t1", "t2", "t3", "t4"},
            id="if_deps_parents_removed",
        ),
        # Tasks with 'if_dependencies' are kept if at least one of said dependencies are kept
        pytest.param(
            make_graph(
                make_task("t1", optimization={"never": None}),
                make_task("t2", optimization={"remove": None}),
                make_task(
                    "t3", optimization={"never": None}, if_dependencies=["t1", "t2"]
                ),
                make_task("t4", optimization={"never": None}, if_dependencies=["t1"]),
                ("t3", "t2", "dep"),
                ("t3", "t1", "dep2"),
                ("t2", "t1", "dep"),
                ("t4", "t1", "dep3"),
            ),
            {},
            # expectations
            set(),
            id="if_deps_kept",
        ),
        # Ancestor of task with 'if_dependencies' does not cause it to be kept
        pytest.param(
            make_graph(
                make_task("t1", optimization={"never": None}),
                make_task("t2", optimization={"remove": None}),
                make_task("t3", optimization={"never": None}, if_dependencies=["t2"]),
                ("t3", "t2", "dep"),
                ("t2", "t1", "dep2"),
            ),
            {},
            # expectations
            {"t2", "t3"},
            id="if_deps_ancestor_does_not_keep",
        ),
        # Unhandled edge case where 't1' and 't2' are kept even though they
        # don't have any dependents and are not in 'requested_tasks'
        pytest.param(
            make_graph(
                make_task("t1", optimization={"never": None}),
                make_task("t2", optimization={"never": None}, if_dependencies=["t1"]),
                make_task("t3", optimization={"remove": None}),
                make_task("t4", optimization={"never": None}, if_dependencies=["t3"]),
                ("t2", "t1", "e1"),
                ("t4", "t2", "e2"),
                ("t4", "t3", "e3"),
            ),
            {"requested_tasks": {"t3", "t4"}},
            # expectations
            {"t1", "t2", "t3", "t4"},
            id="if_deps_edge_case_1",
            marks=pytest.mark.xfail,
        ),
    ),
)
def test_remove_tasks(monkeypatch, graph, kwargs, exp_removed):
    """Tests the `remove_tasks` function.

    Each test case takes three arguments:

    1. A `TaskGraph` instance.
    2. Keyword arguments to pass into `remove_tasks`.
    3. The set of task labels that are expected to be removed.
    """
    # set up strategies
    strategies = default_strategies()
    monkeypatch.setattr(optimize_mod, "registry", strategies)
    extra = kwargs.pop("strategies", None)
    if extra:
        if callable(extra):
            extra = extra()
        strategies.update(extra)

    kwargs.setdefault("params", {})
    kwargs.setdefault("do_not_optimize", set())
    kwargs.setdefault("requested_tasks", graph)

    got_removed = optimize_mod.remove_tasks(
        target_task_graph=graph,
        task_strategies=optimize_mod.resolve_task_strategies(graph, strategies),
        **kwargs,
    )
    assert got_removed == exp_removed


@pytest.mark.parametrize(
    "graph,kwargs,exp_replaced,exp_removed",
    (
        # A task cannot be replaced if it depends on one that was not replaced
        pytest.param(
            make_triangle(
                t1={"replace": "e1"},
                t3={"replace": "e3"},
            ),
            {
                "index_to_taskid": {"t1": "e1"},
            },
            # expectations
            {"t1"},
            set(),
            id="blocked",
        ),
        # A task cannot be replaced if it should not be optimized
        pytest.param(
            make_triangle(
                t1={"replace": "e1"},
                t2={"replace": "xxx"},  # but do_not_optimize
                t3={"replace": "e3"},
            ),
            {
                "do_not_optimize": {"t2"},
                "index_to_taskid": {"t1": "e1"},
            },
            # expectations
            {"t1"},
            set(),
            id="do_not_optimize",
        ),
        # No tasks are replaced when strategy is 'never'
        pytest.param(
            make_triangle(),
            {},
            # expectations
            set(),
            set(),
            id="never",
        ),
        # All replaceable tasks are replaced when strategy is 'replace'
        pytest.param(
            make_triangle(
                t1={"replace": "e1"},
                t2={"replace": "e2"},
                t3={"replace": "e3"},
            ),
            {
                "index_to_taskid": {"t1": "e1", "t2": "e2", "t3": "e3"},
            },
            # expectations
            {"t1", "t2", "t3"},
            set(),
            id="all",
        ),
        # A task can be replaced with nothing
        pytest.param(
            make_triangle(
                t1={"replace": "e1"},
                t2={"replace": True},
                t3={"replace": True},
            ),
            {
                "index_to_taskid": {"t1": "e1"},
            },
            # expectations
            {"t1"},
            {"t2", "t3"},
            id="tasks_removed",
        ),
        # A task which expires before a dependents deadline is not a valid replacement.
        pytest.param(
            make_graph(
                make_task("t1", optimization={"replace": "e1"}),
                make_task(
                    "t2", task_def={"deadline": {"relative-datestamp": "2 days"}}
                ),
                make_task(
                    "t3", task_def={"deadline": {"relative-datestamp": "1 minute"}}
                ),
                ("t2", "t1", "dep1"),
                ("t3", "t1", "dep2"),
            ),
            {},
            # expectations
            set(),
            set(),
            id="deadline",
        ),
    ),
)
def test_replace_tasks(
    graph,
    kwargs,
    exp_replaced,
    exp_removed,
):
    """Tests the `replace_tasks` function.

    Each test case takes five arguments:

    1. A `TaskGraph` instance.
    2. Keyword arguments to pass into `replace_tasks`.
    3. The set of task labels that are expected to be replaced.
    4. The set of task labels that are expected to be removed.
    5. The expected label_to_taskid.
    """
    kwargs.setdefault("params", {})
    kwargs.setdefault("do_not_optimize", set())
    kwargs.setdefault("label_to_taskid", {})
    kwargs.setdefault("index_to_taskid", {})
    kwargs.setdefault("taskid_to_status", {})
    kwargs.setdefault("removed_tasks", set())
    kwargs.setdefault("existing_tasks", {})

    got_replaced = optimize_mod.replace_tasks(
        target_task_graph=graph,
        task_strategies=optimize_mod.resolve_task_strategies(
            graph, default_strategies()
        ),
        **kwargs,
    )
    assert got_replaced == exp_replaced
    assert kwargs["removed_tasks"] == exp_removed


@pytest.mark.parametrize(
    "graph,kwargs,exp_subgraph,exp_label_to_taskid",
    (
        # Test get_subgraph returns a similarly-shaped subgraph when nothing is removed
        pytest.param(
            make_triangle(deps=False),
            {},
            make_opt_graph(
                make_task("t1", task_id="tid1", dependencies={}),
                make_task("t2", task_id="tid2", dependencies={"dep": "tid1"}),
                make_task(
                    "t3", task_id="tid3", dependencies={"dep": "tid2", "dep2": "tid1"}
                ),
                ("tid3", "tid2", "dep"),
                ("tid3", "tid1", "dep2"),
                ("tid2", "tid1", "dep"),
            ),
            {"t1": "tid1", "t2": "tid2", "t3": "tid3"},
            id="no_change",
        ),
        # Test get_subgraph returns a smaller subgraph when tasks are removed
        pytest.param(
            make_triangle(deps=False),
            {
                "removed_tasks": {"t2", "t3"},
            },
            # expectations
            make_opt_graph(make_task("t1", task_id="tid1", dependencies={})),
            {"t1": "tid1"},
            id="removed",
        ),
        # Test get_subgraph returns a smaller subgraph when tasks are replaced
        pytest.param(
            make_triangle(deps=False),
            {
                "replaced_tasks": {"t1", "t2"},
                "label_to_taskid": {"t1": "e1", "t2": "e2"},
            },
            # expectations
            make_opt_graph(
                make_task(
                    "t3", task_id="tid1", dependencies={"dep": "e2", "dep2": "e1"}
                )
            ),
            {"t1": "e1", "t2": "e2", "t3": "tid1"},
            id="replaced",
        ),
    ),
)
def test_get_subgraph(monkeypatch, graph, kwargs, exp_subgraph, exp_label_to_taskid):
    """Tests the `get_subgraph` function.

    Each test case takes 4 arguments:

    1. A `TaskGraph` instance.
    2. Keyword arguments to pass into `get_subgraph`.
    3. The expected subgraph.
    4. The expected label_to_taskid.
    """
    monkeypatch.setattr(
        optimize_mod, "slugid", partial(next, (f"tid{i}" for i in range(1, 10)))
    )

    kwargs.setdefault("removed_tasks", set())
    kwargs.setdefault("replaced_tasks", set())
    kwargs.setdefault("label_to_taskid", {})
    kwargs.setdefault("decision_task_id", "DECISION-TASK")

    got_subgraph = optimize_mod.get_subgraph(graph, **kwargs)
    assert got_subgraph.graph == exp_subgraph.graph
    assert got_subgraph.tasks == exp_subgraph.tasks
    assert kwargs["label_to_taskid"] == exp_label_to_taskid


def test_get_subgraph_removed_dep():
    "get_subgraph raises an Exception when a task depends on a removed task"
    graph = make_triangle()
    with pytest.raises(Exception):
        optimize_mod.get_subgraph(graph, {"t2"}, set(), {})


def test_register_strategy(mocker):
    m = mocker.Mock()
    func = register_strategy("foo", args=("one", "two"), kwargs={"n": 1})
    func(m)
    m.assert_called_with("one", "two", n=1)


class RecordingRemove(OptimizationStrategy):
    def __init__(self, remove=()):
        self.remove = set(remove)
        self.calls = []

    def should_remove_tasks(self, graph, labels, params, args):
        self.calls.append(list(labels))
        return {l for l in labels if l in self.remove}


def make_leaves(n, strategy):
    return make_graph(
        *(make_task(f"t{i}", optimization={strategy: None}) for i in range(1, n + 1))
    )


def run_remove_tasks(graph, strategies, requested_tasks=None, do_not_optimize=()):
    return optimize_mod.remove_tasks(
        target_task_graph=graph,
        requested_tasks=graph if requested_tasks is None else requested_tasks,
        params={},
        task_strategies=optimize_mod.resolve_task_strategies(graph, strategies),
        do_not_optimize=set(do_not_optimize),
    )


def test_resolve_task_strategies():
    strategies = default_strategies()
    strategies["any"] = Any("never", "always")
    graph = make_graph(
        make_task("t1", optimization={"remove": ["a"]}),
        make_task("t2", optimization={"any": None}),
        make_task("t3"),
    )
    resolved = optimize_mod.resolve_task_strategies(graph, strategies)
    assert resolved["t1"] == ("remove", strategies["remove"], ["a"])
    assert resolved["t2"] == ("any (never-or-always)", strategies["any"], None)
    assert resolved["t3"] == ("never", strategies["never"], None)


def test_remove_tasks_batches_candidates_per_strategy():
    graph = make_graph(
        make_task("t1", optimization={"rec": "a1"}),
        make_task("t2", optimization={"rec": "a2"}),
        make_task("t3", optimization={"rec": "a3"}),
        make_task("t4", optimization={"rec": "a4"}),
        make_task("t5", optimization={"remove": None}),
        ("t3", "t1", "dep"),
    )
    strategies = default_strategies()
    args_seen = []

    class Rec(RecordingRemove):
        def should_remove_tasks(self, graph, labels, params, args):
            args_seen.append(dict(args))
            return super().should_remove_tasks(graph, labels, params, args)

    rec = Rec(remove={"t1", "t2", "t3"})
    strategies["rec"] = rec

    removed = run_remove_tasks(
        graph,
        strategies,
        requested_tasks={"t1", "t2", "t3", "t5"},
        do_not_optimize={"t2"},
    )

    assert rec.calls == [["t3", "t1"]]
    assert args_seen == [{"t3": "a3", "t1": "a1"}]
    assert removed == {"t1", "t3", "t4", "t5"}


def test_remove_tasks_groups_by_strategy_object():
    graph = make_graph(
        make_task("t1", optimization={"first-name": None}),
        make_task("t2", optimization={"second-name": None}),
    )
    rec = RecordingRemove(remove={"t2"})
    strategies = default_strategies()
    strategies["first-name"] = rec
    strategies["second-name"] = rec

    assert run_remove_tasks(graph, strategies) == {"t2"}
    assert len(rec.calls) == 1
    assert sorted(rec.calls[0]) == ["t1", "t2"]


def test_remove_tasks_strategy_decides_with_whole_batch():
    class KeepFirst(OptimizationStrategy):
        def should_remove_tasks(self, graph, labels, params, args):
            return set(sorted(labels)[1:])

    graph = make_leaves(3, "keep-first")
    strategies = default_strategies()
    strategies["keep-first"] = KeepFirst()
    assert run_remove_tasks(graph, strategies) == {"t2", "t3"}


@pytest.mark.parametrize(
    "make_composite,first_removes,second_removes,exp_second_sees,exp_removed",
    (
        pytest.param(Any, {"t1"}, {"t2"}, ["t2", "t3"], {"t1", "t2"}, id="any"),
        pytest.param(All, {"t1", "t2"}, {"t2", "t3"}, ["t1", "t2"], {"t2"}, id="all"),
    ),
)
def test_composite_remove_short_circuits(
    make_composite, first_removes, second_removes, exp_second_sees, exp_removed
):
    graph = make_leaves(3, "composite")
    first = RecordingRemove(remove=first_removes)
    second = RecordingRemove(remove=second_removes)
    labels = ["t1", "t2", "t3"]
    assert (
        make_composite(first, second).should_remove_tasks(
            graph, labels, {}, dict.fromkeys(labels)
        )
        == exp_removed
    )
    assert first.calls == [labels]
    assert second.calls == [exp_second_sees]


def test_composite_remove_skips_substrategies_once_decided():
    graph = make_leaves(2, "composite")
    second = RecordingRemove()
    labels = ["t1", "t2"]
    assert Any(RecordingRemove(remove=labels), second).should_remove_tasks(
        graph, labels, {}, dict.fromkeys(labels)
    ) == {"t1", "t2"}
    assert second.calls == []


def test_not_and_alias_remove():
    graph = make_leaves(3, "composite")
    labels = ["t1", "t2", "t3"]
    args = dict.fromkeys(labels)
    inner = RecordingRemove(remove={"t2"})
    assert Not(inner).should_remove_tasks(graph, labels, {}, args) == {"t1", "t3"}
    assert Alias(inner).should_remove_tasks(graph, labels, {}, args) == {"t2"}


def test_composite_split_args_are_per_task():
    class Mark(OptimizationStrategy):
        def should_remove_task(self, task, params, arg):
            arg["seen"] = task.label
            return False

    class RemoveIfMarked(OptimizationStrategy):
        def should_remove_tasks(self, graph, labels, params, args):
            return {l for l in labels if args[l].get("seen") == l and args[l]["rm"]}

    def split(arg, substrategies):
        shared = {"rm": arg}
        return [shared, shared]

    graph = make_leaves(2, "composite")
    composite = Any(Mark(), RemoveIfMarked(), split_args=split)
    assert composite.should_remove_tasks(
        graph, ["t1", "t2"], {}, {"t1": True, "t2": False}
    ) == {"t1"}


def test_custom_composite_uses_per_task_reduce():
    class Majority(optimize_mod.CompositeStrategy):
        description = "majority"

        def reduce(self, results):
            results = list(results)
            return sum(bool(r) for r in results) > len(results) / 2

    graph = make_leaves(1, "composite")
    strategy = Majority("always", "always", "never")
    assert strategy.should_remove_tasks(graph, ["t1"], {}, {"t1": None}) == {"t1"}
