# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import unittest

from taskgraph import target_tasks
from taskgraph.graph import Graph
from taskgraph.task import Task
from taskgraph.taskgraph import TaskGraph


class TestTargetTasks(unittest.TestCase):
    def default_matches_project(self, run_on_projects, project):
        return self.default_matches(
            attributes={
                "run_on_projects": run_on_projects,
            },
            parameters={
                "project": project,
                "tasks_for": "hg-push",
            },
        )

    def default_matches_tasks_for(self, run_on_tasks_for, tasks_for):
        attributes = {"run_on_projects": ["all"]}
        if run_on_tasks_for is not None:
            attributes["run_on_tasks_for"] = run_on_tasks_for

        return self.default_matches(
            attributes=attributes,
            parameters={
                "project": "mozilla-central",
                "repository_type": "hg",
                "tasks_for": tasks_for,
            },
        )

    def default_matches_git_branches(
        self, run_on_tasks_for, tasks_for, run_on_git_branches, git_branch
    ):
        attributes = {
            "run_on_projects": ["all"],
            "run_git_branches": ["all"],
        }
        if run_on_tasks_for is not None:
            attributes["run_on_tasks_for"] = run_on_tasks_for
        if run_on_git_branches is not None:
            attributes["run_on_git_branches"] = run_on_git_branches

        return self.default_matches(
            attributes=attributes,
            parameters={
                "project": "fenix",
                "repository_type": "git",
                "tasks_for": tasks_for,
                "head_ref": git_branch,
            },
        )

    def default_matches(self, attributes, parameters):
        method = target_tasks.get_method("default")
        graph = TaskGraph(
            tasks={
                "a": Task(kind="build", label="a", attributes=attributes, task={}),
            },
            graph=Graph(nodes={"a"}, edges=set()),
        )
        return "a" in method(graph, parameters, {})

    def test_default_all(self):
        """run_on_projects=[all] includes release, integration, and other projects"""
        self.assertTrue(self.default_matches_project(["all"], "mozilla-central"))
        self.assertTrue(self.default_matches_project(["all"], "mozilla-inbound"))
        self.assertTrue(self.default_matches_project(["all"], "baobab"))

    def test_default_nothing(self):
        """run_on_projects=[] includes nothing"""
        self.assertFalse(self.default_matches_project([], "mozilla-central"))
        self.assertFalse(self.default_matches_project([], "mozilla-inbound"))
        self.assertFalse(self.default_matches_project([], "baobab"))

    def test_default_tasks_for(self):
        self.assertTrue(self.default_matches_tasks_for(None, "hg-push"))
        self.assertTrue(self.default_matches_tasks_for(None, "github-pull-request"))

        self.assertFalse(self.default_matches_tasks_for([], "hg-push"))
        self.assertFalse(self.default_matches_tasks_for([], "github-pull-request"))

        self.assertTrue(self.default_matches_tasks_for(["all"], "hg-push"))
        self.assertTrue(self.default_matches_tasks_for(["all"], "github-pull-request"))

        self.assertTrue(self.default_matches_tasks_for(["hg-push"], "hg-push"))
        self.assertFalse(
            self.default_matches_tasks_for(["hg-push"], "github-pull-request")
        )

        self.assertTrue(
            self.default_matches_tasks_for(
                ["github-pull-request"], "github-pull-request"
            )
        )
        self.assertFalse(
            self.default_matches_tasks_for([r"github-pull-request"], "hg-pull")
        )

    def test_default_git_branches(self):
        self.assertTrue(
            self.default_matches_git_branches(
                None, "github-pull-request", None, "master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                None, "github-pull-request", None, "some-branch"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(None, "github-push", None, "master")
        )
        self.assertTrue(
            self.default_matches_git_branches(None, "github-push", None, "main")
        )
        self.assertTrue(
            self.default_matches_git_branches(None, "github-push", None, "some-branch")
        )
        self.assertTrue(
            self.default_matches_git_branches(
                None, "github-release", None, "release/v1.0"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                None, "github-release", None, "release_v2.0"
            )
        )

        self.assertFalse(
            self.default_matches_git_branches([], "github-pull-request", None, "master")
        )
        self.assertFalse(
            self.default_matches_git_branches(
                [], "github-pull-request", None, "some-branch"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches([], "github-push", None, "master")
        )
        self.assertFalse(
            self.default_matches_git_branches([], "github-push", None, "main")
        )
        self.assertFalse(
            self.default_matches_git_branches([], "github-push", None, "some-branch")
        )
        self.assertFalse(
            self.default_matches_git_branches([], "github-release", None, "master")
        )
        self.assertFalse(
            self.default_matches_git_branches(
                [], "github-release", None, "release/v1.0"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                [], "github-release", None, "release_v2.0"
            )
        )

        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-pull-request", ["master"], "master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-pull-request", ["master"], "some-branch"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-push", ["master"], "master"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-push", ["master"], "main"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-push", ["master"], "some-branch"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-release", ["master"], "master"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-release", ["master"], "release/v1.0"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-release", ["master"], "release_v2.0"
            )
        )

        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-pull-request", [r"release/.+"], "master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-pull-request", [r"release/.+"], "some-branch"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-push", [r"release/.+"], "master"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-push", [r"release/.+"], "main"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-push", [r"release/.+"], "some-branch"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-release", [r"release/.+"], "master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-release", [r"release/.+"], "release/v1.0"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-release", [r"release/.+"], "release_v2.0"
            )
        )

        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-pull-request", [r"release/.+"], "refs/heads/master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"],
                "github-pull-request",
                [r"release/.+"],
                "refs/heads/some-branch",
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-push", [r"release/.+"], "refs/heads/master"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-push", [r"release/.+"], "refs/heads/main"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-push", [r"release/.+"], "refs/heads/some-branch"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-release", [r"release/.+"], "refs/heads/master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-release", [r"release/.+"], "refs/heads/release/v1.0"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-release", [r"release/.+"], "refs/heads/release_v2.0"
            )
        )

        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-pull-request", ["master", r"release/.+"], "master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-pull-request", ["master", r"release/.+"], "some-branch"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-push", ["master", r"release/.+"], "master"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-push", ["master", r"release/.+"], "main"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-push", ["master", r"release/.+"], "some-branch"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-release", ["master", r"release/.+"], "master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "github-release", ["master", r"release/.+"], "release/v1.0"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "github-release", ["master", r"release/.+"], "release_v2.0"
            )
        )

    def make_task_graph(self):
        tasks = {
            "a": Task(kind=None, label="a", attributes={}, task={}),
            "b": Task(kind=None, label="b", attributes={"at-at": "yep"}, task={}),
            "c": Task(
                kind=None, label="c", attributes={"run_on_projects": ["try"]}, task={}
            ),
        }
        graph = Graph(nodes=set("abc"), edges=set())
        return TaskGraph(tasks, graph)
