# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import os
import json
import logging

import time
import yaml

from .actions import render_actions_json
from .create import create_tasks
from .generator import TaskGraphGenerator
from .parameters import Parameters
from .taskgraph import TaskGraph
from taskgraph.util.vcs import get_hg_revision_branch, get_commit_message
from taskgraph.util.yaml import load_yaml


logger = logging.getLogger(__name__)

ARTIFACTS_DIR = 'artifacts'

# For each project, this gives a set of parameters specific to the project.
# See `taskcluster/docs/parameters.rst` for information on parameters.
PER_PROJECT_PARAMETERS = {
    # the default parameters are used for projects that do not match above.
    'default': {
        'target_tasks_method': 'default',
    }
}


def full_task_graph_to_runnable_jobs(full_task_json):
    runnable_jobs = {}
    for label, node in full_task_json.iteritems():
        if not ('extra' in node['task'] and 'treeherder' in node['task']['extra']):
            continue

        th = node['task']['extra']['treeherder']
        runnable_jobs[label] = {
            'symbol': th['symbol']
        }

        for i in ('groupName', 'groupSymbol', 'collection'):
            if i in th:
                runnable_jobs[label][i] = th[i]
        if th.get('machine', {}).get('platform'):
            runnable_jobs[label]['platform'] = th['machine']['platform']
    return runnable_jobs


def taskgraph_decision(options, parameters=None):
    """
    Run the decision task.  This function implements `mach taskgraph decision`,
    and is responsible for

     * processing decision task command-line options into parameters
     * running task-graph generation exactly the same way the other `mach
       taskgraph` commands do
     * generating a set of artifacts to memorialize the graph
     * calling TaskCluster APIs to create the graph
    """

    parameters = parameters or (lambda config: get_decision_parameters(config, options))

    # create a TaskGraphGenerator instance
    tgg = TaskGraphGenerator(
        root_dir=options.get('root'),
        parameters=parameters)

    # write out the parameters used to generate this graph
    write_artifact('parameters.yml', dict(**tgg.parameters))

    # write out the public/actions.json file
    write_artifact('actions.json', render_actions_json(tgg.parameters, tgg.graph_config))

    # write out the full graph for reference
    full_task_json = tgg.full_task_graph.to_json()
    write_artifact('full-task-graph.json', full_task_json)

    # write out the public/runnable-jobs.json file
    write_artifact('runnable-jobs.json', full_task_graph_to_runnable_jobs(full_task_json))

    # this is just a test to check whether the from_json() function is working
    _, _ = TaskGraph.from_json(full_task_json)

    # write out the target task set to allow reproducing this as input
    write_artifact('target-tasks.json', tgg.target_task_set.tasks.keys())

    # write out the optimized task graph to describe what will actually happen,
    # and the map of labels to taskids
    write_artifact('task-graph.json', tgg.morphed_task_graph.to_json())
    write_artifact('label-to-taskid.json', tgg.label_to_taskid)

    # actually create the graph
    create_tasks(tgg.graph_config, tgg.morphed_task_graph, tgg.label_to_taskid, tgg.parameters)


def get_decision_parameters(config, options):
    """
    Load parameters from the command-line options for 'taskgraph decision'.
    This also applies per-project parameters, based on the given project.

    """
    parameters = {n: options[n] for n in [
        'base_repository',
        'head_repository',
        'head_rev',
        'head_ref',
        'project',
        'pushlog_id',
        'pushdate',
        'repository_type',
        'owner',
        'level',
        'target_tasks_method',
        'tasks_for',
    ] if n in options}

    commit_message = get_commit_message(parameters['repository_type'], os.getcwd())

    # Define default filter list, as most configurations shouldn't need
    # custom filters.
    parameters['filters'] = [
        'target_tasks_method',
    ]
    parameters['optimize_target_tasks'] = True
    parameters['existing_tasks'] = {}
    parameters['do_not_optimize'] = []

    if parameters['repository_type'] == 'hg':
        parameters['hg_branch'] = get_hg_revision_branch(os.getcwd(),
                                                         revision=parameters['head_rev'])
    else:
        parameters['hg_branch'] = None

    # owner must be an email, but sometimes (e.g., for ffxbld) it is not, in which
    # case, fake it
    if '@' not in parameters['owner']:
        parameters['owner'] += '@noreply.mozilla.org'

    # use the pushdate as build_date if given, else use current time
    parameters['build_date'] = parameters['pushdate'] or int(time.time())
    # moz_build_date is the build identifier based on build_date
    parameters['moz_build_date'] = time.strftime("%Y%m%d%H%M%S",
                                                 time.gmtime(parameters['build_date']))

    project = parameters['project']
    try:
        parameters.update(PER_PROJECT_PARAMETERS[project])
    except KeyError:
        logger.warning("using default project parameters; add {} to "
                       "PER_PROJECT_PARAMETERS in {} to customize behavior "
                       "for this project".format(project, __file__))
        parameters.update(PER_PROJECT_PARAMETERS['default'])

    # `target_tasks_method` has higher precedence than `project` parameters
    if options.get('target_tasks_method'):
        parameters['target_tasks_method'] = options['target_tasks_method']

    # ..but can be overridden by the commit message: if it contains the special
    # string "DONTBUILD" and this is an on-push decision task, then use the
    # special 'nothing' target task method.
    if 'DONTBUILD' in commit_message and options['tasks_for'] == 'hg-push':
        parameters['target_tasks_method'] = 'nothing'

    if options.get('optimize_target_tasks') is not None:
        parameters['optimize_target_tasks'] = options['optimize_target_tasks']

    result = Parameters(**parameters)
    result.check()
    return result


def write_artifact(filename, data):
    logger.info('writing artifact file `{}`'.format(filename))
    if not os.path.isdir(ARTIFACTS_DIR):
        os.mkdir(ARTIFACTS_DIR)
    path = os.path.join(ARTIFACTS_DIR, filename)
    if filename.endswith('.yml'):
        with open(path, 'w') as f:
            yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)
    elif filename.endswith('.json'):
        with open(path, 'w') as f:
            json.dump(data, f, sort_keys=True, indent=2, separators=(',', ': '))
    elif filename.endswith('.gz'):
        import gzip
        with gzip.open(path, 'wb') as f:
            f.write(json.dumps(data))
    else:
        raise TypeError("Don't know how to write to {}".format(filename))


def read_artifact(filename):
    path = os.path.join(ARTIFACTS_DIR, filename)
    if filename.endswith('.yml'):
        return load_yaml(path, filename)
    elif filename.endswith('.json'):
        with open(path, 'r') as f:
            return json.load(f)
    elif filename.endswith('.gz'):
        import gzip
        with gzip.open(path, 'rb') as f:
            return json.load(f)
    else:
        raise TypeError("Don't know how to read {}".format(filename))
