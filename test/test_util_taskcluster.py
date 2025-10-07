# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import os

import pytest

from taskgraph.task import Task
from taskgraph.util import taskcluster as tc


@pytest.fixture
def root_url():
    return "https://tc.example.com"


@pytest.fixture(autouse=True)
def mock_environ(monkeypatch, root_url):
    # Ensure user specified environment variables don't interfere with URLs.
    monkeypatch.setattr(
        os,
        "environ",
        {
            "TASKCLUSTER_ROOT_URL": root_url,
        },
    )


@pytest.fixture(autouse=True)
def mock_production_taskcluster_root_url(monkeypatch, root_url):
    monkeypatch.setattr(tc, "PRODUCTION_TASKCLUSTER_ROOT_URL", root_url)


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
    tc.get_root_url.cache_clear()
    task_id = "abc"
    path = "public/log.txt"
    expected = "https://tc.example.com/api/queue/v1/task/abc/artifacts/public/log.txt"
    expected_proxy = (
        "https://taskcluster-proxy.net/api/queue/v1/task/abc/artifacts/public/log.txt"
    )

    # Test with default root URL (no proxy)
    tc.get_root_url.cache_clear()
    assert tc.get_artifact_url(task_id, path) == expected

    # Test that proxy URL is NOT used by default (since use_proxy defaults to False)
    monkeypatch.setenv("TASKCLUSTER_PROXY_URL", "https://taskcluster-proxy.net")
    tc.get_root_url.cache_clear()
    assert tc.get_artifact_url(task_id, path) == expected

    # Test with use_proxy=True (should use proxy URL)
    assert tc.get_artifact_url(task_id, path, use_proxy=True) == expected_proxy

    # Test with use_proxy=True but no proxy available (not in a task)
    monkeypatch.delenv("TASKCLUSTER_PROXY_URL")
    monkeypatch.delenv("TASK_ID", raising=False)
    tc.get_root_url.cache_clear()
    with pytest.raises(RuntimeError) as exc:
        tc.get_artifact_url(task_id, path, use_proxy=True)
    assert "taskcluster-proxy is not available when not executing in a task" in str(
        exc.value
    )

    # Test with use_proxy=True but proxy not enabled (in a task without proxy)
    monkeypatch.setenv("TASK_ID", "some-task-id")
    with pytest.raises(RuntimeError) as exc:
        tc.get_artifact_url(task_id, path, use_proxy=True)
    assert "taskcluster-proxy is not enabled for this task" in str(exc.value)


def test_get_artifact(responses, root_url):
    tid = "abc123"
    tc.get_taskcluster_client.cache_clear()

    # Test text artifact
    responses.get(
        f"{root_url}/api/queue/v1/task/{tid}/artifacts/artifact.txt",
        body=b"foobar",
    )
    raw = tc.get_artifact(tid, "artifact.txt")
    assert raw.read() == b"foobar"

    # Test JSON artifact
    responses.get(
        f"{root_url}/api/queue/v1/task/{tid}/artifacts/artifact.json",
        json={"foo": "bar"},
    )
    result = tc.get_artifact(tid, "artifact.json")
    assert result == {"foo": "bar"}

    # Test YAML artifact
    expected_result = {"foo": b"\xe2\x81\x83".decode()}
    responses.get(
        f"{root_url}/api/queue/v1/task/{tid}/artifacts/artifact.yml",
        body=b'foo: "\xe2\x81\x83"',
    )
    result = tc.get_artifact(tid, "artifact.yml")
    assert result == expected_result


def test_list_artifact(responses, root_url):
    tid = "abc123"
    tc.get_taskcluster_client.cache_clear()

    responses.get(
        f"{root_url}/api/queue/v1/task/{tid}",
        json={"artifacts": ["file1.txt", "file2.json"]},
    )

    result = tc.list_artifacts(tid)
    assert result == ["file1.txt", "file2.json"]


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
    tc.get_root_url.cache_clear()
    assert tc.get_index_url(index) == f"{root_url}/api/index/v1/task/foo"
    assert (
        tc.get_index_url(index, multiple=True) == f"{root_url}/api/index/v1/tasks/foo"
    )


def test_find_task_id(responses, root_url):
    tid = "abc123"
    index = "foo"
    tc.get_taskcluster_client.cache_clear()

    responses.get(
        f"{root_url}/api/index/v1/task/{index}",
        json={"taskId": tid},
    )
    result = tc.find_task_id(index)
    assert result == tid


def test_find_task_id_batched(responses, root_url):
    tc.get_taskcluster_client.cache_clear()
    responses.post(
        f"{root_url}/api/index/v1/tasks/indexes",
        json={
            "tasks": [{"taskId": "abc", "namespace": "index.abc"}],
            "continuationToken": "abc",
        },
    )
    responses.post(
        f"{root_url}/api/index/v1/tasks/indexes",
        json={
            "tasks": [{"taskId": "def", "namespace": "index.def"}],
            "continuationToken": None,
        },
    )

    result = tc.find_task_id_batched(["index.abc", "index.def"])
    assert result == {"index.abc": "abc", "index.def": "def"}


def test_get_artifact_from_index(responses, root_url):
    index = "foo"
    path = "file.txt"
    tc.get_taskcluster_client.cache_clear()

    responses.get(
        f"{root_url}/api/index/v1/task/{index}/artifacts/{path}",
        body=b"foobar",
    )

    result = tc.get_artifact_from_index(index, path)
    assert result.read() == b"foobar"


def test_list_tasks(responses, root_url):
    index = "foo"
    tc.get_taskcluster_client.cache_clear()
    responses.get(
        f"{root_url}/api/index/v1/tasks/{index}",
        json={
            "tasks": [
                {
                    "namespace": "foo.A08Cbf8KSFqMsa3J0m-yTg",
                    "taskId": "A08Cbf8KSFqMsa3J0m-yTg",
                    "rank": 0,
                    "data": {},
                    "expires": "2025-10-29T11:58:45.474Z",
                }
            ],
            "continuationToken": "qzxkXG8ZWa",
        },
    )
    responses.get(
        f"{root_url}/api/index/v1/tasks/{index}",
        json={
            "tasks": [
                {
                    "namespace": "foo.a0ha8axBTVCCgq1zm6uUhQ",
                    "taskId": "a0ha8axBTVCCgq1zm6uUhQ",
                    "rank": 0,
                    "data": {},
                    "expires": "2025-10-29T11:57:33.217Z",
                }
            ],
        },
    )

    result = tc.list_tasks(index)
    assert result == ["a0ha8axBTVCCgq1zm6uUhQ", "A08Cbf8KSFqMsa3J0m-yTg"]


def test_parse_time():
    exp = datetime.datetime(2018, 10, 10, 18, 33, 3, 463000)
    assert tc.parse_time("2018-10-10T18:33:03.463Z") == exp


def test_get_task_url(root_url):
    tid = "123"
    tc.get_root_url.cache_clear()
    assert tc.get_task_url(tid) == f"{root_url}/api/queue/v1/task/{tid}"


def test_get_task_definition(responses, root_url):
    tid = "abc123"
    tc.get_taskcluster_client.cache_clear()

    responses.get(
        f"{root_url}/api/queue/v1/task/{tid}",
        json={"payload": "blah"},
    )
    result = tc.get_task_definition(tid)
    assert result == {"payload": "blah"}


def test_cancel_task(responses, root_url):
    tid = "abc123"
    tc.get_taskcluster_client.cache_clear()

    responses.post(
        f"{root_url}/api/queue/v1/task/{tid}/cancel",
        json={"status": {"taskId": tid, "state": "cancelled"}},
    )
    tc.cancel_task(tid)


def test_status_task(responses, root_url):
    tid = "abc123"
    tc.get_taskcluster_client.cache_clear()

    responses.get(
        f"{root_url}/api/queue/v1/task/{tid}/status",
        json={"status": {"state": "running"}},
    )
    result = tc.status_task(tid)
    assert result == {"state": "running"}


def test_status_task_batched(responses, root_url):
    tc.get_taskcluster_client.cache_clear()
    responses.post(
        f"{root_url}/api/queue/v1/tasks/status",
        json={
            "statuses": [
                {
                    "taskId": "abc",
                    "status": {"taskId": "abc", "state": "completed", "runs": []},
                }
            ],
            "continuationToken": "abc",
        },
    )
    responses.post(
        f"{root_url}/api/queue/v1/tasks/status",
        json={
            "statuses": [
                {
                    "taskId": "def",
                    "status": {"taskId": "def", "state": "exception", "runs": []},
                }
            ],
            "continuationToken": None,
        },
    )

    result = tc.status_task_batched(["abc", "def"])
    assert result == {
        "abc": {"taskId": "abc", "state": "completed", "runs": []},
        "def": {"taskId": "def", "state": "exception", "runs": []},
    }


def test_state_task(responses, root_url):
    tid = "abc123"
    tc.get_taskcluster_client.cache_clear()

    responses.get(
        f"{root_url}/api/queue/v1/task/{tid}/status",
        json={"status": {"state": "running"}},
    )

    result = tc.state_task(tid)
    assert result == "running"


def test_rerun_task(responses, root_url):
    tid = "abc123"
    tc.get_taskcluster_client.cache_clear()

    responses.post(
        f"{root_url}/api/queue/v1/task/{tid}/rerun",
        json={"status": {"taskId": tid, "state": "unscheduled"}},
    )
    tc.rerun_task(tid)


def test_get_current_scopes(responses, root_url):
    tc.get_taskcluster_client.cache_clear()

    responses.get(
        f"{root_url}/api/auth/v1/scopes/current",
        json={"scopes": ["foo", "bar"]},
    )

    result = tc.get_current_scopes()
    assert result == ["foo", "bar"]


def test_purge_cache(responses, root_url):
    provisioner = "hardware"
    worker_type = "mac"
    cache = "cache"
    tc.get_taskcluster_client.cache_clear()

    # Modern Taskcluster API uses workerPoolId format
    # The "/" in the workerPoolId gets URL-encoded as %2F
    responses.post(
        f"{root_url}/api/purge-cache/v1/purge-cache/hardware%2Fmac",
        json={},
    )

    tc.purge_cache(provisioner, worker_type, cache)


def test_send_email(responses, root_url):
    data = {
        "address": "test@example.org",
        "subject": "Hello",
        "content": "Goodbye",
        "link": "https://example.org",
    }
    tc.get_taskcluster_client.cache_clear()

    responses.post(
        f"{root_url}/api/notify/v1/email",
        json={},
    )

    tc.send_email(**data)


def test_list_task_group_incomplete_tasks(responses, root_url):
    tgid = "abc123"
    tc.get_taskcluster_client.cache_clear()

    responses.get(
        f"{root_url}/api/queue/v1/task-group/{tgid}/list",
        json={
            "tasks": [
                {"status": {"taskId": "1", "state": "pending"}},
                {"status": {"taskId": "2", "state": "completed"}},
                {"status": {"taskId": "3", "state": "running"}},
            ],
            "continuationToken": "page2",
        },
    )

    responses.get(
        f"{root_url}/api/queue/v1/task-group/{tgid}/list",
        json={
            "tasks": [
                {"status": {"taskId": "4", "state": "unscheduled"}},
                {"status": {"taskId": "5", "state": "failed"}},
                {"status": {"taskId": "6", "state": "pending"}},
            ],
            "continuationToken": "page3",
        },
    )

    responses.get(
        f"{root_url}/api/queue/v1/task-group/{tgid}/list",
        json={
            "tasks": [
                {"status": {"taskId": "7", "state": "running"}},
                {"status": {"taskId": "8", "state": "completed"}},
            ]
        },
    )

    result = list(tc.list_task_group_incomplete_tasks(tgid))
    assert result == ["1", "3", "4", "6", "7"]


def test_get_ancestors(responses, root_url):
    tc.get_task_definition.cache_clear()
    tc._get_deps.cache_clear()
    tc.get_taskcluster_client.cache_clear()

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

    # Mock API responses for each task definition
    for task_id, definition in task_definitions.items():
        responses.get(
            f"{root_url}/api/queue/v1/task/{task_id}",
            json=definition,
        )

    got = tc.get_ancestors(["bbb", "fff"])
    expected = {
        "aaa": "task-aaa",
        "ccc": "task-ccc",
        "ddd": "task-ddd",
        "eee": "task-eee",
    }
    assert got == expected, f"got: {got}, expected: {expected}"


def test_get_ancestors_string(responses, root_url):
    tc.get_task_definition.cache_clear()
    tc._get_deps.cache_clear()
    tc.get_taskcluster_client.cache_clear()

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

    # Mock API responses for each task definition
    for task_id, definition in task_definitions.items():
        responses.get(
            f"{root_url}/api/queue/v1/task/{task_id}",
            json=definition,
        )

    got = tc.get_ancestors("fff")
    expected = {
        "aaa": "task-aaa",
        "bbb": "task-bbb",
        "ccc": "task-ccc",
        "ddd": "task-ddd",
        "eee": "task-eee",
    }
    assert got == expected, f"got: {got}, expected: {expected}"
