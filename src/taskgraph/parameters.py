# -*- coding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import json
import time
import yaml
from datetime import datetime

from taskgraph.util.hg import calculate_head_rev, get_repo_path
from taskgraph.util.memoize import memoize
from taskgraph.util.readonlydict import ReadOnlyDict


class ParameterMismatch(Exception):
    """Raised when a parameters.yml has extra or missing parameters."""


@memoize
def _get_head_ref():
    return calculate_head_rev(None)


@memoize
def _get_repo_path():
    return get_repo_path(None)


# Please keep this list sorted and in sync with taskcluster/docs/parameters.rst
# Parameters are of the form: {name: default}
PARAMETERS = {
    'base_repository': _get_repo_path,
    'build_date': lambda: int(time.time()),
    'do_not_optimize': [],
    'existing_tasks': {},
    'filters': ['target_tasks_method'],
    'head_ref': _get_head_ref,
    'head_repository': _get_repo_path,
    'head_rev': _get_head_ref,
    'hg_branch': 'default',
    'level': '3',
    'message': '',
    'moz_build_date': lambda: datetime.now().strftime("%Y%m%d%H%M%S"),
    'optimize_target_tasks': True,
    'owner': 'nobody@mozilla.com',
    'project': lambda: _get_repo_path().rsplit('/', 1)[1],
    'pushdate': lambda: int(time.time()),
    'pushlog_id': '0',
    'target_tasks_method': 'default',
}


class Parameters(ReadOnlyDict):
    """An immutable dictionary with nicer KeyError messages on failure"""

    def __init__(self, strict=True, **kwargs):
        self.strict = strict

        if not self.strict:
            # apply defaults to missing parameters
            for name, default in PARAMETERS.items():
                if name not in kwargs:
                    if callable(default):
                        default = default()
                    kwargs[name] = default

        ReadOnlyDict.__init__(self, **kwargs)

    def check(self):
        names = set(self)
        valid = set(PARAMETERS.keys())
        msg = []

        missing = valid - names
        if missing:
            msg.append("missing parameters: " + ", ".join(missing))

        extra = names - valid

        if extra and self.strict:
            msg.append("extra parameters: " + ", ".join(extra))

        if msg:
            raise ParameterMismatch("; ".join(msg))

    def __getitem__(self, k):
        if k not in PARAMETERS.keys():
            raise KeyError("no such parameter {!r}".format(k))
        try:
            return super(Parameters, self).__getitem__(k)
        except KeyError:
            raise KeyError("taskgraph parameter {!r} not found".format(k))

    def is_try(self):
        """
        Determine whether this graph is being built on a try project or for
        `mach try fuzzy`.
        """
        return 'try' in self['project']

    def file_url(self, path):
        """
        Determine the VCS URL for viewing a file in the tree, suitable for
        viewing by a human.

        :param basestring path: The path, relative to the root of the repository.

        :return basestring: The URL displaying the given path.
        """
        if path.startswith('comm/'):
            path = path[len('comm/'):]
            repo = self['comm_head_repository']
            rev = self['comm_head_rev']
        else:
            repo = self['head_repository']
            rev = self['head_rev']

        return '{}/file/{}/{}'.format(repo, rev, path)


def load_parameters_file(filename, strict=True, overrides=None):
    """
    Load parameters from a path, url, decision task-id or project.

    Examples:
        task-id=fdtgsD5DQUmAQZEaGMvQ4Q
        project=mozilla-central
    """
    import urllib
    from taskgraph.util.taskcluster import get_artifact_url, find_task_id

    if overrides is None:
        overrides = {}

    if not filename:
        return Parameters(strict=strict, **overrides)

    try:
        # reading parameters from a local parameters.yml file
        f = open(filename)
    except IOError:
        # fetching parameters.yml using task task-id, project or supplied url
        task_id = None
        if filename.startswith("task-id="):
            task_id = filename.split("=")[1]
        elif filename.startswith("project="):
            index = "gecko.v2.{project}.latest.taskgraph.decision".format(
                project=filename.split("=")[1],
            )
            task_id = find_task_id(index)

        if task_id:
            filename = get_artifact_url(task_id, 'public/parameters.yml')
        f = urllib.urlopen(filename)

    if filename.endswith('.yml'):
        kwargs = yaml.safe_load(f)
    elif filename.endswith('.json'):
        kwargs = json.load(f)
    else:
        raise TypeError("Parameters file `{}` is not JSON or YAML".format(filename))

    kwargs.update(overrides)

    return Parameters(strict=strict, **kwargs)
