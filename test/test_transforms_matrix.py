from pprint import pprint

import pytest

from taskgraph.transforms import matrix


def assert_single_matrix(tasks):
    assert tasks == [
        {"attributes": {"matrix": {"animal": "dog"}}, "name": "task-dog"},
        {"attributes": {"matrix": {"animal": "cat"}}, "name": "task-cat"},
    ]


def assert_double_matrix(tasks):
    assert tasks == [
        {
            "attributes": {"matrix": {"animal": "dog", "colour": "brown"}},
            "name": "task-brown-dog",
        },
        {
            "attributes": {"matrix": {"animal": "cat", "colour": "brown"}},
            "name": "task-brown-cat",
        },
        {
            "attributes": {"matrix": {"animal": "dog", "colour": "black"}},
            "name": "task-black-dog",
        },
        {
            "attributes": {"matrix": {"animal": "cat", "colour": "black"}},
            "name": "task-black-cat",
        },
    ]


def assert_substitution_basic(tasks):
    assert tasks == [
        {
            "attributes": {"matrix": {"animal": "dog"}},
            "description": "A dog task!",
            "name": "task-dog",
        }
    ]


def assert_substitution_fields(tasks):
    assert tasks == [
        {
            "attributes": {"matrix": {"animal": "dog"}},
            "description": "A {matrix[animal]} task!",
            "name": "task-dog",
            "worker": {"env": {"ANIMAL": "dog"}},
        }
    ]


def assert_exclude(tasks):
    assert len(tasks) == 1
    assert tasks[0]["name"] == "task-black-dog"


def assert_set_name(tasks):
    assert len(tasks) == 1
    assert tasks[0]["name"] == "dog-who-is-brown"


@pytest.mark.parametrize(
    "task",
    (
        pytest.param(
            {"matrix": {"animal": ["dog", "cat"]}},
            id="single_matrix",
        ),
        pytest.param(
            {"matrix": {"colour": ["brown", "black"], "animal": ["dog", "cat"]}},
            id="double_matrix",
        ),
        pytest.param(
            {"description": "A {matrix[animal]} task!", "matrix": {"animal": ["dog"]}},
            id="substitution_basic",
        ),
        pytest.param(
            {
                "description": "A {matrix[animal]} task!",
                "matrix": {"substitution-fields": ["worker.env"], "animal": ["dog"]},
                "worker": {"env": {"ANIMAL": "{matrix[animal]}"}},
            },
            id="substitution_fields",
        ),
        pytest.param(
            {
                "description": "A {matrix[animal]} task!",
                "matrix": {
                    "exclude": [
                        {"animal": "dog", "colour": "brown"},
                        {"animal": "cat"},
                    ],
                    "colour": ["brown", "black"],
                    "animal": ["dog", "cat"],
                },
            },
            id="exclude",
        ),
        pytest.param(
            {
                "description": "A {matrix[animal]} task!",
                "matrix": {
                    "set-name": "{matrix[animal]}-who-is-{matrix[colour]}",
                    "substitution-fields": ["description"],
                    "colour": ["brown"],
                    "animal": ["dog"],
                },
            },
            id="set_name",
        ),
    ),
)
def test_transforms(request, make_transform_config, run_transform, task):
    task.setdefault("name", "task")

    config = make_transform_config()

    try:
        result = run_transform(matrix.transforms, task, config)
    except Exception as e:
        result = e

    print("Dumping result:")
    pprint(result, indent=2)

    param_id = request.node.callspec.id
    assert_func = globals()[f"assert_{param_id}"]
    assert_func(result)
