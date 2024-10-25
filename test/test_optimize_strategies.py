# Any copyright is dedicated to the public domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import logging
import os
from datetime import datetime
from time import mktime

import pytest
from pytest_taskgraph import make_task

from taskgraph.optimize.strategies import IndexSearch, SkipUnlessChanged


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
    "state,expires,expected,logs",
    (
        (
            "completed",
            "2021-06-06T14:53:16.937Z",
            False,
            (
                "not replacing {label} with {taskid} because it expires before {deadline}",
                "not replacing {label} with {taskid} because it expires before {deadline}",
            ),
        ),
        ("completed", "2021-06-08T14:53:16.937Z", "abc", ()),
        (
            "exception",
            "2021-06-08T14:53:16.937Z",
            False,
            (
                "not replacing {label} with {taskid} because it is in failed or exception state",
                "not replacing {label} with {taskid} because it is in failed or exception state",
            ),
        ),
        (
            "failed",
            "2021-06-08T14:53:16.937Z",
            False,
            (
                "not replacing {label} with {taskid} because it is in failed or exception state",
                "not replacing {label} with {taskid} because it is in failed or exception state",
            ),
        ),
    ),
)
def test_index_search(caplog, responses, params, state, expires, expected, logs):
    caplog.set_level(logging.DEBUG, "optimization")
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
            make_task("task-label"),
            params,
            deadline,
            ([index_path], label_to_taskid, taskid_to_status),
        )
        == expected
    )
    # test the non-batched variant as well
    assert (
        opt.should_replace_task(make_task("task-label"), params, deadline, [index_path])
        == expected
    )

    if logs:
        log_records = [
            (
                "optimization",
                logging.DEBUG,
                m.format(label="task-label", taskid=taskid, deadline=deadline),
            )
            for m in logs
        ]
        assert caplog.record_tuples == log_records


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
            {
                "head_rev": "8843d7f92416211de9ebb963ff4ce28125932878",
                "base_rev": "8843d7f92416211de9ebb963ff4ce28125932878",
                "files_changed": ["bar.txt"],
            },
            ["foo.txt"],
            False,
            id="cron task",
        ),
    ),
)
def test_skip_unless_changed(caplog, params, file_patterns, should_optimize):
    caplog.set_level(logging.DEBUG, "optimization")
    task = make_task("task")

    opt = SkipUnlessChanged()
    assert opt.should_remove_task(task, params, file_patterns) == should_optimize

    if should_optimize:
        assert caplog.record_tuples == [
            (
                "optimization",
                logging.DEBUG,
                f'no files found matching a pattern in `skip-unless-changed` for "{task.label}"',
            ),
        ]
