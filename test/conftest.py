import os
import platform
import tempfile
from pathlib import Path

import pytest
from responses import RequestsMock

here = Path(__file__).parent

pytest_plugins = ("pytest-taskgraph",)

# Disable as much system/user level configuration as we can to avoid
# interference with tests.
# This ignores ~/.hgrc
os.environ["HGRCPATH"] = ""
# This ignores system-level git config (eg: in /etc).
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"


@pytest.fixture(scope="session", autouse=True)
def git_global_config():
    # run-task writes to the global git config, so point it at a real
    # (writable) empty file instead of ~/.gitconfig.
    fd, path = tempfile.mkstemp(prefix="taskgraph-gitconfig-")
    os.close(fd)
    os.environ["GIT_CONFIG_GLOBAL"] = path
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
