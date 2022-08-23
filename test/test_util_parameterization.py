# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime

import pytest
from taskcluster_urls import test_root_url

from taskgraph.util.parameterization import resolve_task_references, resolve_timestamps
from taskgraph.util.taskcluster import get_root_url


def test_timestamps_no_change():
    now = datetime.datetime(2018, 1, 1)
    input = {
        "key": "value",
        "numeric": 10,
        "list": ["a", True, False, None],
    }
    assert resolve_timestamps(now, input) == input


def test_timestamps_buried_replacement():
    now = datetime.datetime(2018, 1, 1)
    input = {"key": [{"key2": [{"relative-datestamp": "1 day"}]}]}
    assert resolve_timestamps(now, input) == {
        "key": [{"key2": ["2018-01-02T00:00:00.000Z"]}]
    }


def test_timestamps_appears_with_other_keys():
    now = datetime.datetime(2018, 1, 1)
    input = [{"relative-datestamp": "1 day", "another-key": True}]
    assert resolve_timestamps(now, input) == [
        {"relative-datestamp": "1 day", "another-key": True}
    ]


@pytest.fixture
def assert_task_refs():
    def inner(input, output):
        taskid_for_edge_name = {"edge%d" % n: "tid%d" % n for n in range(1, 4)}
        assert (
            resolve_task_references(
                "subject",
                input,
                "tid-self",
                "tid-decision",
                taskid_for_edge_name,
            )
            == output
        )

    return inner


def test_task_refs_no_change(assert_task_refs):
    "resolve_task_references does nothing when there are no task references"
    assert_task_refs(
        {"in-a-list": ["stuff", {"property": "<edge1>"}]},
        {"in-a-list": ["stuff", {"property": "<edge1>"}]},
    )


def test_task_refs_in_list(assert_task_refs):
    "resolve_task_references resolves task references in a list"
    assert_task_refs(
        {"in-a-list": ["stuff", {"task-reference": "<edge1>"}]},
        {"in-a-list": ["stuff", "tid1"]},
    )


def test_task_refs_in_dict(assert_task_refs):
    "resolve_task_references resolves task references in a dict"
    assert_task_refs(
        {"in-a-dict": {"stuff": {"task-reference": "<edge2>"}}},
        {"in-a-dict": {"stuff": "tid2"}},
    )


def test_task_refs_multiple(assert_task_refs):
    "resolve_task_references resolves multiple references in the same string"
    assert_task_refs(
        {"multiple": {"task-reference": "stuff <edge1> stuff <edge2> after"}},
        {"multiple": "stuff tid1 stuff tid2 after"},
    )


def test_task_refs_embedded(assert_task_refs):
    "resolve_task_references resolves ebmedded references"
    assert_task_refs(
        {"embedded": {"task-reference": "stuff before <edge3> stuff after"}},
        {"embedded": "stuff before tid3 stuff after"},
    )


def test_task_refs_escaping(assert_task_refs):
    "resolve_task_references resolves escapes in task references"
    assert_task_refs(
        {"escape": {"task-reference": "<<><edge3>>"}}, {"escape": "<tid3>"}
    )


def test_task_refs_multikey(assert_task_refs):
    "resolve_task_references is ignored when there is another key in the dict"
    assert_task_refs(
        {"escape": {"task-reference": "<edge3>", "another-key": True}},
        {"escape": {"task-reference": "<edge3>", "another-key": True}},
    )


def test_task_refs_self(assert_task_refs):
    "resolve_task_references resolves `self` to the provided task id"
    assert_task_refs({"escape": {"task-reference": "<self>"}}, {"escape": "tid-self"})


def test_task_refs_decision(assert_task_refs):
    "resolve_task_references resolves `decision` to the provided decision task id"
    assert_task_refs(
        {"escape": {"task-reference": "<decision>"}}, {"escape": "tid-decision"}
    )


def test_task_refs_invalid():
    "resolve_task_references raises a KeyError on reference to an invalid task"
    with pytest.raises(KeyError):
        resolve_task_references(
            "subject",
            {"task-reference": "<no-such>"},
            "tid-self",
            "tid-decision",
            {},
        )


@pytest.fixture
def assert_artifact_refs(monkeypatch):
    monkeypatch.setenv("TASKCLUSTER_ROOT_URL", test_root_url())

    def inner(input, output):
        # Clear memoized function
        get_root_url.clear()
        taskid_for_edge_name = {"edge%d" % n: "tid%d" % n for n in range(1, 4)}
        assert (
            resolve_task_references(
                "subject", input, "tid-self", "tid-decision", taskid_for_edge_name
            )
            == output
        )

    return inner


def test_artifact_refs_in_list(assert_artifact_refs):
    "resolve_task_references resolves artifact references in a list"
    assert_artifact_refs(
        {"in-a-list": ["stuff", {"artifact-reference": "<edge1/public/foo/bar>"}]},
        {
            "in-a-list": [
                "stuff",
                test_root_url() + "/api/queue/v1/task/tid1/artifacts/public/foo/bar",
            ]
        },
    )


def test_artifact_refs_in_dict(assert_artifact_refs):
    "resolve_task_references resolves artifact references in a dict"
    assert_artifact_refs(
        {"in-a-dict": {"stuff": {"artifact-reference": "<edge2/public/bar/foo>"}}},
        {
            "in-a-dict": {
                "stuff": test_root_url()
                + "/api/queue/v1/task/tid2/artifacts/public/bar/foo"
            }
        },
    )


def test_artifact_refs_in_string(assert_artifact_refs):
    "resolve_task_references resolves artifact references embedded in a string"
    assert_artifact_refs(
        {
            "stuff": {
                "artifact-reference": "<edge1/public/filename> and <edge2/public/bar>"
            }
        },
        {
            "stuff": test_root_url()
            + "/api/queue/v1/task/tid1/artifacts/public/filename and "
            + test_root_url()
            + "/api/queue/v1/task/tid2/artifacts/public/bar"
        },
    )


def test_artifact_refs_self():
    "resolve_task_references raises keyerror on artifact references to `self`"
    with pytest.raises(KeyError):
        resolve_task_references(
            "subject",
            {"artifact-reference": "<self/public/artifact>"},
            "tid-self",
            "tid-decision",
            {},
        )


def test_artifact_refs_decision(assert_artifact_refs):
    "resolve_task_references resolves `decision` to the provided decision task id"
    assert_artifact_refs(
        {"stuff": {"artifact-reference": "<decision/public/artifact>"}},
        {
            "stuff": test_root_url()
            + "/api/queue/v1/task/tid-decision/artifacts/public/artifact"
        },
    )


def test_artifact_refs_invalid():
    "resolve_task_references raises a keyerror on reference to an invalid task"
    with pytest.raises(KeyError):
        resolve_task_references(
            "subject",
            {"artifact-reference": "<no-such/public/artifact>"},
            "tid-self",
            "tid-decision",
            {},
        )


def test_artifact_refs_badly_formed():
    "resolve_task_references ignores badly-formatted artifact references"
    for inv in ["<edge1>", "edge1/foo>", "<edge1>/foo", "<edge1>foo"]:
        resolved = resolve_task_references(
            "subject", {"artifact-reference": inv}, "tid-self", "tid-decision", {}
        )
        assert resolved == inv
