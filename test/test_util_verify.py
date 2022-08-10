# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from functools import partial
from itertools import chain

import pytest

from taskgraph.task import Task
from taskgraph.util.treeherder import split_symbol
from taskgraph.util.verify import (
    GraphVerification,
    ParametersVerification,
    VerificationSequence,
    verifications,
)

from .conftest import make_graph, make_task


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
    "name,graph,exception",
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
            None,
            id="task_graph_symbol: valid",
        ),
        pytest.param(
            "verify_task_graph_symbol",
            make_graph(
                make_task_treeherder("a", "M(1)"),
                make_task_treeherder("b", "M(1)"),
            ),
            Exception,
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
            Exception,
            id="task_graph_symbol: too many collections",
        ),
    ),
)
def test_verification(run_verification, name, graph, exception):
    func = partial(run_verification, name, graph=graph)
    if exception:
        with pytest.raises(exception):
            func()
    else:
        func()  # no exceptions
