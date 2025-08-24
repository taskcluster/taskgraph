from itertools import count
from textwrap import dedent
from unittest.mock import Mock

import pytest

from taskgraph.util.json import dump, dumps, load, loads


@pytest.fixture(autouse=True, params=["json", "orjson"])
def with_module(request, mocker):
    module = request.param
    if module == "orjson":
        pytest.importorskip("orjson")

    if module == "json":
        mocker.patch("taskgraph.util.json.orjson", None)


@pytest.mark.parametrize(
    "input_data, expected",
    [
        ('{"key": "value"}', {"key": "value"}),
    ],
    ids=count(),
)
def test_loads(input_data, expected):
    assert loads(input_data) == expected


@pytest.mark.parametrize(
    "input_data, expected",
    [
        ('{"key": "value"}', {"key": "value"}),
    ],
    ids=count(),
)
def test_load(input_data, expected):
    mock_file = Mock(read=Mock(return_value=input_data))
    assert load(mock_file) == expected


@pytest.mark.parametrize(
    "input_data, json_args, expected",
    [
        ({"b": 1, "a": 2}, {}, '{"b":1,"a":2}'),
        ({"b": 1, "a": 2}, {"sort_keys": True}, '{"a":2,"b":1}'),
        (
            {"b": 1, "a": 2},
            {"indent": 2},
            dedent("""
            {
              "b": 1,
              "a": 2
            }""").lstrip(),
        ),
    ],
    ids=count(),
)
def test_dumps(input_data, json_args, expected):
    assert dumps(input_data, **json_args) == expected


@pytest.mark.parametrize(
    "input_data, json_args, expected",
    [
        ({"key": "value"}, {}, '{"key":"value"}'),
    ],
    ids=count(),
)
def test_dump(input_data, json_args, expected):
    mock_file = Mock()

    dump(input_data, mock_file, **json_args)

    mock_file.write.assert_called_once_with(expected)
