# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os
import subprocess
from textwrap import dedent

import pytest

from taskgraph.util.vcs import get_repository, HgRepository, Repository

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

    # This is mostly for local dev
    # If gpg signing is on it will fail calculating the head ref
    subprocess.check_output(
        ["git", "config", "commit.gpgsign", "false"], cwd=repo_dir, env=env
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
    repo_dir = os.path.join(tmpdir.strpath, repo_type)
    os.mkdir(repo_dir)
    first_file_path = tmpdir.join(repo_type, "first_file")
    first_file_path.write("first piece of data")

    subprocess.check_output([repo_type, "init"], cwd=repo_dir)
    subprocess.check_output([repo_type, "add", first_file_path.strpath], cwd=repo_dir)

    return repo_dir


@pytest.fixture(params=("git", "hg"))
def repo(request, hg_repo, git_repo):
    if request.param == "hg":
        return get_repository(hg_repo)
    return get_repository(git_repo)


def test_get_repository(repo):
    r = get_repository(repo.path)
    assert isinstance(r, Repository)

    new_dir = os.path.join(repo.path, "new_dir")
    oldcwd = os.getcwd()
    try:
        os.mkdir(new_dir)
        os.chdir(new_dir)
        r = get_repository(new_dir)
        assert isinstance(r, Repository)
    finally:
        os.chdir(oldcwd)
        os.rmdir(new_dir)


def test_get_repository_type(repo):
    if isinstance(repo, HgRepository):
        assert repo.tool == "hg"
    else:
        assert repo.tool == "git"


def test_get_repository_type_failure(tmpdir):
    with pytest.raises(RuntimeError):
        get_repository(tmpdir.strpath)


def test_hgplain(monkeypatch, hg_repo):
    repo = get_repository(hg_repo)

    def fake_check_output(*args, **kwargs):
        return args, kwargs

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    _, kwargs = repo.run("log")
    assert "env" in kwargs
    assert kwargs["env"]["HGPLAIN"] == "1"


@pytest.mark.parametrize(
    "commit_message",
    (
        "commit message in… pure utf8",
        "commit message in... ascii",
    ),
)
def test_get_commit_message(repo, commit_message):
    some_file_path = os.path.join(repo.path, "some_file")
    with open(some_file_path, "w") as f:
        f.write("some data")

    repo.run("add", some_file_path)
    if repo.tool == "hg":
        repo.run("commit", "-l-", input=commit_message)
    else:
        repo.run("commit", "-F-", input=commit_message)

    # strip because git adds newlines
    assert repo.get_commit_message().strip() == commit_message


def test_calculate_head_ref(repo):
    if repo.tool == "hg":
        assert repo.head_ref == "c6ef323128f7ba6fd47147743e882d9fc6d72a4e"
    else:
        assert repo.head_ref == "c34844580592fcf4575b8f1174285b853b566d85"


def test_get_repo_path(repo):
    if repo.tool == "hg":
        with open(os.path.join(repo.path, ".hg/hgrc"), "w") as f:
            f.write(
                dedent(
                    """
                [paths]
                default = https://some/repo
                other = https://some.other/repo
                """
                )
            )
    else:
        repo.run("remote", "add", "origin", "https://some/repo")
        repo.run("remote", "add", "other", "https://some.other/repo")

    assert repo.get_url() == "https://some/repo"
    assert repo.get_url("other") == "https://some.other/repo"


def test_update(repo):
    bar = os.path.join(repo.path, "bar")
    with open(bar, "w") as fh:
        fh.write("bar")

    first_ref = repo.head_ref
    repo.run("add", bar)
    repo.run("commit", "-m", "Second commit")

    second_ref = repo.head_ref
    repo.update(first_ref)
    assert repo.head_ref == first_ref

    repo.update(second_ref)
    assert repo.head_ref == second_ref


def test_branch(repo):
    if repo.tool == "git":
        assert repo.branch != "test"
        repo.run("checkout", "-b", "test")
    else:
        assert repo.branch is None
        repo.run("bookmark", "test")

    assert repo.branch == "test"

    bar = os.path.join(repo.path, "bar")
    with open(bar, "w") as fh:
        fh.write("bar")

    repo.run("add", bar)
    repo.run("commit", "-m", "Second commit")
    assert repo.branch == "test"

    repo.update(repo.head_ref)
    assert repo.branch is None

    repo.update("test")
    assert repo.branch == "test"


def test_working_directory_clean(repo):
    assert repo.working_directory_clean()

    # untracked file
    bar = os.path.join(repo.path, "bar")
    with open(bar, "w") as fh:
        fh.write("bar")

    assert repo.working_directory_clean()
    assert not repo.working_directory_clean(untracked=True)
    repo.run("add", "bar")
    assert not repo.working_directory_clean()

    repo.run("commit", "-m", "Second commit")
    assert repo.working_directory_clean()

    # modified file
    with open(bar, "a") as fh:
        fh.write("bar2")
    assert not repo.working_directory_clean()

    if repo.tool == "git":
        repo.run("reset", "--hard", "HEAD")
    else:
        repo.run("revert", "-a")
    assert repo.working_directory_clean()

    # removed file
    repo.run("rm", bar)
    assert not repo.working_directory_clean()
