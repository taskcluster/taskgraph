# Any copyright is dedicated to the public domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import os
from datetime import datetime
from time import mktime

import pytest

from taskgraph.optimize.strategies import IndexSearch


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

    opt = IndexSearch()
    deadline = "2021-06-07T19:03:20.482Z"
    assert opt.should_replace_task({}, params, deadline, (index_path,)) == expected
