# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import os
import unittest.mock as mock

import pytest

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
    tc.get_root_url.cache_clear()
    return tc.get_root_url()


@pytest.fixture
def proxy_root_url(monkeypatch, mock_environ):
    monkeypatch.setenv("TASK_ID", "123")
    monkeypatch.setenv("TASKCLUSTER_PROXY_URL", "https://taskcluster-proxy.net")
    tc.get_root_url.cache_clear()
    return tc.get_root_url()


def test_get_root_url(monkeypatch):
    tc.get_root_url.cache_clear()
    assert tc.get_root_url() == tc.PRODUCTION_TASKCLUSTER_ROOT_URL

    custom_url = "https://taskcluster-root.net"
    monkeypatch.setenv("TASKCLUSTER_ROOT_URL", custom_url)
    tc.get_root_url.cache_clear()
    assert tc.get_root_url() == custom_url

    # trailing slash is normalized
    monkeypatch.setenv("TASKCLUSTER_ROOT_URL", custom_url + "/")
    tc.get_root_url.cache_clear()
    assert tc.get_root_url() == custom_url

    # TASKCLUSTER_PROXY_URL takes priority
    proxy_url = "https://taskcluster-proxy.net"
    monkeypatch.setenv("TASKCLUSTER_PROXY_URL", proxy_url)
    tc.get_root_url.cache_clear()
    assert tc.get_root_url() == proxy_url

    # Clean up proxy URL to test fallback
    monkeypatch.delenv("TASKCLUSTER_PROXY_URL")
    tc.get_root_url.cache_clear()
    assert tc.get_root_url() == custom_url

    # no default set, should raise error
    monkeypatch.setattr(tc, "PRODUCTION_TASKCLUSTER_ROOT_URL", None)
    monkeypatch.delenv("TASKCLUSTER_ROOT_URL")
    tc.get_root_url.cache_clear()
    with pytest.raises(RuntimeError):
        tc.get_root_url()


def test_get_artifact_url(monkeypatch):
    task_id = "abc"
    path = "public/log.txt"

    # Test with default root URL
    tc.get_root_url.cache_clear()
    expected = "https://tc.example.com/api/queue/v1/task/abc/artifacts/public/log.txt"
    assert tc.get_artifact_url(task_id, path) == expected

    # Test with proxy URL (takes priority)
    monkeypatch.setenv("TASKCLUSTER_PROXY_URL", "https://taskcluster-proxy.net")
    tc.get_root_url.cache_clear()
    expected_proxy = (
        "https://taskcluster-proxy.net/api/queue/v1/task/abc/artifacts/public/log.txt"
    )
    assert tc.get_artifact_url(task_id, path) == expected_proxy


def test_get_artifact(monkeypatch):
    tid = 123

    mock_queue = mock.MagicMock()

    def mock_client(service):
        if service == "queue":
            return mock_queue
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    mock_response_txt = mock.MagicMock()
    mock_response_txt.raw.read.return_value = b"foobar"
    mock_queue.getLatestArtifact.return_value = mock_response_txt

    raw = tc.get_artifact(tid, "artifact.txt")
    assert raw.read() == b"foobar"
    mock_queue.getLatestArtifact.assert_called_with(tid, "artifact.txt")

    mock_response_json = mock.MagicMock()
    mock_response_json.json.return_value = {"foo": "bar"}
    mock_queue.getLatestArtifact.return_value = mock_response_json
    result = tc.get_artifact(tid, "artifact.json")
    assert result == {"foo": "bar"}

    expected_result = {"foo": b"\xe2\x81\x83".decode()}
    mock_response_yml = mock.MagicMock()
    mock_response_yml.content = b'foo: "\xe2\x81\x83"'
    mock_queue.getLatestArtifact.return_value = mock_response_yml
    result = tc.get_artifact(tid, "artifact.yml")
    assert result == expected_result


def test_list_artifact(monkeypatch):
    tid = 123

    mock_queue = mock.MagicMock()

    def mock_client(service):
        if service == "queue":
            return mock_queue
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    mock_queue.task.return_value = {"artifacts": ["file1.txt", "file2.json"]}

    result = tc.list_artifacts(tid)
    assert result == ["file1.txt", "file2.json"]
    mock_queue.task.assert_called_with(tid)


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


def test_find_task_id(monkeypatch):
    tid = 123
    index = "foo"

    mock_index = mock.MagicMock()

    def mock_client(service):
        if service == "index":
            return mock_index
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    mock_index.findTask.return_value = {"taskId": tid}
    result = tc.find_task_id(index)
    assert result == tid
    mock_index.findTask.assert_called_with(index)


def test_get_artifact_from_index(monkeypatch):
    index = "foo"
    path = "file.txt"

    mock_index = mock.MagicMock()

    def mock_client(service):
        if service == "index":
            return mock_index
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    mock_response = mock.MagicMock()
    mock_response.raw.read.return_value = b"foobar"
    mock_index.findArtifactFromTask.return_value = mock_response

    result = tc.get_artifact_from_index(index, path)
    assert result.read() == b"foobar"
    mock_index.findArtifactFromTask.assert_called_with(index, path)


def test_list_tasks(monkeypatch):
    index = "foo"

    mock_index = mock.MagicMock()

    def mock_client(service):
        if service == "index":
            return mock_index
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    mock_index.listTasks.return_value = {
        "tasks": [
            {"taskId": "123", "expires": "2023-02-10T19:07:33.700Z"},
            {"taskId": "abc", "expires": "2023-02-09T19:07:33.700Z"},
        ]
    }

    result = tc.list_tasks(index)
    assert result == ["abc", "123"]
    mock_index.listTasks.assert_called_with(index, {})


def test_parse_time():
    exp = datetime.datetime(2018, 10, 10, 18, 33, 3, 463000)
    assert tc.parse_time("2018-10-10T18:33:03.463Z") == exp


def test_get_task_url(root_url):
    tid = "123"
    assert tc.get_task_url(tid) == f"{root_url}/api/queue/v1/task/{tid}"


def test_get_task_definition(monkeypatch):
    tid = "123"

    mock_queue = mock.MagicMock()

    def mock_client(service):
        if service == "queue":
            return mock_queue
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    mock_queue.task.return_value = {"payload": "blah"}
    result = tc.get_task_definition(tid)
    assert result == {"payload": "blah"}
    mock_queue.task.assert_called_with(tid)


def test_cancel_task(monkeypatch):
    tid = "123"

    mock_queue = mock.MagicMock()

    def mock_client(service):
        if service == "queue":
            return mock_queue
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    tc.cancel_task(tid)
    mock_queue.cancelTask.assert_called_with(tid)


def test_status_task(monkeypatch):
    tid = "123"

    mock_queue = mock.MagicMock()

    def mock_client(service):
        if service == "queue":
            return mock_queue
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    mock_queue.status.return_value = {"status": {"state": "running"}}
    result = tc.status_task(tid)
    assert result == {"state": "running"}
    mock_queue.status.assert_called_with(tid)


def test_state_task(monkeypatch):
    tid = "123"

    monkeypatch.setattr(
        tc, "status_task", mock.MagicMock(return_value={"state": "running"})
    )

    result = tc.state_task(tid)
    assert result == "running"


def test_rerun_task(monkeypatch):
    tid = "123"

    mock_queue = mock.MagicMock()

    def mock_client(service):
        if service == "queue":
            return mock_queue
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    tc.rerun_task(tid)
    mock_queue.rerunTask.assert_called_with(tid)


def test_get_current_scopes(monkeypatch):
    mock_auth = mock.MagicMock()

    def mock_client(service):
        if service == "auth":
            return mock_auth
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    mock_auth.currentScopes.return_value = {"scopes": ["foo", "bar"]}

    result = tc.get_current_scopes()
    assert result == ["foo", "bar"]
    mock_auth.currentScopes.assert_called_once()


def test_purge_cache(monkeypatch):
    provisioner = "hardware"
    worker_type = "mac"
    cache = "cache"

    mock_purge_cache = mock.MagicMock()

    def mock_client(service):
        if service == "purgeCache":
            return mock_purge_cache
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    tc.purge_cache(provisioner, worker_type, cache)
    mock_purge_cache.purgeCache.assert_called_with(
        provisioner, worker_type, {"cacheName": cache}
    )


def test_send_email(monkeypatch):
    data = {
        "address": "test@example.org",
        "subject": "Hello",
        "content": "Goodbye",
        "link": "https://example.org",
    }

    mock_notify = mock.MagicMock()

    def mock_client(service):
        if service == "notify":
            return mock_notify
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    tc.send_email(**data)
    mock_notify.email.assert_called_with(data)


def test_list_task_group_incomplete_tasks(monkeypatch):
    tgid = "123"

    mock_queue = mock.MagicMock()

    def mock_client(service):
        if service == "queue":
            return mock_queue
        return mock.MagicMock()

    monkeypatch.setattr(tc, "get_taskcluster_client", mock_client)

    mock_queue.listTaskGroup.return_value = {
        "tasks": [
            {"status": {"taskId": "1", "state": "pending"}},
            {"status": {"taskId": "2", "state": "unscheduled"}},
            {"status": {"taskId": "3", "state": "running"}},
            {"status": {"taskId": "4", "state": "completed"}},
        ]
    }

    result = list(tc.list_task_group_incomplete_tasks(tgid))
    assert result == ["1", "2", "3"]
    mock_queue.listTaskGroup.assert_called_with(tgid)


def test_get_ancestors(monkeypatch):
    tc.get_task_definition.cache_clear()
    tc._get_deps.cache_clear()

    task_definitions = {
        "fff": {
            "dependencies": ["eee", "ddd"],
            "metadata": {"name": "task-fff"},
        },
        "eee": {
            "dependencies": [],
            "metadata": {"name": "task-eee"},
        },
        "ddd": {
            "dependencies": ["ccc"],
            "metadata": {"name": "task-ddd"},
        },
        "ccc": {
            "dependencies": [],
            "metadata": {"name": "task-ccc"},
        },
        "bbb": {
            "dependencies": ["aaa"],
            "metadata": {"name": "task-bbb"},
        },
        "aaa": {
            "dependencies": [],
            "metadata": {"name": "task-aaa"},
        },
    }

    def mock_get_task_definition(task_id):
        return task_definitions.get(task_id)

    monkeypatch.setattr(tc, "get_task_definition", mock_get_task_definition)

    got = tc.get_ancestors(["bbb", "fff"])
    expected = {
        "aaa": "task-aaa",
        "ccc": "task-ccc",
        "ddd": "task-ddd",
        "eee": "task-eee",
    }
    assert got == expected, f"got: {got}, expected: {expected}"


def test_get_ancestors_string(monkeypatch):
    tc.get_task_definition.cache_clear()
    tc._get_deps.cache_clear()

    task_definitions = {
        "fff": {
            "dependencies": ["eee", "ddd"],
            "metadata": {"name": "task-fff"},
        },
        "eee": {
            "dependencies": [],
            "metadata": {"name": "task-eee"},
        },
        "ddd": {
            "dependencies": ["ccc", "bbb"],
            "metadata": {"name": "task-ddd"},
        },
        "ccc": {
            "dependencies": ["aaa"],
            "metadata": {"name": "task-ccc"},
        },
        "bbb": {
            "dependencies": [],
            "metadata": {"name": "task-bbb"},
        },
        "aaa": {
            "dependencies": [],
            "metadata": {"name": "task-aaa"},
        },
    }

    def mock_get_task_definition(task_id):
        return task_definitions.get(task_id)

    monkeypatch.setattr(tc, "get_task_definition", mock_get_task_definition)

    got = tc.get_ancestors("fff")
    expected = {
        "aaa": "task-aaa",
        "bbb": "task-bbb",
        "ccc": "task-ccc",
        "ddd": "task-ddd",
        "eee": "task-eee",
    }
    assert got == expected, f"got: {got}, expected: {expected}"
