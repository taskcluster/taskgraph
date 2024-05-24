import io
import os
import stat
import subprocess
import sys
import tempfile
from argparse import Namespace
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from unittest.mock import Mock

import pytest

import taskgraph


@pytest.fixture(scope="module")
def run_task_mod():
    spec = spec_from_loader(
        "run-task",
        SourceFileLoader(
            "run-task",
            os.path.join(os.path.dirname(taskgraph.__file__), "run-task", "run-task"),
        ),
    )
    assert spec
    assert spec.loader
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def patch_run_command(monkeypatch, run_task_mod):
    called_with = []

    def fake_run_command(*args, **kwargs):
        called_with.append((args, kwargs))

    def inner():
        monkeypatch.setattr(run_task_mod, "run_command", fake_run_command)
        nonlocal called_with
        called_with = []
        return called_with

    return inner


@pytest.fixture()
def mock_stdin(monkeypatch):
    _stdin = Mock(
        fileno=lambda: 3,
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        _stdin,
    )


def test_install_pip_requirements(
    tmp_path,
    patch_run_command,
    run_task_mod,
):
    # no requirements
    repositories = [{"pip-requirements": None}]
    called = patch_run_command()
    run_task_mod.install_pip_requirements(repositories)
    assert len(called) == 0

    # single requirement
    req = tmp_path.joinpath("requirements.txt")
    req.write_text("taskcluster-taskgraph==1.0.0")
    repositories = [{"pip-requirements": str(req)}]
    called = patch_run_command()
    run_task_mod.install_pip_requirements(repositories)
    assert len(called) == 1
    assert called[0][0] == (
        b"pip-install",
        [
            sys.executable,
            "-mpip",
            "install",
            "--break-system-packages",
            "--require-hashes",
            "-r",
            str(req),
        ],
    )

    # two requirements
    req2 = tmp_path.joinpath("requirements2.txt")
    req2.write_text("redo")
    repositories.append({"pip-requirements": str(req2)})
    called = patch_run_command()
    run_task_mod.install_pip_requirements(repositories)
    assert len(called) == 1
    assert called[0][0] == (
        b"pip-install",
        [
            sys.executable,
            "-mpip",
            "install",
            "--break-system-packages",
            "--require-hashes",
            "-r",
            str(req),
            "-r",
            str(req2),
        ],
    )


@pytest.mark.parametrize(
    "env,extra_expected",
    [
        pytest.param(
            {
                "REPOSITORY_TYPE": "hg",
                "BASE_REPOSITORY": "https://hg.mozilla.org/mozilla-central",
                "HEAD_REPOSITORY": "https://hg.mozilla.org/mozilla-central",
                "HEAD_REV": "abcdef",
                "PIP_REQUIREMENTS": "taskcluster/requirements.txt",
            },
            {
                "base-repo": "https://hg.mozilla.org/mozilla-unified",
            },
        ),
        pytest.param(
            {
                "REPOSITORY_TYPE": "git",
                "BASE_REPOSITORY": "https://github.com/mozilla-mobile/mozilla-vpn-client.git",
                "HEAD_REPOSITORY": "https://github.com/mozilla-mobile/mozilla-vpn-client.git",
                "HEAD_REV": "abcdef",
                "SUBMODULES": "3rdparty/i18n",
            },
            {},
        ),
        pytest.param(
            {
                "REPOSITORY_TYPE": "git",
                "BASE_REPOSITORY": "https://github.com/mozilla-mobile/mozilla-vpn-client.git",
                "HEAD_REPOSITORY": "https://github.com/mozilla-mobile/mozilla-vpn-client.git",
                "HEAD_REV": "abcdef",
                "SUBMODULES": "auto",
            },
            {
                "submodules": True,
            },
        ),
        pytest.param(
            {
                "REPOSITORY_TYPE": "git",
                "BASE_REPOSITORY": "https://github.com/mozilla-mobile/mozilla-vpn-client.git",
                "HEAD_REPOSITORY": "https://github.com/mozilla-mobile/mozilla-vpn-client.git",
                "HEAD_REV": "abcdef",
                "SUBMODULES": "yes",
            },
            {
                "submodules": True,
            },
        ),
    ],
)
def test_collect_vcs_options(monkeypatch, run_task_mod, env, extra_expected):
    name = "myrepo"
    checkout = "checkout"

    monkeypatch.setattr(os, "environ", {})
    for k, v in env.items():
        monkeypatch.setenv(f"{name.upper()}_{k.upper()}", v)

    args = Namespace()
    setattr(args, f"{name}_checkout", checkout)
    setattr(args, f"{name}_sparse_profile", False)

    result = run_task_mod.collect_vcs_options(args, name, name)

    expected = {
        "base-repo": env.get("BASE_REPOSITORY"),
        "base-ref": env.get("BASE_REF"),
        "base-rev": env.get("BASE_REV"),
        "checkout": os.path.join(os.getcwd(), "checkout"),
        "env-prefix": name.upper(),
        "head-repo": env.get("HEAD_REPOSITORY"),
        "name": name,
        "pip-requirements": None,
        "project": name,
        "ref": env.get("HEAD_REF"),
        "repo-type": env.get("REPOSITORY_TYPE"),
        "revision": env.get("HEAD_REV"),
        "ssh-secret-name": env.get("SSH_SECRET_NAME"),
        "sparse-profile": False,
        "store-path": env.get("HG_STORE_PATH"),
        "submodules": env.get("SUBMODULES"),
    }
    if "PIP_REQUIREMENTS" in env:
        expected["pip-requirements"] = os.path.join(
            expected["checkout"], env.get("PIP_REQUIREMENTS")
        )

    expected.update(extra_expected)
    assert result == expected


def test_remove_directory(monkeypatch, run_task_mod):
    _tempdir = tempfile.TemporaryDirectory()
    assert os.path.isdir(_tempdir.name) is True
    run_task_mod.remove(_tempdir.name)
    assert os.path.isdir(_tempdir.name) is False


def test_remove_closed_file(monkeypatch, run_task_mod):
    _tempdir = tempfile.TemporaryDirectory()
    _tempfile = tempfile.NamedTemporaryFile(dir=_tempdir.name, delete=False)
    _tempfile.write(b"foo")
    _tempfile.close()
    assert os.path.isdir(_tempdir.name) is True
    assert os.path.isfile(_tempfile.name) is True
    run_task_mod.remove(_tempdir.name)
    assert os.path.isdir(_tempdir.name) is False
    assert os.path.isfile(_tempfile.name) is False


def test_remove_readonly_tree(monkeypatch, run_task_mod):
    _tempdir = tempfile.TemporaryDirectory()
    _mark_readonly(_tempdir.name)
    assert os.path.isdir(_tempdir.name) is True
    run_task_mod.remove(_tempdir.name)
    assert os.path.isdir(_tempdir.name) is False


def test_remove_readonly_file(monkeypatch, run_task_mod):
    _tempdir = tempfile.TemporaryDirectory()
    _tempfile = tempfile.NamedTemporaryFile(dir=_tempdir.name, delete=False)
    _tempfile.write(b"foo")
    _tempfile.close()
    _mark_readonly(_tempfile.name)
    # should change write permission and then remove file
    assert os.path.isfile(_tempfile.name) is True
    run_task_mod.remove(_tempfile.name)
    assert os.path.isfile(_tempfile.name) is False
    _tempdir.cleanup()


def _mark_readonly(path):
    """Removes all write permissions from given file/directory.

    :param path: path of directory/file of which modes must be changed
    """
    mode = os.stat(path)[stat.ST_MODE]
    os.chmod(path, mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)


def test_clean_git_checkout(monkeypatch, mock_stdin, run_task_mod):
    prefix = "Would remove "
    root_dir = tempfile.TemporaryDirectory()
    untracked_dir = tempfile.TemporaryDirectory(dir=root_dir.name)
    tracked_dir = tempfile.TemporaryDirectory(dir=root_dir.name)
    untracked_file = tempfile.NamedTemporaryFile(dir=tracked_dir.name, delete=False)
    untracked_file.write(b"untracked")
    untracked_file.close()
    tracked_file = tempfile.NamedTemporaryFile(dir=tracked_dir.name, delete=False)
    tracked_file.write(b"tracked")
    tracked_file.close()
    root_dir_prefix = root_dir.name + "/"
    untracked_dir_rel_path = untracked_dir.name[len(root_dir_prefix) :]
    untracked_file_rel_path = untracked_file.name[len(root_dir_prefix) :]
    output_str = (
        f"{prefix}{untracked_dir_rel_path}/\n{prefix}{untracked_file_rel_path}\n"
    )
    output_bytes = output_str.encode("latin1")
    output = io.BytesIO(output_bytes)

    def _Popen(
        args,
        bufsize=None,
        stdout=None,
        stderr=None,
        stdin=None,
        cwd=None,
        env=None,
        **kwargs,
    ):
        return Mock(
            stdout=output,
            wait=lambda: 0,
        )

    monkeypatch.setattr(
        subprocess,
        "Popen",
        _Popen,
    )

    assert os.path.isdir(root_dir.name) is True
    assert os.path.isdir(tracked_dir.name) is True
    assert os.path.isdir(untracked_dir.name) is True
    assert os.path.isfile(untracked_file.name) is True
    assert os.path.isfile(tracked_file.name) is True

    run_task_mod._clean_git_checkout(root_dir.name)

    assert os.path.isdir(root_dir.name) is True
    assert os.path.isdir(tracked_dir.name) is True
    assert os.path.isfile(tracked_file.name) is True

    assert os.path.isdir(untracked_dir.name) is False
    assert os.path.isfile(untracked_file.name) is False


def git_current_rev(cwd):
    return subprocess.check_output(
        args=["git", "rev-parse", "--verify", "HEAD"],
        cwd=cwd,
        universal_newlines=True,
    ).strip()

@pytest.fixture()
def mock_homedir(monkeypatch):
    "Mock home directory to isolate git config changes"
    with tempfile.TemporaryDirectory() as fakehome:
        env = os.environ.copy()
        env['HOME'] = str(fakehome)
        monkeypatch.setattr(os, "environ", env)

        # Enable the git file protocol for testing.
        subprocess.check_call(
            ["git", "config", "--global", "protocol.file.allow", "always"], env=env)
        yield str(fakehome)

@pytest.fixture(scope="session")  # Tests shouldn't change this repo
def mock_git_repo():
    "Mock repository with files, commits and branches for using as source"
    def _create_empty_repo(path):
        subprocess.check_call(["git", "init", "-b", "main", path])
        subprocess.check_call(["git", "config", "user.name", "pytest"], cwd=path)
        subprocess.check_call(
            ["git", "config", "user.email", "py@tes.t"], cwd=path
        )

    def _commit_file(message, filename, path):
        with open(os.path.join(path, filename), "w") as fout:
            fout.write("test file content")
        subprocess.check_call(["git", "add", filename], cwd=path)
        subprocess.check_call(["git", "commit", "-m", message], cwd=path)
        return git_current_rev(path)
    
    with tempfile.TemporaryDirectory() as repo:
        # Create the submodule repositories
        sm1_path = os.path.join(str(repo), "submodule1")
        _create_empty_repo(sm1_path)
        _commit_file("The first submodule", "first", sm1_path)

        sm2_path = os.path.join(str(repo), "submodule2")
        _create_empty_repo(sm2_path)
        _commit_file("The second submodule", "second", sm2_path)

        # Create the testing repository.
        repo_path = os.path.join(str(repo), "repository")
        _create_empty_repo(repo_path)

        # Add submodules (to main branch)
        subprocess.check_call(
            ["git", "-c", "protocol.file.allow=always",
             "submodule", "add", f"file://{os.path.abspath(sm1_path)}", "sm1"],
            cwd=repo_path
        )
        subprocess.check_call(
            ["git", "-c", "protocol.file.allow=always",
             "submodule", "add", f"file://{os.path.abspath(sm2_path)}", "sm2"],
            cwd=repo_path
        )
        subprocess.check_call(["git", "add", "sm1"], cwd=repo_path)
        subprocess.check_call(["git", "add", "sm2"], cwd=repo_path)
        subprocess.check_call(["git", "commit", "-m", "Add submodules"], cwd=repo_path)

        # Commit mainfile (to main branch)
        main_commit = _commit_file("Initial commit", "mainfile", repo_path)

        # New branch mybranch
        subprocess.check_call(["git", "checkout", "-b", "mybranch"], cwd=repo_path)
        # Commit branchfile to mybranch branch
        branch_commit = _commit_file("File in mybranch", "branchfile", repo_path)

        # Set current branch back to main
        subprocess.check_call(["git", "checkout", "main"], cwd=repo_path)
        yield {"path": repo_path, "main": main_commit, "branch": branch_commit}


@pytest.mark.parametrize(
    "base_ref,ref,submodules,files,hash_key",
    [
        # Check out the repository in a bunch of states.
        (None, None, None, ["mainfile"], "main"),
        (None, "main", None, ["mainfile"], "main"),
        (None, "mybranch", None, ["mainfile", "branchfile"], "branch"),
        ("main", "main", None, ["mainfile"], "main"),
        ("main", "mybranch", None, ["mainfile", "branchfile"], "branch"),
        # Same tests again - but with submodules.
        (None, None, True, ["mainfile", "sm1/first", "sm2/second"], "main"),
        (None, "main", True, ["mainfile", "sm1/first", "sm2/second"], "main"),
        (None, "mybranch", True, ["mainfile", "branchfile", "sm1/first", "sm2/second"], "branch"),
        ("main", "main", True, ["mainfile", "sm1/first", "sm2/second"], "main"),
        ("main", "mybranch", True, ["mainfile", "branchfile", "sm1/first", "sm2/second"], "branch"),
        # Tests for submodule matching rules.
        (None, "main", "sm1", ["mainfile", "sm1/first"], "main"),
        (None, "main", "sm2", ["mainfile", "sm2/second"], "main"),
        (None, "main", "one:two:three", ["mainfile"], "main"),
        (None, "main", "one:two:sm1", ["mainfile", "sm1/first"], "main"),
    ],
)
def test_git_checkout(
    mock_stdin,
    mock_homedir,
    run_task_mod,
    mock_git_repo,
    base_ref,
    ref,
    submodules,
    files,
    hash_key,
):
    with tempfile.TemporaryDirectory() as workdir:
        destination = os.path.join(workdir, "destination")
        run_task_mod.git_checkout(
            destination_path=destination,
            head_repo=mock_git_repo["path"],
            base_repo=mock_git_repo["path"],
            base_ref=base_ref,
            base_rev=None,
            ref=ref,
            commit=None,
            ssh_key_file=None,
            ssh_known_hosts_file=None,
            submodules=submodules,
        )

        # Check desired files exist
        for filename in files:
            assert os.path.exists(os.path.join(destination, filename))

        # Check repo is on the right branch
        if ref:
            current_branch = subprocess.check_output(
                args=["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=destination,
                universal_newlines=True,
            ).strip()
            assert current_branch == ref

            current_rev = git_current_rev(destination)
            assert current_rev == mock_git_repo[hash_key]


def test_git_checkout_with_commit(
    mock_stdin,
    mock_homedir,
    run_task_mod,
    mock_git_repo,
):
    with tempfile.TemporaryDirectory() as workdir:
        destination = os.path.join(workdir, "destination")
        run_task_mod.git_checkout(
            destination_path=destination,
            head_repo=mock_git_repo["path"],
            base_repo=mock_git_repo["path"],
            base_ref="mybranch",
            base_rev=mock_git_repo["main"],
            ref=mock_git_repo["branch"],
            commit=mock_git_repo["branch"],
            ssh_key_file=None,
            ssh_known_hosts_file=None,
            submodules=None,
        )


def test_display_python_version_should_output_python_versions_title(
    run_task_mod, capsys
):
    run_task_mod._display_python_version()

    assert ("Python version:" in capsys.readouterr().out) is True


def test_display_python_version_should_output_python_versions(run_task_mod, capsys):
    run_task_mod._display_python_version()

    output = capsys.readouterr().out
    assert ("Python version: 3." in output) or ("Python version: 2." in output) is True
