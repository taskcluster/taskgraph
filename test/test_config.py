# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os.path

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


def test_vcs_root_property():
    """Test the vcs_root property returns the parent directory of root_dir without throwing an exception."""

    # Test with a standard taskcluster directory structure
    graph_config = GraphConfig({}, "/path/to/project/taskcluster")
    assert graph_config.vcs_root == "/path/to/project"

    # Test with a different directory structure
    graph_config = GraphConfig({}, "/path/to/custom/.taskgraph")
    assert graph_config.vcs_root == "/path/to/custom"
