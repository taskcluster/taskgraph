# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from pprint import pprint

import pytest

from taskgraph.util.keyed_by import iter_dot_path


@pytest.mark.parametrize(
    "container,subfield,expected",
    (
        pytest.param(
            {"a": {"b": {"c": 1}}, "d": 2}, "a.b.c", [({"c": 1}, "c")], id="simple case"
        ),
        pytest.param(
            {"a": [{"b": 1}, {"b": 2}, {"b": 3}], "d": 2},
            "a[].b",
            [({"b": 1}, "b"), ({"b": 2}, "b"), ({"b": 3}, "b")],
            id="list case",
        ),
        pytest.param(
            {"a": [{"b": 1}, {"b": 2}, {"c": 3}], "d": 2},
            "a[].b",
            [({"b": 1}, "b"), ({"b": 2}, "b")],
            id="list partial match case",
        ),
        pytest.param(
            {"a": [{"b": {"c": 4}}, {"b": {"c": 5}}, {"b": {"c": 6}}], "d": 2},
            "a[].b.c",
            [({"c": 4}, "c"), ({"c": 5}, "c"), ({"c": 6}, "c")],
            id="deep list case",
        ),
    ),
)
def test_iter_dot_paths(container, subfield, expected):
    result = list(iter_dot_path(container, subfield))
    pprint(result, indent=2)
    assert result == expected
