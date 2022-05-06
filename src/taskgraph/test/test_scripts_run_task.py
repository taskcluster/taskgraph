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


def test_clean_git_checkout(monkeypatch, run_task_mod):
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

    _stdin = Mock(
        fileno=lambda: 3,
    )

    monkeypatch.setattr(
        subprocess,
        "Popen",
        _Popen,
    )

    monkeypatch.setattr(
        sys,
        "stdin",
        _stdin,
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
