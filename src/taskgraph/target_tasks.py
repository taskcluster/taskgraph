# -*- coding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

from taskgraph.util.attributes import match_run_on_projects, match_run_on_hg_branches

_target_task_methods = {}


def _target_task(name):
    def wrap(func):
        _target_task_methods[name] = func
        return func
    return wrap


def get_method(method):
    """Get a target_task_method to pass to a TaskGraphGenerator."""
    return _target_task_methods[method]


def filter_out_cron(task, parameters):
    """
    Filter out tasks that run via cron.
    """
    return not task.attributes.get('cron')


def filter_for_project(task, parameters):
    """Filter tasks by project.  Optionally enable nightlies."""
    run_on_projects = set(task.attributes.get('run_on_projects', []))
    return match_run_on_projects(parameters['project'], run_on_projects)


def filter_for_hg_branch(task, parameters):
    """Filter tasks by hg branch.
    If `run_on_hg_branch` is not defined, then task runs on all branches"""
    run_on_hg_branches = set(task.attributes.get('run_on_hg_branches', ['all']))
    return match_run_on_hg_branches(parameters['hg_branch'], run_on_hg_branches)


def standard_filter(task, parameters):
    return all(
        filter_func(task, parameters) for filter_func in
        (filter_out_cron, filter_for_project, filter_for_hg_branch)
    )


@_target_task('default')
def target_tasks_default(full_task_graph, parameters, graph_config):
    """Target the tasks which have indicated they should be run on this project
    via the `run_on_projects` attributes."""
    return [l for l, t in full_task_graph.tasks.iteritems()
            if standard_filter(t, parameters)]