import functools
import logging
from datetime import datetime

from taskcluster.exceptions import TaskclusterRestFailure

from taskgraph.optimize.base import OptimizationStrategy, register_strategy
from taskgraph.util.path import match as match_path
from taskgraph.util.taskcluster import (
    find_task_id,
    find_task_id_batched,
    status_task,
    status_task_batched,
)

logger = logging.getLogger("optimization")


@functools.cache
def _parse_time(timestamp, fmt):
    # Many tasks share the same deadline or replacement task, so avoid parsing
    # the same timestamps over and over.
    return datetime.strptime(timestamp, fmt)


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

        def lookup(index_path):
            # 404 is raised as `KeyError`
            task_id = find_task_id(index_path)
            return task_id, status_task(task_id)

        return self._find_replacement(task, arg, deadline, lookup)

    def should_replace_tasks(self, graph, labels, params, deadlines, args):
        index_paths = sorted({path for label in labels for path in args[label] or ()})
        if not index_paths:
            return {}

        # Find their respective status using TC index/queue batch APIs
        index_to_taskid = find_task_id_batched(index_paths)
        taskid_to_status = status_task_batched(list(index_to_taskid.values()))

        def lookup(index_path):
            task_id = index_to_taskid[index_path]
            return task_id, taskid_to_status[task_id]

        replacements = {}
        for label in labels:
            repl = self._find_replacement(
                graph.tasks[label], args[label], deadlines[label], lookup
            )
            if repl:
                replacements[label] = repl
        return replacements

    def _find_replacement(self, task, index_paths, deadline, lookup):
        for index_path in index_paths or ():
            try:
                task_id, status = lookup(index_path)
                # status can be `None` if we're in `testing` mode
                # (e.g. test-action-callback)
                if not status or status.get("state") in ("exception", "failed"):  # type: ignore
                    logger.debug(
                        f"not replacing {task.label} with {task_id} because it is in failed or exception state"
                    )
                    continue

                if deadline and _parse_time(
                    status["expires"],  # type: ignore
                    self.fmt,
                ) < _parse_time(deadline, self.fmt):
                    logger.debug(
                        f"not replacing {task.label} with {task_id} because it expires before {deadline}"
                    )
                    continue

                return task_id
            except (KeyError, TaskclusterRestFailure):
                # go on to the next index path
                pass

        return False


@register_strategy("skip-unless-changed")
class SkipUnlessChanged(OptimizationStrategy):
    def check(self, files_changed, patterns):
        for pattern in patterns:
            for path in files_changed:
                if match_path(path, pattern):
                    return True
        return False

    def should_remove_task(self, task, params, file_patterns):
        # skip-unless-changed should not apply when there is no commit delta,
        # such as for cron and action tasks (there will never be file changes)
        if params.get("base_rev") and params.get("head_rev") == params.get("base_rev"):
            return False

        changed = self.check(params["files_changed"], file_patterns)
        if not changed:
            logger.debug(
                f'no files found matching a pattern in `skip-unless-changed` for "{task.label}"'
            )
            return True
        return False
