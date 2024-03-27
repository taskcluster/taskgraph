import os
import shutil
import subprocess

import pytest

from taskgraph.util.vcs import get_repository

_FORCE_COMMIT_DATE_TIME = "2019-11-04T10:03:58+00:00"


@pytest.fixture(scope="package")
def hg_repo(tmpdir_factory):
    tmpdir = tmpdir_factory.mktemp("hgrepo")
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


@pytest.fixture(scope="package")
def git_repo(tmpdir_factory):
    env = _build_env_with_git_date_env_vars(_FORCE_COMMIT_DATE_TIME)
    tmpdir = tmpdir_factory.mktemp("gitrepo")
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


@pytest.fixture(scope="package")
def default_git_branch():
    proc = subprocess.run(
        ["git", "config", "init.defaultBranch"],
        capture_output=True,
        check=False,
        text=True,
    )
    return proc.stdout.strip() or "master"


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
def repo(request, hg_repo, git_repo, monkeypatch, tmpdir):
    """
    The repo fixture depends on the session-scoped git and hg repo fixtures, and
        copies the contents of the initialized repos to a temp folder
    """
    repodir = tmpdir.join(request.param)
    if request.param == "hg":
        monkeypatch.setenv("HGPLAIN", "1")
        shutil.copytree(hg_repo, repodir)
        return get_repository(repodir)
    shutil.copytree(git_repo, repodir)
    return get_repository(repodir)


@pytest.fixture
def create_remote_repo(default_git_branch):

    def inner(tmpdir, repo, remote_name, remote_path):
        if repo.tool == "hg":
            repo.run("phase", "--public", ".")

        shutil.copytree(repo.path, str(tmpdir / remote_path))

        if repo.tool == "git":
            repo.run("remote", "add", remote_name, f"{tmpdir}/{remote_path}")
            repo.run("fetch", remote_name)
            repo.run(
                "branch", "--set-upstream-to", f"{remote_name}/{default_git_branch}"
            )
        if repo.tool == "hg":
            with open(os.path.join(repo.path, ".hg/hgrc"), "a") as f:
                f.write(f"[paths]\n{remote_name} = {tmpdir}/{remote_path}\n")

    return inner


@pytest.fixture
def repo_with_remote(tmpdir, create_remote_repo, repo):
    remote_name = "upstream"
    create_remote_repo(tmpdir, repo, remote_name, "remote_repo")
    return repo, remote_name


@pytest.fixture
def repo_with_upstream(tmpdir, repo, default_git_branch):
    with open(os.path.join(repo.path, "second_file"), "w") as f:
        f.write("some data for the second file")

    repo.run("add", ".")
    repo.run("commit", "-m", "Add second_file")

    if repo.tool == "hg":
        repo.run("phase", "--public", ".")

    shutil.copytree(repo.path, str(tmpdir / "remoterepo"))
    upstream_location = None

    if repo.tool == "git":
        upstream_location = f"upstream/{default_git_branch}"
        repo.run("remote", "add", "upstream", f"{tmpdir}/remoterepo")
        repo.run("fetch", "upstream")
        repo.run("branch", "--set-upstream-to", upstream_location)
    if repo.tool == "hg":
        upstream_location = f"{tmpdir}/remoterepo"
        with open(os.path.join(repo.path, ".hg/hgrc"), "w") as f:
            f.write(f"[paths]\ndefault = {upstream_location}")

    return repo, upstream_location
