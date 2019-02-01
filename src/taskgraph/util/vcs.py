# -*- coding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import os

import requests
import subprocess
from redo import retry

PUSHLOG_TMPL = '{}/json-pushes?version=2&changeset={}&tipsonly=1&full=1'


def find_hg_revision_push_info(repository, revision):
    """Given the parameters for this action and a revision, find the
    pushlog_id of the revision."""
    pushlog_url = PUSHLOG_TMPL.format(repository, revision)

    def query_pushlog(url):
        r = requests.get(pushlog_url, timeout=60)
        r.raise_for_status()
        return r
    r = retry(
        query_pushlog, args=(pushlog_url,),
        attempts=5, sleeptime=10,
    )
    pushes = r.json()['pushes']
    if len(pushes) != 1:
        raise RuntimeError(
            "Unable to find a single pushlog_id for {} revision {}: {}".format(
                repository, revision, pushes
            )
        )
    pushid = pushes.keys()[0]
    return {
        'pushdate': pushes[pushid]['date'],
        'pushid': pushid,
        'user': pushes[pushid]['user'],
    }


def get_hg_revision_branch(root, revision):
    """Given the parameters for a revision, find the hg_branch (aka
    relbranch) of the revision."""
    return subprocess.check_output([
        'hg', 'identify',
        '-T', '{branch}',
        '--rev', revision,
    ], cwd=root)


def get_repository_type(root):
    root = root or '.'
    if os.path.isdir(os.path.join(root, '.git')):
        return 'git'
    elif os.path.isdir(os.path.join(root, '.hg')):
        return 'hg'
    else:
        raise RuntimeError('Current directory is neither a git or hg repository')


# For these functions, we assume that run-task has correctly checked out the
# revision indicated by GECKO_HEAD_REF, so all that remains is to see what the
# current revision is.  Mercurial refers to that as `.`.
def get_commit_message(repository_type, root):
    if repository_type == 'hg':
        return subprocess.check_output(['hg', 'log', '-r', '.', '-T', '{desc}'], cwd=root)
    elif repository_type == 'git':
        return subprocess.check_output(['git', 'log', '-n1', '--format=%B'], cwd=root)
    else:
        raise RuntimeError('Only the "git" and "hg" repository types are supported for using '
                           'get_commit_message()')


def calculate_head_rev(repository_type, root):
    # we assume that run-task has correctly checked out the revision indicated by
    # VCS_HEAD_REF, so all that remains is to see what the current revision is.

    if repository_type == 'hg':
        # Mercurial refers to the current revision as `.`.
        return subprocess.check_output(['hg', 'log', '-r', '.', '-T', '{node}'], cwd=root)
    elif repository_type == 'git':
        # Git refers to the current revision as HEAD
        return subprocess.check_output(['git', 'rev-parse', '--verify', 'HEAD'], cwd=root)
    else:
        raise RuntimeError('Only the "git" and "hg" repository types are supported for using '
                           'calculate_head_rev()')


def get_repo_path(repository_type, root):
    if repository_type == 'hg':
        return subprocess.check_output(['hg', 'path', '-T', '{url}', 'default'], cwd=root)
    elif repository_type == 'git':
        return subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=root)
    else:
        raise RuntimeError('Only the "git" and "hg" repository types are supported for using '
                           'calculate_head_rev()')
