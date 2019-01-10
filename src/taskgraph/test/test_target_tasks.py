# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import unittest

from taskgraph import target_tasks
from taskgraph.graph import Graph
from taskgraph.taskgraph import TaskGraph
from taskgraph.task import Task


class TestTargetTasks(unittest.TestCase):

    def default_matches_project(self, run_on_projects, project):
        return self.default_matches(
            attributes={
                'run_on_projects': run_on_projects,
            },
            parameters={
                'project': project,
                'hg_branch': 'default',
            },
        )

    def default_matches_hg_branch(self, run_on_hg_branches, hg_branch):
        attributes = {'run_on_projects': ['all']}
        if run_on_hg_branches is not None:
            attributes['run_on_hg_branches'] = run_on_hg_branches

        return self.default_matches(
            attributes=attributes,
            parameters={
                'project': 'mozilla-central',
                'hg_branch': hg_branch,
            },
        )

    def default_matches(self, attributes, parameters):
        method = target_tasks.get_method('default')
        graph = TaskGraph(tasks={
            'a': Task(kind='build', label='a',
                      attributes=attributes,
                      task={}),
        }, graph=Graph(nodes={'a'}, edges=set()))
        return 'a' in method(graph, parameters, {})

    def test_default_all(self):
        """run_on_projects=[all] includes release, integration, and other projects"""
        self.assertTrue(self.default_matches_project(['all'], 'mozilla-central'))
        self.assertTrue(self.default_matches_project(['all'], 'mozilla-inbound'))
        self.assertTrue(self.default_matches_project(['all'], 'baobab'))

    def test_default_nothing(self):
        """run_on_projects=[] includes nothing"""
        self.assertFalse(self.default_matches_project([], 'mozilla-central'))
        self.assertFalse(self.default_matches_project([], 'mozilla-inbound'))
        self.assertFalse(self.default_matches_project([], 'baobab'))

    def test_default_hg_branch(self):
        self.assertTrue(self.default_matches_hg_branch(None, 'default'))
        self.assertTrue(self.default_matches_hg_branch(None, 'GECKOVIEW_62_RELBRANCH'))

        self.assertFalse(self.default_matches_hg_branch([], 'default'))
        self.assertFalse(self.default_matches_hg_branch([], 'GECKOVIEW_62_RELBRANCH'))

        self.assertTrue(self.default_matches_hg_branch(['all'], 'default'))
        self.assertTrue(self.default_matches_hg_branch(['all'], 'GECKOVIEW_62_RELBRANCH'))

        self.assertTrue(self.default_matches_hg_branch(['default'], 'default'))
        self.assertTrue(self.default_matches_hg_branch([r'default'], 'default'))
        self.assertFalse(self.default_matches_hg_branch([r'default'], 'GECKOVIEW_62_RELBRANCH'))

        self.assertTrue(
            self.default_matches_hg_branch(['GECKOVIEW_62_RELBRANCH'], 'GECKOVIEW_62_RELBRANCH')
        )
        self.assertTrue(
            self.default_matches_hg_branch(['GECKOVIEW_\d+_RELBRANCH'], 'GECKOVIEW_62_RELBRANCH')
        )
        self.assertTrue(
            self.default_matches_hg_branch([r'GECKOVIEW_\d+_RELBRANCH'], 'GECKOVIEW_62_RELBRANCH')
        )
        self.assertFalse(self.default_matches_hg_branch([r'GECKOVIEW_\d+_RELBRANCH'], 'default'))

    def make_task_graph(self):
        tasks = {
            'a': Task(kind=None, label='a', attributes={}, task={}),
            'b': Task(kind=None, label='b', attributes={'at-at': 'yep'}, task={}),
            'c': Task(kind=None, label='c', attributes={'run_on_projects': ['try']}, task={}),
        }
        graph = Graph(nodes=set('abc'), edges=set())
        return TaskGraph(tasks, graph)
