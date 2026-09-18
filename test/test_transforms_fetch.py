"""
Tests for the 'fetch' transforms.
"""

from copy import deepcopy
from pprint import pprint

import pytest

from taskgraph.transforms import fetch

TASK_DEFAULTS = {
    "description": "fake description",
    "name": "fake-task-name",
}


def assert_static_url(task):
    assert task["run"]["command"] == [
        "fetch-content",
        "static-url",
        "--sha256",
        "abcdef",
        "--size",
        "123",
        "-H",
        "User-Agent:Mozilla",
        "https://example.com/resource",
        "/builds/worker/artifacts/resource",
    ]
    assert task["attributes"]["fetch-artifact"] == "public/resource"


GIT_REVISION = "0123456789abcdef0123456789abcdef01234567"


def expected_git_command(*extra_args):
    return [
        "fetch-content",
        "git-checkout-archive",
        "--path-prefix",
        "repo",
        "https://example.com/repo",
        GIT_REVISION,
        "/builds/worker/artifacts/repo.tar.zst",
        *extra_args,
    ]


def assert_git(task):
    assert task["run"]["command"] == expected_git_command()


def assert_git_fetch_mode_clone(task):
    assert task["run"]["command"] == expected_git_command()


def assert_git_fetch_mode_init_and_fetch(task):
    assert task["run"]["command"] == expected_git_command(
        "--fetch-mode", "init_and_fetch"
    )


@pytest.mark.parametrize(
    "task_input",
    (
        pytest.param(
            {
                "fetch": {
                    "type": "static-url",
                    "url": "https://example.com/resource",
                    "sha256": "abcdef",
                    "size": 123,
                    "headers": {
                        "User-Agent": "Mozilla",
                    },
                },
            },
            id="static-url",
        ),
        pytest.param(
            {
                "fetch": {
                    "type": "git",
                    "repo": "https://example.com/repo",
                    "revision": GIT_REVISION,
                },
            },
            id="git",
        ),
        pytest.param(
            {
                "fetch": {
                    "type": "git",
                    "repo": "https://example.com/repo",
                    "revision": GIT_REVISION,
                    "fetch-mode": "clone",
                },
            },
            id="git-fetch-mode-clone",
        ),
        pytest.param(
            {
                "fetch": {
                    "type": "git",
                    "repo": "https://example.com/repo",
                    "revision": GIT_REVISION,
                    "fetch-mode": "init_and_fetch",
                },
            },
            id="git-fetch-mode-init-and-fetch",
        ),
    ),
)
def test_transforms(request, run_transform, task_input):
    task = deepcopy(TASK_DEFAULTS)
    task.update(task_input)

    task = run_transform(fetch.transforms, task)[0]
    print("Dumping task:")
    pprint(task, indent=2)

    # Call the assertion function for the given test.
    param_id = request.node.callspec.id
    assertion_func = globals()[f"assert_{param_id.replace('-', '_')}"]
    assertion_func(task)


@pytest.mark.parametrize(
    "fetch_mode,expected_extra_digest",
    (
        pytest.param(None, [], id="unset"),
        pytest.param("clone", [], id="clone"),
        pytest.param(
            "init_and_fetch", ["fetch-mode=init_and_fetch"], id="init-and-fetch"
        ),
    ),
)
def test_git_fetch_mode_digest_data(fetch_mode, expected_extra_digest):
    fetch_config = {
        "type": "git",
        "repo": "https://example.com/repo",
        "revision": GIT_REVISION,
    }
    if fetch_mode:
        fetch_config["fetch-mode"] = fetch_mode

    result = fetch.create_git_fetch_task(None, "fake-task-name", fetch_config)

    assert result["digest_data"] == [
        GIT_REVISION,
        "repo",
        "repo.tar.zst",
        *expected_extra_digest,
    ]
