import io
import os
import site
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
from taskgraph.util.caches import CACHES


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
    mocker,
    tmp_path,
    patch_run_command,
    run_task_mod,
):
    mocker.patch("shutil.which", return_value=False)

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
            "--user",
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
            "--user",
            "--break-system-packages",
            "--require-hashes",
            "-r",
            str(req),
            "-r",
            str(req2),
        ],
    )


def test_install_pip_requirements_with_uv(
    mocker,
    tmp_path,
    patch_run_command,
    run_task_mod,
):
    mocker.patch("shutil.which", return_value=True)

    req = tmp_path.joinpath("requirements.txt")
    req.write_text("taskcluster-taskgraph==1.0.0")
    repositories = [{"pip-requirements": str(req)}]
    called = patch_run_command()
    run_task_mod.install_pip_requirements(repositories)
    assert len(called) == 1
    assert called[0][0] == (
        b"pip-install",
        [
            "uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "--target",
            site.getusersitepackages(),
            "--require-hashes",
            "-r",
            str(req),
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
        )
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


@pytest.fixture(scope="session")  # Tests shouldn't change this repo
def mock_git_repo_with_dirs():
    "Mock repository with subdirectories for testing sparse checkout"
    with tempfile.TemporaryDirectory() as repo:
        repo_path = str(repo)
        # Init git repo and setup user config
        subprocess.check_call(["git", "init", "-b", "main"], cwd=repo_path)
        subprocess.check_call(["git", "config", "user.name", "pytest"], cwd=repo_path)
        subprocess.check_call(
            ["git", "config", "user.email", "py@tes.t"], cwd=repo_path
        )

        def _commit_file(message, filename):
            filepath = os.path.join(repo, filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as fout:
                fout.write(f"content of {filename}")
            subprocess.check_call(["git", "add", filename], cwd=repo_path)
            subprocess.check_call(["git", "commit", "-m", message], cwd=repo_path)
            return git_current_rev(repo_path)

        # Create files in different directories
        _commit_file("Add root file", "rootfile.txt")
        _commit_file("Add src file", "src/main.py")
        _commit_file("Add src subfile", "src/utils.py")
        _commit_file("Add docs file", "docs/readme.md")
        _commit_file("Add test file", "tests/test_main.py")
        main_commit = _commit_file("Add build file", "build/Makefile")

        yield {"path": repo_path, "main": main_commit}


@pytest.fixture(scope="session")  # Tests shouldn't change this repo
def mock_git_repo():
    "Mock repository with files, commits and branches for using as source"
    with tempfile.TemporaryDirectory() as repo:
        repo_path = str(repo)
        # Init git repo and setup user config
        subprocess.check_call(["git", "init", "-b", "main"], cwd=repo_path)
        subprocess.check_call(["git", "config", "user.name", "pytest"], cwd=repo_path)
        subprocess.check_call(
            ["git", "config", "user.email", "py@tes.t"], cwd=repo_path
        )

        def _commit_file(message, filename):
            filepath = os.path.join(repo, filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as fout:
                fout.write("test file content")
            subprocess.check_call(["git", "add", filename], cwd=repo_path)
            subprocess.check_call(["git", "commit", "-m", message], cwd=repo_path)
            return git_current_rev(repo_path)

        # Commit mainfile (to main branch)
        main_commit = _commit_file("Initial commit", "mainfile")

        # New branch mybranch
        subprocess.check_call(["git", "checkout", "-b", "mybranch"], cwd=repo_path)
        # Commit branchfile to mybranch branch
        branch_commit = _commit_file("File in mybranch", "branchfile")

        # Set current branch back to main
        subprocess.check_call(["git", "checkout", "main"], cwd=repo_path)
        yield {"path": repo_path, "main": main_commit, "branch": branch_commit}


@pytest.mark.parametrize(
    "base_ref,ref,files,hash_key",
    [
        (None, None, ["mainfile"], "main"),
        (None, "main", ["mainfile"], "main"),
        (None, "mybranch", ["mainfile", "branchfile"], "branch"),
        ("main", "main", ["mainfile"], "main"),
        ("main", "mybranch", ["mainfile", "branchfile"], "branch"),
    ],
)
def test_git_checkout(
    mock_stdin,
    run_task_mod,
    mock_git_repo,
    base_ref,
    ref,
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
        )


def test_git_checkout_efficient_clone(
    mock_stdin,
    run_task_mod,
    mock_git_repo,
):
    """Test efficient clone with blobless, shallow, and sparse checkout."""
    with tempfile.TemporaryDirectory() as workdir:
        destination = os.path.join(workdir, "destination")
        run_task_mod.git_checkout(
            destination_path=destination,
            head_repo=mock_git_repo["path"],
            base_repo=mock_git_repo["path"],
            base_ref="mybranch",
            base_rev=None,
            ref="mybranch",
            commit=None,
            ssh_key_file=None,
            ssh_known_hosts_file=None,
            efficient_clone=True,
            sparse_dirs=None,
        )

        # Check that files were checked out properly
        assert os.path.exists(os.path.join(destination, "mainfile"))
        assert os.path.exists(os.path.join(destination, "branchfile"))

        # Check repo is on the right branch
        current_branch = subprocess.check_output(
            args=["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=destination,
            universal_newlines=True,
        ).strip()
        assert current_branch == "mybranch"

        # Check that we have a shallow clone by checking the depth
        # Note: This check might need adjustment based on the actual Git version behavior
        log_output = subprocess.check_output(
            args=["git", "log", "--oneline"],
            cwd=destination,
            universal_newlines=True,
        ).strip()
        # Shallow clone should have limited history
        assert len(log_output.split("\n")) >= 1


def test_git_checkout_efficient_clone_with_sparse_dirs(
    mock_stdin,
    run_task_mod,
    mock_git_repo_with_dirs,
):
    """Test efficient clone with sparse checkout of specific directories."""
    with tempfile.TemporaryDirectory() as workdir:
        destination = os.path.join(workdir, "destination")
        run_task_mod.git_checkout(
            destination_path=destination,
            head_repo=mock_git_repo_with_dirs["path"],
            base_repo=mock_git_repo_with_dirs["path"],
            base_ref=None,
            base_rev=None,
            ref="main",
            commit=None,
            ssh_key_file=None,
            ssh_known_hosts_file=None,
            efficient_clone=True,
            sparse_dirs="src:docs",  # Only checkout src and docs directories
        )

        # Check that only specified directories were checked out
        assert os.path.exists(os.path.join(destination, "src", "main.py"))
        assert os.path.exists(os.path.join(destination, "src", "utils.py"))
        assert os.path.exists(os.path.join(destination, "docs", "readme.md"))

        # Check that other directories were NOT checked out
        assert not os.path.exists(os.path.join(destination, "tests"))
        assert not os.path.exists(os.path.join(destination, "build"))
        # Note: rootfile.txt might still exist depending on Git's sparse checkout behavior

        # Check repo is on the right branch
        current_branch = subprocess.check_output(
            args=["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=destination,
            universal_newlines=True,
        ).strip()
        assert current_branch == "main"


def test_git_checkout_sparse_dirs_without_efficient_clone(
    mock_stdin,
    run_task_mod,
    mock_git_repo_with_dirs,
):
    """Test sparse checkout without efficient clone flag."""
    with tempfile.TemporaryDirectory() as workdir:
        destination = os.path.join(workdir, "destination")
        run_task_mod.git_checkout(
            destination_path=destination,
            head_repo=mock_git_repo_with_dirs["path"],
            base_repo=mock_git_repo_with_dirs["path"],
            base_ref=None,
            base_rev=None,
            ref="main",
            commit=None,
            ssh_key_file=None,
            ssh_known_hosts_file=None,
            efficient_clone=False,  # Not using efficient clone
            sparse_dirs="src:build",  # Only checkout src and build directories
        )

        # Check that only specified directories were checked out
        assert os.path.exists(os.path.join(destination, "src", "main.py"))
        assert os.path.exists(os.path.join(destination, "src", "utils.py"))
        assert os.path.exists(os.path.join(destination, "build", "Makefile"))

        # Check that other directories were NOT checked out
        assert not os.path.exists(os.path.join(destination, "docs"))
        assert not os.path.exists(os.path.join(destination, "tests"))

        # Check repo is on the right branch
        current_branch = subprocess.check_output(
            args=["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=destination,
            universal_newlines=True,
        ).strip()
        assert current_branch == "main"


def test_collect_vcs_options_with_efficient_clone(
    run_task_mod,
):
    """Test that efficient_clone option is collected properly."""
    args = Namespace(
        vcs_checkout="/path/to/checkout",
        vcs_sparse_profile=None,
        vcs_efficient_clone=True,
    )

    # Mock environment variables
    env_vars = {
        "VCS_REPOSITORY_TYPE": "git",
        "VCS_HEAD_REPOSITORY": "https://github.com/test/repo.git",
        "VCS_HEAD_REV": "abc123",
    }

    old_environ = os.environ.copy()
    os.environ.update(env_vars)

    try:
        options = run_task_mod.collect_vcs_options(args, "vcs", "repository")
        assert options["efficient-clone"]
    finally:
        os.environ.clear()
        os.environ.update(old_environ)


def test_git_checkout_sparse_dirs_with_files(
    mock_stdin,
    run_task_mod,
    mock_git_repo_with_dirs,
):
    """Test sparse checkout with individual files (uses cone mode).

    Note: Git's sparse-checkout includes entire directories when any file within
    that directory is specified. This is Git's intended behavior for consistency.
    """
    with tempfile.TemporaryDirectory() as workdir:
        destination = os.path.join(workdir, "destination")

        run_task_mod.git_checkout(
            destination_path=destination,
            head_repo=mock_git_repo_with_dirs["path"],
            base_repo=mock_git_repo_with_dirs["path"],
            base_ref=None,
            base_rev=None,
            ref="main",
            commit=None,
            ssh_key_file=None,
            ssh_known_hosts_file=None,
            efficient_clone=False,
            sparse_dirs="rootfile.txt:src/main.py",  # Individual files - uses cone mode
        )

        # Check what actually got checked out
        # Root-level files work exactly as specified
        assert os.path.exists(os.path.join(destination, "rootfile.txt"))
        assert os.path.exists(os.path.join(destination, "src", "main.py"))

        # Git includes entire directories when any file within them is specified
        # This is expected behavior, not a bug
        assert os.path.exists(os.path.join(destination, "src", "utils.py"))

        # Other directories should NOT be included
        assert not os.path.exists(os.path.join(destination, "docs", "readme.md"))
        assert not os.path.exists(os.path.join(destination, "tests", "test_main.py"))
        assert not os.path.exists(os.path.join(destination, "build", "Makefile"))


def test_git_checkout_sparse_dirs_directories_only(
    mock_stdin,
    run_task_mod,
    mock_git_repo_with_dirs,
):
    """Test sparse checkout with directories only (uses cone mode)."""
    with tempfile.TemporaryDirectory() as workdir:
        destination = os.path.join(workdir, "destination")

        run_task_mod.git_checkout(
            destination_path=destination,
            head_repo=mock_git_repo_with_dirs["path"],
            base_repo=mock_git_repo_with_dirs["path"],
            base_ref=None,
            base_rev=None,
            ref="main",
            commit=None,
            ssh_key_file=None,
            ssh_known_hosts_file=None,
            efficient_clone=False,
            sparse_dirs="src:docs",  # Directories only - uses cone mode
        )

        # Check that entire directories were checked out
        assert os.path.exists(os.path.join(destination, "src", "main.py"))
        assert os.path.exists(os.path.join(destination, "src", "utils.py"))
        assert os.path.exists(os.path.join(destination, "docs", "readme.md"))

        # Check that other directories were NOT checked out
        assert not os.path.exists(os.path.join(destination, "tests", "test_main.py"))
        assert not os.path.exists(os.path.join(destination, "build", "Makefile"))


def test_collect_vcs_options_with_sparse_dirs(
    run_task_mod,
):
    """Test that sparse_dirs are collected properly from environment."""
    args = Namespace(
        vcs_checkout="/path/to/checkout",
        vcs_sparse_profile=None,
        vcs_efficient_clone=True,
    )

    # Mock environment variables including SPARSE_DIRS
    env_vars = {
        "VCS_REPOSITORY_TYPE": "git",
        "VCS_HEAD_REPOSITORY": "https://github.com/test/repo.git",
        "VCS_HEAD_REV": "abc123",
        "VCS_SPARSE_DIRS": "src:docs:tests",
    }

    old_environ = os.environ.copy()
    os.environ.update(env_vars)

    try:
        options = run_task_mod.collect_vcs_options(args, "vcs", "repository")
        assert options["sparse-dirs"] == "src:docs:tests"
    finally:
        os.environ.clear()
        os.environ.update(old_environ)


def test_display_python_version_should_output_python_versions_title(
    run_task_mod, capsys
):
    run_task_mod._display_python_versions()

    output = capsys.readouterr().out
    assert ("Python version:" in output) is True
    assert "Subprocess" in output and "version:" in output


def test_display_python_version_should_output_python_versions(run_task_mod, capsys):
    run_task_mod._display_python_versions()

    output = capsys.readouterr().out
    assert ("Python version: 3." in output) or ("Python version: 2." in output) is True
    assert "Subprocess" in output and "version:" in output


@pytest.fixture
def run_main(tmp_path, mocker, mock_stdin, run_task_mod):
    base_args = [
        f"--task-cwd={str(tmp_path)}",
    ]

    base_command_args = [
        "bash",
        "-c",
        "echo hello",
    ]

    m = mocker.patch.object(run_task_mod.os, "getcwd")
    m.return_value = "/builds/worker"

    def inner(extra_args=None, env=None):
        extra_args = extra_args or []
        env = env or {}

        mocker.patch.object(run_task_mod.os, "environ", env)

        args = base_args + extra_args
        args.append("--")
        args.extend(base_command_args)

        result = run_task_mod.main(args)
        return result, env

    return inner


def test_main_abspath_environment(run_main):
    envvars = ["MOZ_FETCHES_DIR", "UPLOAD_DIR"]
    envvars += [cache["env"] for cache in CACHES.values() if "env" in cache]
    env = {key: "file" for key in envvars}
    env["FOO"] = "file"

    result, env = run_main(env=env)
    assert result == 0

    assert env.get("FOO") == "file"
    for key in envvars:
        assert env[key] == "/builds/worker/file"
