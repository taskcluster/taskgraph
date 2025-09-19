"""
Tests for the 'from_deps' transforms.
"""

from pprint import pprint
from typing import Dict

import pytest
from pytest_taskgraph import make_task

from taskgraph.task import Task
from taskgraph.transforms import from_deps


def get_task_label_by_attributes(
    tasks: Dict[str, Task], attributes: Dict[str, str]
) -> str:
    for task in tasks.values():
        if all([task.attributes[k] == v for k, v in attributes.items()]):
            return task.label

    return ""


def handle_exception(obj, exc=None):
    if exc:
        assert isinstance(obj, exc)
    elif isinstance(obj, Exception):
        raise obj


def assert_no_kind_dependencies(_, e):
    handle_exception(e, exc=Exception)


def assert_invalid_only_kinds(_, e):
    handle_exception(e, exc=Exception)


def assert_defaults(deps, tasks):
    handle_exception(tasks)
    assert len(tasks) == 2
    assert tasks[0]["attributes"] == {
        "primary-kind-dependency": "foo",
        "primary-dependency-label": get_task_label_by_attributes(deps, {"kind": "foo"}),
    }
    assert tasks[0]["dependencies"] == {"foo": "a"}
    assert tasks[0]["name"] == "a"
    assert tasks[1]["attributes"] == {
        "primary-kind-dependency": "bar",
        "primary-dependency-label": get_task_label_by_attributes(deps, {"kind": "bar"}),
    }
    assert tasks[1]["dependencies"] == {"bar": "bar-b"}
    assert tasks[1]["name"] == "b"


assert_group_by_single = assert_defaults


def assert_group_by_attribute(deps, tasks):
    handle_exception(tasks)
    assert len(tasks) == 2
    assert tasks[0]["dependencies"] == {"foo": "a"}
    assert tasks[0]["attributes"] == {
        "primary-kind-dependency": "foo",
        "primary-dependency-label": get_task_label_by_attributes(
            deps, {"kind": "foo", "build-type": "linux"}
        ),
    }
    assert tasks[1]["dependencies"] == {"foo": "b", "bar": "c"}
    assert tasks[1]["attributes"] == {
        "primary-kind-dependency": "foo",
        "primary-dependency-label": get_task_label_by_attributes(
            deps, {"kind": "foo", "build-type": "win"}
        ),
    }


def assert_group_by_attribute_dupe(_, e):
    handle_exception(e, exc=Exception)


def assert_group_by_attribute_dupe_allowed(deps, tasks):
    handle_exception(tasks)
    assert len(tasks) == 2
    assert tasks[0]["dependencies"] == {"a": "a"}
    assert tasks[0]["attributes"] == {
        "primary-kind-dependency": "foo",
        "primary-dependency-label": get_task_label_by_attributes(
            deps, {"kind": "foo", "build-type": "linux"}
        ),
    }
    assert tasks[1]["dependencies"] == {"b": "b", "c": "c"}
    assert tasks[1]["attributes"] == {
        "primary-kind-dependency": "foo",
        "primary-dependency-label": get_task_label_by_attributes(
            deps, {"kind": "foo", "build-type": "win"}
        ),
    }


def assert_copy_attributes(deps, tasks):
    handle_exception(tasks)
    assert len(tasks) == 1

    task = tasks[0]
    assert task["attributes"] == {
        "build-type": "win",
        "kind": "foo",
        "primary-kind-dependency": "foo",
        "primary-dependency-label": get_task_label_by_attributes(deps, {"kind": "foo"}),
    }


def assert_group_by_all(deps, tasks):
    handle_exception(tasks)
    assert len(tasks) == 1
    assert tasks[0]["dependencies"] == {"foo": "a", "bar": "bar-b"}


def assert_group_by_all_dupe_allowed(deps, tasks):
    handle_exception(tasks)
    assert len(tasks) == 1
    assert tasks[0]["dependencies"] == {"a": "a", "b": "b", "c": "c"}


def assert_dont_set_name(deps, tasks):
    handle_exception(tasks)
    assert len(tasks) == 1
    assert tasks[0]["name"] == "a-special-name"


def assert_dont_set_name_false(deps, tasks):
    handle_exception(tasks)
    assert len(tasks) == 1
    assert tasks[0]["name"] == "a-special-name"


def assert_set_name_strip_kind(deps, tasks):
    handle_exception(tasks)
    assert len(tasks) == 2
    assert tasks[0]["name"] == "a"
    assert tasks[1]["name"] == "b"


def assert_set_name_retain_kind(deps, tasks):
    handle_exception(tasks)
    assert len(tasks) == 2
    assert tasks[0]["name"] == "a"
    assert tasks[1]["name"] == "bar-b"


def assert_group_by_all_with_fetch(deps, tasks):
    handle_exception(tasks)
    assert len(tasks) == 1
    assert tasks[0]["dependencies"] == {
        "foo1": "foo1",
        "foo2": "foo2",
        "foo3": "foo3",
        "foo4": "foo4",
    }
    assert tasks[0]["fetches"] == {
        "foo1": [
            {
                "artifact": "foo.1.txt",
                "dest": "foo-1.txt",
            },
        ],
        "foo2": [
            {
                "artifact": "foo.2.txt",
                "dest": "foo-2.txt",
            },
        ],
        "foo3": [
            {
                "artifact": "foo.3.txt",
                "dest": "foo-3.txt",
            },
        ],
        "foo4": [
            {
                "artifact": "foo.4.txt",
                "dest": "foo-4.txt",
            },
        ],
    }


def assert_unique_kinds_with_fetch(deps, tasks):
    handle_exception(tasks)
    assert tasks[0]["fetches"] == {"foo": [{"artifact": "foo.txt"}]}


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
            {
                "name": "a-special-name",
                "from-deps": {
                    "group-by": "all",
                    "set-name": None,
                },
            },
            # kind config
            None,
            # deps
            None,
            id="dont_set_name",
        ),
        pytest.param(
            # task
            {
                "name": "a-special-name",
                "from-deps": {
                    "group-by": "all",
                    "set-name": False,
                },
            },
            # kind config
            None,
            # deps
            None,
            id="dont_set_name_false",
        ),
        pytest.param(
            # task
            {
                "from-deps": {
                    "set-name": "strip-kind",
                },
            },
            # kind config
            None,
            # deps
            None,
            id="set_name_strip_kind",
        ),
        pytest.param(
            # task
            {
                "from-deps": {
                    "set-name": "retain-kind",
                },
            },
            # kind config
            None,
            # deps
            None,
            id="set_name_retain_kind",
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
                    "unique-kinds": False,
                    "group-by": {"attribute": "build-type"},
                }
            },
            # kind config
            None,
            # deps
            {
                "a": make_task("a", attributes={"build-type": "linux"}, kind="foo"),
                "b": make_task("b", attributes={"build-type": "win"}, kind="foo"),
                "c": make_task("c", attributes={"build-type": "win"}, kind="foo"),
            },
            id="group_by_attribute_dupe_allowed",
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
        pytest.param(
            # task
            {
                "from-deps": {
                    "group-by": "all",
                }
            },
            # kind config
            None,
            # deps
            None,
            id="group_by_all",
        ),
        pytest.param(
            # task
            {
                "from-deps": {
                    "unique-kinds": False,
                    "group-by": "all",
                }
            },
            # kind config
            None,
            # deps
            {
                "a": make_task("a", kind="foo"),
                "b": make_task("b", kind="foo"),
                "c": make_task("c", kind="foo"),
            },
            id="group_by_all_dupe_allowed",
        ),
        pytest.param(
            # task
            {
                "from-deps": {
                    "group-by": "all",
                    "unique-kinds": False,
                    "kinds": ["foo"],
                    "fetches": {
                        "foo": [
                            {
                                "artifact": "foo.{this_chunk}.txt",
                                "dest": "foo-{this_chunk}.txt",
                            },
                        ],
                    },
                },
            },
            # kind config
            None,
            # deps
            {
                "foo1": make_task(
                    "foo1",
                    kind="foo",
                    attributes={"this_chunk": "1", "total_chunks": "4", "kind": "foo"},
                ),
                "foo2": make_task(
                    "foo2",
                    kind="foo",
                    attributes={"this_chunk": "2", "total_chunks": "4", "kind": "foo"},
                ),
                "foo3": make_task(
                    "foo3",
                    kind="foo",
                    attributes={"this_chunk": "3", "total_chunks": "4", "kind": "foo"},
                ),
                "foo4": make_task(
                    "foo4",
                    kind="foo",
                    attributes={"this_chunk": "4", "total_chunks": "4", "kind": "foo"},
                ),
                "bar": make_task("bar", kind="bar", attributes={"kind": "bar"}),
            },
            id="group_by_all_with_fetch",
        ),
        pytest.param(
            # task
            {
                "from-deps": {
                    "kinds": ["foo"],
                    "unique-kinds": True,
                    "fetches": {
                        "foo": [
                            {"artifact": "foo.txt"},
                        ],
                    },
                },
            },
            # kind config
            None,
            # deps
            None,
            id="unique_kinds_with_fetch",
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
    assert_func(deps, result)
