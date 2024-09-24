# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from taskgraph.config import GraphConfig


def test_graph_config_basic():
    graph_config = GraphConfig({"foo": "bar"}, "root")

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
