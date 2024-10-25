import os
from pathlib import Path

import pytest
from responses import RequestsMock

here = Path(__file__).parent

pytest_plugins = ("pytest-taskgraph",)

# Disable as much system/user level configuration as we can to avoid
# interference with tests.
# This ignores ~/.hgrc
os.environ["HGRCPATH"] = ""
# This ignores system-level git config (eg: in /etc). There apperas to be
# no way to ignore ~/.gitconfig other than overriding $HOME, which is overkill.
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"


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
