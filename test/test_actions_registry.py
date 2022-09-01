from test import does_not_raise

import pytest
from mozilla_repo_urls import InvalidRepoUrlError

from taskgraph.actions import registry


@pytest.mark.parametrize(
    "callback, parameters, current_scopes, expectation",
    (
        ("non-existing-action", {}, [], pytest.raises(ValueError)),
        (
            "retrigger",
            {"head_repository": "https://some.git.repo"},
            [],
            pytest.raises(InvalidRepoUrlError),
        ),
        (
            "retrigger",
            {"head_repository": "https://hg.mozilla.org/try"},
            ["unrelated:scope"],
            pytest.raises(ValueError),
        ),
        (
            "retrigger",
            {"head_repository": "https://hg.mozilla.org/mozilla-central"},
            ["assume:repo:hg.mozilla.org/mozilla-central:action:generic"],
            does_not_raise(),
        ),
        (
            "retrigger",
            {"head_repository": "https://github.com/taskcluster/taskgraph"},
            ["assume:repo:github.com/taskcluster/taskgraph:action:generic"],
            does_not_raise(),
        ),
        (
            "retrigger",
            {"head_repository": "git@github.com:mozilla-mobile/firefox-android.git"},
            ["assume:repo:github.com/mozilla-mobile/firefox-android:action:generic"],
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
