import functools
import json
import os
import signal
import site
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
from argparse import Namespace
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from unittest.mock import Mock

import pytest

import taskgraph
from taskgraph.util.caches import CACHES

from .conftest import nowin


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
            "--prefix",
            site.getuserbase(),
            "--require-hashes",
            "-r",
            str(req),
        ],
    )


@pytest.mark.parametrize(
    "args,env,extra_expected",
    [
        pytest.param(
            {},
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
            id="hg",
        ),
        pytest.param(
            {"myrepo_shallow_clone": True},
            {
                "REPOSITORY_TYPE": "git",
                "HEAD_REPOSITORY": "https://github.com/test/repo.git",
                "HEAD_REV": "abc123",
                "BASE_REF": "refs/heads/main",
            },
            {"shallow-clone": True},
            id="git_with_shallow_clone",
        ),
        pytest.param(
            {"myrepo_sparse_profile": "profiles/docs"},
            {
                "REPOSITORY_TYPE": "git",
                "HEAD_REPOSITORY": "https://github.com/test/repo.git",
                "HEAD_REV": "abc123",
                "SPARSE_PATTERNS": '["/docs", "*.md"]',
            },
            {"sparse-profile": "profiles/docs", "sparse-patterns": ["/docs", "*.md"]},
            id="git_with_sparse_profile",
        ),
    ],
)
def test_collect_vcs_options(
    monkeypatch,
    run_task_mod,
    args,
    env,
    extra_expected,
):
    name = "myrepo"
    checkout = "checkout"

    monkeypatch.setattr(os, "environ", {})
    for k, v in env.items():
        monkeypatch.setenv(f"{name.upper()}_{k.upper()}", v)

    args.setdefault(f"{name}_checkout", checkout)
    args.setdefault(f"{name}_shallow_clone", False)
    args = Namespace(**args)

    result = run_task_mod.collect_vcs_options(args, name, name)

    expected = {
        "base-repo": env.get("BASE_REPOSITORY"),
        "base-rev": env.get("BASE_REV"),
        "base-ref": env.get("BASE_REF"),
        "checkout": os.path.join(os.getcwd(), "checkout"),
        "env-prefix": name.upper(),
        "head-repo": env.get("HEAD_REPOSITORY"),
        "name": name,
        "pip-requirements": None,
        "project": name,
        "head-ref": env.get("HEAD_REF"),
        "head-rev": env.get("HEAD_REV"),
        "repo-type": env.get("REPOSITORY_TYPE"),
        "shallow-clone": False,
        "sparse-profile": None,
        "sparse-patterns": None,
        "ssh-secret-name": env.get("SSH_SECRET_NAME"),
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

    real_popen = subprocess.Popen

    def _Popen(
        args,
        **kwargs,
    ):
        kwargs["stdin"] = subprocess.PIPE
        proc = real_popen(
            ["cat"],
            **kwargs,
        )
        proc.stdin.write(output_str)
        return proc

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

        def _commit_file(message, filename, content):
            filepath = os.path.join(repo, filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as fout:
                fout.write(content)
            subprocess.check_call(["git", "add", filename], cwd=repo_path)
            subprocess.check_call(["git", "commit", "-m", message], cwd=repo_path)
            return git_current_rev(repo_path)

        # Commit mainfile (to main branch)
        main_commits = [_commit_file("Initial commit", "mainfile", "foo")]

        # New branch mybranch
        subprocess.check_call(["git", "checkout", "-b", "mybranch"], cwd=repo_path)
        # Create two commits to mybranch
        branch_commits = []
        branch_commits.append(
            _commit_file("Add file in mybranch2", "branchfile", "bar")
        )
        branch_commits.append(
            _commit_file("Update file in mybranch", "branchfile", "baz")
        )

        # Set current branch back to main
        subprocess.check_call(["git", "checkout", "main"], cwd=repo_path)
        yield {"path": repo_path, "main": main_commits, "branch": branch_commits}


@pytest.mark.parametrize(
    "base_rev,head_ref,files,hash_key,exc",
    [
        (None, None, ["mainfile"], "main", AssertionError),
        (None, "main", ["mainfile"], "main", None),
        (None, "mybranch", ["mainfile", "branchfile"], "branch", None),
        ("main", "main", ["mainfile"], "main", None),
        ("main", "mybranch", ["mainfile", "branchfile"], "branch", None),
    ],
)
def test_git_checkout(
    mock_stdin,
    run_task_mod,
    mock_git_repo,
    tmp_path,
    base_rev,
    head_ref,
    files,
    hash_key,
    exc,
):
    destination = tmp_path / "destination"
    run_git_checkout = functools.partial(
        run_task_mod.git_checkout,
        destination_path=destination,
        head_repo=mock_git_repo["path"],
        base_repo=mock_git_repo["path"],
        base_rev=base_rev,
        head_ref=head_ref,
        head_rev=None,
        ssh_key_file=None,
        ssh_known_hosts_file=None,
    )
    if exc:
        with pytest.raises(exc):
            run_git_checkout()
        return

    run_git_checkout()

    # Check desired files exist
    for filename in files:
        assert os.path.exists(os.path.join(destination, filename))

    # Check repo is on the right branch
    if head_ref:
        current_branch = subprocess.check_output(
            args=["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=destination,
            universal_newlines=True,
        ).strip()
        assert current_branch == head_ref

        current_rev = git_current_rev(destination)
        assert current_rev == mock_git_repo[hash_key][-1]


@pytest.mark.parametrize(
    "env_value,expected",
    (
        pytest.param(None, "0", id="default"),
        pytest.param("1", "1", id="disabled"),
        pytest.param("4", "4", id="pinned"),
    ),
)
def test_git_checkout_enables_parallel_checkout(
    monkeypatch, mock_stdin, run_task_mod, mock_git_repo, tmp_path, env_value, expected
):
    monkeypatch.delenv("RUN_TASK_GIT_CHECKOUT_WORKERS", raising=False)
    if env_value is not None:
        monkeypatch.setenv("RUN_TASK_GIT_CHECKOUT_WORKERS", env_value)
    destination = tmp_path / "destination"
    run_task_mod.git_checkout(
        destination_path=destination,
        head_repo=mock_git_repo["path"],
        base_repo=mock_git_repo["path"],
        base_rev=None,
        head_ref="main",
        head_rev=None,
        ssh_key_file=None,
        ssh_known_hosts_file=None,
    )

    workers = subprocess.check_output(
        ["git", "config", "--global", "--get", "checkout.workers"],
        cwd=destination,
        universal_newlines=True,
    ).strip()
    # 0 means one worker per logical core, see
    # https://git-scm.com/docs/git-config#Documentation/git-config.txt-checkoutworkers
    assert workers == expected


@pytest.mark.parametrize(
    "head_ref,head_rev_index",
    (
        pytest.param("mybranch", 1, id="head"),
        pytest.param("mybranch", 0, id="non tip"),
        pytest.param(None, 0, id="non tip without head_ref"),
    ),
)
def test_git_checkout_with_commit(
    mock_stdin,
    run_task_mod,
    mock_git_repo,
    tmp_path,
    head_ref,
    head_rev_index,
):
    destination = tmp_path / "destination"
    base_rev = mock_git_repo["main"][-1]
    head_rev = mock_git_repo["branch"][head_rev_index]
    run_task_mod.git_checkout(
        destination_path=str(destination),
        head_repo=mock_git_repo["path"],
        base_repo=mock_git_repo["path"],
        base_rev=base_rev,
        head_ref=head_ref,
        head_rev=head_rev,
        ssh_key_file=None,
        ssh_known_hosts_file=None,
    )

    current_rev = subprocess.check_output(
        args=["git", "rev-parse", "HEAD"],
        cwd=str(destination),
        universal_newlines=True,
    ).strip()
    assert current_rev == head_rev


def test_git_checkout_shallow(
    mock_stdin,
    run_task_mod,
    mock_git_repo,
    tmp_path,
):
    destination = tmp_path / "destination"

    # Git ignores `--depth` when cloning from local directories, so use file://
    # protocol to force shallow clone.
    repo_url = f"file://{mock_git_repo['path']}"
    base_rev = mock_git_repo["main"][-1]
    head_rev = mock_git_repo["branch"][-1]

    # Use shallow clone with head_ref != head_rev
    run_task_mod.git_checkout(
        destination_path=str(destination),
        head_repo=repo_url,
        base_repo=repo_url,
        base_rev=base_rev,
        head_ref="mybranch",
        head_rev=head_rev,
        ssh_key_file=None,
        ssh_known_hosts_file=None,
        shallow=True,
    )
    shallow_file = destination / ".git" / "shallow"
    assert shallow_file.exists()

    # Verify we're on the correct commit
    final_rev = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=str(destination),
        universal_newlines=True,
    ).strip()
    assert final_rev == head_rev

    # Verify both base_rev and head_rev are available.
    for sha in (base_rev, head_rev):
        result = subprocess.run(
            ["git", "cat-file", "-t", sha],
            cwd=str(destination),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Commit {sha} should be available"
        assert result.stdout.strip() == "commit"


def test_git_fetch_shallow(
    mock_stdin,
    run_task_mod,
    mock_git_repo,
    tmp_path,
):
    destination = tmp_path / "destination"

    # Git ignores `--depth` when cloning from local directories, so use file://
    # protocol to force shallow clone.
    repo_url = f"file://{mock_git_repo['path']}"

    run_task_mod.run_command(
        b"vcs",
        [
            "git",
            "clone",
            "--depth=1",
            "--no-checkout",
            repo_url,
            str(destination),
        ],
    )
    shallow_file = destination / ".git" / "shallow"
    assert shallow_file.exists()

    # Verify base_rev doesn't exist yet
    base_rev = mock_git_repo["branch"][-1]
    result = subprocess.run(
        ["git", "cat-file", "-t", base_rev],
        cwd=str(destination),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0

    run_task_mod.git_fetch(str(destination), base_rev, remote=repo_url, shallow=True)

    # Verify base_rev is now available
    result = subprocess.run(
        ["git", "cat-file", "-t", base_rev],
        cwd=str(destination),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "commit"


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


@pytest.fixture
def perf(run_task_mod):
    return run_task_mod.PerfRecorder("vcs")


def test_perfrecorder_record(perf):
    with perf.record("op"):
        pass
    assert len(perf.optimes) == 1
    name, duration = perf.optimes[0]
    assert name == "op"
    assert duration >= 0


def test_perfrecorder_record_multiple(perf):
    with perf.record("overall", "overall_clone"):
        pass
    assert len(perf.optimes) == 2
    assert perf.optimes[0][0] == "overall"
    assert perf.optimes[1][0] == "overall_clone"
    assert perf.optimes[0][1] == perf.optimes[1][1]


def test_perfrecorder_record_errored(perf):
    with pytest.raises(ValueError):
        with perf.record("op"):
            raise ValueError("boom")
    assert perf.optimes[0][0] == "op_errored"


def test_perfrecorder_start_stop(perf):
    perf.start("op")
    perf.stop()
    assert len(perf.optimes) == 1
    name, duration = perf.optimes[0]
    assert name == "op"
    assert duration >= 0


def test_perfrecorder_emit_no_instance_type(monkeypatch, perf, capsys):
    monkeypatch.delenv("TASKCLUSTER_INSTANCE_TYPE", raising=False)
    perf.optimes.extend([("overall", 1.5)])
    perf.emit()
    assert capsys.readouterr().out == ""


def test_perfrecorder_emit(monkeypatch, perf, capsys):
    monkeypatch.setenv("TASKCLUSTER_INSTANCE_TYPE", "m5.4xlarge")
    perf.optimes.extend([("overall_clone", 42.0), ("clone", 10.0)])
    perf.emit()

    out = capsys.readouterr().out
    assert out.startswith("PERFHERDER_DATA: ")
    data = json.loads(out[len("PERFHERDER_DATA: ") :])

    assert data["framework"] == {"name": "vcs"}
    assert len(data["suites"]) == 2

    overall, clone = data["suites"]
    assert overall == {
        "name": "overall_clone",
        "value": 42.0,
        "lowerIsBetter": True,
        "shouldAlert": False,
        "extraOptions": ["m5.4xlarge"],
        "subtests": [],
    }
    assert clone["name"] == "clone"
    assert clone["value"] == 10.0


@nowin
def test_main_abspath_environment(mocker, run_main):
    envvars = ["GECKO_PATH", "MOZ_FETCHES_DIR", "UPLOAD_DIR"]
    envvars += [cache["env"] for cache in CACHES.values() if "env" in cache]
    env = {key: "file" for key in envvars}
    env["FOO"] = "file"

    mocker.patch("os.sep", "\\")
    env["MOZ_PYTHON_HOME"] = "dir\\python"
    env["MOZ_UV_HOME"] = "dir/uv"

    result, env = run_main(env=env)
    assert result == 0

    assert env.get("FOO") == "file"
    assert env.get("MOZ_PYTHON_HOME") == "/builds/worker/dir/python"
    assert env.get("MOZ_UV_HOME") == "/builds/worker/dir/uv"
    for key in envvars:
        assert env[key] == "/builds/worker/file"


def test_pre_task_run_hook_sets_env(run_main, tmp_path):
    hook = tmp_path / "hook.py"
    hook.write_text("import os\nos.environ['HOOK_RAN'] = '1'\n")

    result, env = run_main(env={"RUN_TASK_PRE_COMMAND_HOOK": str(hook)})

    assert result == 0
    assert env.get("HOOK_RAN") == "1"


def test_pre_task_run_hook_failure_aborts_before_task(
    run_main, patch_run_command, tmp_path, capsys
):
    called_with = patch_run_command()
    hook = tmp_path / "hook.py"
    hook.write_text("raise RuntimeError('boom')")

    with pytest.raises(SystemExit) as excinfo:
        run_main(env={"RUN_TASK_PRE_COMMAND_HOOK": str(hook)})

    assert excinfo.value.code == 1
    assert called_with == []

    output = capsys.readouterr().out
    assert "script" in output and "failed" in output
    assert "RuntimeError: boom" in output
    assert "hook.py" in output and "line 1" in output


def test_pre_task_run_hook_output_is_prefixed(run_main, tmp_path, capsys):
    hook = tmp_path / "hook.py"
    hook.write_text("print('hello')\nprint('world')\n")

    result, env = run_main(env={"RUN_TASK_PRE_COMMAND_HOOK": str(hook)})
    assert result == 0

    lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("[script ") and line.endswith(("] hello", "] world"))
    ]
    assert len(lines) == 2


def test_no_pre_task_run_hook_is_noop(run_main):
    result, env = run_main(env={})
    assert result == 0


def test_startup_hook_sets_env(run_main, tmp_path):
    hook = tmp_path / "hook.py"
    hook.write_text("import os\nos.environ['HOOK_RAN'] = '1'\n")

    result, env = run_main(env={"RUN_TASK_STARTUP_HOOK": str(hook)})

    assert result == 0
    assert env.get("HOOK_RAN") == "1"


def test_startup_hook_runs_before_vcs_checkout(
    mocker, run_main, run_task_mod, tmp_path
):
    hook = tmp_path / "hook.py"
    hook.write_text("import os\nos.environ['HOOK_RAN'] = '1'\n")

    seen = []
    mocker.patch.object(
        run_task_mod,
        "vcs_checkout_from_args",
        side_effect=lambda repo: seen.append(run_task_mod.os.environ.get("HOOK_RAN")),
    )

    result, env = run_main(env={"RUN_TASK_STARTUP_HOOK": str(hook)})

    assert result == 0
    assert seen == ["1"]


@nowin
def test_startup_hook_env_is_normalized(run_main, tmp_path):
    hook = tmp_path / "hook.py"
    hook.write_text("import os\nos.environ['UPLOAD_DIR'] = 'artifacts'\n")

    result, env = run_main(env={"RUN_TASK_STARTUP_HOOK": str(hook)})

    assert result == 0
    assert env.get("UPLOAD_DIR") == "/builds/worker/artifacts"


def test_startup_hook_failure_aborts_before_checkout(
    mocker, run_main, run_task_mod, patch_run_command, tmp_path, capsys
):
    called_with = patch_run_command()
    checkout = mocker.patch.object(run_task_mod, "vcs_checkout_from_args")
    hook = tmp_path / "hook.py"
    hook.write_text("raise RuntimeError('boom')")

    with pytest.raises(SystemExit) as excinfo:
        run_main(env={"RUN_TASK_STARTUP_HOOK": str(hook)})

    assert excinfo.value.code == 1
    assert called_with == []
    checkout.assert_not_called()

    output = capsys.readouterr().out
    assert "script" in output and "failed" in output
    assert "RuntimeError: boom" in output
    assert "hook.py" in output and "line 1" in output


def test_startup_hook_output_is_prefixed(run_main, tmp_path, capsys):
    hook = tmp_path / "hook.py"
    hook.write_text("print('hello')\nprint('world')\n")

    result, env = run_main(env={"RUN_TASK_STARTUP_HOOK": str(hook)})
    assert result == 0

    lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("[script ") and line.endswith(("] hello", "] world"))
    ]
    assert len(lines) == 2


def test_startup_hook_runs_before_pre_command_hook(run_main, tmp_path):
    startup = tmp_path / "startup.py"
    startup.write_text("import os\nos.environ['ORDER'] = 'startup'\n")
    pre_command = tmp_path / "pre_command.py"
    pre_command.write_text("import os\nos.environ['ORDER'] += ',pre-command'\n")

    result, env = run_main(
        env={
            "RUN_TASK_STARTUP_HOOK": str(startup),
            "RUN_TASK_PRE_COMMAND_HOOK": str(pre_command),
        }
    )

    assert result == 0
    assert env.get("ORDER") == "startup,pre-command"


SPARSE_REPO_FILES = [
    "a/deep/two.txt",
    "a/one.txt",
    "b/three.txt",
    "c/four.md",
    "root.txt",
]


@pytest.fixture(scope="session")  # Tests shouldn't change this repo
def sparse_git_repo():
    "Repository with nested directories for sparse checkouts"
    with tempfile.TemporaryDirectory() as repo:
        repo_path = str(repo)
        subprocess.check_call(["git", "init", "-b", "main"], cwd=repo_path)
        subprocess.check_call(["git", "config", "user.name", "pytest"], cwd=repo_path)
        subprocess.check_call(
            ["git", "config", "user.email", "py@tes.t"], cwd=repo_path
        )
        subprocess.check_call(
            ["git", "config", "uploadpack.allowFilter", "true"], cwd=repo_path
        )
        subprocess.check_call(
            ["git", "config", "uploadpack.allowAnySHA1InWant", "true"], cwd=repo_path
        )
        for filename in SPARSE_REPO_FILES:
            filepath = os.path.join(repo_path, filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as fout:
                fout.write(filename)
        subprocess.check_call(["git", "add", "."], cwd=repo_path)
        subprocess.check_call(["git", "commit", "-m", "Initial commit"], cwd=repo_path)
        yield {"url": f"file://{repo_path}", "rev": git_current_rev(repo_path)}


def materialized_files(destination):
    out = subprocess.check_output(["git", "ls-files", "-t", "-z"], cwd=str(destination))
    return sorted(
        entry[2:].decode() for entry in out.split(b"\0") if entry and entry[:1] != b"S"
    )


def git_config(destination, key):
    result = subprocess.run(
        ["git", "config", "--get", key],
        cwd=str(destination),
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def sparse_git_checkout(run_task_mod, repo, destination, patterns=None):
    run_task_mod.git_checkout(
        destination_path=str(destination),
        head_repo=repo["url"],
        base_repo=repo["url"],
        base_rev=None,
        head_ref="main",
        head_rev=repo["rev"],
        ssh_key_file=None,
        ssh_known_hosts_file=None,
        shallow=True,
        sparse_profile="profiles/test" if patterns else None,
        sparse_patterns=patterns,
    )


def test_git_checkout_sparse(mock_stdin, run_task_mod, sparse_git_repo, tmp_path):
    destination = tmp_path / "destination"
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination, ["/b", "*.md"])

    assert materialized_files(destination) == ["b/three.txt", "c/four.md"]
    assert git_config(destination, "core.sparseCheckout") == "true"
    assert git_config(destination, "core.sparseCheckoutCone") != "true"
    assert git_config(destination, "remote.origin.promisor") == "true"
    assert git_current_rev(destination) == sparse_git_repo["rev"]


@pytest.mark.parametrize(
    "args,env,error",
    (
        pytest.param(
            {"myrepo_sparse_profile": "profiles/test"},
            {},
            "must be given together",
            id="option_without_patterns",
        ),
        pytest.param(
            {},
            {"MYREPO_SPARSE_PATTERNS": '["/a"]'},
            "must be given together",
            id="patterns_without_option",
        ),
        pytest.param(
            {"myrepo_sparse_profile": "profiles/test"},
            {"MYREPO_SPARSE_PATTERNS": "[]"},
            "holds no patterns",
            id="empty_patterns",
        ),
        pytest.param(
            {"myrepo_sparse_profile": "profiles/test"},
            {"MYREPO_SPARSE_PATTERNS": "/a\n*.md\n"},
            "is not a JSON list",
            id="patterns_not_json",
        ),
        pytest.param(
            {"myrepo_sparse_profile": "profiles/test"},
            {"MYREPO_SPARSE_PATTERNS": '["/a", ""]'},
            "must be a JSON list of non-empty",
            id="empty_pattern_string",
        ),
        pytest.param(
            {"myrepo_sparse_profile": "profiles/test", "myrepo_checkout": None},
            {"MYREPO_SPARSE_PATTERNS": '["/a"]'},
            "needs --myrepo-checkout",
            id="no_checkout",
        ),
    ),
)
def test_vcs_checkout_from_args_sparse_validation(
    monkeypatch, run_task_mod, args, env, error
):
    environ = {
        "MYREPO_REPOSITORY_TYPE": "git",
        "MYREPO_HEAD_REPOSITORY": "https://github.com/test/repo.git",
        "MYREPO_HEAD_REV": "abc123",
    }
    environ.update(env)
    monkeypatch.setattr(os, "environ", environ)
    args.setdefault("myrepo_checkout", "checkout")
    args.setdefault("myrepo_shallow_clone", True)

    with pytest.raises(RuntimeError, match=error):
        options = run_task_mod.collect_vcs_options(
            Namespace(**args), "myrepo", "myrepo"
        )
        run_task_mod.vcs_checkout_from_args(options)


def test_git_checkout_sparse_widens_on_full_task(
    mock_stdin, run_task_mod, sparse_git_repo, tmp_path
):
    destination = tmp_path / "destination"
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination, ["/b", "*.md"])
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination)

    assert git_config(destination, "core.sparseCheckout") != "true"
    assert materialized_files(destination) == SPARSE_REPO_FILES


def test_git_checkout_sparse_widens_over_modified_files(
    mock_stdin, run_task_mod, sparse_git_repo, tmp_path
):
    destination = tmp_path / "destination"
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination, ["/b", "*.md"])
    (destination / "b" / "three.txt").write_text("modified")
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination)

    assert git_config(destination, "core.sparseCheckout") != "true"
    assert materialized_files(destination) == SPARSE_REPO_FILES
    assert (destination / "b" / "three.txt").read_text() == "b/three.txt"


def test_git_checkout_sparse_adds_over_modified_files(
    mock_stdin, run_task_mod, sparse_git_repo, tmp_path
):
    destination = tmp_path / "destination"
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination, ["/b"])
    (destination / "b" / "three.txt").write_text("modified")
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination, ["/a/deep"])

    assert materialized_files(destination) == [
        "a/deep/two.txt",
        "a/one.txt",
        "b/three.txt",
        "root.txt",
    ]
    assert (destination / "b" / "three.txt").read_text() == "b/three.txt"


def test_git_checkout_sparse_on_full_cache_stays_full(
    mock_stdin, run_task_mod, sparse_git_repo, tmp_path
):
    destination = tmp_path / "destination"
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination)
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination, ["/b", "*.md"])

    assert git_config(destination, "core.sparseCheckout") is None
    assert materialized_files(destination) == SPARSE_REPO_FILES


def test_git_checkout_sparse_adds_second_profile(
    mock_stdin, run_task_mod, sparse_git_repo, tmp_path
):
    destination = tmp_path / "destination"
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination, ["/b", "*.md"])
    sparse_git_checkout(
        run_task_mod, sparse_git_repo, destination, ["/a/one.txt", "*.md"]
    )

    assert materialized_files(destination) == ["a/one.txt", "b/three.txt", "c/four.md"]
    patterns = subprocess.check_output(
        ["git", "sparse-checkout", "list"], cwd=str(destination), text=True
    ).split()
    assert set(patterns) == {"/b", "*.md", "/a/one.txt"}


def test_git_checkout_sparse_cone(mock_stdin, run_task_mod, sparse_git_repo, tmp_path):
    destination = tmp_path / "destination"
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination, ["/a/deep", "/b"])

    assert git_config(destination, "core.sparseCheckoutCone") == "true"
    assert git_config(destination, "index.sparse") == "true"
    assert materialized_files(destination) == [
        "a/deep/two.txt",
        "a/one.txt",
        "b/three.txt",
        "root.txt",
    ]


def test_git_checkout_sparse_cone_adds_directories(
    mock_stdin, run_task_mod, sparse_git_repo, tmp_path
):
    destination = tmp_path / "destination"
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination, ["/b"])
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination, ["/a/deep"])

    assert git_config(destination, "core.sparseCheckoutCone") == "true"
    assert materialized_files(destination) == [
        "a/deep/two.txt",
        "a/one.txt",
        "b/three.txt",
        "root.txt",
    ]


def test_git_checkout_sparse_cone_converts_for_globs(
    mock_stdin, run_task_mod, sparse_git_repo, tmp_path
):
    destination = tmp_path / "destination"
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination, ["/b"])
    before = materialized_files(destination)
    sparse_git_checkout(run_task_mod, sparse_git_repo, destination, ["*.md"])

    assert git_config(destination, "core.sparseCheckoutCone") == "false"
    after = materialized_files(destination)
    assert set(before) <= set(after)
    assert "c/four.md" in after


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/owner/repo.git", ("owner", "repo")),
        ("https://github.com/owner/repo/", ("owner", "repo")),
        ("git@github.com:owner/repo.git", ("owner", "repo")),
        ("ssh://git@github.com/owner/repo", ("owner", "repo")),
        ("https://github.com.evil/owner/repo", None),
        ("https://example.com/owner/repo", None),
        (None, None),
    ],
)
def test_github_owner_repo(run_task_mod, url, expected):
    assert run_task_mod._github_owner_repo(url) == expected


def test_fetch_github_token(run_task_mod, mocker):
    response = mocker.MagicMock()
    response.__enter__.return_value.read.return_value = b'{"token": "secret"}'
    urlopen = mocker.patch("urllib.request.urlopen", return_value=response)
    permissions = {"contents": "read"}
    assert (
        run_task_mod.fetch_github_token("read", "owner", "repo", permissions)
        == "secret"
    )
    request = urlopen.call_args.args[0]
    assert (
        request.full_url
        == f"{run_task_mod.TASKCLUSTER_PROXY_URL}/api/auth/v1/github/read/owner/repo-token"
    )
    assert request.method == "POST"
    assert json.loads(request.data) == {
        "repositories": ["repo"],
        "permissions": {"contents": "read"},
    }
    assert urlopen.call_args.kwargs == {"timeout": 10}
    urlopen.side_effect = urllib.error.URLError("denied")
    assert run_task_mod.fetch_github_token("read", "owner", "repo", permissions) is None


GITHUB_SECRET = {
    "type": "github-repo-token",
    "app": "read",
    "repo": "https://github.com/Owner/Repo",
}


@pytest.fixture
def github_tokens(run_task_mod, monkeypatch):
    tokens = {}
    monkeypatch.setattr(run_task_mod, "GITHUB_TOKENS", tokens)
    return tokens


def test_fetch_secrets_unset(run_task_mod, monkeypatch, mocker):
    monkeypatch.setattr(os, "environ", {})
    fetch = mocker.patch.object(run_task_mod, "fetch_github_token")
    run_task_mod.fetch_secrets()
    fetch.assert_not_called()
    assert os.environ == {}


@pytest.mark.parametrize(
    "value,error",
    [
        pytest.param("not json", "not valid JSON", id="invalid_json"),
        pytest.param({"type": "github-repo-token"}, "list of objects", id="not_list"),
        pytest.param(["string"], "list of objects", id="not_objects"),
        pytest.param([{**GITHUB_SECRET, "type": "secret"}], "unsupported type"),
        pytest.param([{**GITHUB_SECRET, "extra": 1}], "unknown keys"),
        pytest.param(
            [{**GITHUB_SECRET, "repo": "https://example.com/o/r"}], "GitHub repository"
        ),
        pytest.param(
            [{**GITHUB_SECRET, "repo": 1}], "GitHub repository", id="repo_type"
        ),
        pytest.param(
            [{k: v for k, v in GITHUB_SECRET.items() if k != "repo"}],
            "GitHub repository",
            id="no_repo",
        ),
        pytest.param([{**GITHUB_SECRET, "file": "token"}], "unknown keys", id="file"),
    ],
)
def test_fetch_secrets_invalid(run_task_mod, monkeypatch, mocker, value, error):
    if not isinstance(value, str):
        value = json.dumps(value)
    monkeypatch.setattr(os, "environ", {"RUN_TASK_SECRETS": value})
    fetch = mocker.patch.object(run_task_mod, "fetch_github_token")
    with pytest.raises(RuntimeError, match=error):
        run_task_mod.fetch_secrets()
    fetch.assert_not_called()


def test_fetch_secrets(run_task_mod, monkeypatch, mocker, capsys, github_tokens):
    entries = [
        # Defaults to read access to contents, exported as GITHUB_TOKEN.
        GITHUB_SECRET,
        {
            **GITHUB_SECRET,
            "repo": "https://github.com/owner/other",
            "permissions": {"pull_requests": "write"},
            "env": "EXISTING",
        },
        {**GITHUB_SECRET, "env": "FAILED"},
    ]
    # fetch_secrets sets variables, so keep them out of the real environment.
    monkeypatch.setattr(
        os,
        "environ",
        {"RUN_TASK_SECRETS": json.dumps(entries), "EXISTING": "explicit"},
    )
    fetch = mocker.patch.object(
        run_task_mod, "fetch_github_token", side_effect=["t1", "t2", None]
    )

    run_task_mod.fetch_secrets()

    assert fetch.call_args_list == [
        mocker.call("read", "Owner", "Repo", {"contents": "read"}),
        mocker.call("read", "owner", "other", {"pull_requests": "write"}),
        mocker.call("read", "Owner", "Repo", {"contents": "read"}),
    ]
    assert {k: v for k, v in os.environ.items() if k != "RUN_TASK_SECRETS"} == {
        "GITHUB_TOKEN": "t1",
        "EXISTING": "explicit",
    }
    assert github_tokens == {("owner", "repo"): "t1", ("owner", "other"): "t2"}
    out = capsys.readouterr().out
    assert out.count("fetched github-repo-token for Owner/Repo") == 1
    assert out.count("fetched github-repo-token for owner/other") == 1
    assert "t1" not in out and "t2" not in out


def test_main_exports_secrets(run_main, mocker, run_task_mod, github_tokens):
    mocker.patch.object(run_task_mod, "fetch_github_token", return_value="t1")

    result, env = run_main(env={"RUN_TASK_SECRETS": json.dumps([GITHUB_SECRET])})

    assert result == 0
    assert env["GITHUB_TOKEN"] == "t1"


@pytest.mark.parametrize(
    "minted,env,expected",
    [
        (None, None, None),
        (None, "from-env", "from-env"),
        ("minted", None, "minted"),
        ("minted", "from-env", "minted"),
    ],
)
def test_github_compare(
    run_task_mod, monkeypatch, mocker, github_tokens, minted, env, expected
):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    if env:
        monkeypatch.setenv("GITHUB_TOKEN", env)
    if minted:
        github_tokens[("owner", "repo")] = minted
    sha = "a" * 40
    response = mocker.MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {"status": "diverged", "merge_base_commit": {"sha": sha}}
    ).encode()
    urlopen = mocker.patch("urllib.request.urlopen", return_value=response)
    assert run_task_mod.github_compare("owner", "repo", "refs/heads/main", "abc") == (
        "diverged",
        sha,
    )
    request = urlopen.call_args.args[0]
    assert (
        request.full_url
        == "https://api.github.com/repos/owner/repo/compare/refs%2Fheads%2Fmain...abc?per_page=1"
    )
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == (
        f"Bearer {expected}" if expected else None
    )
    assert urlopen.call_args.kwargs == {"timeout": 10}
    urlopen.side_effect = urllib.error.URLError("unavailable")
    assert run_task_mod.github_compare("owner", "repo", "main", "abc") is None


@pytest.mark.parametrize(
    "base_rev,base_ref,head_ref,fork,comparisons,expected,bases,default_calls",
    [
        ("old", "main", "feature", False, [("ahead", "old")], None, ["old"], 0),
        (
            "old",
            "main",
            "feature",
            False,
            [("diverged", "merge")],
            "merge",
            ["old"],
            0,
        ),
        (
            "old",
            "main",
            "main",
            True,
            [("diverged", "merge")],
            "merge",
            ["old"],
            0,
        ),
        ("old", "feature", "feature", False, [("ahead", "old")], None, ["old"], 0),
        (
            "old",
            "refs/heads/feature",
            "feature",
            False,
            [("diverged", "old-base"), ("ahead", "merge")],
            "merge",
            ["old", "main"],
            1,
        ),
        (
            "old",
            "main",
            "refs/heads/main",
            False,
            [("diverged", "old-base")],
            "old-base",
            ["old"],
            1,
        ),
        (
            "0" * 40,
            "source",
            "feature",
            False,
            [("ahead", "merge")],
            "merge",
            ["source"],
            0,
        ),
        ("0" * 40, None, "feature", False, [("ahead", "merge")], "merge", ["main"], 1),
        ("old", "main", "refs/tags/v1", False, [], None, [], 0),
        ("old", "feature", "feature", False, [None], None, ["old"], 0),
        (None, "main", "feature", False, [None], None, ["main"], 0),
        ("old", "main", "feature", False, [("identical", "old")], None, ["old"], 0),
        (None, None, "main", False, [], None, [], 1),
    ],
)
def test_derive_base_rev(
    run_task_mod,
    mocker,
    base_rev,
    base_ref,
    head_ref,
    fork,
    comparisons,
    expected,
    bases,
    default_calls,
):
    compare = mocker.patch.object(
        run_task_mod, "github_compare", side_effect=comparisons
    )
    default = mocker.patch.object(run_task_mod, "_default_branch", return_value="main")
    base_repo = "https://github.com/owner/repo"
    head_repo = "https://github.com/fork/repo" if fork else base_repo
    assert (
        run_task_mod.derive_base_rev(
            ("owner", "repo"),
            base_repo,
            head_repo,
            base_rev,
            base_ref,
            head_ref,
            "head",
        )
        == expected
    )
    assert compare.call_args_list == [
        mocker.call("owner", "repo", base, "head") for base in bases
    ]
    assert default.call_count == default_calls


@pytest.mark.parametrize(
    "output,expected",
    [("ref: refs/heads/main\tHEAD\nabc\tHEAD\n", "main"), ("abc\tHEAD\n", None)],
)
def test_default_branch(run_task_mod, mocker, output, expected):
    check = mocker.patch("subprocess.check_output", return_value=output)
    assert run_task_mod._default_branch("https://github.com/owner/repo") == expected
    check.assert_called_once_with(
        ["git", "ls-remote", "--symref", "https://github.com/owner/repo", "HEAD"],
        universal_newlines=True,
        timeout=60,
    )
    check.side_effect = subprocess.TimeoutExpired("git", 60)
    assert run_task_mod._default_branch("https://github.com/owner/repo") is None


@pytest.mark.parametrize(
    "repo_type,repo,base_rev,base_ref,expected",
    [
        ("git", "https://example.com/owner/repo", "old", "main", False),
        ("hg", "https://github.com/owner/repo", "old", "main", False),
        ("git", "https://github.com/owner/repo", None, None, False),
        ("git", "https://github.com/owner/repo", "old", None, True),
        ("git", "https://github.com/owner/repo", None, "main", True),
    ],
)
def test_vcs_checkout_derive_gating(
    run_task_mod,
    monkeypatch,
    mocker,
    tmp_path,
    repo_type,
    repo,
    base_rev,
    base_ref,
    expected,
):
    monkeypatch.setattr(os, "environ", {})
    options = run_task_mod.collect_vcs_options(
        Namespace(myrepo_checkout=str(tmp_path), myrepo_shallow_clone=False),
        "myrepo",
        "myrepo",
    )
    options.update(
        {
            "repo-type": repo_type,
            "head-repo": repo,
            "head-rev": "head",
            "base-rev": base_rev,
            "base-ref": base_ref,
        }
    )
    derive = mocker.patch.object(run_task_mod, "derive_base_rev", return_value=None)
    compare = mocker.patch.object(run_task_mod, "github_compare")
    mocker.patch.object(run_task_mod, "git_checkout", return_value="head")
    mocker.patch.object(run_task_mod, "hg_checkout", return_value="head")
    run_task_mod.vcs_checkout_from_args(options)
    assert derive.call_count == int(expected)
    compare.assert_not_called()
    if expected:
        assert os.environ["MYREPO_BASE_REV"] == (base_rev or "")
    else:
        assert "MYREPO_BASE_REV" not in os.environ


def test_vcs_checkout_derived_base_fetched(
    run_task_mod, monkeypatch, mocker, mock_git_repo, mock_stdin, tmp_path
):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    repo_url = "https://github.com/owner/repo"
    # Keep the GitHub URL for derivation, but route checkout to the local fixture.
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv(
        "GIT_CONFIG_KEY_0", f"url.file://{mock_git_repo['path']}.insteadOf"
    )
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", repo_url)
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    derived = mock_git_repo["branch"][-1]
    options = run_task_mod.collect_vcs_options(
        Namespace(
            myrepo_checkout=str(tmp_path / "checkout"), myrepo_shallow_clone=True
        ),
        "myrepo",
        "myrepo",
    )
    options.update(
        {
            "repo-type": "git",
            "base-repo": repo_url,
            "head-repo": repo_url,
            "base-rev": "0" * 40,
            "head-rev": mock_git_repo["main"][-1],
            "head-ref": "refs/heads/main",
        }
    )
    derive = mocker.patch.object(run_task_mod, "derive_base_rev", return_value=derived)
    run_task_mod.vcs_checkout_from_args(options)
    derive.assert_called_once()
    assert options["base-rev"] == derived
    assert os.environ["MYREPO_BASE_REV"] == derived
    assert (
        subprocess.check_output(
            ["git", "cat-file", "-t", derived], cwd=options["checkout"], text=True
        ).strip()
        == "commit"
    )


@pytest.mark.parametrize(
    "payload",
    [
        b"invalid JSON",
        b"{}",
        b"null",
        b'{"status": "ahead", "merge_base_commit": {"sha": "invalid"}}',
    ],
)
def test_github_compare_invalid_response(run_task_mod, mocker, payload):
    response = mocker.MagicMock()
    response.__enter__.return_value.read.return_value = payload
    mocker.patch("urllib.request.urlopen", return_value=response)
    assert run_task_mod.github_compare("owner", "repo", "main", "head") is None


def test_derive_base_rev_default_branch_failure(run_task_mod, mocker):
    mocker.patch.object(run_task_mod, "_default_branch", return_value=None)
    compare = mocker.patch.object(run_task_mod, "github_compare")
    assert (
        run_task_mod.derive_base_rev(
            ("owner", "repo"),
            "https://github.com/owner/repo",
            "https://github.com/owner/repo",
            None,
            None,
            "feature",
            "head",
        )
        is None
    )
    compare.assert_not_called()


@pytest.fixture
def sigterm_handler():
    previous = signal.getsignal(signal.SIGTERM)
    yield previous
    signal.signal(signal.SIGTERM, previous)


def test_schedule_max_run_time_abort_without_env(monkeypatch, run_task_mod):
    monkeypatch.delenv("TASKCLUSTER_MAX_RUN_TIME", raising=False)
    assert run_task_mod.schedule_max_run_time_abort() is None


@nowin
@pytest.mark.parametrize("value", ("", "soon", "0", "-5"))
def test_schedule_max_run_time_abort_invalid_value(
    monkeypatch, run_task_mod, capsys, value
):
    monkeypatch.setenv("TASKCLUSTER_MAX_RUN_TIME", value)
    assert run_task_mod.schedule_max_run_time_abort() is None
    out = capsys.readouterr().out
    assert ("ignoring invalid TASKCLUSTER_MAX_RUN_TIME" in out) == bool(value)


@nowin
@pytest.mark.parametrize(
    "max_run_time,margin",
    (
        (3600, 60),
        (1200, 60),
        (600, 30),
        (100, 5),
        (20, 1),
        (19, None),
    ),
)
def test_schedule_max_run_time_abort_margin(
    monkeypatch, run_task_mod, sigterm_handler, max_run_time, margin
):
    monkeypatch.setenv("TASKCLUSTER_MAX_RUN_TIME", str(max_run_time))
    timer = run_task_mod.schedule_max_run_time_abort()
    if margin is None:
        assert timer is None
        assert signal.getsignal(signal.SIGTERM) is sigterm_handler
        return
    try:
        assert timer.interval == max_run_time - margin
        assert timer.daemon
        assert timer.args == (max_run_time, margin)
        assert signal.getsignal(signal.SIGTERM) is run_task_mod.ignore_sigterm
    finally:
        timer.cancel()


@nowin
def test_ignore_sigterm_not_inherited(run_task_mod, sigterm_handler):
    signal.signal(signal.SIGTERM, run_task_mod.ignore_sigterm)
    os.kill(os.getpid(), signal.SIGTERM)
    # Unlike SIG_IGN, the handler is not inherited across exec.
    child = subprocess.run(["sh", "-c", "kill -TERM $$"])
    assert child.returncode == -signal.SIGTERM


@pytest.fixture
def abort_flag(run_task_mod):
    run_task_mod.max_run_time_abort.clear()
    yield run_task_mod.max_run_time_abort
    run_task_mod.max_run_time_abort.clear()


@nowin
def test_abort_task_processes_signals_process_group(
    mocker, run_task_mod, abort_flag, capsys
):
    mocker.patch.object(run_task_mod.os, "getpgrp", return_value=1234)
    killpg = mocker.patch.object(run_task_mod.os, "killpg")

    run_task_mod.abort_task_processes(600, 30)

    killpg.assert_called_once_with(1234, signal.SIGTERM)
    assert abort_flag.is_set()
    assert "maxRunTime of 600s" in capsys.readouterr().out


@nowin
def test_run_command_keeps_forwarding_output_after_abort(
    mocker, mock_stdin, run_task_mod, abort_flag, capsys, tmp_path
):
    # Signal the command alone rather than the process group of the test
    # runner.
    pid_file = tmp_path / "pid"

    def kill_command(pgid, sig):
        for _ in range(100):
            if pid_file.exists() and pid_file.read_text().strip():
                break
            time.sleep(0.05)
        os.kill(int(pid_file.read_text()), sig)

    mocker.patch.object(run_task_mod.os, "killpg", side_effect=kill_command)
    timer = threading.Timer(0.5, run_task_mod.abort_task_processes, (20, 1))
    timer.start()
    try:
        returncode = run_task_mod.run_command(
            b"task",
            [
                "sh",
                "-c",
                f"echo $$ > '{pid_file}'; "
                "trap 'echo got TERM; kill $!; exit 3' TERM; "
                "sleep 30 >/dev/null 2>&1 & wait $!; echo not aborted",
            ],
        )
    finally:
        timer.cancel()

    assert returncode == 1
    assert abort_flag.is_set()
    # Skip the line echoing the command itself.
    output = capsys.readouterr().out.splitlines()[1:]
    assert any("got TERM" in line for line in output)
    assert any("exiting with code 1" in line for line in output)
    assert not any("not aborted" in line for line in output)


def test_run_command_not_started_after_abort(
    run_task_mod, abort_flag, capsys, tmp_path
):
    abort_flag.set()
    marker = tmp_path / "started"

    returncode = run_task_mod.run_command(
        b"task", [sys.executable, "-c", f"open({str(marker)!r}, 'w')"]
    )

    assert returncode == 1
    assert not marker.exists()
    assert "not executing" in capsys.readouterr().out


def test_retry_required_command_not_retried_after_abort(
    mocker, run_task_mod, abort_flag
):
    abort_flag.set()
    sleep = mocker.patch.object(run_task_mod.time, "sleep")

    with pytest.raises(SystemExit) as excinfo:
        run_task_mod.retry_required_command(b"vcs", [sys.executable, "-c", "pass"])

    assert excinfo.value.code == 1
    sleep.assert_not_called()
