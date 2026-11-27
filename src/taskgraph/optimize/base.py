# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
The objective of optimization is to remove as many tasks from the graph as
possible, as efficiently as possible, thereby delivering useful results as
quickly as possible.  For example, ideally if only a test script is modified in
a push, then the resulting graph contains only the corresponding test suite
task.

See ``taskcluster/docs/optimization.rst`` for more information.
"""

import datetime
import functools
import logging
from abc import ABCMeta, abstractmethod
from collections import defaultdict
from typing import Any as AnyType
from typing import NamedTuple, cast

from slugid import nice as slugid

from taskgraph.graph import Graph
from taskgraph.taskgraph import TaskGraph
from taskgraph.util.parameterization import resolve_task_references, resolve_timestamps
from taskgraph.util.python_path import import_sibling_modules

logger = logging.getLogger("optimization")
registry = {}


def register_strategy(name, args=(), kwargs=None):
    kwargs = kwargs or {}

    def wrap(cls):
        if name not in registry:
            registry[name] = cls(*args, **kwargs)
            if not hasattr(registry[name], "description"):
                registry[name].description = name
        return cls

    return wrap


def optimize_task_graph(
    target_task_graph,
    requested_tasks,
    params,
    do_not_optimize,
    decision_task_id,
    existing_tasks=None,
    strategy_override=None,
):
    """
    Perform task optimization, returning a taskgraph and a map from label to
    assigned taskId, including replacement tasks.
    """
    label_to_taskid = {}
    if not existing_tasks:
        existing_tasks = {}

    # instantiate the strategies for this optimization process
    strategies = registry.copy()
    if strategy_override:
        strategies.update(strategy_override)

    # Map task labels -> TaskStrategy. This is done once, upfront, to make
    # things easier for `remove_tasks` and `replace_tasks`, and ensure that
    # we don't do this work differently in different places.
    task_strategies = resolve_task_strategies(target_task_graph, strategies)

    removed_tasks = remove_tasks(
        target_task_graph=target_task_graph,
        requested_tasks=requested_tasks,
        task_strategies=task_strategies,
        params=params,
        do_not_optimize=do_not_optimize,
    )

    replaced_tasks = replace_tasks(
        target_task_graph=target_task_graph,
        task_strategies=task_strategies,
        params=params,
        do_not_optimize=do_not_optimize,
        label_to_taskid=label_to_taskid,
        existing_tasks=existing_tasks,
        removed_tasks=removed_tasks,
    )

    return (
        get_subgraph(
            target_task_graph,
            removed_tasks,
            replaced_tasks,
            label_to_taskid,
            decision_task_id,
        ),
        label_to_taskid,
    )


class TaskStrategy(NamedTuple):
    name: str
    strategy: "OptimizationStrategy"
    arg: AnyType


def resolve_task_strategies(target_task_graph, strategies):
    task_strategies = {}
    for label, task in target_task_graph.tasks.items():
        if task.optimization:
            name, arg = next(iter(task.optimization.items()))
            strategy = strategies[name]
            if hasattr(strategy, "description"):
                name += f" ({strategy.description})"
            task_strategies[label] = TaskStrategy(name, strategy, arg)
        else:
            task_strategies[label] = TaskStrategy("never", strategies["never"], None)
    return task_strategies


def _group_by_strategy(labels, task_strategies):
    groups = {}
    for label in labels:
        _, strategy, arg = task_strategies[label]
        _, group_labels, args = groups.setdefault(id(strategy), (strategy, [], {}))
        group_labels.append(label)
        args[label] = arg
    return groups.values()


def _log_optimization(verb, opt_counts, opt_reasons=None):
    if opt_reasons:
        message = "optimize: {label} {action} because of {reason}"
        for label, (action, reason) in opt_reasons.items():
            logger.debug(message.format(label=label, action=action, reason=reason))

    if opt_counts:
        logger.info(
            f"{verb.title()} "
            + ", ".join(f"{c} tasks by {b}" for b, c in sorted(opt_counts.items()))
            + " during optimization."
        )
    else:
        logger.info(f"No tasks {verb} during optimization")


def remove_tasks(
    target_task_graph, requested_tasks, params, task_strategies, do_not_optimize
):
    """
    Implement the "Removing Tasks" phase, returning a set of task labels of all removed tasks.
    """
    opt_counts = defaultdict(int)
    opt_reasons = {}
    _, dependents_of = target_task_graph.graph.links_and_reverse_links_dict()
    tasks = target_task_graph.tasks

    # Generate an ordered list of tasks that optimization strategies need to
    # be called. Traverse the graph so dependents (child nodes) are guaranteed
    # to be process first.
    order = list(target_task_graph.graph.visit_preorder())
    # Only tasks that are both requested for removal _and_ not in
    # `do_not_optimize` are candidates for explicit removal.
    candidates = [l for l in order if l in requested_tasks and l not in do_not_optimize]

    # Find the tasks that would be removed by any strategy.
    strategy_removes = set()
    for strategy, labels, args in _group_by_strategy(candidates, task_strategies):
        strategy_removes |= strategy.should_remove_tasks(
            target_task_graph, labels, params, args
        )

    removed = set()
    prune_candidates = set()

    # Now that we have all of the necessary information, find tasks that can
    # definitely be removed, and those that are candidates for removal (subject
    # to additional conditions that cannot be evaluated in this loop).
    for label in order:
        # Dependents that can be pruned away (shouldn't cause this task to run).
        # Only dependents that either:
        #   A) Explicitly reference this task in their 'if_dependencies' list, or
        #   B) Don't have an 'if_dependencies' attribute (i.e are in 'prune_candidates'
        #      because they should be removed but have prune_deps themselves)
        # should be considered.
        prune_deps = {
            l
            for l in dependents_of[label]
            if l in prune_candidates
            if not tasks[l].if_dependencies or label in tasks[l].if_dependencies
        }

        def _keep(reason):
            """Mark a task as being kept in the graph. Also recursively removes
            any dependents from `prune_candidates`, assuming they should be
            kept because of this task.
            """
            opt_reasons[label] = ("kept", reason)

            # Removes dependents that were in 'prune_candidates' from a task
            # that ended up being kept (and therefore the dependents should
            # also be kept).
            queue = list(prune_deps)
            while queue:
                l = queue.pop()

                # If l is a prune_dep of multiple tasks it could be queued up
                # multiple times. Guard against it being already removed.
                if l not in prune_candidates:
                    continue

                # If a task doesn't set 'if_dependencies' itself (rather it was
                # added to 'prune_candidates' due to one of its depenendents),
                # then we shouldn't remove it.
                if not tasks[l].if_dependencies:
                    continue

                prune_candidates.remove(l)
                queue.extend([r for r in dependents_of[l] if r in prune_candidates])

        def _remove(reason):
            """Potentially mark a task as being removed from the graph. If the
            task has dependents that can be pruned, add this task to
            `prune_candidates` rather than removing it.
            """
            if prune_deps:
                # If there are prune_deps, unsure if we can remove this task yet.
                prune_candidates.add(label)
            else:
                opt_reasons[label] = ("removed", reason)
                opt_counts[reason] += 1
                removed.add(label)

        # if we're not allowed to optimize, that's easy..
        if label in do_not_optimize:
            _keep("do not optimize")
            continue

        # If there are remaining tasks depending on this one, do not remove.
        if any(
            l for l in dependents_of[label] if l not in removed and l not in prune_deps
        ):
            _keep("dependent tasks")
            continue

        # Some tasks in the task graph only exist because they were required
        # by a task that has just been optimized away. They can now be removed.
        if label not in requested_tasks:
            _remove("dependents optimized")
            continue

        opt_by = task_strategies[label].name
        # The task is not in `do_not_optimize`, not required for a descendent
        # task that was kept, and explicitly requested for removal: remove it.
        if label in strategy_removes:
            _remove(opt_by)
            continue

        # Some tasks should only run if their dependency was also run. Since we
        # haven't processed dependencies yet, we add them to a list of
        # candidate tasks for pruning.
        if tasks[label].if_dependencies:
            opt_reasons[label] = ("kept", opt_by)
            prune_candidates.add(label)
        else:
            _keep(opt_by)

    # Add any `prune_candidates` that qualify to `removed`.
    if prune_candidates:
        reason = "if-dependencies pruning"
        for label in prune_candidates:
            # There's an edge case where a triangle graph can cause a
            # dependency to stay in 'prune_candidates' when the dependent
            # remains. Do a final check to ensure we don't create any bad
            # edges.
            dependents = any(
                d
                for d in dependents_of[label]
                if d not in prune_candidates
                if d not in removed
            )
            if dependents:
                opt_reasons[label] = ("kept", "dependent tasks")
                continue
            removed.add(label)
            opt_counts[reason] += 1
            opt_reasons[label] = ("removed", reason)

    _log_optimization("removed", opt_counts, opt_reasons)
    return removed


def replace_tasks(
    target_task_graph,
    params,
    task_strategies,
    do_not_optimize,
    label_to_taskid,
    removed_tasks,
    existing_tasks,
):
    """
    Implement the "Replacing Tasks" phase, returning a set of task labels of
    all replaced tasks. The replacement taskIds are added to label_to_taskid as
    a side-effect.
    """
    opt_counts = defaultdict(int)
    replaced = set()
    dependencies_of, dependents_of = (
        target_task_graph.graph.links_and_reverse_links_dict()
    )

    # Many tasks share dependents (e.g. docker images or toolchains), so
    # resolve the deadline of each dependent only once.
    now = datetime.datetime.now(datetime.timezone.utc)

    @functools.cache
    def get_deadline(label) -> str:
        return cast(
            str,
            resolve_timestamps(now, target_task_graph.tasks[label].task["deadline"]),
        )

    order = list(target_task_graph.graph.visit_postorder())
    candidates = [
        l for l in order if l not in do_not_optimize and not existing_tasks.get(l)
    ]
    deadlines = {
        label: (
            max(get_deadline(l) for l in dependents_of[label])
            if dependents_of[label]
            else None
        )
        for label in candidates
    }
    replacements = {}
    for strategy, labels, args in _group_by_strategy(candidates, task_strategies):
        replacements.update(
            strategy.should_replace_tasks(
                target_task_graph, labels, params, deadlines, args
            )
        )

    for label in order:
        logger.debug(f"replace_tasks: {label}")
        # if we're not allowed to optimize, that's easy..
        if label in do_not_optimize:
            logger.debug(f"replace_tasks: {label} is in do_not_optimize")
            continue

        # if this task depends on un-replaced, un-removed tasks, do not replace
        if any(
            l not in replaced and l not in removed_tasks for l in dependencies_of[label]
        ):
            logger.debug(
                f"replace_tasks: {label} depends on an unreplaced or unremoved task"
            )
            continue

        # if the task already exists, that's an easy replacement
        repl = existing_tasks.get(label)
        if repl:
            label_to_taskid[label] = repl
            replaced.add(label)
            opt_counts["existing_tasks"] += 1
            logger.debug(f"replace_tasks: {label} replaced from existing_tasks")
            continue

        opt_by = task_strategies[label].name
        repl = replacements.get(label)
        if repl:
            if repl is True:
                logger.debug(f"replace_tasks: {label} removed by optimization strategy")
                # True means remove this task; get_subgraph will catch any
                # problems with removed tasks being depended on
                removed_tasks.add(label)
            else:
                logger.debug(
                    f"replace_tasks: {label} replaced with {repl} by optimization strategy"
                )
                label_to_taskid[label] = repl
                replaced.add(label)
            opt_counts[opt_by] += 1
            continue
        else:
            logger.debug(f"replace_tasks: {label} kept by optimization strategy")

    _log_optimization("replaced", opt_counts)
    return replaced


def get_subgraph(
    target_task_graph: TaskGraph,
    removed_tasks: set[str],
    replaced_tasks: set[str],
    label_to_taskid: dict[str, str],
    decision_task_id: str,
):
    """
    Return the subgraph of target_task_graph consisting only of
    non-optimized tasks and edges between them.

    To avoid losing track of taskIds for tasks optimized away, this method
    simultaneously substitutes real taskIds for task labels in the graph, and
    populates each task definition's `dependencies` key with the appropriate
    taskIds.  Task references are resolved in the process.
    """

    # check for any dependency edges from included to removed tasks
    bad_edges = [
        (l, r, n)
        for l, r, n in target_task_graph.graph.edges
        if l not in removed_tasks and r in removed_tasks
    ]
    if bad_edges:
        probs = ", ".join(
            f"{l} depends on {r} as {n} but it has been removed"
            for l, r, n in bad_edges
        )
        raise Exception("Optimization error: " + probs)

    # fill in label_to_taskid for anything not removed or replaced
    assert replaced_tasks <= set(label_to_taskid)
    for label in sorted(
        target_task_graph.graph.nodes - removed_tasks - set(label_to_taskid)
    ):
        task_id = slugid()
        assert isinstance(task_id, str)
        label_to_taskid[label] = task_id

    # resolve labels to taskIds and populate task['dependencies']
    tasks_by_taskid = {}
    named_links_dict = target_task_graph.graph.named_links_dict()
    omit = removed_tasks | replaced_tasks
    for label, task in target_task_graph.tasks.items():
        if label in omit:
            continue
        task.task_id = label_to_taskid[label]
        named_task_dependencies = {
            name: label_to_taskid[label]
            for name, label in named_links_dict.get(label, {}).items()
        }

        # Add remaining soft dependencies
        if task.soft_dependencies:
            named_task_dependencies.update(
                {
                    label: label_to_taskid[label]
                    for label in task.soft_dependencies
                    if label in label_to_taskid and label not in omit
                }
            )

        assert task.task_id
        task.task = resolve_task_references(
            task.label,
            task.task,
            task_id=task.task_id,
            decision_task_id=decision_task_id,
            dependencies=named_task_dependencies,
        )
        deps = task.task.setdefault("dependencies", [])
        deps.extend(sorted(named_task_dependencies.values()))
        task.dependencies.update(named_task_dependencies)
        tasks_by_taskid[task.task_id] = task

    # resolve edges to taskIds
    edges_by_taskid = (
        (label_to_taskid.get(left), label_to_taskid.get(right), name)
        for (left, right, name) in target_task_graph.graph.edges
    )
    # ..and drop edges that are no longer entirely in the task graph
    #   (note that this omits edges to replaced tasks, but they are still in task.dependnecies)
    edges_by_taskid = {
        (left, right, name)
        for (left, right, name) in edges_by_taskid
        if left in tasks_by_taskid and right in tasks_by_taskid
    }

    return TaskGraph(
        tasks_by_taskid, Graph(frozenset(tasks_by_taskid), edges_by_taskid)
    )


@register_strategy("never")
class OptimizationStrategy:
    def should_remove_task(self, task, params, arg):
        """Determine whether to optimize this task by removing it.  Returns
        True to remove."""
        return False

    def should_replace_task(self, task, params, deadline, arg):
        """Determine whether to optimize this task by replacing it.  Returns a
        taskId to replace this task, True to replace with nothing, or False to
        keep the task."""
        return False

    def should_remove_tasks(self, graph, labels, params, args):
        """Determine which of the tasks in `labels` should be removed, returning
        the set of labels to remove. This default implementation simply calls
        `self.should_remove_task` for each task. Subclasses that only make the
        removal decision based on task data should override that method.
        Subclasses that need to evaluate all of their tasks at once to
        determine what to remove should override _this_ method."""
        tasks = graph.tasks
        return {
            label
            for label in labels
            if self.should_remove_task(tasks[label], params, args[label])
        }

    def should_replace_tasks(self, graph, labels, params, deadlines, args):
        """Determine which of the tasks in `labels` should be replaced with
        an existing task. The default implementation simply calls
        `self.should_replace_task` for each task. Subclasses that only make
        the replacement decision based on task data should override that
        method. Subclasses that need to evaluate all of their tasks at once
        to determine what to replace should override _this_ method."""
        tasks = graph.tasks
        replacements = {}
        for label in labels:
            repl = self.should_replace_task(
                tasks[label], params, deadlines[label], args[label]
            )
            if repl:
                replacements[label] = repl
        return replacements


@register_strategy("always")
class Always(OptimizationStrategy):
    def should_remove_task(self, task, params, arg):
        return True


class CompositeStrategy(OptimizationStrategy, metaclass=ABCMeta):
    def __init__(self, *substrategies, **kwargs):
        self.substrategies = []
        missing = set()
        for sub in substrategies:
            if isinstance(sub, str):
                if sub not in registry.keys():
                    missing.add(sub)
                    continue
                sub = registry[sub]

            self.substrategies.append(sub)

        if missing:
            raise TypeError(
                "substrategies aren't registered: {}".format(
                    ",  ".join(sorted(missing))
                )
            )

        self.split_args = kwargs.pop("split_args", None)
        if not self.split_args:
            self.split_args = lambda arg, substrategies: [arg] * len(substrategies)
        if kwargs:
            raise TypeError("unexpected keyword args")

    @property
    @abstractmethod
    def description(self):
        """A textual description of the combined substrategies."""

    @abstractmethod
    def reduce(self, results):
        """Given all substrategy results as a generator, return the overall
        result."""

    def _generate_results(self, fname, *args):
        *passthru, arg = args
        for sub, arg in zip(
            self.substrategies, self.split_args(arg, self.substrategies)
        ):
            yield getattr(sub, fname)(*passthru, arg)

    def should_remove_task(self, *args):
        results = self._generate_results("should_remove_task", *args)
        return self.reduce(results)

    def should_replace_task(self, *args):
        results = self._generate_results("should_replace_task", *args)
        return self.reduce(results)

    def _split_args(self, labels, args):
        """Return the args for all strategies and all labels."""
        splits = {
            label: list(self.split_args(args[label], self.substrategies))
            for label in labels
        }
        return [
            {label: split[i] for label, split in splits.items() if i < len(split)}
            for i in range(len(self.substrategies))
        ]


class Any(CompositeStrategy):
    """Given one or more optimization strategies, remove or replace a task if any of them
    says to.

    Replacement will use the value returned by the first strategy that says to replace.
    """

    @property
    def description(self):
        return "-or-".join([s.description for s in self.substrategies])

    @classmethod
    def reduce(cls, results):
        for rv in results:
            if rv:
                return rv
        return False

    def should_remove_tasks(self, graph, labels, params, args):
        removed = set()
        remaining = labels
        for sub, sub_args in zip(self.substrategies, self._split_args(labels, args)):
            sub_labels = [l for l in remaining if l in sub_args]
            if sub_labels:
                removed |= sub.should_remove_tasks(graph, sub_labels, params, sub_args)
                remaining = [l for l in remaining if l not in removed]
            if not remaining:
                break
        return removed

    def should_replace_tasks(self, graph, labels, params, deadlines, args):
        replacements = {}
        remaining = labels
        for sub, sub_args in zip(self.substrategies, self._split_args(labels, args)):
            sub_labels = [l for l in remaining if l in sub_args]
            if sub_labels:
                result = sub.should_replace_tasks(
                    graph, sub_labels, params, deadlines, sub_args
                )
                replacements.update((l, r) for l, r in result.items() if r)
                remaining = [l for l in remaining if l not in replacements]
            if not remaining:
                break
        return replacements


class All(CompositeStrategy):
    """Given one or more optimization strategies, remove or replace a task if all of them
    says to.

    Replacement will use the value returned by the first strategy passed in.
    Note the values used for replacement need not be the same, as long as they
    all say to replace.
    """

    @property
    def description(self):
        return "-and-".join([s.description for s in self.substrategies])

    @classmethod
    def reduce(cls, results):
        for rv in results:
            if not rv:
                return rv
        return True

    def should_remove_tasks(self, graph, labels, params, args):
        candidates = labels
        for sub, sub_args in zip(self.substrategies, self._split_args(labels, args)):
            sub_labels = [l for l in candidates if l in sub_args]
            if sub_labels:
                removed = sub.should_remove_tasks(graph, sub_labels, params, sub_args)
                candidates = [
                    l for l in candidates if l not in sub_args or l in removed
                ]
            if not candidates:
                break
        return set(candidates)

    def should_replace_tasks(self, graph, labels, params, deadlines, args):
        candidates = labels
        for sub, sub_args in zip(self.substrategies, self._split_args(labels, args)):
            sub_labels = [l for l in candidates if l in sub_args]
            if sub_labels:
                result = sub.should_replace_tasks(
                    graph, sub_labels, params, deadlines, sub_args
                )
                candidates = [
                    l for l in candidates if l not in sub_args or result.get(l)
                ]
            if not candidates:
                break
        return dict.fromkeys(candidates, True)


class Alias(CompositeStrategy):
    """Provides an alias to an existing strategy.

    This can be useful to swap strategies in and out without needing to modify
    the task transforms.
    """

    def __init__(self, strategy):
        super().__init__(strategy)

    @property
    def description(self):
        return self.substrategies[0].description

    def reduce(self, results):
        return next(results)

    def should_remove_tasks(self, graph, labels, params, args):
        return self.substrategies[0].should_remove_tasks(graph, labels, params, args)

    def should_replace_tasks(self, graph, labels, params, deadlines, args):
        return self.substrategies[0].should_replace_tasks(
            graph, labels, params, deadlines, args
        )


class Not(CompositeStrategy):
    """Given a strategy, returns the opposite."""

    def __init__(self, strategy):
        super().__init__(strategy)

    @property
    def description(self):
        return "not-" + self.substrategies[0].description

    def reduce(self, results):
        return not next(results)

    def should_remove_tasks(self, graph, labels, params, args):
        removed = self.substrategies[0].should_remove_tasks(graph, labels, params, args)
        return {l for l in labels if l not in removed}

    def should_replace_tasks(self, graph, labels, params, deadlines, args):
        result = self.substrategies[0].should_replace_tasks(
            graph, labels, params, deadlines, args
        )
        return {l: True for l in labels if not result.get(l)}


# Trigger registration in sibling modules.
import_sibling_modules()
