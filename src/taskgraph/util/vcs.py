# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import logging
import os
import re
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from shutil import which
from typing import Optional
from urllib.parse import quote

import requests

from taskgraph.util.path import ancestors

PUSHLOG_TMPL = "{}/json-pushes?version=2&changeset={}&tipsonly=1&full=1"

logger = logging.getLogger(__name__)


class _GitHubCompareError(Exception):
    pass


class Repository(ABC):
    # Both mercurial and git use sha1 as revision identifiers. Luckily, both define
    # the same value as the null revision.
    #
    # https://github.com/git/git/blob/dc04167d378fb29d30e1647ff6ff51dd182bc9a3/t/oid-info/hash-info#L7
    # https://www.mercurial-scm.org/repo/hg-stable/file/82efc31bd152/mercurial/node.py#l30
    NULL_REVISION = "0000000000000000000000000000000000000000"

    def __init__(self, path):
        self.path = path
        self.binary = which(self.tool)
        if self.binary is None:
            raise OSError(f"{self.tool} not found!")
        self._valid_diff_filter = ("m", "a", "d")

        self._env = os.environ.copy()

    def run(self, *args: str, **kwargs) -> str:
        return_codes = kwargs.pop("return_codes", [])
        cmd = (self.binary,) + args

        try:
            return subprocess.check_output(  # type: ignore
                cmd,  # type: ignore
                cwd=self.path,
                env=self._env,
                encoding="utf-8",
                **kwargs,
            )
        except subprocess.CalledProcessError as e:
            if e.returncode in return_codes:
                return ""
            raise

    @property
    @abstractmethod
    def tool(self) -> str:
        """Version control system being used, either 'hg' or 'git'."""

    @property
    @abstractmethod
    def is_shallow(self) -> str:
        """Whether this repo is a shallow clone."""

    @property
    @abstractmethod
    def head_rev(self) -> str:
        """Hash of HEAD revision."""

    @property
    @abstractmethod
    def base_rev(self) -> str:
        """Hash of revision the current topic branch is based on."""

    @property
    @abstractmethod
    def branch(self) -> Optional[str]:
        """Current branch or bookmark the checkout has active."""

    @property
    @abstractmethod
    def all_remote_names(self) -> list[str]:
        """Name of all configured remote repositories."""

    @property
    @abstractmethod
    def default_remote_name(self) -> str:
        """Name the VCS defines for the remote repository when cloning
        it for the first time. This name may not exist anymore if users
        changed the default configuration, for instance."""

    @property
    @abstractmethod
    def remote_name(self) -> str:
        """Name of the remote repository."""

    def _get_most_suitable_remote(self, remote_instructions) -> str:
        remotes = self.all_remote_names

        # in case all_remote_names raised a RuntimeError
        if remotes is None:
            raise RuntimeError("No valid remotes found")

        if len(remotes) == 1:
            return remotes[0]

        if self.default_remote_name in remotes:
            return self.default_remote_name

        first_remote = remotes[0]
        logger.warning(
            f"Unable to determine which remote repository to use between: {remotes}. "
            f'Arbitrarily using the first one "{first_remote}". Please set an '
            f"`{self.default_remote_name}` remote if the arbitrarily selected one "
            f"is not right. To do so: {remote_instructions}"
        )

        return first_remote

    @property
    @abstractmethod
    def default_branch(self) -> str:
        """Name of the default branch."""

    @abstractmethod
    def get_url(self, remote: Optional[str]) -> str:
        """Get URL of the upstream repository."""

    @abstractmethod
    def get_commit_message(self, revision: Optional[str]) -> str:
        """Commit message of specified revision or current commit."""

    @abstractmethod
    def get_tracked_files(self, *paths: str, rev: Optional[str] = None) -> list[str]:
        """Return list of tracked files.

        ``*paths`` are path specifiers to limit results to.
        ``rev`` is a revision specifier at which to retrieve the files.
        Defaults to the parent of the working copy if unspecified.
        """

    @abstractmethod
    def get_changed_files(
        self,
        diff_filter: Optional[str],
        mode: Optional[str],
        rev: Optional[str],
        base: Optional[str],
    ) -> list[str]:
        """Return a list of files that are changed in:
         * either this repository's working copy,
         * or at a given revision (``rev``)
         * or between 2 revisions (``base`` and ``rev``)

        ``diff_filter`` controls which kinds of modifications are returned.
        It is a string which may only contain the following characters:

            A - Include files that were added
            D - Include files that were deleted
            M - Include files that were modified

        By default, all three will be included.

        ``mode`` can be one of 'unstaged', 'staged' or 'all'. Only has an
        effect on git. Defaults to 'unstaged'.

        ``rev`` is a specifier for which changesets to consider for
        changes. The exact meaning depends on the vcs system being used.

        ``base`` specifies the range of changesets. This parameter cannot
        be used without ``rev``. The range includes ``rev`` but excludes
        ``base``.
        """

    @abstractmethod
    def get_outgoing_files(self, diff_filter: str, upstream: str) -> list[str]:
        """Return a list of changed files compared to upstream.

        ``diff_filter`` works the same as `get_changed_files`.
        ``upstream`` is a remote ref to compare against. If unspecified,
        this will be determined automatically. If there is no remote ref,
        a MissingUpstreamRepo exception will be raised.
        """

    @abstractmethod
    def working_directory_clean(
        self, untracked: Optional[bool] = False, ignored: Optional[bool] = False
    ) -> bool:
        """Determine if the working directory is free of modifications.

        Returns True if the working directory does not have any file
        modifications. False otherwise.

        By default, untracked and ignored files are not considered. If
        ``untracked`` or ``ignored`` are set, they influence the clean check
        to factor these file classes into consideration.
        """

    @abstractmethod
    def update(self, ref: str) -> None:
        """Update the working directory to the specified reference."""

    @abstractmethod
    def find_latest_common_revision(self, base_ref_or_rev: str, head_rev: str) -> str:
        """Find the latest revision that is common to both the given
        ``head_rev`` and ``base_ref_or_rev``.

        If no common revision exists, ``Repository.NULL_REVISION`` will
        be returned."""

    @abstractmethod
    def does_revision_exist_locally(self, revision: str) -> bool:
        """Check whether this revision exists in the local repository.

        If this function returns an unexpected value, then make sure
        the revision was fetched from the remote repository."""

    def derive_base_rev(
        self,
        head_repository: str,
        head_rev: str,
        head_ref: str,
        base_rev: str,
    ) -> Optional[str]:
        """Return the base to use for a push of ``head_rev`` to ``head_ref``
        when the reported ``base_rev`` is not it, or ``None`` to keep
        ``base_rev`` as reported.

        Only supported by Git; returns ``None`` for all other VCS types.
        """
        return None

    def derive_pull_request_base_rev(
        self,
        base_repository: str,
        head_rev: str,
        base_ref: str,
    ) -> Optional[str]:
        return None

    def get_note(
        self,
        note: str,
        remote: str,
        revision: Optional[str] = None,
    ) -> Optional[str]:
        """Read a note attached to the given revision (defaults to HEAD).

        The notes ref is fetched from ``remote`` first; a missing ref on the
        remote is tolerated while other fetch failures propagate.

        Returns the note content as a string, or ``None`` if no note exists.
        Only supported by Git; returns ``None`` for all other VCS types.
        """
        return None


class HgRepository(Repository):
    @property
    def tool(self) -> str:
        return "hg"

    @property
    def default_remote_name(self) -> str:
        return "default"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._env["HGPLAIN"] = "1"

    @property
    def is_shallow(self):
        return False

    @property
    def head_rev(self):
        return self.run("log", "-r", ".", "-T", "{node}").strip()

    @property
    def base_rev(self):
        return self.run("log", "-r", "last(ancestors(.) and public())", "-T", "{node}")

    @property
    def branch(self):
        bookmarks_fn = os.path.join(self.path, ".hg", "bookmarks.current")
        if os.path.exists(bookmarks_fn):
            with open(bookmarks_fn) as f:
                bookmark = f.read()
                return bookmark or None

        return None

    @property
    def all_remote_names(self):
        remotes = self.run("paths", "--quiet").splitlines()
        if not remotes:
            raise RuntimeError("No remotes defined")
        return remotes

    @property
    def remote_name(self):
        return self._get_most_suitable_remote(
            "Edit .hg/hgrc and add:\n\n[paths]\ndefault = $URL",
        )

    @property
    def default_branch(self):
        # Mercurial recommends keeping "default"
        # https://www.mercurial-scm.org/wiki/StandardBranching#Don.27t_use_a_name_other_than_default_for_your_main_development_branch
        return "default"

    def get_url(self, remote=None):
        remote = remote or "default"
        return self.run("path", "-T", "{url}", remote).strip()

    def get_commit_message(self, revision=None):
        revision = revision or "."
        return self.run("log", "-r", revision, "-T", "{desc}")

    def _format_diff_filter(self, diff_filter, for_status=False):
        df = diff_filter.lower()
        assert all(f in self._valid_diff_filter for f in df)

        # When looking at the changes in the working directory, the hg status
        # command uses 'd' for files that have been deleted with a non-hg
        # command, and 'r' for files that have been `hg rm`ed. Use both.
        return df.replace("d", "dr") if for_status else df

    def _files_template(self, diff_filter):
        template = ""
        df = self._format_diff_filter(diff_filter)
        if "a" in df:
            template += "{file_adds % '{file}\\n'}"
        if "d" in df:
            template += "{file_dels % '{file}\\n'}"
        if "m" in df:
            template += "{file_mods % '{file}\\n'}"
        return template

    def get_tracked_files(self, *paths, rev=None):
        rev = rev or "."
        return self.run("files", "-r", rev, *paths).splitlines()

    def get_changed_files(self, diff_filter=None, mode=None, rev=None, base=None):
        diff_filter = diff_filter or "ADM"
        if rev is None:
            if base is not None:
                raise ValueError("Cannot specify `base` without `rev`")
            # Use --no-status to print just the filename.
            df = self._format_diff_filter(diff_filter, for_status=True)
            return self.run("status", "--no-status", f"-{df}").splitlines()
        else:
            template = self._files_template(diff_filter)
            revision_argument = rev if base is None else f"{rev} % {base}"
            return self.run("log", "-r", revision_argument, "-T", template).splitlines()

    def get_outgoing_files(self, diff_filter="ADM", upstream=None):
        template = self._files_template(diff_filter)

        if not upstream:
            return self.run(
                "log", "-r", "draft() and ancestors(.)", "--template", template
            ).split()

        return self.run(
            "outgoing",
            "-r",
            ".",
            "--quiet",
            "--template",
            template,
            upstream,
            return_codes=(1,),
        ).split()

    def working_directory_clean(self, untracked=False, ignored=False):
        args = ["status", "--modified", "--added", "--removed", "--deleted"]
        if untracked:
            args.append("--unknown")
        if ignored:
            args.append("--ignored")

        # If output is empty, there are no entries of requested status, which
        # means we are clean.
        return not len(self.run(*args).strip())

    def update(self, ref):
        self.run("update", "--check", ref)

    def find_latest_common_revision(self, base_ref_or_rev, head_rev):
        ancestor = self.run(
            "log",
            "-r",
            f"last(ancestors('{base_ref_or_rev}') and ancestors('{head_rev}'))",
            "--template",
            "{node}",
        ).strip()
        return ancestor or self.NULL_REVISION

    def does_revision_exist_locally(self, revision):
        try:
            return bool(self.run("log", "-r", revision).strip())
        except subprocess.CalledProcessError as e:
            # Error code 255 comes with the message:
            # "abort: unknown revision $REVISION"
            if e.returncode == 255:
                return False
            raise


class GitRepository(Repository):
    @property
    def tool(self) -> str:
        return "git"

    @property
    def default_remote_name(self) -> str:
        return "origin"

    _LS_REMOTE_PATTERN = re.compile(r"ref:\s+refs/heads/(?P<branch_name>\S+)\s+HEAD")

    # A fetch against GitHub takes a few seconds here. A failed derivation only
    # falls back to the reported base, so a stalled transfer must not eat the
    # decision task's time budget.
    FETCH_TIMEOUT = 120
    DERIVE_TIMEOUT = 300
    # Enough history to find the reported base under a normal push without
    # fetching the whole branch. The check is repeated with more history when
    # this misses, so this depth only saves a fetch.
    PROBE_DEPTH = 50
    MERGE_BASE_DEPTHS = (200, 800, 3200, 12800)
    _GITHUB_URL = re.compile(r"https://github\.com/(?P<repo>[^/]+/[^/]+?)(?:\.git)?/?$")
    # Each network call gets FETCH_TIMEOUT or what is left of the
    # DERIVE_TIMEOUT budget, whichever is shorter. Outside a derivation the
    # deadline is infinite, so only FETCH_TIMEOUT applies.
    _deadline = float("inf")

    def _timeout(self):
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired("derive base_rev", self.DERIVE_TIMEOUT)
        return min(self.FETCH_TIMEOUT, remaining)

    @property
    def is_shallow(self):
        return self.run("rev-parse", "--is-shallow-repository").strip() == "true"

    @property
    def head_rev(self):
        return self.run("rev-parse", "--verify", "HEAD").strip()

    @property
    def base_rev(self):
        refs = self.run(
            "rev-list", "HEAD", "--topo-order", "--boundary", "--not", "--remotes"
        ).splitlines()
        if refs:
            return refs[-1][1:]  # boundary starts with a prefix `-`
        return self.head_rev

    @property
    def branch(self):
        return self.run("branch", "--show-current").strip() or None

    @property
    def all_remote_names(self):
        remotes = self.run("remote").splitlines()
        if not remotes:
            raise RuntimeError("No remotes defined")
        return remotes

    @property
    def remote_name(self):
        try:
            remote_branch_name = self.run(
                "rev-parse",
                "--verify",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{u}",
                stderr=subprocess.PIPE,
            ).strip()
            return remote_branch_name.split("/")[0]
        except subprocess.CalledProcessError as e:
            # Error code 128 comes with the message:
            # "fatal: no upstream configured for branch $BRANCH"
            if e.returncode != 128:
                print(e.stderr)
                raise

        return self._get_most_suitable_remote("`git remote add origin $URL`")

    @property
    def default_branch(self):
        try:
            # this one works if the current repo was cloned from an existing
            # repo elsewhere
            return self._get_default_branch_from_cloned_metadata()
        except (subprocess.CalledProcessError, RuntimeError):
            pass

        try:
            # This call works if you have (network) access to the repo
            return self._get_default_branch_from_remote_query()
        except (subprocess.CalledProcessError, RuntimeError):
            pass

        # this one is the last resort in case the remote is not accessible and
        # the local repo is where `git init` was made
        return self._guess_default_branch()

    def _get_default_branch_from_remote_query(self):
        # This function requires network access to the repo
        remote_name = self.remote_name
        output = self.run("ls-remote", "--symref", remote_name, "HEAD")  # type: ignore
        matches = self._LS_REMOTE_PATTERN.search(output)
        if not matches:
            raise RuntimeError(
                f'Could not find the default branch of remote repository "{remote_name}". '
                "Got: {output}"
            )

        branch_name = matches.group("branch_name")
        return f"{remote_name}/{branch_name}"

    def _get_default_branch_from_cloned_metadata(self):
        return self.run("rev-parse", "--abbrev-ref", f"{self.remote_name}/HEAD").strip()

    def _guess_default_branch(self):
        branches = [
            line.strip()
            for line in self.run(
                "branch", "--all", "--no-color", "--format=%(refname)"
            ).splitlines()
            for candidate_branch in ("main", "master", "branches/default/tip")
            if line.strip().endswith(candidate_branch)
        ]

        if len(branches) == 1:
            return branches[0]

        raise RuntimeError(f"Unable to find default branch. Got: {branches}")

    def get_url(self, remote=None):
        remote = remote or "origin"
        return self.run("remote", "get-url", remote).strip()

    def get_commit_message(self, revision=None):
        revision = revision or "HEAD"
        return self.run("log", "-n1", "--format=%B", revision)

    def get_tracked_files(self, *paths, rev=None):
        rev = rev or "HEAD"
        return self.run("ls-tree", "-r", "--name-only", rev, *paths).splitlines()

    def get_changed_files(self, diff_filter=None, mode=None, rev=None, base=None):
        diff_filter = diff_filter or "ADM"
        mode = mode or "unstaged"
        assert all(f.lower() in self._valid_diff_filter for f in diff_filter)

        if rev is None:
            if base is not None:
                raise ValueError("Cannot specify `base` without `rev`")
            cmd = ["diff"]
            if mode == "staged":
                cmd.append("--cached")
            elif mode == "all":
                cmd.append("HEAD")
        elif base == self.NULL_REVISION:
            # When base is NULL_REVISION (e.g new branches on Github), diff
            # from the empty tree to show all files present at rev. Use Git's
            # well-known empty tree hash.
            cmd = ["diff", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", rev]
        elif self.is_shallow:
            # In shallow clones, `git log` won't have the history necessary to
            # determine the files changed. Using `git diff` finds the
            # differences between the two trees which is slightly more
            # accurate. However, Github events often don't provide the true
            # base revision so shallow Github clones will still return
            # incorrect files changed in many cases, most notably pull
            # requests that need rebasing.
            cmd = ["diff", base, rev]
        else:
            revision_argument = f"{rev}~1..{rev}" if base is None else f"{base}..{rev}"
            cmd = ["log", "--format=format:", revision_argument]

        cmd.append("--name-only")
        cmd.append(
            "--no-renames"
        )  # Consider renames as deletion of old, addition of new.
        cmd.append("--diff-filter=" + diff_filter.upper())

        files = self.run(*cmd).splitlines()
        return [f for f in files if f]

    def get_outgoing_files(self, diff_filter="ADM", upstream=None):
        assert all(f.lower() in self._valid_diff_filter for f in diff_filter)

        not_condition = upstream if upstream else "--remotes"

        files = self.run(
            "log",
            "--name-only",
            f"--diff-filter={diff_filter.upper()}",
            "--oneline",
            "--pretty=format:",
            "HEAD",
            "--not",
            not_condition,
        ).splitlines()
        return [f for f in files if f]

    def working_directory_clean(self, untracked=False, ignored=False):
        args = ["status", "--porcelain"]

        # Even in --porcelain mode, behavior is affected by the
        # ``status.showUntrackedFiles`` option, which means we need to be
        # explicit about how to treat untracked files.
        if untracked:
            args.append("--untracked-files=all")
        else:
            args.append("--untracked-files=no")

        if ignored:
            args.append("--ignored")

        # If output is empty, there are no entries of requested status, which
        # means we are clean.
        return not len(self.run(*args).strip())

    def update(self, ref):
        self.run("checkout", ref)

    def find_latest_common_revision(self, base_ref_or_rev, head_rev):
        try:
            return self.run("merge-base", base_ref_or_rev, head_rev).strip()
        except subprocess.CalledProcessError:
            return self.NULL_REVISION

    def does_revision_exist_locally(self, revision):
        try:
            return self.run("cat-file", "-t", revision).strip() == "commit"
        except subprocess.CalledProcessError as e:
            # Error code 128 comes with the message:
            # "git cat-file: could not get object info"
            if e.returncode == 128:
                return False
            raise

    def _default_branch(self, repository):
        output = self.run(
            "ls-remote", "--symref", repository, "HEAD", timeout=self._timeout()
        )
        if not (matches := self._LS_REMOTE_PATTERN.search(output)):
            return None, None
        tip = next(
            (
                line.split()[0]
                for line in output.splitlines()
                if not line.startswith("ref:")
            ),
            None,
        )
        return f"refs/heads/{matches['branch_name']}", tip

    def _github_compare(self, repository, base, head):
        if not (match := self._GITHUB_URL.match(repository)):
            raise _GitHubCompareError(f"{repository} is not on GitHub")
        headers = {"Accept": "application/vnd.github+json"}
        if token := os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = requests.get(
                f"https://api.github.com/repos/{match['repo']}/compare/{quote(base)}...{head}",
                params={"per_page": 1},
                headers=headers,
                timeout=self._timeout(),
            )
            response.raise_for_status()
            compare = response.json()
            if not (compare["status"] and compare["merge_base_commit"]["sha"]):
                raise ValueError("no status or merge base")
            return compare
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            raise _GitHubCompareError(
                f"GitHub compare of {base}...{head} failed: {e}"
            ) from e

    def _github_base_rev(self, repository, head_rev, head_ref, base_rev, branch_ref):
        # A push has no target of its own, so it targets the default branch.
        if branch_ref is None:
            compare = None
            if base_rev:
                compare = self._github_compare(repository, base_rev, head_rev)
                # The push only added commits on top of the reported base, which
                # is then the right base.
                if compare["status"] in ("ahead", "identical"):
                    self._ensure_commit(repository, base_rev)
                    return None
            branch_ref, _ = self._default_branch(repository)
            if not branch_ref:
                return None
            # A push to the default branch that rewrote it uses the merge base of
            # its old and new tips. A new default branch keeps the reported base.
            if head_ref == branch_ref:
                return compare and self._ensure_commit(
                    repository, compare["merge_base_commit"]["sha"]
                )
        # Otherwise the base is the merge base of the head and the target branch.
        branch = branch_ref.removeprefix("refs/heads/")
        compare = self._github_compare(repository, branch, head_rev)
        return self._ensure_commit(repository, compare["merge_base_commit"]["sha"])

    def _ensure_commit(self, repository, rev):
        if not self._has_commit(rev):
            self._fetch(repository, rev, "--depth=1")
        return rev

    def _has_commit(self, rev):
        return bool(
            self.run(
                "cat-file", "-t", rev, return_codes=[128], stderr=subprocess.DEVNULL
            )
        )

    def _resolve(self, rev):
        return (
            self.run(
                "rev-parse",
                "--verify",
                "--quiet",
                f"{rev}^{{commit}}",
                return_codes=[1],
            ).strip()
            or rev
        )

    def _remote_tip(self, repository, ref):
        output = self.run("ls-remote", repository, ref, timeout=self._timeout()).split()
        return output[0] if output else None

    def _is_ancestor(self, rev, descendant):
        # merge-base exits 1 without shared history and 128 when rev is
        # unknown locally. Both mean rev is not an ancestor we can see.
        merge_base = self.run(
            "merge-base",
            rev,
            descendant,
            return_codes=[1, 128],
            stderr=subprocess.DEVNULL,
        ).strip()
        return merge_base.startswith(rev)

    def _fetch(self, repository, refspec, *options):
        remote = self.default_remote_name
        if (
            self.run(
                "remote", "get-url", remote, return_codes=[2], stderr=subprocess.DEVNULL
            ).strip()
            == repository
        ):
            repository = remote
        timeout = self._timeout()
        try:
            self.run("fetch", *options, repository, refspec, timeout=timeout)
        except subprocess.TimeoutExpired:
            lock = self.run("rev-parse", "--git-path", "shallow.lock").strip()
            Path(self.path, lock).unlink(missing_ok=True)
            raise

    def _shallow_commits(self):
        shallow = Path(
            self.path, self.run("rev-parse", "--git-path", "shallow").strip()
        )
        return shallow.read_text().split() if shallow.exists() else []

    def _fetch_missing_shallow_commits(self, repository):
        if not (commits := self._shallow_commits()):
            return
        found = self.run("cat-file", "--batch-check", input="\n".join(commits) + "\n")
        for line in found.splitlines():
            if line.endswith(" missing"):
                self._fetch(repository, line.split()[0], "--depth=1")

    def _fetch_excluding(self, repository, rev, ref):
        try:
            self._fetch(repository, rev, f"--shallow-exclude={ref}")
        except subprocess.CalledProcessError:
            return None
        tip = self.run("rev-parse", "FETCH_HEAD").strip()
        self._fetch_missing_shallow_commits(repository)
        return tip

    def _graft_root_parents(self, rev):
        """Return the parents recorded in the raw commit objects of the graft
        roots below ``rev``.

        After an excluding fetch, a single parent is the fork point. Several
        mean the fetched history crosses the shallow boundary through more
        than one parent, as after a merge from the excluded branch."""
        parents = set()
        for root in self.run("rev-list", "--max-parents=0", rev).split():
            for line in self.run("cat-file", "-p", root, errors="replace").splitlines():
                if not line:
                    break
                if line.startswith("parent "):
                    parents.add(line.split()[1])
        return parents

    def _merge_base(self, repository, head_rev, target):
        if not self.is_shallow:
            if target.startswith("refs/") or not self._has_commit(target):
                self._fetch(repository, target)
                target = "FETCH_HEAD"
            return (
                self.run("merge-base", target, head_rev, return_codes=[1]).strip()
                or None
            )
        for depth in self.MERGE_BASE_DEPTHS:
            self._fetch(repository, head_rev, f"--depth={depth}")
            self._fetch(repository, target, f"--depth={depth}")
            tip = self.run("rev-parse", "FETCH_HEAD").strip()
            merge_base = self.run("merge-base", tip, head_rev, return_codes=[1]).strip()
            if merge_base and not set(self._shallow_commits()).intersection(
                self.run("rev-list", tip, head_rev, "--not", merge_base).split()
            ):
                return merge_base
            if not merge_base and not self.is_shallow:
                break
        logger.warning(f"No merge base of {head_rev} and {target} found")
        return None

    def _contains(self, repository, head_rev, rev, branch_ref, complete):
        """Return True when ``rev`` is an ancestor of ``head_rev``, False when
        it is not, and None when a shallow clone cannot tell."""
        if self._is_ancestor(rev, head_rev):
            return True
        if not self.is_shallow:
            return False
        if complete and self._fetch_excluding(repository, rev, branch_ref):
            return False
        if merge_base := self._merge_base(repository, head_rev, rev):
            return merge_base.startswith(rev)
        return None if self.is_shallow else False

    def derive_base_rev(self, head_repository, head_rev, head_ref, base_rev):
        """Return the base to use for a push of ``head_rev`` to ``head_ref``, or
        ``None`` to keep ``base_rev`` as reported.

        A fast forward push keeps ``base_rev``. A push to the default branch keeps
        it unless the push rewrote the branch, which makes the base the merge base
        of ``base_rev`` and ``head_rev``. Otherwise the base is the merge base of
        ``head_rev`` and the default branch. GitHub's compare API answers when it
        can, and Git finds the merge base when it cannot."""
        if not head_ref.startswith("refs/heads/"):
            return None
        return self._try_derive_base_rev(
            head_repository, head_rev, head_ref=head_ref, base_rev=base_rev
        )

    def derive_pull_request_base_rev(self, base_repository, head_rev, base_ref):
        """Return the merge base of ``head_rev`` and the target branch
        ``base_ref``, or ``None`` to keep the reported base."""
        if not base_ref:
            return None
        branch_ref = f"refs/heads/{base_ref.removeprefix('refs/heads/')}"
        return self._try_derive_base_rev(
            base_repository, head_rev, branch_ref=branch_ref
        )

    def _try_derive_base_rev(
        self, repository, head_rev, head_ref=None, base_rev=None, branch_ref=None
    ):
        self._deadline = time.monotonic() + self.DERIVE_TIMEOUT
        try:
            return self._derive_base_rev(
                repository,
                head_rev,
                head_ref=head_ref,
                base_rev=base_rev,
                branch_ref=branch_ref,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Cannot derive base_rev for {head_rev}: {e}")
            return None
        finally:
            del self._deadline

    def _derive_base_rev(
        self, repository, head_rev, head_ref=None, base_rev=None, branch_ref=None
    ):
        shallow = self.is_shallow
        head_rev = self._resolve(head_rev)
        if base_rev == self.NULL_REVISION:
            base_rev = None
        if base_rev:
            base_rev = self._resolve(base_rev)

        if self._GITHUB_URL.match(repository):
            try:
                return self._github_base_rev(
                    repository, head_rev, head_ref, base_rev, branch_ref
                )
            except _GitHubCompareError as e:
                logger.info(f"{e}, using git")

        # A normal push adds commits on top of the reported base. Look for it
        # in recent history first, which is cheap.
        if base_rev:
            if shallow:
                self._fetch(repository, head_rev, f"--depth={self.PROBE_DEPTH}")
            if self._is_ancestor(base_rev, head_rev):
                return None

        branch_tip = None
        if branch_ref is None:
            branch_ref, branch_tip = self._default_branch(repository)
            if not branch_ref:
                return None

        if head_ref == branch_ref:
            # A push to the default branch reports its previous tip, which is
            # the right base unless the push rewrote it.
            if not base_rev:
                return None
            return self._merge_base(repository, head_rev, base_rev)

        fork_point = None
        unrelated = False
        if shallow:
            # Fetch the pushed commits and nothing else. This fails when
            # head_rev is already on the branch.
            if self._fetch_excluding(repository, head_rev, branch_ref):
                parents = self._graft_root_parents(head_rev)
                unrelated = not parents
                if len(parents) == 1:
                    (fork_point,) = parents
            elif (branch_tip or self._remote_tip(repository, branch_ref)) == head_rev:
                fork_point = head_rev
            elif (
                head_ref
                and (tip := self._fetch_excluding(repository, branch_ref, head_ref))
                and head_rev in self._graft_root_parents(tip)
            ):
                fork_point = head_rev
            complete = fork_point is not None
        else:
            complete = False

        if unrelated:
            return None

        # A normal push of more than PROBE_DEPTH commits ends here.
        if base_rev and (
            self._contains(repository, head_rev, base_rev, branch_ref, complete)
            is not False
        ):
            return None

        if fork_point is None:
            return self._merge_base(repository, head_rev, branch_ref)
        return self._ensure_commit(repository, fork_point)

    def get_note(
        self,
        note: str,
        remote: str,
        revision: Optional[str] = None,
    ) -> Optional[str]:
        if not note.startswith("refs/notes/"):
            note = f"refs/notes/{note}"

        try:
            self.run("fetch", remote, f"{note}:{note}", stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            ls_output = self.run(
                "ls-remote",
                "--exit-code",
                remote,
                note,
                return_codes=(2,),
                stderr=subprocess.PIPE,
            )
            if not ls_output:
                logger.info(
                    "Failed to fetch %s but the remote doesn't have it. Ignoring.", note
                )
                return None
            raise

        try:
            return self.run(
                "notes", f"--ref={note}", "show", revision or "HEAD"
            ).strip()
        except subprocess.CalledProcessError as e:
            if e.returncode == 1:
                return None
            raise


def get_repository(path: str):
    """Get a repository object for the repository at `path`.
    If `path` is not a known VCS repository, raise an exception.
    """
    for path in ancestors(path):
        if os.path.isdir(os.path.join(path, ".hg")):
            return HgRepository(path)
        elif os.path.exists(os.path.join(path, ".git")):
            return GitRepository(path)

    raise RuntimeError("Current directory is neither a git or hg repository")
