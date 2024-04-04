from pprint import pprint

import pytest

from taskgraph.util.cached_tasks import add_optimization


def handle_exception(obj, exc=None):
    if exc:
        assert isinstance(obj, exc)
    elif isinstance(obj, Exception):
        raise obj


def assert_digest_and_digest_data(e):
    handle_exception(e, exc=Exception)


def assert_basic(task, digest):
    assert task == {
        "attributes": {
            "cached_task": {
                "digest": digest,
                "name": "cache-name",
                "type": "cache-type",
            }
        },
        "optimization": {
            "index-search": [
                f"test-domain.cache.level-3.cache-type.cache-name.hash.{digest}",
                f"test-domain.cache.level-2.cache-type.cache-name.hash.{digest}",
                f"test-domain.cache.level-1.cache-type.cache-name.hash.{digest}",
            ]
        },
        "routes": [
            f"index.test-domain.cache.level-1.cache-type.cache-name.hash.{digest}",
            "index.test-domain.cache.level-1.cache-type.cache-name.latest",
            "index.test-domain.cache.level-1.cache-type.cache-name.pushdate.1970.01.01.19700101000000",
        ],
    }


def assert_digest_basic(task):
    handle_exception(task)
    assert_basic(task, "abc")


def assert_digest_data_basic(task):
    handle_exception(task)
    assert_basic(
        task, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def assert_cached_task_prefix(task):
    handle_exception(task)
    assert task == {
        "attributes": {
            "cached_task": {"digest": "abc", "name": "cache-name", "type": "cache-type"}
        },
        "optimization": {
            "index-search": [
                "foobar.cache.level-3.cache-type.cache-name.hash.abc",
                "foobar.cache.level-2.cache-type.cache-name.hash.abc",
                "foobar.cache.level-1.cache-type.cache-name.hash.abc",
            ]
        },
        "routes": [
            "index.foobar.cache.level-1.cache-type.cache-name.hash.abc",
            "index.foobar.cache.level-1.cache-type.cache-name.latest",
            "index.foobar.cache.level-1.cache-type.cache-name.pushdate.1970.01.01.19700101000000",
        ],
    }


def assert_pull_request(task):
    handle_exception(task)
    assert task == {
        "attributes": {
            "cached_task": {"digest": "abc", "name": "cache-name", "type": "cache-type"}
        },
        "optimization": {
            "index-search": [
                "test-domain.cache.level-3.cache-type.cache-name.hash.abc",
                "test-domain.cache.level-2.cache-type.cache-name.hash.abc",
                "test-domain.cache.level-1.cache-type.cache-name.hash.abc",
                "test-domain.cache.pr.cache-type.cache-name.hash.abc",
            ]
        },
        "routes": ["index.test-domain.cache.pr.cache-type.cache-name.hash.abc"],
    }


def assert_pull_request_nocache(task):
    handle_exception(task)
    assert task == {
        "attributes": {
            "cached_task": {"digest": "abc", "name": "cache-name", "type": "cache-type"}
        },
        "optimization": {
            "index-search": [
                "test-domain.cache.level-3.cache-type.cache-name.hash.abc",
                "test-domain.cache.level-2.cache-type.cache-name.hash.abc",
                "test-domain.cache.level-1.cache-type.cache-name.hash.abc",
            ]
        },
    }


@pytest.mark.parametrize(
    "extra_params,extra_graph_config,digest,digest_data",
    (
        pytest.param(
            # extra_params
            None,
            # extra_graph_config
            None,
            # digest
            "abc",
            # digest_data
            ["def"],
            id="digest_and_digest_data",
        ),
        pytest.param(
            # extra_params
            None,
            # extra_graph_config
            None,
            # digest
            "abc",
            # digest_data
            None,
            id="digest_basic",
        ),
        pytest.param(
            # extra_params
            None,
            # extra_graph_config
            None,
            # digest
            None,
            # digest_data
            ["abc"],
            id="digest_data_basic",
        ),
        pytest.param(
            # extra_params
            None,
            # extra_graph_config
            {"taskgraph": {"cached-task-prefix": "foobar"}},
            # digest
            "abc",
            # digest_data
            None,
            id="cached_task_prefix",
        ),
        pytest.param(
            # extra_params
            {"tasks_for": "github-pull-request"},
            # extra_graph_config
            None,
            # digest
            "abc",
            # digest_data
            None,
            id="pull_request",
        ),
        pytest.param(
            # extra_params
            {"tasks_for": "github-pull-request"},
            # extra_graph_config
            {"taskgraph": {"cache-pull-requests": False}},
            # digest
            "abc",
            # digest_data
            None,
            id="pull_request_nocache",
        ),
    ),
)
def test_add_optimization(
    request,
    make_transform_config,
    extra_params,
    extra_graph_config,
    digest,
    digest_data,
):
    taskdesc = {"attributes": {}}
    cache_type = "cache-type"
    cache_name = "cache-name"

    config = make_transform_config(None, None, extra_params, extra_graph_config)

    try:
        add_optimization(
            config,
            taskdesc,
            cache_type,
            cache_name,
            digest=digest,
            digest_data=digest_data,
        )
        result = taskdesc
    except Exception as e:
        result = e

    print("Dumping result:")
    pprint(result, indent=2)

    param_id = request.node.callspec.id
    assert_func = globals()[f"assert_{param_id}"]
    assert_func(result)
