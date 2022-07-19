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


def test_index_search(responses, params):
    taskid = "abc"
    index_path = "foo.bar.latest"
    responses.add(
        responses.GET,
        f"{os.environ['TASKCLUSTER_ROOT_URL']}/api/index/v1/task/{index_path}",
        json={"taskId": taskid},
        status=200,
    )

    opt = IndexSearch()
    assert opt.should_replace_task({}, params, (index_path,)) == "abc"
