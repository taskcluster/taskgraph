# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os
import subprocess

import pytest

from taskgraph.util.vcs import (
    get_repository_type,
    calculate_head_rev,
    get_commit_message,
    get_repo_path,
)

_FORCE_COMMIT_DATE_TIME = "2019-11-04T10:03:58+00:00"


@pytest.fixture(scope="function")
def hg_repo(tmpdir, monkeypatch):
    # Set HGPLAIN to ensure local .hgrc configs don't cause test failures.
    monkeypatch.setenv("HGPLAIN", "1")
    repo_dir = _init_repo(tmpdir, "hg")
    with open(os.path.join(repo_dir, ".hg", "hgrc"), "a") as f:
        f.write(
            """[ui]
username = Integration Tests <integration@tests.test>
"""
        )

    # hg sometimes errors out with "nothing changed" even though the commit succeeded
    subprocess.call(
        ["hg", "commit", "-m", "First commit", "--date", _FORCE_COMMIT_DATE_TIME],
        cwd=repo_dir,
    )
    yield repo_dir


_GIT_DATE_ENV_VARS = ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")


@pytest.fixture(scope="function")
def git_repo(tmpdir):
    env = _build_env_with_git_date_env_vars(_FORCE_COMMIT_DATE_TIME)

    repo_dir = _init_repo(tmpdir, "git")

    subprocess.check_output(
        ["git", "config", "user.email", "integration@tests.test"], cwd=repo_dir, env=env
    )
    subprocess.check_output(
        ["git", "config", "user.name", "Integration Tests"], cwd=repo_dir, env=env
    )
    subprocess.check_output(
        ["git", "commit", "-m", "First commit"], cwd=repo_dir, env=env
    )

    yield repo_dir


def _build_env_with_git_date_env_vars(date_time_string):
    env = os.environ.copy()
    env.update({env_var: date_time_string for env_var in _GIT_DATE_ENV_VARS})
    return env


def _init_repo(tmpdir, repo_type):
    repo_dir = tmpdir.strpath
    first_file_path = tmpdir.join("first_file")
    first_file_path.write("first piece of data")

    subprocess.check_output([repo_type, "init"], cwd=repo_dir)
    subprocess.check_output([repo_type, "add", first_file_path.strpath], cwd=repo_dir)

    return repo_dir


def test_get_repository_type_hg(hg_repo):
    assert get_repository_type(hg_repo) == "hg"


def test_get_repository_type_git(git_repo):
    assert get_repository_type(git_repo) == "git"


def test_get_repository_type_failure(tmpdir):
    with pytest.raises(RuntimeError):
        get_repository_type(tmpdir.strpath)


@pytest.mark.parametrize(
    "repo_type, commit_message",
    (
        (
            "hg",
            "commit message in… pure utf8",
        ),
        (
            "hg",
            "commit message in... ascii",
        ),
    ),
)
def test_get_commit_message_hg(hg_repo, repo_type, commit_message):
    _test_get_commit_message(
        hg_repo, repo_type, commit_message, expected_result=commit_message
    )


@pytest.mark.parametrize(
    "repo_type, commit_message, expected_result",
    (
        (
            "git",
            "commit message in… pure utf8",
            "commit message in… pure utf8\n\n",
        ),
        (
            "git",
            "commit message in... ascii",
            "commit message in... ascii\n\n",
        ),
    ),
)
def test_get_commit_message_git(git_repo, repo_type, commit_message, expected_result):
    _test_get_commit_message(git_repo, repo_type, commit_message, expected_result)


def _test_get_commit_message(repo_dir, repo_type, commit_message, expected_result):
    some_file_path = os.path.join(repo_dir, "some_file")
    with open(some_file_path, "w") as f:
        f.write("some data")

    subprocess.check_output([repo_type, "add", some_file_path], cwd=repo_dir)
    # hg sometimes errors out with "nothing changed" even though the commit succeeded
    subprocess.call([repo_type, "commit", "-m", commit_message], cwd=repo_dir)

    assert get_commit_message(repo_type, repo_dir) == expected_result


def test_get_commit_message_unsupported_repo():
    with pytest.raises(RuntimeError):
        get_commit_message("svn", "/some/repo/dir")


def test_calculate_head_rev_hg(hg_repo):
    # Similarly to git (below), hg hashes can be forecast.
    assert (
        calculate_head_rev("hg", hg_repo) == "c6ef323128f7ba6fd47147743e882d9fc6d72a4e"
    )


def test_calculate_head_rev_git(git_repo):
    # Git hashes are predictible if you set:
    #  * the date/time of the commit (and it's timezone, here UTC)
    #  * the hash of the parent commit (here, there's none)
    #  * the hash of the files stored on disk (here, it's always the same file)
    # https://gist.github.com/masak/2415865
    assert (
        calculate_head_rev("git", git_repo)
        == "c34844580592fcf4575b8f1174285b853b566d85"
    )


def test_get_repo_path_hg(hg_repo):
    with open(os.path.join(hg_repo, ".hg/hgrc"), "w") as f:
        f.write(
            """
[paths]
default = https://some.hg/repo
"""
        )
    assert get_repo_path("hg", hg_repo) == "https://some.hg/repo"


def test_get_repo_path_git(git_repo):
    subprocess.check_output(
        ["git", "remote", "add", "origin", "https://some.git/repo"], cwd=git_repo
    )
    assert get_repo_path("git", git_repo) == "https://some.git/repo"
