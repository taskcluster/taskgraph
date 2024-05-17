import logging
from datetime import datetime

from taskgraph.optimize.base import OptimizationStrategy, register_strategy
from taskgraph.util.path import match as match_path
from taskgraph.util.taskcluster import find_task_id, status_task

logger = logging.getLogger(__name__)


@register_strategy("index-search")
class IndexSearch(OptimizationStrategy):
    # A task with no dependencies remaining after optimization will be replaced
    # if artifacts exist for the corresponding index_paths.
    # Otherwise, we're in one of the following cases:
    # - the task has un-optimized dependencies
    # - the artifacts have expired
    # - some changes altered the index_paths and new artifacts need to be
    # created.
    # In every of those cases, we need to run the task to create or refresh
    # artifacts.

    fmt = "%Y-%m-%dT%H:%M:%S.%fZ"

    def should_replace_task(self, task, params, deadline, arg):
        "Look for a task with one of the given index paths"
        batched = False
        # Appease static checker that doesn't understand that this is not needed
        label_to_taskid = {}
        taskid_to_status = {}

        if isinstance(arg, tuple) and len(arg) == 3:
            # allow for a batched call optimization instead of two queries
            # per index path
            index_paths, label_to_taskid, taskid_to_status = arg
            batched = True
        else:
            index_paths = arg

        for index_path in index_paths:
            try:
                if batched:
                    task_id, status = _find_task_id_and_status_from_batch(
                        label_to_taskid, taskid_to_status, index_path
                    )
                else:
                    # 404 is raised as `KeyError` also end up here
                    task_id = find_task_id(index_path)
                    status = status_task(task_id)
                # status can be `None` if we're in `testing` mode
                # (e.g. test-action-callback)
                if not status or status.get("state") in ("exception", "failed"):
                    continue

                if deadline and datetime.strptime(
                    status["expires"], self.fmt
                ) < datetime.strptime(deadline, self.fmt):
                    continue

                return task_id
            except KeyError as e:
                logger.debug(e)

        return False


def _find_task_id_and_status_from_batch(label_to_taskid, taskid_to_status, index_path):
    try:
        task_id = label_to_taskid[index_path]
    except KeyError as e:
        raise KeyError(
            f'Couldn\'t find cached task for index path "{index_path}".'
        ) from e
    try:
        status = taskid_to_status[task_id]
    except KeyError as e:
        raise KeyError(
            f'Couldn\'t find cached status for taskId {task_id} (index path "{index_path}").'
        ) from e

    return task_id, status


@register_strategy("skip-unless-changed")
class SkipUnlessChanged(OptimizationStrategy):

    def check(self, files_changed, patterns):
        for pattern in patterns:
            for path in files_changed:
                if match_path(path, pattern):
                    return True
        return False

    def should_remove_task(self, task, params, file_patterns):
        # pushlog_id == -1 - this is the case when run from a cron.yml job or on a git repository
        if params.get("repository_type") == "hg" and params.get("pushlog_id") == -1:
            return False

        changed = self.check(params["files_changed"], file_patterns)
        if not changed:
            logger.debug(
                f'no files found matching a pattern in `skip-unless-changed` for "{task.label}"'
            )
            return True
        return False
