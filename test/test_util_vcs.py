# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import shutil
import subprocess
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

import pytest
import requests

from taskgraph.util.vcs import (
    GitRepository,
    HgRepository,
    Repository,
    _GitHubCompareError,
    get_repository,
)

from .conftest import nowin


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


def test_all_remote_names(tmpdir, create_remote_repo, repo_with_remote):
    repo, remote_name = repo_with_remote
    assert repo.all_remote_names == [remote_name]
    create_remote_repo(tmpdir, repo, "upstream2", "remote_path2")
    assert repo.all_remote_names == [remote_name, "upstream2"]


def test_remote_name_many_remotes(tmpdir, create_remote_repo, repo_with_remote):
    repo, _ = repo_with_remote
    create_remote_repo(tmpdir, repo, "upstream2", "remote_path2")

    if repo.tool == "git":
        assert repo.remote_name == "upstream2"  # Branch is set to an upstream one
        repo.run("branch", "--unset-upstream")

    assert repo.remote_name == "upstream"


def test_remote_name_default_and_origin(tmpdir, create_remote_repo, repo_with_remote):
    repo, _ = repo_with_remote
    remote_name = "origin" if repo.tool == "git" else "default"
    create_remote_repo(tmpdir, repo, remote_name, "remote_path2")

    if repo.tool == "git":
        repo.run("branch", "--unset-upstream")

    assert repo.remote_name == remote_name


def test_default_branch_guess(default_git_branch, repo):
    if repo.tool == "git":
        assert repo.default_branch == f"refs/heads/{default_git_branch}"
    else:
        assert repo.default_branch == "default"


def test_default_branch_remote_query(default_git_branch, repo_with_remote):
    repo, _ = repo_with_remote
    if repo.tool == "git":
        assert repo.default_branch == f"upstream/{default_git_branch}"
    else:
        assert repo.default_branch == "default"


def test_default_branch_cloned_metadata(tmpdir, default_git_branch, repo):
    if repo.tool == "git":
        clone_repo_path = tmpdir / "cloned_repo"
        command = ("git", "clone", repo.path, clone_repo_path)
        subprocess.check_output(command, cwd=tmpdir)
        cloned_repo = get_repository(clone_repo_path)
        assert cloned_repo.default_branch == f"origin/{default_git_branch}"


def assert_files(actual, expected):
    assert set(actual) == set(expected)


@nowin
def test_get_tracked_files(repo):
    assert_files(repo.get_tracked_files(), ["first_file"])

    second_file = Path(repo.path) / "subdir" / "second_file"
    second_file.parent.mkdir()
    second_file.write_text("foo")
    assert_files(repo.get_tracked_files(), ["first_file"])

    repo.run("add", str(second_file))
    assert_files(repo.get_tracked_files(), ["first_file"])

    repo.run("commit", "-m", "Add second file")
    rev = ".~1" if repo.tool == "hg" else "HEAD~1"
    assert_files(repo.get_tracked_files(), ["first_file", "subdir/second_file"])
    assert_files(repo.get_tracked_files("subdir"), ["subdir/second_file"])
    assert_files(repo.get_tracked_files(rev=rev), ["first_file"])

    if repo.tool == "git":
        assert_files(repo.get_tracked_files("subdir", rev=rev), [])
    elif repo.tool == "hg":
        with pytest.raises(subprocess.CalledProcessError):
            repo.get_tracked_files("subdir", rev=rev)


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
    with open(os.path.join(repo.path, "fourth_file"), "w") as f:
        f.write("some data for the fourth file")
    repo.run("add", "second_file", "fourth_file")
    repo.run("commit", "-m", "Add second_file and fourth_file")

    os.remove(os.path.join(repo.path, "first_file"))
    with open(os.path.join(repo.path, "second_file"), "w") as f:
        f.write("new data for second file")
    with open(os.path.join(repo.path, "third_file"), "w") as f:
        f.write("third type of data")
    os.rename(
        os.path.join(repo.path, "fourth_file"),
        os.path.join(repo.path, "fourth_file_new"),
    )

    repo.run("rm", "first_file", "fourth_file")
    repo.run("add", ".")
    repo.run(
        "commit",
        "-m",
        "Remove first_file; modify second_file; add third_file, rename fourth_file",
    )

    last_revision = "HEAD" if repo.tool == "git" else "."
    assert_files(
        repo.get_changed_files("A", "all", last_revision),
        ["third_file", "fourth_file_new"],
    )
    assert_files(repo.get_changed_files("M", "all", last_revision), ["second_file"])
    assert_files(
        repo.get_changed_files("D", "all", last_revision), ["first_file", "fourth_file"]
    )
    assert_files(
        repo.get_changed_files("AMD", "all", last_revision),
        ["first_file", "second_file", "third_file", "fourth_file_new", "fourth_file"],
    )

    one_before_last_revision = "HEAD~1" if repo.tool == "git" else ".^"
    assert_files(
        repo.get_changed_files("A", "all", one_before_last_revision),
        ["second_file", "fourth_file"],
    )
    assert_files(repo.get_changed_files("M", "all", one_before_last_revision), [])
    assert_files(repo.get_changed_files("D", "all", one_before_last_revision), [])
    assert_files(
        repo.get_changed_files("AMD", "all", one_before_last_revision),
        ["second_file", "fourth_file"],
    )

    two_before_last_revision = "HEAD~2" if repo.tool == "git" else ".^^"
    assert_files(
        repo.get_changed_files("A", "all", last_revision, two_before_last_revision),
        ["third_file", "second_file", "fourth_file", "fourth_file_new"],
    )
    assert_files(
        repo.get_changed_files("M", "all", last_revision, two_before_last_revision),
        ["second_file"],
    )
    assert_files(
        repo.get_changed_files("D", "all", last_revision, two_before_last_revision),
        ["first_file", "fourth_file"],
    )
    assert_files(
        repo.get_changed_files("AMD", "all", last_revision, two_before_last_revision),
        ["first_file", "second_file", "third_file", "fourth_file", "fourth_file_new"],
    )


@nowin
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

        # Test no common ancestors
        repo.run("checkout", "--orphan", "new_branch")
        repo.run("add", ".")
        repo.run("commit", "-m", "Add another new revision")
        base_ref = f"{remote_name}/{repo.branch}"
        assert (
            repo.find_latest_common_revision(base_ref, repo.head_rev)
            == Repository.NULL_REVISION
        )
    elif repo.tool == "hg":
        # hg doesn't have the concept of remote branches
        assert (
            repo.find_latest_common_revision(
                expected_latest_common_revision, repo.head_rev
            )
            == expected_latest_common_revision
        )

        # Test no common ancestors
        repo.run("update", Repository.NULL_REVISION)
        with open(os.path.join(repo.path, "some_file"), "w") as f:
            f.write("some content")

        repo.run("add", ".")
        repo.run("commit", "-m", "Add another new revision")
        assert (
            repo.find_latest_common_revision(
                repo.head_rev, expected_latest_common_revision
            )
            == Repository.NULL_REVISION
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


def test_get_changed_files_shallow_clone(git_repo, tmp_path, default_git_branch):
    tmp_repo = Path(git_repo)

    # Add initial files to the existing repo (which already has first_file from fixture)
    (tmp_repo / "common.txt").write_text("common content")
    (tmp_repo / "file_to_modify.txt").write_text("original content")
    (tmp_repo / "file_to_delete.txt").write_text("will be deleted")
    subprocess.check_call(["git", "add", "."], cwd=tmp_repo)
    subprocess.check_call(["git", "commit", "-m", "Add test files"], cwd=tmp_repo)

    # Create feature branch and make changes
    subprocess.check_call(["git", "checkout", "-b", "feature"], cwd=tmp_repo)

    # On feature branch: modify file, add new file, delete file
    (tmp_repo / "file_to_modify.txt").write_text("modified in feature")
    (tmp_repo / "feature_only.txt").write_text("feature specific file")
    (tmp_repo / "file_to_delete.txt").unlink()
    subprocess.check_call(["git", "rm", "file_to_delete.txt"], cwd=tmp_repo)
    subprocess.check_call(["git", "add", "."], cwd=tmp_repo)
    subprocess.check_call(["git", "commit", "-m", "Feature changes"], cwd=tmp_repo)

    feature_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_repo, text=True
    ).strip()

    # Switch back to main and make different changes
    subprocess.check_call(["git", "checkout", default_git_branch], cwd=tmp_repo)

    # On main branch: different modifications
    (tmp_repo / "file_to_modify.txt").write_text("modified in main")
    (tmp_repo / "main_only.txt").write_text("main specific file")
    subprocess.check_call(["git", "add", "."], cwd=tmp_repo)
    subprocess.check_call(["git", "commit", "-m", "Main changes"], cwd=tmp_repo)

    main_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_repo, text=True
    ).strip()

    # Create a shallow clone with only the latest commit from each branch
    shallow_path = tmp_path / "shallow"
    subprocess.check_call(
        [
            "git",
            "clone",
            "--depth=1",
            "--no-single-branch",
            f"file://{tmp_repo}",
            str(shallow_path),
        ]
    )
    shallow_repo = get_repository(str(shallow_path))
    assert shallow_repo.is_shallow

    # Between main and feature:
    # - file_to_modify.txt was modified differently (M)
    # - file_to_delete.txt exists in main but not in feature (D)
    # - feature_only.txt exists in feature but not in main (A)
    # - main_only.txt exists in main but not in feature (D when comparing feature to main)
    changed_files = shallow_repo.get_changed_files(
        "AMD", "all", feature_commit, main_commit
    )
    assert "file_to_modify.txt" in changed_files  # Modified
    assert "file_to_delete.txt" in changed_files  # Deleted in feature
    assert "feature_only.txt" in changed_files  # Added in feature
    assert (
        "main_only.txt" in changed_files
    )  # Not in feature (shows as deleted from main's perspective)

    added = shallow_repo.get_changed_files("A", "all", feature_commit, main_commit)
    assert "feature_only.txt" in added
    assert "file_to_delete.txt" not in added

    deleted = shallow_repo.get_changed_files("D", "all", feature_commit, main_commit)
    assert "file_to_delete.txt" in deleted
    assert (
        "main_only.txt" in deleted
    )  # From feature's perspective, main_only.txt doesn't exist

    modified = shallow_repo.get_changed_files("M", "all", feature_commit, main_commit)
    assert "file_to_modify.txt" in modified


def test_get_changed_files_with_null_base_revision(repo):
    second_file = os.path.join(repo.path, "second_file")
    with open(second_file, "w") as f:
        f.write("second file content")

    repo.run("add", second_file)
    repo.run("commit", "-m", "Add second file")

    head_rev = repo.head_rev

    changed_files = repo.get_changed_files(
        "AMD", "all", rev=head_rev, base=Repository.NULL_REVISION
    )

    assert isinstance(changed_files, list)
    # When base is NULL_REVISION, we should get all files from the beginning
    # of history up to head_rev. This includes both the initial "first_file"
    # and the newly added "second_file".
    assert "first_file" in changed_files
    assert "second_file" in changed_files


def test_get_changed_files_with_null_base_revision_shallow_clone(
    git_repo, tmp_path, default_git_branch
):
    tmp_repo = Path(git_repo)

    (tmp_repo / "file1.txt").write_text("content 1")
    (tmp_repo / "file2.txt").write_text("content 2")
    subprocess.check_call(["git", "add", "."], cwd=tmp_repo)
    subprocess.check_call(["git", "commit", "-m", "Add files"], cwd=tmp_repo)

    commit_hash = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_repo, text=True
    ).strip()

    shallow_path = tmp_path / "shallow_null_test"
    subprocess.check_call(
        ["git", "clone", "--depth=1", f"file://{tmp_repo}", str(shallow_path)],
        cwd=tmp_path,
    )

    shallow_repo = get_repository(str(shallow_path))
    assert shallow_repo.is_shallow

    changed_files = shallow_repo.get_changed_files(
        "AMD", "all", rev=commit_hash, base=Repository.NULL_REVISION
    )

    assert "first_file" in changed_files
    assert "file1.txt" in changed_files
    assert "file2.txt" in changed_files


def test_get_note_git(git_repo, tmpdir):
    """get_note returns note content when present, None otherwise."""
    src_path = str(tmpdir.join("git-src"))
    dst_path = str(tmpdir.join("git-dst"))
    shutil.copytree(git_repo, src_path)
    shutil.copytree(git_repo, dst_path)
    repo = get_repository(dst_path)

    # No note yet on the remote
    assert repo.get_note("try-config", src_path) is None

    rev = repo.head_rev
    subprocess.check_call(
        ["git", "notes", "--ref=refs/notes/try-config", "add", "-m", "test note", rev],
        cwd=src_path,
    )

    assert repo.get_note("try-config", src_path) == "test note"
    assert repo.get_note("try-config", src_path, revision=rev) == "test note"
    assert repo.get_note("other", src_path) is None


PUSH_BRANCH = "topic"


def git(cwd, *args):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout.strip()


@pytest.fixture
def push_origin(tmp_path):
    """A repository whose `main` moved on after `topic` branched off.

    `old_tip` is an earlier tip of that branch, `previous` a rebuilt stack that
    a force push orphaned (still served by sha, as GitHub does), `merge_tip` a
    stack that merged `main` back in and `on_main` a branch pointing at the tip
    of `main`."""
    path = tmp_path / "origin"
    path.mkdir()
    git(path, "init", "-q")
    git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "uploadpack.allowAnySHA1InWant", "true")

    (path / "a.txt").write_bytes(b"a\n")
    (path / "b.txt").write_bytes(b"b\n")
    git(path, "add", ".")
    git(path, "commit", "-qm", "base1")
    (path / "a.txt").write_bytes(b"a2\n")
    git(path, "commit", "-qam", "base2")
    base = git(path, "rev-parse", "HEAD")
    (path / "m.txt").write_bytes(b"m\n")
    git(path, "add", ".")
    git(path, "commit", "-qm", "main3")
    main_rev = git(path, "rev-parse", "HEAD")
    git(path, "branch", "on_main", main_rev)

    git(path, "checkout", "-qb", "previous", base)
    (path / "p.txt").write_bytes(b"p\n")
    git(path, "add", ".")
    git(path, "commit", "-qm", "previous stack")
    previous = git(path, "rev-parse", "HEAD")

    git(path, "checkout", "-qb", PUSH_BRANCH, base)
    (path / "c.txt").write_bytes(b"c\n")
    git(path, "add", ".")
    git(path, "commit", "-qm", "stack1")
    old_tip = git(path, "rev-parse", "HEAD")
    (path / "b.txt").write_bytes(b"b\nd\n")
    git(path, "commit", "-qam", "stack2")
    head = git(path, "rev-parse", "HEAD")

    git(path, "checkout", "-qb", "merged", head)
    git(path, "merge", "-q", "-m", "merge main", "main")
    merge_tip = git(path, "rev-parse", "HEAD")
    git(path, "checkout", "-q", "main")
    git(path, "branch", "-qD", "previous")

    return SimpleNamespace(
        path=path,
        url=path.as_uri(),
        base=base,
        head=head,
        old_tip=old_tip,
        previous=previous,
        main_rev=main_rev,
        merge_tip=merge_tip,
    )


def shallow_checkout(tmp_path, origin, branch, head, base_rev=None):
    """The checkout `run-task` produces for a shallow clone when
    `<PREFIX>_BASE_REV` is `base_rev` (unset or the null revision when None)."""
    checkout = tmp_path / "checkout"
    git(
        tmp_path, "clone", "-q", "--depth=1", "--no-checkout", origin.url, str(checkout)
    )
    if base_rev:
        git(checkout, "fetch", "-q", "--depth=1", origin.url, base_rev)
    git(checkout, "fetch", "-q", "--depth=1", origin.url, head)
    git(checkout, "checkout", "-qf", "-B", branch, head)
    return get_repository(str(checkout))


def test_derive_base_rev_new_branch(tmp_path, push_origin):
    repo = shallow_checkout(tmp_path, push_origin, PUSH_BRANCH, push_origin.head)
    head_ref = f"refs/heads/{PUSH_BRANCH}"

    base = repo.derive_base_rev(
        push_origin.url, push_origin.head, head_ref, Repository.NULL_REVISION
    )

    assert base == push_origin.base
    assert repo.get_changed_files(rev=push_origin.head, base=base) == ["b.txt", "c.txt"]


def test_derive_base_rev_force_push(tmp_path, push_origin):
    repo = shallow_checkout(
        tmp_path, push_origin, PUSH_BRANCH, push_origin.head, push_origin.previous
    )
    head_ref = f"refs/heads/{PUSH_BRANCH}"

    base = repo.derive_base_rev(
        push_origin.url, push_origin.head, head_ref, push_origin.previous
    )

    assert base == push_origin.base
    assert repo.get_changed_files(rev=push_origin.head, base=base) == ["b.txt", "c.txt"]


@pytest.mark.parametrize("abbreviate", (False, True))
def test_derive_base_rev_fast_forward_push_keeps_base_rev(
    tmp_path, push_origin, abbreviate, monkeypatch
):
    repo = shallow_checkout(
        tmp_path, push_origin, PUSH_BRANCH, push_origin.head, push_origin.old_tip
    )
    monkeypatch.setattr(repo, "_default_branch", lambda *args: pytest.fail("looked up"))
    head_ref = f"refs/heads/{PUSH_BRANCH}"
    base_rev = push_origin.old_tip[:12] if abbreviate else push_origin.old_tip

    assert (
        repo.derive_base_rev(push_origin.url, push_origin.head, head_ref, base_rev)
        is None
    )


def test_derive_base_rev_fast_forward_push_longer_than_probe(
    tmp_path, push_origin, monkeypatch
):
    monkeypatch.setattr(GitRepository, "PROBE_DEPTH", 1)
    repo = shallow_checkout(
        tmp_path, push_origin, PUSH_BRANCH, push_origin.head, push_origin.old_tip
    )
    head_ref = f"refs/heads/{PUSH_BRANCH}"

    assert (
        repo.derive_base_rev(
            push_origin.url, push_origin.head, head_ref, push_origin.old_tip
        )
        is None
    )


def test_derive_base_rev_fast_forward_over_default_branch_commits(
    tmp_path, push_origin, monkeypatch
):
    monkeypatch.setattr(GitRepository, "PROBE_DEPTH", 1)
    git(push_origin.path, "checkout", "-qb", "tracking", push_origin.main_rev)
    (push_origin.path / "t.txt").write_bytes(b"t\n")
    git(push_origin.path, "add", ".")
    git(push_origin.path, "commit", "-qm", "tracking")
    head = git(push_origin.path, "rev-parse", "HEAD")
    git(push_origin.path, "checkout", "-q", "main")
    repo = shallow_checkout(tmp_path, push_origin, "tracking", head, push_origin.base)

    assert (
        repo.derive_base_rev(
            push_origin.url, head, "refs/heads/tracking", push_origin.base
        )
        is None
    )


def test_derive_base_rev_force_push_from_default_branch_commit(tmp_path, push_origin):
    repo = shallow_checkout(
        tmp_path, push_origin, PUSH_BRANCH, push_origin.head, push_origin.main_rev
    )

    base = repo.derive_base_rev(
        push_origin.url,
        push_origin.head,
        f"refs/heads/{PUSH_BRANCH}",
        push_origin.main_rev,
    )

    assert base == push_origin.base
    assert repo.get_changed_files(rev=push_origin.head, base=base) == ["b.txt", "c.txt"]


def test_derive_base_rev_default_branch(tmp_path, push_origin, monkeypatch):
    repo = shallow_checkout(
        tmp_path, push_origin, "main", push_origin.main_rev, push_origin.base
    )
    monkeypatch.setattr(
        repo, "_fetch_excluding", lambda *args: pytest.fail("excluding fetch")
    )

    assert (
        repo.derive_base_rev(
            push_origin.url, push_origin.main_rev, "refs/heads/main", push_origin.base
        )
        is None
    )


@pytest.mark.parametrize("abbreviate", (False, True))
def test_derive_base_rev_default_branch_force_push(tmp_path, push_origin, abbreviate):
    repo = shallow_checkout(
        tmp_path, push_origin, "main", push_origin.main_rev, push_origin.previous
    )
    previous = push_origin.previous[:12] if abbreviate else push_origin.previous

    base = repo.derive_base_rev(
        push_origin.url, push_origin.main_rev, "refs/heads/main", previous
    )

    assert base == push_origin.base
    assert repo.get_changed_files(rev=push_origin.main_rev, base=base) == ["m.txt"]


def test_derive_base_rev_new_branch_at_default_branch_tip(
    tmp_path, push_origin, monkeypatch
):
    monkeypatch.setattr(GitRepository, "MERGE_BASE_DEPTHS", ())
    repo = shallow_checkout(tmp_path, push_origin, "on_main", push_origin.main_rev)

    base = repo.derive_base_rev(
        push_origin.url,
        push_origin.main_rev,
        "refs/heads/on_main",
        Repository.NULL_REVISION,
    )

    assert base == push_origin.main_rev
    assert repo.get_changed_files(rev=push_origin.main_rev, base=base) == []


def test_derive_base_rev_unknown_ancestry_keeps_base_rev(
    tmp_path, push_origin, monkeypatch
):
    monkeypatch.setattr(GitRepository, "PROBE_DEPTH", 1)
    monkeypatch.setattr(GitRepository, "MERGE_BASE_DEPTHS", ())
    git(push_origin.path, "branch", "staging", push_origin.main_rev)
    repo = shallow_checkout(
        tmp_path, push_origin, "staging", push_origin.main_rev, push_origin.base
    )

    assert (
        repo.derive_base_rev(
            push_origin.url,
            push_origin.main_rev,
            "refs/heads/staging",
            push_origin.base,
        )
        is None
    )


@pytest.mark.parametrize("reported", ("null", "main"))
def test_derive_base_rev_unrelated_history(
    tmp_path, push_origin, monkeypatch, reported
):
    base_rev = push_origin.main_rev if reported == "main" else Repository.NULL_REVISION
    git(push_origin.path, "checkout", "-q", "--orphan", "lone")
    git(push_origin.path, "rm", "-rqf", ".")
    (push_origin.path / "z.txt").write_bytes(b"z\n")
    git(push_origin.path, "add", ".")
    git(push_origin.path, "commit", "-qm", "lone")
    head = git(push_origin.path, "rev-parse", "HEAD")
    git(push_origin.path, "checkout", "-qf", "main")
    repo = shallow_checkout(tmp_path, push_origin, "lone", head)
    monkeypatch.setattr(repo, "_merge_base", lambda *args: pytest.fail("deepened"))

    assert (
        repo.derive_base_rev(push_origin.url, head, "refs/heads/lone", base_rev) is None
    )


def test_derive_base_rev_keeps_partial_clone_filter(tmp_path, push_origin):
    git(push_origin.path, "config", "uploadpack.allowFilter", "true")
    git(push_origin.path, "checkout", "-qb", "partial", push_origin.base)
    (push_origin.path / "x.txt").write_bytes(b"x1\n")
    git(push_origin.path, "add", ".")
    git(push_origin.path, "commit", "-qm", "x1")
    blob = git(push_origin.path, "rev-parse", "HEAD:x.txt")
    (push_origin.path / "x.txt").write_bytes(b"x2\n")
    git(push_origin.path, "commit", "-qam", "x2")
    head = git(push_origin.path, "rev-parse", "HEAD")
    git(push_origin.path, "checkout", "-q", "main")
    checkout = tmp_path / "checkout"
    git(
        tmp_path,
        "clone",
        "-q",
        "--depth=1",
        "--filter=blob:none",
        "--no-checkout",
        push_origin.url,
        str(checkout),
    )
    git(checkout, "fetch", "-q", "--depth=1", "origin", head)
    repo = get_repository(str(checkout))

    base = repo.derive_base_rev(
        push_origin.url, head, "refs/heads/partial", Repository.NULL_REVISION
    )

    assert base == push_origin.base
    missing = git(checkout, "rev-list", "--objects", "--missing=print", head)
    assert f"?{blob}" in missing.splitlines()


def test_derive_base_rev_tag(tmp_path, push_origin):
    git(push_origin.path, "tag", "v1", push_origin.head)
    repo = shallow_checkout(tmp_path, push_origin, PUSH_BRANCH, push_origin.head)

    assert (
        repo.derive_base_rev(
            push_origin.url,
            push_origin.head,
            "refs/tags/v1",
            Repository.NULL_REVISION,
        )
        is None
    )


def test_derive_base_rev_merge_from_default_branch(tmp_path, push_origin):
    repo = shallow_checkout(tmp_path, push_origin, "merged", push_origin.merge_tip)

    base = repo.derive_base_rev(
        push_origin.url,
        push_origin.merge_tip,
        "refs/heads/merged",
        Repository.NULL_REVISION,
    )

    assert base == push_origin.main_rev
    assert repo.get_changed_files(rev=push_origin.merge_tip, base=base) == [
        "b.txt",
        "c.txt",
    ]


def test_derive_base_rev_unreachable_repository(tmp_path, push_origin, caplog):
    repo = shallow_checkout(tmp_path, push_origin, PUSH_BRANCH, push_origin.head)
    missing = (tmp_path / "missing").as_uri()

    assert (
        repo.derive_base_rev(
            missing,
            push_origin.head,
            f"refs/heads/{PUSH_BRANCH}",
            Repository.NULL_REVISION,
        )
        is None
    )
    assert "Cannot derive base_rev" in caplog.text


def test_derive_base_rev_fetch_timeout(tmp_path, push_origin, monkeypatch, caplog):
    repo = shallow_checkout(tmp_path, push_origin, PUSH_BRANCH, push_origin.head)
    run = repo.run

    lock = Path(repo.path, ".git", "shallow.lock")

    def slow_run(*args, **kwargs):
        if args[0] == "fetch":
            lock.touch()
            raise subprocess.TimeoutExpired(args, kwargs.get("timeout"))
        return run(*args, **kwargs)

    monkeypatch.setattr(repo, "run", slow_run)

    assert (
        repo.derive_base_rev(
            push_origin.url,
            push_origin.head,
            f"refs/heads/{PUSH_BRANCH}",
            Repository.NULL_REVISION,
        )
        is None
    )
    assert "Cannot derive base_rev" in caplog.text
    assert not lock.exists()


def test_derive_base_rev_deadline(tmp_path, push_origin, monkeypatch, caplog):
    monkeypatch.setattr(GitRepository, "DERIVE_TIMEOUT", 0)
    repo = shallow_checkout(tmp_path, push_origin, PUSH_BRANCH, push_origin.head)
    run = repo.run

    def local_run(*args, **kwargs):
        assert args[0] not in ("fetch", "ls-remote")
        return run(*args, **kwargs)

    monkeypatch.setattr(repo, "run", local_run)

    assert (
        repo.derive_base_rev(
            push_origin.url,
            push_origin.head,
            f"refs/heads/{PUSH_BRANCH}",
            Repository.NULL_REVISION,
        )
        is None
    )
    assert "Cannot derive base_rev" in caplog.text
    assert repo._deadline == float("inf")


def test_derive_base_rev_full_clone_stays_complete(tmp_path, push_origin):
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "--branch", PUSH_BRANCH, push_origin.url, str(clone))
    repo = get_repository(str(clone))

    base = repo.derive_base_rev(
        push_origin.url,
        push_origin.head,
        f"refs/heads/{PUSH_BRANCH}",
        Repository.NULL_REVISION,
    )

    assert base == push_origin.base
    assert repo.get_changed_files(rev=push_origin.head, base=base) == ["b.txt", "c.txt"]
    assert not repo.is_shallow


def test_derive_base_rev_new_branch_at_default_branch_commit(
    tmp_path, push_origin, monkeypatch
):
    monkeypatch.setattr(GitRepository, "MERGE_BASE_DEPTHS", ())
    git(push_origin.path, "branch", "old", push_origin.base)
    repo = shallow_checkout(tmp_path, push_origin, "old", push_origin.base)

    base = repo.derive_base_rev(
        push_origin.url,
        push_origin.base,
        "refs/heads/old",
        Repository.NULL_REVISION,
    )

    assert base == push_origin.base
    assert repo.get_changed_files(rev=push_origin.base, base=base) == []


def test_derive_base_rev_fast_forward_along_default_branch(
    tmp_path, push_origin, monkeypatch
):
    monkeypatch.setattr(GitRepository, "PROBE_DEPTH", 1)
    git(push_origin.path, "branch", "staging", push_origin.main_rev)
    repo = shallow_checkout(
        tmp_path, push_origin, "staging", push_origin.main_rev, push_origin.base
    )

    assert (
        repo.derive_base_rev(
            push_origin.url,
            push_origin.main_rev,
            "refs/heads/staging",
            push_origin.base,
        )
        is None
    )


def test_derive_pull_request_base_rev_hidden_by_shallow_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(GitRepository, "MERGE_BASE_DEPTHS", (3, 6, 100))
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q")
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    git(origin, "config", "user.name", "Test")
    git(origin, "config", "user.email", "test@example.com")
    git(origin, "config", "uploadpack.allowAnySHA1InWant", "true")

    def commit(name):
        (origin / f"{name}.txt").write_bytes(f"{name}\n".encode())
        git(origin, "add", ".")
        git(origin, "commit", "-qm", name)
        return git(origin, "rev-parse", "HEAD")

    commit("a0")
    commit("A")
    git(origin, "checkout", "-qb", "side")
    commit("s1")
    git(origin, "checkout", "-q", "main")
    commit("B")
    git(origin, "checkout", "-qb", "pr")
    commit("h1")
    git(origin, "checkout", "-q", "main")
    y1 = commit("y1")
    git(origin, "checkout", "-q", "pr")
    git(origin, "merge", "-q", "-m", "merge main", "main")
    head = commit("h2")
    git(origin, "checkout", "-q", "main")
    for name in ("y2", "y3", "y4", "y5"):
        commit(name)
    git(origin, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    commit("T")
    repo = shallow_checkout(tmp_path, SimpleNamespace(url=origin.as_uri()), "pr", head)

    base = repo.derive_pull_request_base_rev(origin.as_uri(), head, "main")

    assert base == y1
    assert sorted(repo.get_changed_files(rev=head, base=base)) == ["h1.txt", "h2.txt"]


def test_derive_base_rev_non_utf8_commit_message(tmp_path, push_origin):
    git(push_origin.path, "checkout", "-qb", "latin", push_origin.base)
    (push_origin.path / "l.txt").write_bytes(b"l\n")
    git(push_origin.path, "add", ".")
    message = tmp_path / "message"
    message.write_bytes("café\n".encode("latin1"))
    git(push_origin.path, "-c", "i18n.commitEncoding=latin1", "commit", "-qF", message)
    head = git(push_origin.path, "rev-parse", "HEAD")
    git(push_origin.path, "checkout", "-q", "main")
    repo = shallow_checkout(tmp_path, push_origin, "latin", head)

    base = repo.derive_base_rev(
        push_origin.url, head, "refs/heads/latin", Repository.NULL_REVISION
    )

    assert base == push_origin.base


@pytest.fixture
def fork_pull_request(tmp_path, push_origin):
    fork = tmp_path / "fork"
    git(tmp_path, "clone", "-q", push_origin.url, str(fork))
    git(fork, "config", "user.name", "Test")
    git(fork, "config", "user.email", "test@example.com")
    git(fork, "checkout", "-qb", "feature", push_origin.base)
    (fork / "e.txt").write_bytes(b"e\n")
    git(fork, "add", ".")
    git(fork, "commit", "-qm", "fork stack")
    head = git(fork, "rev-parse", "HEAD")
    git(fork, "push", "-q", push_origin.url, f"{head}:refs/pull/1/head")
    return SimpleNamespace(url=fork.as_uri(), head=head)


@pytest.mark.parametrize(
    "base_ref,abbreviate",
    (("main", False), ("refs/heads/main", False), ("main", True)),
)
def test_derive_pull_request_base_rev_behind_base(
    tmp_path, push_origin, base_ref, abbreviate
):
    repo = shallow_checkout(
        tmp_path, push_origin, PUSH_BRANCH, push_origin.head, push_origin.main_rev
    )
    head = push_origin.head[:12] if abbreviate else push_origin.head

    base = repo.derive_pull_request_base_rev(push_origin.url, head, base_ref)

    assert base == push_origin.base
    assert repo.get_changed_files(rev=push_origin.head, base=base) == ["b.txt", "c.txt"]


def test_derive_pull_request_base_rev_after_merge_from_target(tmp_path, push_origin):
    (push_origin.path / "n.txt").write_bytes(b"n\n")
    git(push_origin.path, "add", ".")
    git(push_origin.path, "commit", "-qm", "main4")
    tip = git(push_origin.path, "rev-parse", "HEAD")
    repo = shallow_checkout(tmp_path, push_origin, "merged", push_origin.merge_tip, tip)

    base = repo.derive_pull_request_base_rev(
        push_origin.url, push_origin.merge_tip, "main"
    )

    assert base == push_origin.main_rev
    assert repo.get_changed_files(rev=push_origin.merge_tip, base=base) == [
        "b.txt",
        "c.txt",
    ]


def test_derive_pull_request_base_rev_from_fork(
    tmp_path, push_origin, fork_pull_request
):
    repo = shallow_checkout(
        tmp_path, push_origin, "feature", fork_pull_request.head, push_origin.main_rev
    )

    base = repo.derive_pull_request_base_rev(
        push_origin.url, fork_pull_request.head, "main"
    )

    assert base == push_origin.base
    assert repo.get_changed_files(rev=fork_pull_request.head, base=base) == ["e.txt"]


def test_derive_pull_request_base_rev_without_base_ref(tmp_path, push_origin):
    repo = shallow_checkout(tmp_path, push_origin, PUSH_BRANCH, push_origin.head)

    assert (
        repo.derive_pull_request_base_rev(push_origin.url, push_origin.head, "") is None
    )


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def raise_for_status(self):
        if self.status != 200:
            raise requests.HTTPError(str(self.status))

    def json(self):
        return self.payload


GITHUB_URL = "https://github.com/test/repo"


@pytest.fixture
def github(push_origin, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{push_origin.url}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", GITHUB_URL)
    requests_made = []

    def fake_get(url, **kwargs):
        requests_made.append(url)
        base, head = url.rsplit("/compare/", 1)[1].split("...")
        try:
            merge_base = git(push_origin.path, "merge-base", base, head)
        except subprocess.CalledProcessError:
            return FakeResponse({}, status=404)
        status = {
            (True, True): "identical",
            (True, False): "ahead",
            (False, True): "behind",
        }.get(
            (
                merge_base == git(push_origin.path, "rev-parse", base),
                merge_base == git(push_origin.path, "rev-parse", head),
            ),
            "diverged",
        )
        return FakeResponse(
            {"status": status, "merge_base_commit": {"sha": merge_base}}
        )

    monkeypatch.setattr(requests, "get", fake_get)
    return requests_made


def github_clone(tmp_path, head):
    checkout = tmp_path / "checkout"
    git(
        tmp_path, "clone", "-q", "--depth=1", "--no-checkout", GITHUB_URL, str(checkout)
    )
    git(checkout, "fetch", "-q", "--depth=1", "origin", head)
    git(checkout, "checkout", "-qf", head)
    return get_repository(str(checkout))


def github_checkout(tmp_path, head, monkeypatch):
    repo = github_clone(tmp_path, head)
    for name in ("_fetch_excluding", "_is_ancestor", "_merge_base"):
        monkeypatch.setattr(repo, name, lambda *args: pytest.fail("used git"))
    return repo


@pytest.mark.parametrize(
    "head,base_ref,expected",
    (
        pytest.param("head", "main", "base", id="behind-base"),
        pytest.param("merge_tip", "refs/heads/main", "main_rev", id="merged-target"),
    ),
)
def test_derive_pull_request_base_rev_github(
    tmp_path, push_origin, github, monkeypatch, head, base_ref, expected
):
    head = getattr(push_origin, head)
    repo = github_checkout(tmp_path, head, monkeypatch)

    base = repo.derive_pull_request_base_rev(GITHUB_URL, head, base_ref)

    assert base == getattr(push_origin, expected)
    assert repo.get_changed_files(rev=head, base=base) == ["b.txt", "c.txt"]
    assert github == [f"https://api.github.com/repos/test/repo/compare/main...{head}"]


@pytest.mark.parametrize(
    "head,head_ref,base_rev,expected,compares",
    (
        pytest.param("head", PUSH_BRANCH, "null", "base", ["main"], id="new-branch"),
        pytest.param(
            "head",
            PUSH_BRANCH,
            "previous",
            "base",
            ["previous", "main"],
            id="force-push",
        ),
        pytest.param(
            "head", PUSH_BRANCH, "old_tip", None, ["old_tip"], id="fast-forward"
        ),
        pytest.param(
            "main_rev", "main", "base", None, ["base"], id="default-fast-forward"
        ),
        pytest.param(
            "main_rev",
            "main",
            "previous",
            "base",
            ["previous"],
            id="default-force-push",
        ),
        pytest.param("main_rev", "main", "null", None, [], id="new-default-branch"),
    ),
)
def test_derive_base_rev_github(
    tmp_path,
    push_origin,
    github,
    monkeypatch,
    head,
    head_ref,
    base_rev,
    expected,
    compares,
):
    head = getattr(push_origin, head)
    base_rev = (
        Repository.NULL_REVISION
        if base_rev == "null"
        else getattr(push_origin, base_rev)
    )
    repo = github_checkout(tmp_path, head, monkeypatch)

    base = repo.derive_base_rev(GITHUB_URL, head, f"refs/heads/{head_ref}", base_rev)

    assert base == (expected and getattr(push_origin, expected))
    assert github == [
        "https://api.github.com/repos/test/repo/compare/"
        f"{getattr(push_origin, compare, compare)}...{head}"
        for compare in compares
    ]
    if base_rev != Repository.NULL_REVISION:
        repo.get_changed_files(rev=head, base=base or base_rev)


def test_derive_pull_request_base_rev_github_falls_back_to_git(
    tmp_path, push_origin, github, monkeypatch
):
    calls = []

    def rate_limited(url, **kwargs):
        calls.append(url)
        return FakeResponse({}, status=403)

    monkeypatch.setattr(requests, "get", rate_limited)
    repo = github_clone(tmp_path, push_origin.head)

    base = repo.derive_pull_request_base_rev(GITHUB_URL, push_origin.head, "main")

    assert base == push_origin.base
    assert calls == [
        f"https://api.github.com/repos/test/repo/compare/main...{push_origin.head}"
    ]


@pytest.mark.parametrize(
    "failing,compares",
    (
        pytest.param("", ["previous"], id="first-compare"),
        pytest.param("main", ["previous", "main"], id="second-compare"),
    ),
)
def test_derive_base_rev_github_falls_back_to_git(
    tmp_path, push_origin, github, monkeypatch, failing, compares
):
    fake_get = requests.get

    def rate_limited(url, **kwargs):
        if f"/compare/{failing}" not in url:
            return fake_get(url, **kwargs)
        github.append(url)
        return FakeResponse({}, status=403)

    monkeypatch.setattr(requests, "get", rate_limited)
    repo = github_clone(tmp_path, push_origin.head)

    base = repo.derive_base_rev(
        GITHUB_URL,
        push_origin.head,
        f"refs/heads/{PUSH_BRANCH}",
        push_origin.previous,
    )

    assert base == push_origin.base
    assert github == [
        "https://api.github.com/repos/test/repo/compare/"
        f"{getattr(push_origin, compare, compare)}...{push_origin.head}"
        for compare in compares
    ]


@pytest.mark.parametrize("token", (None, "secret"))
def test_github_compare(git_repo, monkeypatch, token):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse({"status": "ahead", "merge_base_commit": {"sha": "abc"}})

    monkeypatch.setattr(requests, "get", fake_get)
    if token:
        monkeypatch.setenv("GITHUB_TOKEN", token)
    else:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    repo = get_repository(git_repo)

    assert repo._github_compare(
        "https://github.com/mozilla-firefox/firefox.git", "fix/#12?x", "def"
    ) == {"status": "ahead", "merge_base_commit": {"sha": "abc"}}
    ((url, kwargs),) = calls
    assert url == (
        "https://api.github.com/repos/mozilla-firefox/firefox/compare/fix/%2312%3Fx...def"
    )
    assert kwargs["params"] == {"per_page": 1}
    assert kwargs["headers"].get("Authorization") == (
        f"Bearer {token}" if token else None
    )


def test_derive_base_rev_full_clone_uses_local_base(tmp_path, push_origin, monkeypatch):
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", push_origin.url, str(clone))
    git(clone, "fetch", "-q", "origin", push_origin.previous)
    repo = get_repository(str(clone))
    fetch = repo._fetch

    def checked_fetch(repository, refspec, *options):
        assert refspec != push_origin.previous
        return fetch(repository, refspec, *options)

    monkeypatch.setattr(repo, "_fetch", checked_fetch)

    base = repo.derive_base_rev(
        push_origin.url, push_origin.main_rev, "refs/heads/main", push_origin.previous
    )

    assert base == push_origin.base


def test_derive_base_rev_force_push_from_unrelated_history(tmp_path, push_origin):
    git(push_origin.path, "checkout", "-q", "--orphan", "lone")
    git(push_origin.path, "rm", "-rqf", ".")
    (push_origin.path / "z.txt").write_bytes(b"z\n")
    git(push_origin.path, "add", ".")
    git(push_origin.path, "commit", "-qm", "lone")
    lone = git(push_origin.path, "rev-parse", "HEAD")
    git(push_origin.path, "checkout", "-qf", "main")
    repo = shallow_checkout(
        tmp_path, push_origin, "merged", push_origin.merge_tip, lone
    )

    base = repo.derive_base_rev(
        push_origin.url, push_origin.merge_tip, "refs/heads/merged", lone
    )

    assert base == push_origin.main_rev


@pytest.mark.parametrize(
    "response",
    (
        pytest.param(FakeResponse({}, status=403), id="http-error"),
        pytest.param(FakeResponse({}), id="empty"),
        pytest.param(
            FakeResponse({"merge_base_commit": {"sha": "abc"}}), id="no-status"
        ),
        pytest.param(
            FakeResponse({"status": "diverged", "merge_base_commit": {"sha": None}}),
            id="no-merge-base",
        ),
    ),
)
def test_github_compare_unavailable(git_repo, monkeypatch, response):
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: response)
    repo = get_repository(git_repo)

    with pytest.raises(_GitHubCompareError):
        repo._github_compare("https://github.com/a/b", "main", "def")


def test_github_compare_not_github(git_repo):
    repo = get_repository(git_repo)

    with pytest.raises(_GitHubCompareError, match="is not on GitHub"):
        repo._github_compare("https://example.com/a/b", "main", "def")


def test_derive_base_rev_hg(hg_repo):
    repo = get_repository(hg_repo)

    assert repo.derive_base_rev("https://example.com", "abc", "default", "def") is None
    assert (
        repo.derive_pull_request_base_rev("https://example.com", "abc", "main") is None
    )
