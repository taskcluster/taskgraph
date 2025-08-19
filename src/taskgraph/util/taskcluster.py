# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import copy
import datetime
import functools
import logging
import os
from typing import Dict, List, Union

import requests
import taskcluster_urls as liburls
from requests.packages.urllib3.util.retry import Retry  # type: ignore

import taskcluster
from taskgraph.task import Task
from taskgraph.util import yaml

logger = logging.getLogger(__name__)

# this is set to true for `mach taskgraph action-callback --test`
testing = False

# Default rootUrl to use if none is given in the environment; this should point
# to the production Taskcluster deployment used for CI.
PRODUCTION_TASKCLUSTER_ROOT_URL = None

# the maximum number of parallel Taskcluster API calls to make
CONCURRENCY = 50


@functools.lru_cache(maxsize=None)
def get_root_url(use_proxy):
    """Get the current TASKCLUSTER_ROOT_URL.

    When running in a task, this must come from $TASKCLUSTER_ROOT_URL; when run
    on the command line, a default may be provided that points to the
    production deployment of Taskcluster. If use_proxy is set, this attempts to
    get TASKCLUSTER_PROXY_URL instead, failing if it is not set.
    """
    if use_proxy:
        try:
            return liburls.normalize_root_url(os.environ["TASKCLUSTER_PROXY_URL"])
        except KeyError:
            if "TASK_ID" not in os.environ:
                raise RuntimeError(
                    "taskcluster-proxy is not available when not executing in a task"
                )
            else:
                raise RuntimeError("taskcluster-proxy is not enabled for this task")

    if "TASKCLUSTER_ROOT_URL" in os.environ:
        logger.debug(
            "Running in Taskcluster instance {}{}".format(
                os.environ["TASKCLUSTER_ROOT_URL"],
                (
                    " with taskcluster-proxy"
                    if "TASKCLUSTER_PROXY_URL" in os.environ
                    else ""
                ),
            )
        )
        return liburls.normalize_root_url(os.environ["TASKCLUSTER_ROOT_URL"])

    if "TASK_ID" in os.environ:
        raise RuntimeError("$TASKCLUSTER_ROOT_URL must be set when running in a task")

    if PRODUCTION_TASKCLUSTER_ROOT_URL is None:
        raise RuntimeError(
            "Could not detect Taskcluster instance, set $TASKCLUSTER_ROOT_URL"
        )

    logger.debug("Using default TASKCLUSTER_ROOT_URL")
    return liburls.normalize_root_url(PRODUCTION_TASKCLUSTER_ROOT_URL)


@functools.lru_cache(maxsize=None)
def get_taskcluster_client(service: str):
    if "TASKCLUSTER_PROXY_URL" in os.environ:
        options = {"rootUrl": os.environ["TASKCLUSTER_PROXY_URL"]}
    else:
        options = taskcluster.optionsFromEnvironment()

    return getattr(taskcluster, service.capitalize())(options)


def requests_retry_session(
    retries,
    backoff_factor=0.1,
    status_forcelist=(500, 502, 503, 504),
    concurrency=CONCURRENCY,
    session=None,
    allowed_methods=None,
):
    session = session or requests.Session()
    kwargs = {}
    if allowed_methods is not None:
        kwargs["allowed_methods"] = allowed_methods
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        **kwargs,
    )

    # Default HTTPAdapter uses 10 connections. Mount custom adapter to increase
    # that limit. Connections are established as needed, so using a large value
    # should not negatively impact performance.
    http_adapter = requests.adapters.HTTPAdapter(  # type: ignore
        pool_connections=concurrency,
        pool_maxsize=concurrency,
        max_retries=retry,
    )
    session.mount("http://", http_adapter)
    session.mount("https://", http_adapter)

    return session


@functools.lru_cache(maxsize=None)
def get_session():
    return requests_retry_session(retries=5)


@functools.lru_cache(maxsize=None)
def get_retry_post_session():
    allowed_methods = set(("POST",)) | Retry.DEFAULT_ALLOWED_METHODS
    return requests_retry_session(retries=5, allowed_methods=allowed_methods)


def _do_request(url, method=None, session=None, **kwargs):
    if method is None:
        method = "post" if kwargs else "get"
    if session is None:
        session = get_session()
    if method == "get":
        kwargs["stream"] = True

    response = getattr(session, method)(url, **kwargs)

    if response.status_code >= 400:
        # Consume content before raise_for_status, so that the connection can be
        # reused.
        response.content
    response.raise_for_status()
    return response


def _handle_artifact(path, response):
    if path.endswith(".json"):
        return response.json()
    if path.endswith(".yml"):
        return yaml.load_stream(response.content)
    response.raw.read = functools.partial(response.raw.read, decode_content=True)
    return response.raw


def get_artifact_url(task_id, path, use_proxy=False):
    artifact_tmpl = liburls.api(
        get_root_url(use_proxy), "queue", "v1", "task/{}/artifacts/{}"
    )
    return artifact_tmpl.format(task_id, path)


def get_artifact(task_id, path, use_proxy=False):
    """
    Returns the artifact with the given path for the given task id.

    If the path ends with ".json" or ".yml", the content is deserialized as,
    respectively, json or yaml, and the corresponding python data (usually
    dict) is returned.
    For other types of content, a file-like object is returned.
    """
    queue = get_taskcluster_client("queue")
    response = queue.getArtifact(task_id, path)
    return response


def list_artifacts(task_id, use_proxy=False):
    queue = get_taskcluster_client("queue")
    task = queue.task(task_id)
    if task:
        return task["artifacts"]


def get_artifact_prefix(task):
    prefix = None
    if isinstance(task, dict):
        prefix = task.get("attributes", {}).get("artifact_prefix")
    elif isinstance(task, Task):
        prefix = task.attributes.get("artifact_prefix")
    else:
        raise Exception(f"Can't find artifact-prefix of non-task: {task}")
    return prefix or "public/build"


def get_artifact_path(task, path):
    return f"{get_artifact_prefix(task)}/{path}"


def get_index_url(index_path, use_proxy=False, multiple=False):
    index_tmpl = liburls.api(get_root_url(use_proxy), "index", "v1", "task{}/{}")
    return index_tmpl.format("s" if multiple else "", index_path)


def find_task_id(index_path, use_proxy=False):
    index = get_taskcluster_client("index")
    task = index.findTask(index_path)
    return task["taskId"]  # type: ignore


def find_task_id_batched(index_paths, use_proxy=False):
    """Gets the task id of multiple tasks given their respective index.

    Args:
        index_paths (List[str]): A list of task indexes.
        use_proxy (bool): Whether to use taskcluster-proxy (default: False)

    Returns:
        Dict[str, str]: A dictionary object mapping each valid index path
                        to its respective task id.

    See the endpoint here:
        https://docs.taskcluster.net/docs/reference/core/index/api#findTasksAtIndex
    """
    index = get_taskcluster_client("index")
    response = index.findTasksAtIndex({"indexes": index_paths})

    if not response or "tasks" not in response:
        return {}

    task_ids = {}
    tasks = response.get("tasks", [])
    for task in tasks:
        namespace = task.get("namespace")  # type: ignore
        task_id = task.get("taskId")  # type: ignore
        if namespace and task_id:
            task_ids[namespace] = task_id
    return task_ids


def get_artifact_from_index(index_path, artifact_path, use_proxy=False):
    index = get_taskcluster_client("index")
    return index.findArtifactFromTask(index_path, artifact_path)


def list_tasks(index_path, use_proxy=False):
    """
    Returns a list of task_ids where each task_id is indexed under a path
    in the index. Results are sorted by expiration date from oldest to newest.
    """
    index = get_taskcluster_client("index")
    response = index.listTasks(index_path, {})

    if not response or "tasks" not in response:
        return []

    results = []
    tasks = response.get("tasks", [])
    for task in tasks:
        results.append(task)

    # We can sort on expires because in the general case
    # all of these tasks should be created with the same expires time so they end up in
    # order from earliest to latest action. If more correctness is needed, consider
    # fetching each task and sorting on the created date.
    results.sort(key=lambda t: parse_time(t["expires"]))

    task_ids = []
    for t in results:
        if "taskId" in t:
            task_id = t.get("taskId")
            if task_id:
                task_ids.append(task_id)

    return task_ids


def parse_time(timestamp):
    """Turn a "JSON timestamp" as used in TC APIs into a datetime"""
    return datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")


def get_task_url(task_id, use_proxy=False):
    task_tmpl = liburls.api(get_root_url(use_proxy), "queue", "v1", "task/{}")
    return task_tmpl.format(task_id)


@functools.lru_cache(maxsize=None)
def get_task_definition(task_id, use_proxy=False):
    queue = get_taskcluster_client("queue")
    return queue.task(task_id)


def cancel_task(task_id, use_proxy=False):
    """Cancels a task given a task_id. In testing mode, just logs that it would
    have cancelled."""
    if testing:
        logger.info(f"Would have cancelled {task_id}.")
    else:
        queue = get_taskcluster_client("queue")
        queue.cancelTask(task_id)


def status_task(task_id, use_proxy=False):
    """Gets the status of a task given a task_id.

    In testing mode, just logs that it would have retrieved status.

    Args:
        task_id (str): A task id.
        use_proxy (bool): Whether to use taskcluster-proxy (default: False)

    Returns:
        dict: A dictionary object as defined here:
          https://docs.taskcluster.net/docs/reference/platform/queue/api#status
    """
    if testing:
        logger.info(f"Would have gotten status for {task_id}.")
    else:
        queue = get_taskcluster_client("queue")
        response = queue.status(task_id)
        if response:
            return response.get("status", {})
        else:
            return {}


def status_task_batched(task_ids, use_proxy=False):
    """Gets the status of multiple tasks given task_ids.

    In testing mode, just logs that it would have retrieved statuses.

    Args:
        task_id (List[str]): A list of task ids.
        use_proxy (bool): Whether to use taskcluster-proxy (default: False)

    Returns:
        dict: A dictionary object as defined here:
          https://docs.taskcluster.net/docs/reference/platform/queue/api#statuses
    """
    if testing:
        logger.info(f"Would have gotten status for {len(task_ids)} tasks.")
        return {}

    queue = get_taskcluster_client("queue")
    response = queue.statuses({"taskIds": task_ids})

    if not response or "statuses" not in response:
        return {}

    statuses = {}
    status_list = response.get("statuses", [])
    for task_status in status_list:
        task_id = task_status.get("taskId")  # type: ignore
        status = task_status.get("status")  # type: ignore
        if task_id and status:
            statuses[task_id] = status

    return statuses


def state_task(task_id, use_proxy=False):
    """Gets the state of a task given a task_id.

    In testing mode, just logs that it would have retrieved state. This is a subset of the
    data returned by :func:`status_task`.

    Args:
        task_id (str): A task id.
        use_proxy (bool): Whether to use taskcluster-proxy (default: False)

    Returns:
        str: The state of the task, one of
          ``pending, running, completed, failed, exception, unknown``.
    """
    if testing:
        logger.info(f"Would have gotten state for {task_id}.")
    else:
        status = status_task(task_id, use_proxy=use_proxy).get("state") or "unknown"  # type: ignore
        return status


def rerun_task(task_id):
    """Reruns a task given a task_id. In testing mode, just logs that it would
    have reran."""
    if testing:
        logger.info(f"Would have rerun {task_id}.")
    else:
        queue = get_taskcluster_client("queue")
        queue.rerunTask(task_id)


def get_current_scopes():
    """Get the current scopes.  This only makes sense in a task with the Taskcluster
    proxy enabled, where it returns the actual scopes accorded to the task."""
    auth = get_taskcluster_client("auth")
    resp = auth.currentScopes()
    if resp:
        return resp.get("scopes")  # type: ignore
    return []


def get_purge_cache_url(provisioner_id, worker_type, use_proxy=False):
    url_tmpl = liburls.api(
        get_root_url(use_proxy), "purge-cache", "v1", "purge-cache/{}/{}"
    )
    return url_tmpl.format(provisioner_id, worker_type)


def purge_cache(provisioner_id, worker_type, cache_name, use_proxy=False):
    """Requests a cache purge from the purge-caches service."""
    if testing:
        logger.info(f"Would have purged {provisioner_id}/{worker_type}/{cache_name}.")
    else:
        logger.info(f"Purging {provisioner_id}/{worker_type}/{cache_name}.")
        purge_cache_client = get_taskcluster_client("purgeCache")
        purge_cache_client.purgeCache(
            provisioner_id, worker_type, {"cacheName": cache_name}
        )


def send_email(address, subject, content, link, use_proxy=False):
    """Sends an email using the notify service"""
    logger.info(f"Sending email to {address}.")
    notify = get_taskcluster_client("notify")
    notify.email(
        {
            "address": address,
            "subject": subject,
            "content": content,
            "link": link,
        }
    )


def list_task_group_incomplete_tasks(task_group_id):
    """Generate the incomplete tasks in a task group"""
    queue = get_taskcluster_client("queue")
    response = queue.listTaskGroup(task_group_id)

    if not response or "tasks" not in response:
        return

    tasks = response.get("tasks", [])
    for task in tasks:
        if "status" in task:  # type: ignore
            status = task["status"]  # type: ignore
            state = status.get("state")
            task_id = status.get("taskId")
            if state in ["running", "pending", "unscheduled"] and task_id:
                yield task_id


@functools.lru_cache(maxsize=None)
def _get_deps(task_ids, use_proxy):
    upstream_tasks = {}
    for task_id in task_ids:
        task_def = get_task_definition(task_id, use_proxy)
        if not task_def:
            continue

        metadata = task_def.get("metadata", {})  # type: ignore
        name = metadata.get("name")  # type: ignore
        if name:
            upstream_tasks[task_id] = name

        dependencies = task_def.get("dependencies", [])
        if dependencies:
            upstream_tasks.update(_get_deps(tuple(dependencies), use_proxy))

    return upstream_tasks


def get_ancestors(
    task_ids: Union[List[str], str], use_proxy: bool = False
) -> Dict[str, str]:
    """Gets the ancestor tasks of the given task_ids as a dictionary of taskid -> label.

    Args:
        task_ids (str or [str]): A single task id or a list of task ids to find the ancestors of.
        use_proxy (bool): See get_root_url.

    Returns:
        dict: A dict whose keys are task ids and values are task labels.
    """
    upstream_tasks: Dict[str, str] = {}

    if isinstance(task_ids, str):
        task_ids = [task_ids]

    for task_id in task_ids:
        task_def = get_task_definition(task_id, use_proxy)
        if not task_def:
            # Task has most likely expired, which means it's no longer a
            # dependency for the purposes of this function.
            continue

        dependencies = task_def.get("dependencies", [])
        if dependencies:
            upstream_tasks.update(_get_deps(tuple(dependencies), use_proxy))

    return copy.deepcopy(upstream_tasks)
