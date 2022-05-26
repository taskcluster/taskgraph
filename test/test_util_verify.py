# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from taskgraph.graph import Graph
from taskgraph.task import Task
from taskgraph.taskgraph import TaskGraph
from taskgraph.util.verify import (
    GraphVerification,
    VerificationSequence,
)


def get_graph():
    tasks = {
        "a": Task(kind=None, label="a", attributes={}, task={}),
        "b": Task(kind=None, label="b", attributes={"at-at": "yep"}, task={}),
        "c": Task(
            kind=None, label="c", attributes={"run_on_projects": ["try"]}, task={}
        ),
    }
    graph = Graph(nodes=set("abc"), edges=set())
    return TaskGraph(tasks, graph)


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
