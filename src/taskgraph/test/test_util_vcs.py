# -*- coding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import os
import pytest
import subprocess

from taskgraph.util.vcs import get_commit_message


@pytest.mark.parametrize('repo_type, commit_message, expected_result', ((
    'git', u'commit message in… pure utf8', u'commit message in… pure utf8\n\n',
), (
    'git', u'commit message in... ascii',
    u'commit message in... ascii\n\n',
), (
    'hg', 'hg commit message', 'hg commit message',
), (
    'hg', u'commit message in… pure utf8', u'commit message in… pure utf8',
), (
    'hg', b'commit message in... ascii then utf8',
    u'commit message in... ascii then utf8',
)))
def test_get_commit_message(tmpdir, repo_type, commit_message, expected_result):
    repo_dir = tmpdir.strpath
    some_file = tmpdir.join('some_file')
    some_file.write('some data')

    subprocess.check_output([repo_type, 'init'], cwd=repo_dir)
    subprocess.check_output([repo_type, 'add', some_file.strpath], cwd=repo_dir)
    # hg sometimes errors out with "nothing changed" even though the commit succeeded
    subprocess.call([repo_type, 'commit', '-m', commit_message], cwd=repo_dir)

    assert get_commit_message(repo_type, repo_dir) == expected_result


def test_get_commit_message_unsupported_repo():
    with pytest.raises(RuntimeError):
        get_commit_message('svn', '/some/repo/dir')
