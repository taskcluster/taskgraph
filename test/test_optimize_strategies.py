# Any copyright is dedicated to the public domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import os
from datetime import datetime
from time import mktime

import pytest

from taskgraph.optimize.strategies import IndexSearch, SkipUnlessChanged
from test.fixtures.gen import make_task


@pytest.fixture
def params():
    return {
        "branch": "integration/autoland",
        "head_repository": "https://hg.mozilla.org/integration/autoland",
        "head_rev": "abcdef",
        "project": "autoland",
        "pushlog_id": 1,
        "pushdate": mktime(datetime.now().timetuple()),
    }


@pytest.mark.parametrize(
    "state,expires,expected",
    (
        (
            "completed",
            "2021-06-06T14:53:16.937Z",
            False,
        ),
        ("completed", "2021-06-08T14:53:16.937Z", "abc"),
        (
            "exception",
            "2021-06-08T14:53:16.937Z",
            False,
        ),
        (
            "failed",
            "2021-06-08T14:53:16.937Z",
            False,
        ),
    ),
)
def test_index_search(responses, params, state, expires, expected):
    taskid = "abc"
    index_path = "foo.bar.latest"

    responses.add(
        responses.GET,
        f"{os.environ['TASKCLUSTER_ROOT_URL']}/api/index/v1/task/{index_path}",
        json={"taskId": taskid},
        status=200,
    )

    responses.add(
        responses.GET,
        f"{os.environ['TASKCLUSTER_ROOT_URL']}/api/queue/v1/task/{taskid}/status",
        json={
            "status": {
                "state": state,
                "expires": expires,
            }
        },
        status=200,
    )

    label_to_taskid = {index_path: taskid}
    taskid_to_status = {
        taskid: {
            "state": state,
            "expires": expires,
        }
    }

    opt = IndexSearch()
    deadline = "2021-06-07T19:03:20.482Z"
    assert (
        opt.should_replace_task(
            {}, params, deadline, ([index_path], label_to_taskid, taskid_to_status)
        )
        == expected
    )
    # test the non-batched variant as well
    assert opt.should_replace_task({}, params, deadline, [index_path]) == expected


@pytest.mark.parametrize(
    "params,file_patterns,should_optimize",
    (
        pytest.param({"files_changed": []}, ["foo.txt"], True, id="no files changed"),
        pytest.param(
            {"files_changed": ["foo.txt"]}, ["foo.txt"], False, id="files match"
        ),
        pytest.param(
            {"files_changed": ["foo.txt"]},
            ["bar.tx", "foo.txt"],
            False,
            id="files match multiple",
        ),
        pytest.param(
            {"files_changed": ["bar.txt"]}, ["foo.txt"], True, id="files don't match"
        ),
        pytest.param(
            {"repository_type": "hg", "pushlog_id": -1, "files_changed": ["bar.txt"]},
            ["foo.txt"],
            False,
            id="cron task",
        ),
    ),
)
def test_skip_unless_changed(params, file_patterns, should_optimize):
    task = make_task("task")

    opt = SkipUnlessChanged()
    assert opt.should_remove_task(task, params, file_patterns) == should_optimize
