# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from contextlib import nullcontext as does_not_raise
from functools import partial
from itertools import chain

import pytest
from pytest_taskgraph import make_graph, make_task

from taskgraph import MAX_DEPENDENCIES
from taskgraph.task import Task
from taskgraph.util.treeherder import split_symbol
from taskgraph.util.verify import (
    GraphConfigVerification,
    GraphVerification,
    ParametersVerification,
    VerificationSequence,
    verifications,
)


def get_graph():
    tasks = [
        make_task("a"),
        make_task("b", attributes={"at-at": "yep"}),
        make_task("c", attributes={"run_on_projects": ["try"]}),
    ]
    return make_graph(*tasks)


@pytest.fixture
def run_verification(parameters, graph_config):
    def inner(name, **kwargs):
        for v in chain(*verifications._verifications.values()):
            if v.func.__name__ == name:
                break
        else:
            raise Exception(f"verification '{name}' not found!")

        if isinstance(v, GraphVerification):
            assert "graph" in kwargs

        if isinstance(v, (GraphVerification, GraphConfigVerification)):
            kwargs.setdefault("graph_config", graph_config)

        if isinstance(v, (GraphVerification, ParametersVerification)):
            kwargs.setdefault("parameters", parameters)

        return v.verify(**kwargs)

    return inner


def assert_graph_verification(task, tg, scratch_pad, graph_config, parameters):
    if task:
        assert isinstance(task, Task)
    else:
        assert task is None
    assert tg == get_graph()
    assert scratch_pad == {}
    assert graph_config == "graph_config"
    assert parameters == "parameters"


def assert_simple_verification(arg):
    assert arg == "passed-thru"


@pytest.mark.parametrize(
    "name,input,run_assertions,expected_called",
    (
        pytest.param(
            "full_task_graph",
            (get_graph(), "graph_config", "parameters"),
            assert_graph_verification,
            4,
            id="GraphVerification",
        ),
        pytest.param(
            "initial",
            (),
            lambda: None,
            1,
            id="InitialVerification",
        ),
        pytest.param(
            "kinds",
            ("passed-thru",),
            assert_simple_verification,
            1,
            id="KindsVerification",
        ),
        pytest.param(
            "parameters",
            ("passed-thru",),
            assert_simple_verification,
            1,
            id="ParametersVerification",
        ),
        pytest.param(
            "graph_config",
            ("passed-thru",),
            assert_simple_verification,
            1,
            id="GraphConfigVerification",
        ),
    ),
)
def test_verification_types(name, input, run_assertions, expected_called):
    v = VerificationSequence()
    called = 0

    @v.add(name)
    def verification(*args, **kwargs):
        nonlocal called
        called += 1
        run_assertions(*args, **kwargs)

    assert len(v._verifications[name]) == 1
    assert isinstance(
        v._verifications[name][0], v._verification_types.get(name, GraphVerification)
    )
    assert called == 0
    v(name, *input)
    assert called == expected_called


def make_task_treeherder(label, symbol, platform="linux/opt"):
    config = {"machine": {}}
    config["groupSymbol"], config["symbol"] = split_symbol(symbol)
    config["machine"]["platform"], collection = platform.rsplit("/", 1)
    config["collection"] = {collection: True}
    return make_task(label, task_def={"extra": {"treeherder": config}})


@pytest.mark.parametrize(
    "name,graph,expectation",
    (
        pytest.param(
            "verify_task_graph_symbol",
            make_graph(
                make_task_treeherder("a", "M(1)", "linux/opt"),
                make_task_treeherder("b", "M(1)", "windows/opt"),
                make_task_treeherder("c", "M(1)", "linux/debug"),
                make_task_treeherder("d", "M(2)", "linux/opt"),
                make_task_treeherder("e", "1", "linux/opt"),
            ),
            does_not_raise(),
            id="task_graph_symbol: valid",
        ),
        pytest.param(
            "verify_task_graph_symbol",
            make_graph(
                make_task_treeherder("a", "M(1)"),
                make_task_treeherder("b", "M(1)"),
            ),
            pytest.raises(Exception),
            id="task_graph_symbol: conflicting symbol",
        ),
        pytest.param(
            "verify_task_graph_symbol",
            make_graph(
                make_task(
                    "a",
                    task_def={
                        "extra": {
                            "treeherder": {"collection": {"foo": True, "bar": True}}
                        }
                    },
                ),
            ),
            pytest.raises(Exception),
            id="task_graph_symbol: too many collections",
        ),
        pytest.param(
            "verify_routes_notification_filters",
            make_graph(
                make_task(
                    "good1",
                    task_def={
                        "routes": ["notify.email.default@email.address.on-completed"]
                    },
                ),
            ),
            does_not_raise(),
            id="routes_notfication_filter: valid",
        ),
        pytest.param(
            "verify_routes_notification_filters",
            make_graph(
                make_task(
                    "bad1",
                    task_def={
                        "routes": ["notify.email.default@email.address.on-bogus"]
                    },
                ),
            ),
            pytest.raises(Exception),
            id="routes_notfication_filter: invalid",
        ),
        pytest.param(
            "verify_routes_notification_filters",
            make_graph(
                make_task(
                    "deprecated",
                    task_def={"routes": ["notify.email.default@email.address.on-any"]},
                ),
            ),
            pytest.raises(DeprecationWarning),
            id="routes_notfication_filter: deprecated",
        ),
        pytest.param(
            "verify_index_route",
            make_graph(
                make_task(
                    "invalid_slash",
                    task_def={
                        "routes": [
                            "index.example.com/foobar.v2.latest.taskgraph.decision"
                        ]
                    },
                ),
            ),
            pytest.raises(Exception),
            id="verify_index_route: invalid slash in route",
        ),
        pytest.param(
            "verify_task_dependencies",
            make_graph(
                make_task(
                    "task2",
                    dependencies=["dependency"] * (MAX_DEPENDENCIES - 3),
                    soft_dependencies=["dependency"] * 1,
                    if_dependencies=["dependency"] * 1,
                )
            ),
            does_not_raise(),
            id="dependencies under limit",
        ),
        pytest.param(
            "verify_task_dependencies",
            make_graph(
                make_task(
                    "task3",
                    dependencies=["dependency"] * (MAX_DEPENDENCIES - 2),
                    soft_dependencies=["dependency"] * 1,
                    if_dependencies=["dependency"] * 1,
                )
            ),
            does_not_raise(),
            id="dependencies at limit",
        ),
        pytest.param(
            "verify_task_dependencies",
            make_graph(
                make_task(
                    "task3",
                    dependencies=["dependency"] * (MAX_DEPENDENCIES - 1),
                    soft_dependencies=["dependency"] * 1,
                    if_dependencies=["dependency"] * 1,
                )
            ),
            pytest.raises(Exception),
            id="dependencies over limit",
        ),
        pytest.param(
            "verify_run_task_caches",
            make_graph(
                make_task("task1", task_def={"payload": {"cache": {"foo": {}}}})
            ),
            pytest.raises(Exception, match="not appropriate for its trust-domain"),
            id="using cache with wrong trust-domain",
        ),
        pytest.param(
            "verify_run_task_caches",
            make_graph(
                make_task(
                    "task1",
                    task_def={
                        "payload": {"cache": {"test-domain-level-1-checkouts": {}}}
                    },
                )
            ),
            pytest.raises(Exception, match="reserved for run-task"),
            id="using reserved cache",
        ),
        pytest.param(
            "verify_run_task_caches",
            make_graph(
                make_task(
                    "task1",
                    task_def={
                        "payload": {
                            "cache": {"test-domain-level-1-checkouts": {}},
                            "command": ["run-task"],
                        }
                    },
                )
            ),
            pytest.raises(Exception, match="cache name is not dep"),
            id="using run-task without cache suffix",
        ),
        pytest.param(
            "verify_run_task_caches",
            make_graph(
                make_task(
                    "task1",
                    task_def={
                        "payload": {
                            "cache": {"test-domain-level-1-checkouts": {}},
                            "command": ["run-task-hg"],
                        }
                    },
                )
            ),
            pytest.raises(Exception, match="cache name is not dep"),
            id="using run-task-hg without cache suffix",
        ),
    ),
)
@pytest.mark.filterwarnings("error")
def test_verification(run_verification, name, graph, expectation):
    func = partial(run_verification, name, graph=graph)
    with expectation:
        func()
