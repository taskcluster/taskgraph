from types import FunctionType

import pytest
from mozilla_repo_urls import InvalidRepoUrlError

from taskgraph.actions import registry
from test import does_not_raise


def test_action(*args, **kwargs):
    pass


def assert_basic(action):
    assert action.order == 10000
    assert action.permission == "generic"
    assert action.cb_name == "test-action"
    assert isinstance(action.action_builder, FunctionType)


def assert_permission(action):
    assert action.permission == "sensitive"


@pytest.mark.parametrize(
    "kwargs",
    (
        pytest.param({}, id="basic"),
        pytest.param({"permission": "sensitive"}, id="permission"),
    ),
)
def test_register_callback_action(request, monkeypatch, kwargs):
    actions = []
    callbacks = {}
    monkeypatch.setattr(registry, "actions", actions)
    monkeypatch.setattr(registry, "callbacks", callbacks)

    kwargs.setdefault("name", "test-action")
    kwargs.setdefault("title", "Test Action")
    kwargs.setdefault("symbol", "ta")
    kwargs.setdefault("description", "Used for a test")

    cb = registry.register_callback_action(**kwargs)(test_action)
    assert cb == test_action
    assert len(actions) == 1

    param_id = request.node.callspec.id
    assert_func = globals()[f"assert_{param_id}"]
    assert_func(actions[0])


@pytest.mark.parametrize(
    "callback, parameters, current_scopes, expectation",
    (
        ("non-existing-action", {}, [], pytest.raises(ValueError)),
        (
            "retrigger",
            {
                "base_repository": "https://some.git.repo",
                "head_repository": "https://some.git.repo",
            },
            [],
            pytest.raises(InvalidRepoUrlError),
        ),
        (
            "retrigger",
            {
                "base_repository": "https://hg.mozilla.org/mozilla-unified",
                "head_repository": "https://hg.mozilla.org/try",
            },
            ["unrelated:scope"],
            pytest.raises(ValueError),
        ),
        (
            "retrigger",
            {
                "base_repository": "https://hg.mozilla.org/mozilla-unified",
                "head_repository": "https://hg.mozilla.org/try",
            },
            ["assume:repo:hg.mozilla.org/try:action:generic"],
            does_not_raise(),
        ),
        (
            "retrigger",
            {
                "base_repository": "https://hg.mozilla.org/mozilla-central",
                "head_repository": "https://hg.mozilla.org/mozilla-central",
            },
            ["assume:repo:hg.mozilla.org/mozilla-central:action:generic"],
            does_not_raise(),
        ),
        (
            "retrigger",
            {
                "base_repository": "https://github.com/taskcluster/taskgraph",
                "head_repository": "https://github.com/taskcluster/taskgraph",
            },
            ["assume:repo:github.com/taskcluster/taskgraph:action:generic"],
            does_not_raise(),
        ),
        (
            "retrigger",
            {
                "base_repository": "git@github.com:mozilla-mobile/firefox-android.git",
                "head_repository": "git@github.com:mozilla-mobile/firefox-android.git",
            },
            ["assume:repo:github.com/mozilla-mobile/firefox-android:action:generic"],
            does_not_raise(),
        ),
        (
            "retrigger",
            {
                "base_repository": "git@github.com:mozilla-mobile/firefox-android.git",
                "head_repository": "git@github.com:someuser/firefox-android.git",
            },
            ["assume:repo:github.com/mozilla-mobile/firefox-android:pr-action:generic"],
            does_not_raise(),
        ),
    ),
)
def test_sanity_check_task_scope(
    monkeypatch, callback, parameters, current_scopes, expectation
):
    monkeypatch.setattr(
        registry.taskcluster, "get_current_scopes", lambda: current_scopes
    )
    with expectation:
        registry.sanity_check_task_scope(callback, parameters, graph_config={})
