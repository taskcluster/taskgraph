import functools
import io
import os
import site
import stat
import subprocess
import sys
import tarfile
import tempfile
from argparse import Namespace
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from unittest.mock import Mock

import pytest
import zstandard

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
            },
            {"shallow-clone": True},
            id="git_with_shallow_clone",
        ),
        pytest.param(
            {"myrepo_checkout_bundle": "checkout.tar.zst"},
            {
                "REPOSITORY_TYPE": "git",
                "HEAD_REPOSITORY": "https://github.com/test/repo.git",
                "HEAD_REV": "abc123",
            },
            {},
            id="git_with_checkout_bundle",
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
    args.setdefault(f"{name}_checkout_bundle", None)
    args = Namespace(**args)

    result = run_task_mod.collect_vcs_options(args, name, name)

    expected = {
        "base-repo": env.get("BASE_REPOSITORY"),
        "base-rev": env.get("BASE_REV"),
        "checkout": os.path.join(os.getcwd(), "checkout"),
        "checkout-bundle": None,
        "env-prefix": name.upper(),
        "head-repo": env.get("HEAD_REPOSITORY"),
        "name": name,
        "pip-requirements": None,
        "project": name,
        "head-ref": env.get("HEAD_REF"),
        "head-rev": env.get("HEAD_REV"),
        "repo-type": env.get("REPOSITORY_TYPE"),
        "shallow-clone": False,
        "ssh-secret-name": env.get("SSH_SECRET_NAME"),
        "store-path": env.get("HG_STORE_PATH"),
    }
    if "PIP_REQUIREMENTS" in env:
        expected["pip-requirements"] = os.path.join(
            expected["checkout"], env.get("PIP_REQUIREMENTS")
        )

    bundle = getattr(args, f"{name}_checkout_bundle")
    if bundle:
        # Derived independently (like the ``checkout`` expectation above) so the
        # abspath handling in collect_vcs_options is load-bearing, not mirrored.
        expected["checkout-bundle"] = os.path.join(os.getcwd(), bundle)

    expected.update(extra_expected)
    assert result == expected


def test_create_checkout_bundle(run_task_mod, tmp_path):
    # Build a fake checkout containing vcs metadata (including a nested .git, as
    # produced by submodules/sub-checkouts) plus real working files.
    checkout = tmp_path / "myco"
    (checkout / ".git").mkdir(parents=True)
    (checkout / ".git" / "config").write_text("[core]\n")
    (checkout / ".hg").mkdir()
    (checkout / ".hg" / "hgrc").write_text("[paths]\n")
    (checkout / "sub" / ".git").mkdir(parents=True)
    (checkout / "sub" / ".git" / "config").write_text("[core]\n")
    (checkout / "file1.txt").write_text("hello")
    (checkout / "sub" / "file2.txt").write_text("world")
    (checkout / ".gitignore").write_text("*.pyc\n")

    dest = tmp_path / "out.tar.zst"
    run_task_mod.create_checkout_bundle(str(checkout), str(dest))

    assert dest.exists()
    # No leftover temporary file.
    assert not dest.with_name(f"{dest.name}.tmp").exists()

    # The archive should be valid zstd + tar. Decompress fully so it can be read
    # in random-access mode (to also verify file contents survive intact).
    dctx = zstandard.ZstdDecompressor()
    with dest.open("rb") as fh:
        tar_bytes = dctx.stream_reader(fh).read()
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tf:
        members = tf.getnames()
        assert tf.extractfile("myco/file1.txt").read() == b"hello"
        assert tf.extractfile("myco/sub/file2.txt").read() == b"world"

    # Regular files are present under the checkout's basename prefix.
    assert "myco/file1.txt" in members
    assert "myco/sub/file2.txt" in members
    # A dotfile that merely starts with ".git" is not excluded.
    assert "myco/.gitignore" in members
    # vcs metadata directories are excluded at any depth (no history).
    assert not any(".git" in m.split("/") or ".hg" in m.split("/") for m in members), (
        members
    )


def test_create_checkout_bundle_rejects_bad_suffix(run_task_mod, tmp_path):
    checkout = tmp_path / "myco"
    checkout.mkdir()
    (checkout / "file1.txt").write_text("hello")

    with pytest.raises(ValueError):
        run_task_mod.create_checkout_bundle(str(checkout), str(tmp_path / "out.tar.gz"))


def test_create_checkout_bundle_fails_fast(run_task_mod, tmp_path):
    # tar exits nonzero for a checkout dir that does not exist; the helper must
    # raise and leave neither the destination nor the temporary file behind.
    dest = tmp_path / "out.tar.zst"
    missing = tmp_path / "does-not-exist"

    with pytest.raises(RuntimeError):
        run_task_mod.create_checkout_bundle(str(missing), str(dest))

    assert not dest.exists()
    assert not dest.with_name(f"{dest.name}.tmp").exists()


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


@nowin
def test_main_runs_checkout_bundle(mocker, run_main, run_task_mod, tmp_path):
    # Drive main() to verify the bundle step is opt-in (default OFF) and wired to
    # create_checkout_bundle once per eligible repo. Stub out the real checkout
    # and archiving; just record the bundle invocations.
    mocker.patch.object(run_task_mod, "vcs_checkout_from_args", lambda repo: None)

    calls = []
    mocker.patch.object(
        run_task_mod,
        "create_checkout_bundle",
        lambda checkout_dir, dest_path: calls.append((checkout_dir, dest_path)),
    )

    checkout = tmp_path / "checkouts" / "vcs"
    bundle = tmp_path / "artifacts" / "src.tar.zst"

    # Default OFF: without --vcs-checkout-bundle, the bundle step is skipped.
    result, _ = run_main(extra_args=[f"--vcs-checkout={checkout}"])
    assert result == 0
    assert calls == []

    # Opt-in: the bundle step runs once with the (abspath'd) checkout and dest.
    result, _ = run_main(
        extra_args=[
            f"--vcs-checkout={checkout}",
            f"--vcs-checkout-bundle={bundle}",
        ]
    )
    assert result == 0
    assert calls == [(os.path.abspath(str(checkout)), os.path.abspath(str(bundle)))]
