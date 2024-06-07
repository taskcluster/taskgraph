import pytest

from taskgraph.task import Task
from taskgraph.util.copy import deepcopy, immutable_types
from taskgraph.util.readonlydict import ReadOnlyDict


@pytest.mark.parametrize(
    "input",
    (
        1,
        False,
        "foo",
        ReadOnlyDict(a=1, b="foo"),
        ["foo", "bar"],
        {
            "foo": Task(
                label="abc",
                kind="kind",
                attributes={"bar": "baz"},
                dependencies={"dep": "bar"},
                task={"payload": {"command": ["echo hello"]}},
            )
        },
    ),
)
def test_deepcopy(input):
    result = deepcopy(input)
    assert result == input

    if type(result) in immutable_types:
        assert id(result) == id(input)
    else:
        assert id(result) != id(input)
