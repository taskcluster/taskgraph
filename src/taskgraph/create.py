# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import logging
import sys
from collections import defaultdict
from concurrent import futures

from slugid import nice as slugid

from taskgraph.util import json
from taskgraph.util.parameterization import resolve_timestamps
from taskgraph.util.taskcluster import CONCURRENCY, get_session, get_taskcluster_client
from taskgraph.util.time import current_json_time

logger = logging.getLogger(__name__)

# this is set to true for `mach taskgraph action-callback --test`
testing = False


class CreateTasksException(Exception):
    """Exception raised when one or more tasks could not be created."""

    def __init__(self, errors: dict[str, Exception]):
        message = ""
        for label, exc in errors.items():
            message += f"\nERROR: Could not create '{label}':\n\n"
            message += "\n".join(f"    {line}" for line in str(exc).splitlines()) + "\n"

        super().__init__(message)


def create_tasks(graph_config, taskgraph, label_to_taskid, params, decision_task_id):
    taskid_to_label = {t: l for l, t in label_to_taskid.items()}

    # when running as an actual decision task, we use the decision task's
    # taskId as the taskGroupId.  The process that created the decision task
    # helpfully placed it in this same taskGroup.  If there is no $TASK_ID,
    # fall back to a slugid
    scheduler_id = "{}-level-{}".format(graph_config["trust-domain"], params["level"])

    # Add the taskGroupId, schedulerId and optionally the decision task
    # dependency
    for task_id in taskgraph.graph.nodes:
        task_def = taskgraph.tasks[task_id].task

        # if this task has no dependencies *within* this taskgraph, make it
        # depend on this decision task. If it has another dependency within
        # the taskgraph, then it already implicitly depends on the decision
        # task.  The result is that tasks do not start immediately. if this
        # loop fails halfway through, none of the already-created tasks run.
        if not any(t in taskgraph.tasks for t in task_def.get("dependencies", [])):
            task_def.setdefault("dependencies", []).append(decision_task_id)

        task_def["taskGroupId"] = decision_task_id
        task_def["schedulerId"] = scheduler_id

    # We can't submit a task until its dependencies have been created. So
    # track, for each task, how many of its dependencies within this graph are
    # still pending, and submit it once that number drops to zero. Tasks
    # depending (directly or not) on a task that failed to be created are never
    # submitted, as their creation would fail anyway.
    pending_deps = {}
    dependents = defaultdict(list)
    for task_id in taskgraph.graph.nodes:
        # Some dependencies aren't in our graph, so make sure to filter those
        # out.
        deps = {
            d
            for d in taskgraph.tasks[task_id].task.get("dependencies", [])
            if d in taskgraph.tasks
        }
        pending_deps[task_id] = len(deps)
        for dep in deps:
            dependents[dep].append(task_id)

    # If `testing` is True, then run without parallelization
    concurrency = CONCURRENCY if not testing else 1
    session = get_session()
    with futures.ThreadPoolExecutor(concurrency) as e:
        # Maps each future to the task it is creating, and whether it is the
        # primary creation of that task (as opposed to a duplicate).
        fs_to_task = {}
        in_flight = set()

        def submit(task_id):
            task = taskgraph.tasks[task_id]
            label = taskid_to_label[task_id]
            # Schedule tasks as many times as task_duplicates indicates. We
            # use slugid() for duplicates since we want a distinct task id.
            for i in range(task.attributes.get("task_duplicates", 1)):
                fut_task_id = task_id if i == 0 else slugid()
                fut = e.submit(create_task, session, fut_task_id, label, task.task)
                fs_to_task[fut] = (task_id, label, i == 0)
                in_flight.add(fut)

        for task_id, count in pending_deps.items():
            if count == 0:
                submit(task_id)

        # As each of those futures complete, schedule the tasks that were
        # waiting on them.
        while in_flight:
            done, _ = futures.wait(in_flight, return_when=futures.FIRST_COMPLETED)
            for fut in done:
                in_flight.remove(fut)
                task_id, _, primary = fs_to_task[fut]
                if not primary or fut.exception():
                    continue
                for dependent in dependents[task_id]:
                    pending_deps[dependent] -= 1
                    if pending_deps[dependent] == 0:
                        submit(dependent)

        # Collect errors.
        errors = {}
        for fut, (_, label, _) in fs_to_task.items():
            if exc := fut.exception():
                errors[label] = exc

        if errors:
            raise CreateTasksException(errors)


def create_task(session, task_id, label, task_def):
    # Resolve timestamps
    now = current_json_time(datetime_format=True)
    task_def = resolve_timestamps(now, task_def)

    if testing:
        json.dump(
            [task_id, task_def],
            sys.stdout,
            sort_keys=True,
            indent=2,
        )
        # add a newline
        print("")
        return

    logger.info(f"Creating task with taskId {task_id} for {label}")
    queue = get_taskcluster_client("queue")
    queue.createTask(task_id, task_def)
