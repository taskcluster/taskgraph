"""
Tests for the 'rebuild_cached_tasks' action.
"""
import pytest

from taskgraph import create
from taskgraph.actions import trigger_action_callback
from taskgraph.util import taskcluster as tc_util

from .conftest import make_graph, make_task


@pytest.fixture
def run_action(capsys, mocker, monkeypatch, parameters, graph_config):
    # Monkeypatch these here so they get restored to their original values.
    # Otherwise, `trigger_action_callback` will leave them set to `True` and
    # cause failures in other tests.
    monkeypatch.setattr(create, "testing", True)
    monkeypatch.setattr(tc_util, "testing", True)

    def inner(name, graph):
        tgid = "group-id"
        m = mocker.patch(
            "taskgraph.actions.rebuild_cached_tasks.fetch_graph_and_labels"
        )
        m.return_value = (
            tgid,
            graph,
            {},
        )
        trigger_action_callback(
            task_group_id=tgid,
            task_id=None,
            input=None,
            callback=name,
            parameters=parameters,
            root=graph_config.root_dir,
            test=True,
        )
        captured = capsys.readouterr()
        return captured.out, captured.err

    return inner


def test_rebuild_cached_tasks(run_action):
    graph = make_graph(
        make_task(
            label="foo", attributes={"cached_task": True}, task_def={"name": "foo"}
        ),
        make_task(label="bar", task_def={"name": "bar"}),
    )
    out, _ = run_action("rebuild-cached-tasks", graph)
    assert "foo" in out
    assert "bar" not in out
