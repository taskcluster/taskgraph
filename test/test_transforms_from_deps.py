"""
Tests for the 'from_deps' transforms.
"""

from pprint import pprint

import pytest

from taskgraph.transforms import from_deps

from .conftest import make_task


def handle_exception(obj, exc=None):
    if exc:
        assert isinstance(obj, exc)
    elif isinstance(obj, Exception):
        raise obj


def assert_no_kind_dependencies(e):
    handle_exception(e, exc=Exception)


def assert_invalid_only_kinds(e):
    handle_exception(e, exc=Exception)


def assert_defaults(tasks):
    handle_exception(tasks)
    assert len(tasks) == 2
    assert tasks[0]["attributes"] == {"primary-kind-dependency": "foo"}
    assert tasks[0]["dependencies"] == {"foo": "a"}
    assert tasks[0]["name"] == "a"
    assert tasks[1]["attributes"] == {"primary-kind-dependency": "bar"}
    assert tasks[1]["dependencies"] == {"bar": "bar-b"}
    assert tasks[1]["name"] == "b"


assert_group_by_single = assert_defaults


def assert_group_by_attribute(tasks):
    handle_exception(tasks)
    assert len(tasks) == 2
    assert tasks[0]["dependencies"] == {"foo": "a"}
    assert tasks[0]["attributes"] == {"primary-kind-dependency": "foo"}
    assert tasks[1]["dependencies"] == {"foo": "b", "bar": "c"}
    assert tasks[1]["attributes"] == {"primary-kind-dependency": "foo"}


def assert_group_by_attribute_dupe(e):
    handle_exception(e, exc=Exception)


def assert_copy_attributes(tasks):
    handle_exception(tasks)
    assert len(tasks) == 1

    task = tasks[0]
    assert task["attributes"] == {
        "build-type": "win",
        "kind": "foo",
        "primary-kind-dependency": "foo",
    }


@pytest.mark.parametrize(
    "task, kind_config, deps",
    (
        pytest.param(
            # task
            {"from-deps": {}},
            # kind config
            {},
            # deps
            None,
            id="no_kind_dependencies",
        ),
        pytest.param(
            # task
            {"from-deps": {"kinds": ["foo", "baz"]}},
            # kind config
            None,
            # deps
            None,
            id="invalid_only_kinds",
        ),
        pytest.param(
            # task
            {"from-deps": {}},
            # kind config
            None,
            # deps
            None,
            id="defaults",
        ),
        pytest.param(
            # task
            {"from-deps": {}},
            # kind config
            None,
            # deps
            None,
            id="group_by_single",
        ),
        pytest.param(
            # task
            {"from-deps": {"group-by": {"attribute": "build-type"}}},
            # kind config
            None,
            # deps
            {
                "a": make_task("a", attributes={"build-type": "linux"}, kind="foo"),
                "b": make_task("b", attributes={"build-type": "win"}, kind="foo"),
                "c": make_task("c", attributes={"build-type": "win"}, kind="bar"),
            },
            id="group_by_attribute",
        ),
        pytest.param(
            # task
            {"from-deps": {"group-by": {"attribute": "build-type"}}},
            # kind config
            None,
            # deps
            {
                "a": make_task("a", attributes={"build-type": "linux"}, kind="foo"),
                "b": make_task("b", attributes={"build-type": "win"}, kind="foo"),
                "c": make_task("c", attributes={"build-type": "win"}, kind="foo"),
            },
            id="group_by_attribute_dupe",
        ),
        pytest.param(
            # task
            {
                "from-deps": {
                    "group-by": {"attribute": "build-type"},
                    "copy-attributes": True,
                }
            },
            # kind config
            None,
            # deps
            {
                "a": make_task(
                    "a", attributes={"build-type": "win", "kind": "bar"}, kind="bar"
                ),
                "b": make_task(
                    "b", attributes={"build-type": "win", "kind": "foo"}, kind="foo"
                ),
            },
            id="copy_attributes",
        ),
    ),
)
def test_transforms(
    request, make_transform_config, run_transform, task, kind_config, deps
):
    task.setdefault("name", "task")
    task.setdefault("description", "description")

    if kind_config is None:
        kind_config = {"kind-dependencies": ["foo", "bar"]}

    if deps is None:
        deps = {
            "a": make_task("a", kind="foo"),
            "b": make_task("bar-b", kind="bar"),
        }
    config = make_transform_config(kind_config, deps)

    try:
        result = run_transform(from_deps.transforms, task, config)
    except Exception as e:
        result = e

    print("Dumping result:")
    pprint(result, indent=2)

    param_id = request.node.callspec.id
    assert_func = globals()[f"assert_{param_id}"]
    assert_func(result)
