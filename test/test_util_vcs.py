# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os
import shutil
import subprocess
from textwrap import dedent

import pytest

from taskgraph.util.vcs import HgRepository, Repository, get_repository

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


def _create_remote_repo(tmpdir, repo, remote_name, remote_path):
    if repo.tool == "hg":
        repo.run("phase", "--public", ".")

    shutil.copytree(repo.path, str(tmpdir / remote_path))

    if repo.tool == "git":
        repo.run("remote", "add", remote_name, f"{tmpdir}/{remote_path}")
        repo.run("fetch", remote_name)
        repo.run("branch", "--set-upstream-to", f"{remote_name}/master")
    if repo.tool == "hg":
        with open(os.path.join(repo.path, ".hg/hgrc"), "a") as f:
            f.write(f"[paths]\n{remote_name} = {tmpdir}/{remote_path}\n")


@pytest.fixture
def repo_with_remote(tmpdir, repo):
    remote_name = "upstream"
    _create_remote_repo(tmpdir, repo, remote_name, "remote_repo")
    return repo, remote_name


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


def test_calculate_head_rev(repo):
    if repo.tool == "hg":
        assert repo.head_rev == "c6ef323128f7ba6fd47147743e882d9fc6d72a4e"
    else:
        assert repo.head_rev == "c34844580592fcf4575b8f1174285b853b566d85"


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

    first_rev = repo.head_rev
    repo.run("add", bar)
    repo.run("commit", "-m", "Second commit")

    second_rev = repo.head_rev
    repo.update(first_rev)
    assert repo.head_rev == first_rev

    repo.update(second_rev)
    assert repo.head_rev == second_rev


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

    repo.update(repo.head_rev)
    assert repo.branch is None

    repo.update("test")
    assert repo.branch == "test"


def test_remote_name_no_remote(repo):
    with pytest.raises(RuntimeError):
        repo.remote_name


def test_remote_name(repo_with_remote):
    repo, remote_name = repo_with_remote
    assert repo.remote_name == remote_name

    if repo.tool == "git":
        repo.run("branch", "--unset-upstream")
        assert repo.remote_name == remote_name


def test_all_remote_names(tmpdir, repo_with_remote):
    repo, remote_name = repo_with_remote
    assert repo.all_remote_names == [remote_name]
    _create_remote_repo(tmpdir, repo, "upstream2", "remote_path2")
    assert repo.all_remote_names == [remote_name, "upstream2"]


def test_remote_name_many_remotes(tmpdir, repo_with_remote):
    repo, _ = repo_with_remote
    _create_remote_repo(tmpdir, repo, "upstream2", "remote_path2")

    if repo.tool == "git":
        assert repo.remote_name == "upstream2"  # Branch is set to an upstream one
        repo.run("branch", "--unset-upstream")

    assert repo.remote_name == "upstream"


def test_remote_name_default_and_origin(tmpdir, repo_with_remote):
    repo, _ = repo_with_remote
    remote_name = "origin" if repo.tool == "git" else "default"
    _create_remote_repo(tmpdir, repo, remote_name, "remote_path2")

    if repo.tool == "git":
        repo.run("branch", "--unset-upstream")

    assert repo.remote_name == remote_name


def test_default_branch_guess(repo):
    if repo.tool == "git":
        assert repo.default_branch == "refs/heads/master"
    else:
        assert repo.default_branch == "default"


def test_default_branch_remote_query(repo_with_remote):
    repo, _ = repo_with_remote
    if repo.tool == "git":
        assert repo.default_branch == "upstream/master"
    else:
        assert repo.default_branch == "default"


def test_default_branch_cloned_metadata(tmpdir, repo):
    if repo.tool == "git":
        clone_repo_path = tmpdir / "cloned_repo"
        command = ("git", "clone", repo.path, clone_repo_path)
        subprocess.check_output(command, cwd=tmpdir)
        cloned_repo = get_repository(clone_repo_path)
        assert cloned_repo.default_branch == "origin/master"


def assert_files(actual, expected):
    assert set(map(os.path.basename, actual)) == set(expected)


def test_get_changed_files_no_changes(repo):
    assert_files(repo.get_changed_files("A", "all"), [])
    assert_files(repo.get_changed_files("M", "all"), [])
    assert_files(repo.get_changed_files("D", "all"), [])
    assert_files(repo.get_changed_files("AMD", "all"), [])


def test_get_changed_files_one_modified_file(repo):
    with open(os.path.join(repo.path, "first_file"), "w") as f:
        f.write("some new data")

    assert_files(repo.get_changed_files("A", "all"), [])
    assert_files(repo.get_changed_files("M", "all"), ["first_file"])
    assert_files(repo.get_changed_files("D", "all"), [])

    if repo.tool == "git":
        assert_files(repo.get_changed_files("M", "staged"), [])
        assert_files(repo.get_changed_files("M", "unstaged"), ["first_file"])
    repo.run("add", ".")
    if repo.tool == "git":
        assert_files(repo.get_changed_files("M", "staged"), ["first_file"])
        assert_files(repo.get_changed_files("M", "unstaged"), [])

    repo.run("commit", "-m", "Modify first_file")
    assert_files(repo.get_changed_files("AMD", "all"), [])
    revision = "HEAD" if repo.tool == "git" else "."
    assert_files(repo.get_changed_files("M", "all", revision), ["first_file"])


def test_get_changed_files_one_deleted_file(repo):
    os.remove(os.path.join(repo.path, "first_file"))

    assert_files(repo.get_changed_files("A", "all"), [])
    assert_files(repo.get_changed_files("M", "all"), [])
    assert_files(repo.get_changed_files("D", "all"), ["first_file"])

    repo.run("rm", "first_file")
    repo.run("commit", "-m", "Delete first_file")
    assert_files(repo.get_changed_files("AMD", "all"), [])
    revision = "HEAD" if repo.tool == "git" else "."
    assert_files(repo.get_changed_files("D", "all", revision), ["first_file"])


def test_get_changed_files_one_added_file(repo):
    with open(os.path.join(repo.path, "second_file"), "w") as f:
        f.write("some data for the second file")

    assert_files(repo.get_changed_files("A", "all"), [])  # File is still untracked
    assert_files(repo.get_changed_files("M", "all"), [])
    assert_files(repo.get_changed_files("D", "all"), [])

    repo.run("add", ".")
    assert_files(repo.get_changed_files("A", "all"), ["second_file"])

    repo.run("commit", "-m", "Add second_file")
    assert_files(repo.get_changed_files("AMD", "all"), [])
    revision = "HEAD" if repo.tool == "git" else "."
    assert_files(repo.get_changed_files("A", "all", revision), ["second_file"])


def test_get_changed_files_two_revisions(repo):
    with open(os.path.join(repo.path, "second_file"), "w") as f:
        f.write("some data for the second file")
    repo.run("add", "second_file")
    repo.run("commit", "-m", "Add second_file")

    os.remove(os.path.join(repo.path, "first_file"))
    with open(os.path.join(repo.path, "second_file"), "w") as f:
        f.write("new data for second file")
    with open(os.path.join(repo.path, "third_file"), "w") as f:
        f.write("third type of data")

    repo.run("rm", "first_file")
    repo.run("add", ".")
    repo.run("commit", "-m", "Remove first_file; modify second_file; add third_file")

    last_revision = "HEAD" if repo.tool == "git" else "."
    assert_files(repo.get_changed_files("A", "all", last_revision), ["third_file"])
    assert_files(repo.get_changed_files("M", "all", last_revision), ["second_file"])
    assert_files(repo.get_changed_files("D", "all", last_revision), ["first_file"])
    assert_files(
        repo.get_changed_files("AMD", "all", last_revision),
        ["first_file", "second_file", "third_file"],
    )

    one_before_last_revision = "HEAD~1" if repo.tool == "git" else ".^"
    assert_files(
        repo.get_changed_files("A", "all", one_before_last_revision), ["second_file"]
    )
    assert_files(repo.get_changed_files("M", "all", one_before_last_revision), [])
    assert_files(repo.get_changed_files("D", "all", one_before_last_revision), [])
    assert_files(
        repo.get_changed_files("AMD", "all", one_before_last_revision), ["second_file"]
    )

    two_before_last_revision = "HEAD~2" if repo.tool == "git" else ".^^"
    assert_files(
        repo.get_changed_files("A", "all", last_revision, two_before_last_revision),
        ["third_file", "second_file"],
    )
    assert_files(
        repo.get_changed_files("M", "all", last_revision, two_before_last_revision),
        ["second_file"],
    )
    assert_files(
        repo.get_changed_files("D", "all", last_revision, two_before_last_revision),
        ["first_file"],
    )
    assert_files(
        repo.get_changed_files("AMD", "all", last_revision, two_before_last_revision),
        ["first_file", "second_file", "third_file"],
    )


@pytest.fixture
def repo_with_upstream(tmpdir, repo):
    with open(os.path.join(repo.path, "second_file"), "w") as f:
        f.write("some data for the second file")

    repo.run("add", ".")
    repo.run("commit", "-m", "Add second_file")

    if repo.tool == "hg":
        repo.run("phase", "--public", ".")

    shutil.copytree(repo.path, str(tmpdir / "remoterepo"))
    upstream_location = None

    if repo.tool == "git":
        upstream_location = "upstream/master"
        repo.run("remote", "add", "upstream", f"{tmpdir}/remoterepo")
        repo.run("fetch", "upstream")
        repo.run("branch", "--set-upstream-to", upstream_location)
    if repo.tool == "hg":
        upstream_location = f"{tmpdir}/remoterepo"
        with open(os.path.join(repo.path, ".hg/hgrc"), "w") as f:
            f.write(f"[paths]\ndefault = {upstream_location}")

    return repo, upstream_location


def test_workdir_outgoing(repo_with_upstream):
    repo, upstream_location = repo_with_upstream

    os.remove(os.path.join(repo.path, "first_file"))
    with open(os.path.join(repo.path, "second_file"), "w") as f:
        f.write("new data for second file")
    with open(os.path.join(repo.path, "third_file"), "w") as f:
        f.write("third type of data")

    assert_files(repo.get_outgoing_files("AMD"), [])
    assert_files(repo.get_outgoing_files("AMD", upstream_location), [])

    repo.run("rm", "first_file")
    repo.run("add", ".")
    assert_files(repo.get_outgoing_files("AMD"), [])
    assert_files(repo.get_outgoing_files("AMD", upstream_location), [])

    repo.run("commit", "-m", "Remove first_file; modify second_file; add third_file")
    assert_files(repo.get_outgoing_files("A"), ["third_file"])
    assert_files(repo.get_outgoing_files("M"), ["second_file"])
    assert_files(repo.get_outgoing_files("D"), ["first_file"])
    assert_files(repo.get_outgoing_files("A", upstream_location), ["third_file"])
    assert_files(repo.get_outgoing_files("M", upstream_location), ["second_file"])
    assert_files(repo.get_outgoing_files("D", upstream_location), ["first_file"])

    with open(os.path.join(repo.path, "fourth_file"), "w") as f:
        f.write("breaking the fourth wall")
    repo.run("add", ".")
    repo.run("commit", "-m", "Add fourth file")

    assert_files(repo.get_outgoing_files("A"), ["fourth_file", "third_file"])
    assert_files(repo.get_outgoing_files("M"), ["second_file"])
    assert_files(repo.get_outgoing_files("D"), ["first_file"])
    assert_files(
        repo.get_outgoing_files("A", upstream_location), ["fourth_file", "third_file"]
    )
    assert_files(repo.get_outgoing_files("M", upstream_location), ["second_file"])
    assert_files(repo.get_outgoing_files("D", upstream_location), ["first_file"])


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


def test_find_latest_common_revision(repo_with_remote):
    repo, remote_name = repo_with_remote

    expected_latest_common_revision = repo.head_rev

    with open(os.path.join(repo.path, "some_file"), "w") as f:
        f.write("some content")

    repo.run("add", ".")
    repo.run("commit", "-m", "Add new revision")

    assert repo.head_rev != expected_latest_common_revision

    if repo.tool == "git":
        base_ref = f"{remote_name}/{repo.branch}"
        assert (
            repo.find_latest_common_revision(base_ref, repo.head_rev)
            == expected_latest_common_revision
        )
    else:
        # hg doesn't have the concept of remote branches
        assert (
            repo.find_latest_common_revision(
                expected_latest_common_revision, repo.head_rev
            )
            == expected_latest_common_revision
        )


def test_does_revision_exist_locally(repo):
    first_revision = repo.head_rev

    with open(os.path.join(repo.path, "some_file"), "w") as f:
        f.write("some content")

    repo.run("add", ".")
    repo.run("commit", "-m", "Add new revision")

    last_revision = repo.head_rev
    assert repo.does_revision_exist_locally(first_revision)
    assert repo.does_revision_exist_locally(last_revision)
    assert not repo.does_revision_exist_locally("deadbeef")
