# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os.path
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from taskgraph.config import GraphConfig


def test_graph_config_basic():
    graph_config = GraphConfig({"foo": "bar"}, "root")

    assert os.path.isabs(graph_config.root_dir)

    assert "foo" in graph_config
    assert graph_config["foo"] == "bar"
    assert graph_config.get("foo") == "bar"

    assert "missing" not in graph_config
    assert graph_config.get("missing") is None

    with pytest.raises(KeyError):
        graph_config["missing"]

    # does not support assignment
    with pytest.raises(TypeError):
        graph_config["foo"] = "different"

    with pytest.raises(TypeError):
        graph_config["baz"] = 2


def test_vcs_root_with_non_standard_dir():
    """Test that  property uses vcs_root correctly with a non standard path"""

    path_repo = "/path/to/repo"
    mock_repo = Mock()
    mock_repo.path = path_repo

    with patch("taskgraph.config.get_repository", return_value=mock_repo):
        graph_config = GraphConfig({"foo": "bar"}, "root/data")
        vcs_root = graph_config.vcs_root

        expected_path = Path("/path/to/repo")

        assert vcs_root == expected_path


def test_vcs_root_fallback(mocker):
    mocker.patch("os.getcwd", return_value="/path/to/repo")

    cfg = {"foo": "bar"}
    with mocker.patch("taskgraph.config.get_repository", side_effect=RuntimeError):
        assert GraphConfig(cfg, "taskcluster").vcs_root == Path("/path/to/repo")

    with mocker.patch("taskgraph.config.get_repository", side_effect=RuntimeError):
        with pytest.raises(Exception):
            GraphConfig(cfg, "root/data").vcs_root
