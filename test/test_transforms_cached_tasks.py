import base64
from pprint import pprint

import pytest

from taskgraph.transforms import cached_tasks

from .conftest import make_task


def handle_exception(obj, exc=None):
    if exc:
        assert isinstance(obj, exc)
    elif isinstance(obj, Exception):
        raise obj


def assert_no_cache(tasks):
    handle_exception(tasks)
    assert len(tasks) == 1
    assert tasks[0] == {
        "label": "cached-task",
        "description": "description",
        "attributes": {},
    }


def assert_cache_basic(tasks):
    handle_exception(tasks)
    assert len(tasks) == 1
    assert tasks[0] == {
        "attributes": {
            "cached_task": {
                "digest": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                "name": "cache-foo",
                "type": "cached-task.v2",
            }
        },
        "description": "description",
        "label": "cached-task",
        "optimization": {
            "index-search": [
                "test-domain.cache.level-3.cached-task.v2.cache-foo.hash.ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                "test-domain.cache.level-2.cached-task.v2.cache-foo.hash.ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                "test-domain.cache.level-1.cached-task.v2.cache-foo.hash.ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            ]
        },
        "routes": [
            "index.test-domain.cache.level-1.cached-task.v2.cache-foo.hash.ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            "index.test-domain.cache.level-1.cached-task.v2.cache-foo.latest",
            "index.test-domain.cache.level-1.cached-task.v2.cache-foo.pushdate.1970.01.01.19700101000000",
        ],
    }


def assert_cache_with_dependency(tasks):
    handle_exception(tasks)
    assert len(tasks) == 2
    assert tasks[1] == {
        "attributes": {
            "cached_task": {
                "digest": "db201e53944fccbb16736c8153a14de39748c0d290de84bd976c11ddcc413089",
                "name": "cache-foo",
                "type": "cached-task.v2",
            }
        },
        "dependencies": {"edge": "dep-cached"},
        "description": "description",
        "label": "cached-task",
        "optimization": {
            "index-search": [
                "test-domain.cache.level-3.cached-task.v2.cache-foo.hash.db201e53944fccbb16736c8153a14de39748c0d290de84bd976c11ddcc413089",
                "test-domain.cache.level-2.cached-task.v2.cache-foo.hash.db201e53944fccbb16736c8153a14de39748c0d290de84bd976c11ddcc413089",
                "test-domain.cache.level-1.cached-task.v2.cache-foo.hash.db201e53944fccbb16736c8153a14de39748c0d290de84bd976c11ddcc413089",
            ]
        },
        "routes": [
            "index.test-domain.cache.level-1.cached-task.v2.cache-foo.hash.db201e53944fccbb16736c8153a14de39748c0d290de84bd976c11ddcc413089",
            "index.test-domain.cache.level-1.cached-task.v2.cache-foo.latest",
            "index.test-domain.cache.level-1.cached-task.v2.cache-foo.pushdate.1970.01.01.19700101000000",
        ],
    }

    # The digest should not be the same as above, as it takes the dependency digest into account.
    digest_0 = tasks[0]["attributes"]["cached_task"]["digest"]
    digest_1 = tasks[1]["attributes"]["cached_task"]["digest"]
    assert digest_0 != digest_1


def assert_cache_with_non_cached_dependency(e):
    handle_exception(e, exc=Exception)


def assert_chain_of_trust_influences_digest(tasks):
    assert len(tasks) == 3
    # The first two tasks are chain-of-trust unspecified, and chain-of-trust: False
    # which should result in the same digest.
    digest_0 = tasks[0]["attributes"]["cached_task"]["digest"]
    digest_1 = tasks[1]["attributes"]["cached_task"]["digest"]
    assert digest_0 == digest_1

    # The third task is chain-of-trust: True, and should have a different digest
    digest_2 = tasks[2]["attributes"]["cached_task"]["digest"]
    assert digest_0 != digest_2


@pytest.mark.parametrize(
    "tasks, kind_config, deps",
    (
        pytest.param(
            # tasks
            [{}],
            # kind config
            {},
            # kind deps
            None,
            id="no_cache",
        ),
        pytest.param(
            # tasks
            [
                {
                    "cache": {
                        "type": "cached-task.v2",
                        "name": "cache-foo",
                        "digest-data": ["abc"],
                    }
                }
            ],
            # kind config
            {},
            # kind deps
            None,
            id="cache_basic",
        ),
        pytest.param(
            # tasks
            [
                # This task has same digest-data, and no dependencies.
                {
                    "cache": {
                        "type": "cached-task.v2",
                        "name": "cache-foo",
                        "digest-data": ["abc"],
                    }
                },
                # This task has same digest-data, but a dependency on a cached task.
                {
                    "cache": {
                        "type": "cached-task.v2",
                        "name": "cache-foo",
                        "digest-data": ["abc"],
                    },
                    "dependencies": {"edge": "dep-cached"},
                },
            ],
            # kind config
            {},
            # kind deps
            {
                "dep-cached": make_task(
                    "dep-cached",
                    attributes={
                        "cached_task": {
                            "type": "cached-dep.v2",
                            "name": "cache-dep",
                            "digest": base64.b64encode(b"def").decode("utf-8"),
                        }
                    },
                )
            },
            id="cache_with_dependency",
        ),
        pytest.param(
            # tasks
            [
                # This task depends on a non-cached task.
                {
                    "cache": {
                        "type": "cached-task.v2",
                        "name": "cache-foo",
                        "digest-data": ["abc"],
                    },
                    "dependencies": {"edge": "dep"},
                },
            ],
            # kind config
            {},
            # kind deps
            {"dep": make_task("dep")},
            id="cache_with_non_cached_dependency",
        ),
        pytest.param(
            # tasks
            [
                {
                    "cache": {
                        "type": "cached-task.v2",
                        "name": "cache-foo",
                        "digest-data": ["abc"],
                    },
                    # no explicit chain of trust configuration; should be the
                    # same as when it is set to False
                },
                {
                    "cache": {
                        "type": "cached-task.v2",
                        "name": "cache-foo",
                        "digest-data": ["abc"],
                    },
                    "worker": {
                        "chain-of-trust": False,
                    },
                },
                {
                    "cache": {
                        "type": "cached-task.v2",
                        "name": "cache-foo",
                        "digest-data": ["abc"],
                    },
                    "worker": {"chain-of-trust": True},
                },
            ],
            # kind config
            {},
            # kind deps
            {},
            id="chain_of_trust_influences_digest",
        ),
    ),
)
def test_transforms(
    request, make_transform_config, run_transform, tasks, kind_config, deps
):
    for task in tasks:
        task.setdefault("label", "cached-task")
        task.setdefault("description", "description")
        task.setdefault("attributes", {})

    config = make_transform_config(kind_config, deps)

    try:
        result = run_transform(cached_tasks.transforms, tasks, config)
    except Exception as e:
        result = e

    print("Dumping result:")
    pprint(result, indent=2)

    param_id = request.node.callspec.id
    assert_func = globals()[f"assert_{param_id}"]
    assert_func(result)
