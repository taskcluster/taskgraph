# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os
import json
import shutil
import unittest
import tempfile
from pathlib import Path

from taskgraph import decision
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


class TestGetDecisionParameters(unittest.TestCase):
    def setUp(self):
        self.options = {
            "base_repository": "https://hg.mozilla.org/mozilla-unified",
            "head_repository": "https://hg.mozilla.org/mozilla-central",
            "head_rev": "abcd",
            "head_ref": "ef01",
            "head_tag": "v0.0.1",
            "project": "mozilla-central",
            "pushlog_id": "143",
            "pushdate": 1503691511,
            "repository_type": "hg",
            "owner": "nobody@mozilla.com",
            "tasks_for": "hg-push",
            "level": "3",
        }

    def test_simple_options(self):
        params = decision.get_decision_parameters(FAKE_GRAPH_CONFIG, self.options)
        self.assertEqual(params["build_date"], 1503691511)
        self.assertEqual(params["head_tag"], "v0.0.1")
        self.assertEqual(params["pushlog_id"], "143")
        self.assertEqual(params["moz_build_date"], "20170825200511")

    def test_no_email_owner(self):
        self.options["owner"] = "ffxbld"
        params = decision.get_decision_parameters(FAKE_GRAPH_CONFIG, self.options)
        self.assertEqual(params["owner"], "ffxbld@noreply.mozilla.org")
