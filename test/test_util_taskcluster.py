# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import os

import pytest
from requests import Session
from requests.exceptions import HTTPError
from requests.packages.urllib3.util.retry import Retry
from responses import matchers

from taskgraph.task import Task
from taskgraph.util import taskcluster as tc


@pytest.fixture(autouse=True)
def mock_environ(monkeypatch):
    # Ensure user specified environment variables don't interfere with URLs.
    monkeypatch.setattr(os, "environ", {})


@pytest.fixture(autouse=True)
def mock_production_taskcluster_root_url(monkeypatch):
    monkeypatch.setattr(tc, "PRODUCTION_TASKCLUSTER_ROOT_URL", "https://tc.example.com")


@pytest.fixture
def root_url(mock_environ):
    tc.get_root_url.clear()
    return tc.get_root_url(False)


@pytest.fixture
def proxy_root_url(monkeypatch, mock_environ):
    monkeypatch.setenv("TASK_ID", "123")
    monkeypatch.setenv("TASKCLUSTER_PROXY_URL", "https://taskcluster-proxy.net")
    tc.get_root_url.clear()
    return tc.get_root_url(True)


def test_get_root_url(monkeypatch):

    tc.get_root_url.clear()
    assert tc.get_root_url(False) == tc.PRODUCTION_TASKCLUSTER_ROOT_URL

    custom_url = "https://taskcluster-root.net"
    monkeypatch.setenv("TASKCLUSTER_ROOT_URL", custom_url)
    tc.get_root_url.clear()
    assert tc.get_root_url(False) == custom_url

    # trailing slash is normalized
    monkeypatch.setenv("TASKCLUSTER_ROOT_URL", custom_url + "/")
    tc.get_root_url.clear()
    assert tc.get_root_url(False) == custom_url

    with pytest.raises(RuntimeError):
        tc.get_root_url(True)

    task_id = "123"
    monkeypatch.setenv("TASK_ID", task_id)

    with pytest.raises(RuntimeError):
        tc.get_root_url(True)

    proxy_url = "https://taskcluster-proxy.net"
    monkeypatch.setenv("TASKCLUSTER_PROXY_URL", proxy_url)
    assert tc.get_root_url(True) == proxy_url
    tc.get_root_url.clear()

    # no default set
    monkeypatch.setattr(tc, "PRODUCTION_TASKCLUSTER_ROOT_URL", None)
    monkeypatch.delenv("TASKCLUSTER_ROOT_URL")
    with pytest.raises(RuntimeError):
        tc.get_root_url(False)


def test_get_session():
    session = tc.get_session()
    assert isinstance(session, Session)
    assert list(session.adapters.keys()) == ["https://", "http://"]

    adapter = session.adapters["https://"]
    assert adapter._pool_connections == tc.CONCURRENCY
    assert adapter._pool_maxsize == tc.CONCURRENCY

    retry = adapter.max_retries
    assert isinstance(retry, Retry)
    assert retry.total == 5


def test_do_request(responses):
    responses.add(responses.GET, "https://example.org", body="method:get")
    r = tc._do_request("https://example.org")
    assert r.text == "method:get"

    responses.add(responses.POST, "https://example.org", body="method:post")
    r = tc._do_request("https://example.org", method="post")
    assert r.text == "method:post"

    r = tc._do_request("https://example.org", data={"foo": "bar"})
    assert r.text == "method:post"

    responses.replace(responses.GET, "https://example.org", status=404)
    with pytest.raises(HTTPError):
        tc._do_request("https://example.org")


def test_get_artifact(responses, root_url):
    tid = 123
    responses.add(
        responses.GET,
        f"{root_url}/api/queue/v1/task/{tid}/artifacts/artifact.txt",
        body="foobar",
    )
    raw = tc.get_artifact(tid, "artifact.txt")
    assert raw.read() == b"foobar"

    responses.add(
        responses.GET,
        f"{root_url}/api/queue/v1/task/{tid}/artifacts/artifact.json",
        body='{"foo": "bar"}',
    )
    assert tc.get_artifact(tid, "artifact.json") == {"foo": "bar"}

    responses.add(
        responses.GET,
        f"{root_url}/api/queue/v1/task/{tid}/artifacts/artifact.yml",
        body="foo: bar",
    )
    assert tc.get_artifact(tid, "artifact.yml") == {"foo": "bar"}


def test_list_artifact(responses, root_url):
    tid = 123
    responses.add(
        responses.GET,
        f"{root_url}/api/queue/v1/task/{tid}/artifacts",
        json={"artifacts": ["file1.txt", "file2.json"]},
    )
    assert tc.list_artifacts(tid) == ["file1.txt", "file2.json"]


def test_get_artifact_path():
    path = "file.txt"
    prefix = "public/build"
    task = {
        "kind": "test",
        "label": "test",
        "task": {},
        "optimization": None,
        "attributes": {},
    }
    assert tc.get_artifact_path(task, path) == f"{prefix}/{path}"
    assert tc.get_artifact_path(Task.from_json(task), path) == f"{prefix}/{path}"

    with pytest.raises(Exception):
        tc.get_artifact_path("task", path)

    prefix = "custom/prefix"
    task["attributes"]["artifact_prefix"] = prefix
    assert tc.get_artifact_path(task, path) == f"{prefix}/{path}"
    assert tc.get_artifact_path(Task.from_json(task), path) == f"{prefix}/{path}"


def test_get_index_url(root_url):
    index = "foo"
    assert tc.get_index_url(index) == f"{root_url}/api/index/v1/task/foo"
    assert (
        tc.get_index_url(index, multiple=True) == f"{root_url}/api/index/v1/tasks/foo"
    )


def test_find_task_id(responses, root_url):
    tid = 123
    index = "foo"

    responses.add(
        responses.GET, f"{root_url}/api/index/v1/task/{index}", json={"taskId": tid}
    )
    assert tc.find_task_id(index) == tid

    responses.replace(
        responses.GET,
        f"{root_url}/api/index/v1/task/{index}",
        status=404,
    )
    with pytest.raises(KeyError):
        tc.find_task_id(index)

    responses.replace(
        responses.GET,
        f"{root_url}/api/index/v1/task/{index}",
        status=500,
    )
    with pytest.raises(HTTPError):
        tc.find_task_id(index)


def test_get_artifact_from_index(responses, root_url):
    index = "foo"
    path = "file.txt"
    responses.add(
        responses.GET,
        f"{root_url}/api/index/v1/task/{index}/artifacts/{path}",
        body="foobar",
    )
    assert tc.get_artifact_from_index(index, path).read() == b"foobar"


def test_list_tasks(responses, root_url):
    index = "foo"
    responses.add(
        responses.POST,
        f"{root_url}/api/index/v1/tasks/{index}",
        json={
            "continuationToken": "x",
            "tasks": [{"taskId": "123", "expires": "2023-02-10T19:07:33.700Z"}],
        },
    )
    responses.add(
        responses.POST,
        f"{root_url}/api/index/v1/tasks/{index}",
        json={
            "tasks": [{"taskId": "abc", "expires": "2023-02-09T19:07:33.700Z"}],
        },
    )
    assert tc.list_tasks(index) == ["abc", "123"]


def test_parse_time():
    exp = datetime.datetime(2018, 10, 10, 18, 33, 3, 463000)
    assert tc.parse_time("2018-10-10T18:33:03.463Z") == exp


def test_get_task_url(root_url):
    tid = "123"
    assert tc.get_task_url(tid) == f"{root_url}/api/queue/v1/task/{tid}"


def test_get_task_definition(responses, root_url):
    tid = "123"
    responses.add(
        responses.GET, f"{root_url}/api/queue/v1/task/{tid}", json={"payload": "blah"}
    )
    assert tc.get_task_definition(tid) == {"payload": "blah"}


def test_cancel_task(responses, root_url):
    tid = "123"
    url = f"{root_url}/api/queue/v1/task/{tid}/cancel"
    responses.add(
        responses.POST,
        url,
    )
    tc.cancel_task(tid)
    responses.assert_call_count(url, 1)


def test_status_task(responses, root_url):
    tid = "123"
    responses.add(
        responses.GET,
        f"{root_url}/api/queue/v1/task/{tid}/status",
        json={"status": {"state": "running"}},
    )
    assert tc.status_task(tid) == {"state": "running"}


def test_state_task(responses, root_url):
    tid = "123"
    responses.add(
        responses.GET,
        f"{root_url}/api/queue/v1/task/{tid}/status",
        json={"status": {"state": "running"}},
    )
    assert tc.state_task(tid) == "running"


def test_rerun_task(responses, proxy_root_url):
    tid = "123"
    url = f"{proxy_root_url}/api/queue/v1/task/{tid}/rerun"
    responses.add(
        responses.POST,
        url,
    )
    tc.rerun_task(tid)
    responses.assert_call_count(url, 1)


def test_get_current_scopes(responses, proxy_root_url):
    responses.add(
        responses.GET,
        f"{proxy_root_url}/api/auth/v1/scopes/current",
        json={"scopes": ["foo", "bar"]},
    )
    assert tc.get_current_scopes() == ["foo", "bar"]


def test_purge_cache(responses, root_url):
    provisioner = "hardware"
    worker_type = "mac"
    cache = "cache"

    url = f"{root_url}/api/purge-cache/v1/purge-cache/{provisioner}/{worker_type}"
    responses.add(
        responses.POST,
        url,
        match=[matchers.json_params_matcher({"cacheName": cache})],
    )
    tc.purge_cache(provisioner, worker_type, cache)
    responses.assert_call_count(url, 1)


def test_send_email(responses, root_url):
    data = {
        "address": "test@example.org",
        "subject": "Hello",
        "content": "Goodbye",
        "link": "https://example.org",
    }
    url = f"{root_url}/api/notify/v1/email"
    responses.add(
        responses.POST,
        url,
        match=[matchers.json_params_matcher(data)],
    )
    tc.send_email(**data)
    responses.assert_call_count(url, 1)


def test_list_task_group_incomplete_tasks(responses, root_url):
    tgid = "123"

    url = f"{root_url}/api/queue/v1/task-group/{tgid}/list"
    responses.add(
        responses.GET,
        url,
        json={
            "continuationToken": "x",
            "tasks": [
                {"status": {"taskId": "1", "state": "pending"}},
                {"status": {"taskId": "2", "state": "unscheduled"}},
            ],
        },
    )
    responses.add(
        responses.GET,
        url,
        json={
            "tasks": [
                {"status": {"taskId": "3", "state": "running"}},
                {"status": {"taskId": "4", "state": "completed"}},
            ],
        },
    )
    assert list(tc.list_task_group_incomplete_tasks(tgid)) == ["1", "2", "3"]
