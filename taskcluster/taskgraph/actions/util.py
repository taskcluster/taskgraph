# -*- coding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import logging

from requests.exceptions import HTTPError

from taskgraph import create
from taskgraph.decision import write_artifact
from taskgraph.taskgraph import TaskGraph
from taskgraph.optimize import optimize_task_graph
from taskgraph.util.taskcluster import get_session, find_task_id, get_artifact, list_tasks

logger = logging.getLogger(__name__)


def find_decision_task(parameters):
    """Given the parameters for this action, find the taskId of the decision
    task"""
    return find_task_id('gecko.v2.{}.pushlog-id.{}.decision'.format(
        parameters['project'],
        parameters['pushlog_id']))


def fetch_graph_and_labels(parameters):
    decision_task_id = find_decision_task(parameters)

    # First grab the graph and labels generated during the initial decision task
    full_task_graph = get_artifact(decision_task_id, "public/full-task-graph.json")
    _, full_task_graph = TaskGraph.from_json(full_task_graph)
    label_to_taskid = get_artifact(decision_task_id, "public/label-to-taskid.json")

    # Now fetch any modifications made by action tasks and swap out new tasks
    # for old ones
    namespace = 'gecko.v2.{}.pushlog-id.{}.actions'.format(
        parameters['project'],
        parameters['pushlog_id'])
    for action in list_tasks(namespace):
        try:
            run_label_to_id = get_artifact(action, "public/label-to-taskid.json")
            label_to_taskid.update(run_label_to_id)
        except HTTPError as e:
            logger.info('Skipping {} due to missing artifact! Error: {}'.format(action, e))
            continue

    return (decision_task_id, full_task_graph, label_to_taskid)


def create_task_from_def(task_id, task_def, level):
    """Create a new task from a definition rather than from a label
    that is already in the full-task-graph. The task definition will
    have {relative-datestamp': '..'} rendered just like in a decision task.
    Use this for entirely new tasks or ones that change internals of the task.
    It is useful if you want to "edit" the full_task_graph and then hand
    it to this function. No dependencies will be scheduled. You must handle
    this yourself. Seeing how create_tasks handles it might prove helpful."""
    task_def['schedulerId'] = 'gecko-level-{}'.format(level)
    label = task_def['metadata']['name']
    session = get_session()
    create.create_task(session, task_id, label, task_def)


def create_tasks(to_run, full_task_graph, label_to_taskid, params, decision_task_id):
    """Create new tasks.  The task definition will have {relative-datestamp':
    '..'} rendered just like in a decision task.  Action callbacks should use
    this function to create new tasks,
    allowing easy debugging with `mach taskgraph action-callback --test`.
    This builds up all required tasks to run in order to run the tasks requested."""
    to_run = set(to_run)
    target_graph = full_task_graph.graph.transitive_closure(to_run)
    target_task_graph = TaskGraph(
        {l: full_task_graph[l] for l in target_graph.nodes},
        target_graph)
    optimized_task_graph, label_to_taskid = optimize_task_graph(target_task_graph,
                                                                params,
                                                                to_run,
                                                                label_to_taskid)
    write_artifact('task-graph.json', optimized_task_graph.to_json())
    write_artifact('label-to-taskid.json', label_to_taskid)
    write_artifact('to-run.json', list(to_run))
    create.create_tasks(optimized_task_graph, label_to_taskid, params, decision_task_id)
