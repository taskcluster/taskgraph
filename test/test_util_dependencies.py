from taskgraph.util.dependencies import get_dependencies, get_primary_dependency

from .conftest import make_task


def test_get_dependencies(make_transform_config):
    dep_tasks = {
        "foo": make_task("foo", kind="kind1"),
        "bar": make_task("bar", kind="kind2"),
    }
    config = make_transform_config(kind_dependencies_tasks=dep_tasks)
    task = {}
    assert list(get_dependencies(config, task)) == []

    task["dependencies"] = {"kind1": "foo", "kind2": "bar"}
    deps = list(get_dependencies(config, task))
    assert deps == list(dep_tasks.values())


def test_get_primary_dependency(make_transform_config):
    dep_tasks = {
        "foo": make_task("foo", kind="kind1"),
        "bar": make_task("bar", kind="kind2"),
    }
    config = make_transform_config(kind_dependencies_tasks=dep_tasks)
    task = {
        "attributes": {},
        "dependencies": {"kind1": "foo", "kind2": "bar"},
    }
    assert get_primary_dependency(config, task) is None

    task["attributes"]["primary-kind-dependency"] = "kind2"
    assert get_primary_dependency(config, task) == list(dep_tasks.values())[1]
