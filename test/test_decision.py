# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import pytest

from taskgraph import decision
from taskgraph.util.vcs import GitRepository, HgRepository
from taskgraph.util.yaml import load_yaml

FAKE_GRAPH_CONFIG = {"product-dir": "browser", "taskgraph": {}}


class TestDecision(unittest.TestCase):
    def test_write_artifact_json(self):
        data = [{"some": "data"}]
        tmpdir = tempfile.mkdtemp()
        try:
            decision.ARTIFACTS_DIR = Path(tmpdir) / "artifacts"
            decision.write_artifact("artifact.json", data)
            with open(os.path.join(decision.ARTIFACTS_DIR, "artifact.json")) as f:
                self.assertEqual(json.load(f), data)
        finally:
            if os.path.exists(tmpdir):
                shutil.rmtree(tmpdir)
            decision.ARTIFACTS_DIR = Path("artifacts")

    def test_write_artifact_yml(self):
        data = [{"some": "data"}]
        tmpdir = tempfile.mkdtemp()
        try:
            decision.ARTIFACTS_DIR = Path(tmpdir) / "artifacts"
            decision.write_artifact("artifact.yml", data)
            self.assertEqual(load_yaml(decision.ARTIFACTS_DIR, "artifact.yml"), data)
        finally:
            if os.path.exists(tmpdir):
                shutil.rmtree(tmpdir)
            decision.ARTIFACTS_DIR = Path("artifacts")


@unittest.mock.patch.object(
    GitRepository,
    "get_changed_files",
)
class TestGetDecisionParameters(unittest.TestCase):
    def setUp(self):
        self.options = {
            "base_repository": "https://hg.mozilla.org/mozilla-unified",
            "head_repository": "https://hg.mozilla.org/mozilla-central",
            "head_rev": "bbbb",
            "head_ref": "default",
            "head_tag": "v0.0.1",
            "project": "mozilla-central",
            "pushlog_id": "143",
            "pushdate": 1503691511,
            "repository_type": "hg",
            "optimize_strategies": None,
            "owner": "nobody@mozilla.com",
            "tasks_for": "hg-push",
            "level": "3",
        }
        self.old_determine_more_accurate_base_rev = (
            decision._determine_more_accurate_base_rev
        )
        decision._determine_more_accurate_base_rev = lambda *_, **__: "aaaa"
        self.old_determine_more_accurate_base_ref = (
            decision._determine_more_accurate_base_ref
        )
        decision._determine_more_accurate_base_ref = lambda *_, **__: "aaaa"

    def tearDown(self):
        decision._determine_more_accurate_base_rev = (
            self.old_determine_more_accurate_base_rev
        )
        decision._determine_more_accurate_base_ref = (
            self.old_determine_more_accurate_base_ref
        )

    def test_simple_options(self, mock_files_changed):
        mock_files_changed.return_value = ["foo.txt"]
        params = decision.get_decision_parameters(FAKE_GRAPH_CONFIG, self.options)
        mock_files_changed.assert_called_once_with(rev="bbbb", base_rev="aaaa")
        self.assertEqual(params["build_date"], 1503691511)
        self.assertEqual(params["head_tag"], "v0.0.1")
        self.assertEqual(params["pushlog_id"], "143")
        self.assertEqual(params["moz_build_date"], "20170825200511")
        self.assertEqual(params["files_changed"], ["foo.txt"])

    def test_no_email_owner(self, mock_files_changed):
        mock_files_changed.return_value = ["foo.txt"]
        self.options["owner"] = "ffxbld"
        params = decision.get_decision_parameters(FAKE_GRAPH_CONFIG, self.options)
        self.assertEqual(params["owner"], "ffxbld@noreply.mozilla.org")

    @unittest.mock.patch.object(
        GitRepository,
        "get_commit_message",
        unittest.mock.MagicMock(return_value="Add Foo"),
    )
    @unittest.mock.patch.object(
        HgRepository,
        "get_commit_message",
        unittest.mock.MagicMock(return_value="Add Foo"),
    )
    def test_regular_commit_message_yields_default_target_tasks_method(
        self, mock_files_changed
    ):
        """
        Ensures `target_tasks_method` is `default` when the commit message does not contain
        `DONTBUILD`.
        """
        mock_files_changed.return_value = ["foo.txt"]
        self.options["tasks_for"] = "github-push"
        params = decision.get_decision_parameters(FAKE_GRAPH_CONFIG, self.options)
        self.assertEqual(params["target_tasks_method"], "default")

        self.options["tasks_for"] = "hg-push"
        params = decision.get_decision_parameters(FAKE_GRAPH_CONFIG, self.options)
        self.assertEqual(params["target_tasks_method"], "default")

    @unittest.mock.patch.object(
        GitRepository,
        "get_commit_message",
        unittest.mock.MagicMock(return_value="DONTBUILD"),
    )
    @unittest.mock.patch.object(
        HgRepository,
        "get_commit_message",
        unittest.mock.MagicMock(return_value="DONTBUILD"),
    )
    def test_dontbuild_commit_message_yields_default_target_tasks_method(
        self, mock_files_changed
    ):
        """
        Ensures `target_tasks_method` is `nothing` when the commit message contains `DONTBUILD`.
        """
        mock_files_changed.return_value = ["foo.txt"]
        self.options["tasks_for"] = "github-release"
        params = decision.get_decision_parameters(FAKE_GRAPH_CONFIG, self.options)
        self.assertNotEqual(params["target_tasks_method"], "nothing")

        self.options["tasks_for"] = "github-push"
        params = decision.get_decision_parameters(FAKE_GRAPH_CONFIG, self.options)
        self.assertEqual(params["target_tasks_method"], "nothing")

        self.options["tasks_for"] = "hg-push"
        params = decision.get_decision_parameters(FAKE_GRAPH_CONFIG, self.options)
        self.assertEqual(params["target_tasks_method"], "nothing")


@pytest.mark.parametrize(
    "candidate_base_ref, base_rev, expected_base_ref",
    (
        ("", "base-rev", "default-branch"),
        ("head-ref", "base-rev", "head-ref"),
        ("head-ref", "0000000000000000000000000000000000000000", "default-branch"),
    ),
)
def test_determine_more_accurate_base_ref(
    candidate_base_ref, base_rev, expected_base_ref
):
    repo_mock = unittest.mock.MagicMock()
    repo_mock.default_branch = "default-branch"

    assert (
        decision._determine_more_accurate_base_ref(
            repo_mock, candidate_base_ref, "head-ref", base_rev
        )
        == expected_base_ref
    )


@pytest.mark.parametrize(
    "common_rev, candidate_base_rev, expected_base_ref_or_rev, expected_base_rev",
    (
        ("found-rev", "", "base-ref", "found-rev"),
        (
            "found-rev",
            "0000000000000000000000000000000000000000",
            "base-ref",
            "found-rev",
        ),
        ("found-rev", "non-existing-rev", "base-ref", "found-rev"),
        ("existing-rev", "existing-rev", "existing-rev", "existing-rev"),
    ),
)
def test_determine_more_accurate_base_rev(
    common_rev, candidate_base_rev, expected_base_ref_or_rev, expected_base_rev
):
    repo_mock = unittest.mock.MagicMock()
    repo_mock.find_latest_common_revision.return_value = common_rev
    repo_mock.does_revision_exist_locally = lambda rev: rev == "existing-rev"

    assert (
        decision._determine_more_accurate_base_rev(
            repo_mock, "base-ref", candidate_base_rev, "head-rev", env_prefix="PREFIX"
        )
        == expected_base_rev
    )
    repo_mock.find_latest_common_revision.assert_called_once_with(
        expected_base_ref_or_rev, "head-rev"
    )


@pytest.mark.parametrize(
    "graph_config, expected_value",
    (
        ({"taskgraph": {}}, ""),
        ({"taskgraph": {"repositories": {}}}, ""),
        ({"taskgraph": {"repositories": {"mobile": {}}}}, "mobile"),
        (
            {"taskgraph": {"repositories": {"mobile": {}, "some-other-repo": {}}}},
            "mobile",
        ),
    ),
)
def test_get_env_prefix(graph_config, expected_value):
    assert decision._get_env_prefix(graph_config) == expected_value
