# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os
import subprocess
from abc import ABC, abstractproperty, abstractmethod
from shutil import which

import requests
from redo import retry

PUSHLOG_TMPL = "{}/json-pushes?version=2&changeset={}&tipsonly=1&full=1"


class Repository(ABC):
    def __init__(self, path):
        self.path = path
        self.binary = which(self.tool)
        if self.binary is None:
            raise OSError(f"{self.tool} not found!")

    def run(self, *args: str):
        cmd = (self.binary,) + args
        return subprocess.check_output(cmd, cwd=self.path, universal_newlines=True)

    @abstractproperty
    def tool(self) -> str:
        """Version control system being used, either 'hg' or 'git'."""

    @abstractproperty
    def head_ref(self) -> str:
        """Hash of HEAD revision."""

    @abstractmethod
    def get_url(self, remote=None):
        """Get URL of the upstream repository."""

    @abstractmethod
    def get_commit_message(self, revision=None):
        """Commit message of specified revision or current commit."""


class HgRepository(Repository):
    tool = "hg"

    @property
    def head_ref(self):
        return self.run("log", "-r", ".", "-T", "{node}").strip()

    def get_url(self, remote="default"):
        return self.run("path", "-T", "{url}", remote).strip()

    def get_commit_message(self, revision=None):
        revision = revision or self.head_ref
        return self.run("log", "-r", ".", "-T", "{desc}")


class GitRepository(Repository):
    tool = "git"

    @property
    def head_ref(self):
        return self.run("rev-parse", "--verify", "HEAD").strip()

    def get_url(self, remote="origin"):
        return self.run("remote", "get-url", remote).strip()

    def get_commit_message(self, revision=None):
        revision = revision or self.head_ref
        return self.run("log", "-n1", "--format=%B")


def get_repository(path):
    """Get a repository object for the repository at `path`.
    If `path` is not a known VCS repository, raise an exception.
    """
    if os.path.isdir(os.path.join(path, ".hg")):
        return HgRepository(path)
    elif os.path.exists(os.path.join(path, ".git")):
        return GitRepository(path)

    raise RuntimeError("Current directory is neither a git or hg repository")


def find_hg_revision_push_info(repository, revision):
    """Given the parameters for this action and a revision, find the
    pushlog_id of the revision."""
    pushlog_url = PUSHLOG_TMPL.format(repository, revision)

    def query_pushlog(url):
        r = requests.get(pushlog_url, timeout=60)
        r.raise_for_status()
        return r

    r = retry(
        query_pushlog,
        args=(pushlog_url,),
        attempts=5,
        sleeptime=10,
    )
    pushes = r.json()["pushes"]
    if len(pushes) != 1:
        raise RuntimeError(
            "Unable to find a single pushlog_id for {} revision {}: {}".format(
                repository, revision, pushes
            )
        )
    pushid = list(pushes.keys())[0]
    return {
        "pushdate": pushes[pushid]["date"],
        "pushid": pushid,
        "user": pushes[pushid]["user"],
    }
