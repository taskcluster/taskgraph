import os
import platform
import subprocess
import tempfile
from pathlib import Path

import pytest
from responses import RequestsMock

here = Path(__file__).parent

pytest_plugins = ("pytest-taskgraph",)


def pytest_ignore_collect(collection_path, config):
    if collection_path.name == "test_graph_perf.py" and not config.getoption(
        "codspeed"
    ):
        return True


# Disable as much system/user level configuration as we can to avoid
# interference with tests.
# This ignores ~/.hgrc
os.environ["HGRCPATH"] = ""
# This ignores system-level git config (eg: in /etc).
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"


@pytest.fixture(scope="session", autouse=True)
def git_global_config():
    # Until https://github.com/taskcluster/taskcluster/issues/6561 we need to
    # preserved the safe directories that `run-task` sets to keep tests
    # working in CI when workers run subsequent tasks.
    existing_safe_dirs = subprocess.run(
        ["git", "config", "--global", "--get-all", "safe.directory"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()

    fd, path = tempfile.mkstemp(prefix="taskgraph-gitconfig-")
    os.close(fd)
    os.environ["GIT_CONFIG_GLOBAL"] = path

    for entry in existing_safe_dirs:
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", entry],
            check=False,
        )

    yield
    del os.environ["GIT_CONFIG_GLOBAL"]
    os.unlink(path)


# Some of the tests marked with this may be fixable on Windows; we should
# look into these in more depth at some point.
nowin = pytest.mark.skipif(
    platform.system() == "Windows", reason="test currently broken on Windows"
)


@pytest.fixture
def responses():
    with RequestsMock() as rsps:
        yield rsps


@pytest.fixture(scope="session", autouse=True)
def patch_taskcluster_root_url(session_mocker):
    session_mocker.patch.dict(
        os.environ, {"TASKCLUSTER_ROOT_URL": "https://tc-tests.localhost"}
    )


@pytest.fixture(scope="session")
def datadir():
    return here / "data"


@pytest.fixture(scope="session")
def project_root():
    return here.parent
