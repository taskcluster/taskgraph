# -*- coding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import json
import time
from datetime import datetime

from six import text_type

from taskgraph.util.schema import validate_schema
from taskgraph.util.vcs import calculate_head_rev, get_repo_path, get_repository_type
from taskgraph.util.memoize import memoize
from taskgraph.util.readonlydict import ReadOnlyDict
from voluptuous import (
    ALLOW_EXTRA,
    Required,
    Optional,
    Schema,
)


class ParameterMismatch(Exception):
    """Raised when a parameters.yml has extra or missing parameters."""


@memoize
def _get_repository_type():
    return get_repository_type(None)


@memoize
def _get_head_ref():
    return calculate_head_rev(_get_repository_type(), None)


@memoize
def _get_repo_path():
    return get_repo_path(_get_repository_type(), None)


# Please keep this list sorted and in sync with taskcluster/docs/parameters.rst
base_schema = Schema({
    Required('base_repository'): basestring,
    Required('build_date'): int,
    Required('do_not_optimize'): [basestring],
    Required('existing_tasks'): {basestring: basestring},
    Required('filters'): [basestring],
    Required('head_ref'): basestring,
    Required('head_repository'): basestring,
    Required('head_rev'): basestring,
    Required('head_tag'): basestring,
    Required('level'): basestring,
    Required('moz_build_date'): basestring,
    Required('optimize_target_tasks'): bool,
    Required('owner'): basestring,
    Required('project'): basestring,
    Required('pushdate'): int,
    Required('pushlog_id'): basestring,
    Required('repository_type'): basestring,
    Required('target_tasks_method'): basestring,
    Required('tasks_for'): basestring,
    Optional('code-review'): {
        Required('phabricator-build-target'): text_type,
    }
})


def extend_parameters_schema(schema):
    """
    Extend the schema for parameters to include per-project configuration.

    This should be called by the `taskgraph.register` function in the
    graph-configuration.
    """
    global base_schema
    base_schema = base_schema.extend(schema)


class Parameters(ReadOnlyDict):
    """An immutable dictionary with nicer KeyError messages on failure"""

    def __init__(self, strict=True, **kwargs):
        self.strict = strict

        if not self.strict:
            # apply defaults to missing parameters
            kwargs = Parameters._fill_defaults(**kwargs)

        ReadOnlyDict.__init__(self, **kwargs)

    @staticmethod
    def _fill_defaults(**kwargs):
        defaults = {
            'base_repository': _get_repo_path(),
            'build_date': int(time.time()),
            'do_not_optimize': [],
            'existing_tasks': {},
            'filters': ['target_tasks_method'],
            'head_ref': _get_head_ref(),
            'head_repository': _get_repo_path(),
            'head_rev': _get_head_ref(),
            'head_tag': '',
            'level': '3',
            'moz_build_date': datetime.now().strftime("%Y%m%d%H%M%S"),
            'optimize_target_tasks': True,
            'owner': 'nobody@mozilla.com',
            'project': _get_repo_path().rsplit('/', 1)[1],
            'pushdate': int(time.time()),
            'pushlog_id': '0',
            'repository_type': _get_repository_type(),
            'target_tasks_method': 'default',
            'tasks_for': '',
        }

        for name, default in defaults.items():
            if name not in kwargs:
                kwargs[name] = default
        return kwargs

    def check(self):
        schema = base_schema if self.strict else base_schema.extend({}, extra=ALLOW_EXTRA)
        try:
            validate_schema(schema, self.copy(), 'Invalid parameters:')
        except Exception as e:
            raise ParameterMismatch(e.message)

    def __getitem__(self, k):
        try:
            return super(Parameters, self).__getitem__(k)
        except KeyError:
            raise KeyError("taskgraph parameter {!r} not found".format(k))

    def is_try(self):
        """
        Determine whether this graph is being built on a try project or for
        `mach try fuzzy`.
        """
        return 'try' in self['project'] or self['tasks_for'] == 'github-pull-request'

    @property
    def moz_build_date(self):
        # XXX self["moz_build_date"] is left as a string because:
        #  * of backward compatibility
        #  * parameters are output in a YAML file
        return datetime.strptime(self["moz_build_date"], "%Y%m%d%H%M%S")

    def file_url(self, path, pretty=False):
        """
        Determine the VCS URL for viewing a file in the tree, suitable for
        viewing by a human.

        :param basestring path: The path, relative to the root of the repository.
        :param bool pretty: Whether to return a link to a formatted version of the
            file, or the raw file version.

        :return basestring: The URL displaying the given path.
        """
        if self['repository_type'] == 'hg':
            if path.startswith('comm/'):
                path = path[len('comm/'):]
                repo = self['comm_head_repository']
                rev = self['comm_head_rev']
            else:
                repo = self['head_repository']
                rev = self['head_rev']
            endpoint = 'file' if pretty else 'raw-file'
            return '{}/{}/{}/{}'.format(repo, endpoint, rev, path)
        elif self['repository_type'] == 'git':
            # For getting the file URL for git repositories, we only support a Github HTTPS remote
            repo = self['head_repository']
            if repo.startswith('https://github.com/'):
                if repo.endswith('/'):
                    repo = repo[:-1]

                rev = self['head_rev']
                endpoint = 'blob' if pretty else 'raw'
                return '{}/{}/{}/{}'.format(repo, endpoint, rev, path)
            elif repo.startswith('git@github.com:'):
                if repo.endswith('.git'):
                    repo = repo[:-4]
                rev = self['head_rev']
                endpoint = 'blob' if pretty else 'raw'
                return "{}/{}/{}/{}".format(
                    repo.replace("git@github.com:", "https://github.com/"),
                    endpoint,
                    rev,
                    path,
                )
            else:
                raise ParameterMismatch("Don't know how to determine file URL for non-github"
                                        "repo: {}".format(repo))
        else:
            raise RuntimeError(
                'Only the "git" and "hg" repository types are supported for using file_url()')


def load_parameters_file(filename, strict=True, overrides=None, trust_domain=None):
    """
    Load parameters from a path, url, decision task-id or project.

    Examples:
        task-id=fdtgsD5DQUmAQZEaGMvQ4Q
        project=mozilla-central
    """
    import urllib
    from taskgraph.util.taskcluster import get_artifact_url, find_task_id
    from taskgraph.util import yaml

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
            if trust_domain is None:
                raise ValueError(
                    "Can't specify parameters by project "
                    "if trust domain isn't supplied.",
                )
            index = "{trust_domain}.v2.{project}.latest.taskgraph.decision".format(
                trust_domain=trust_domain,
                project=filename.split("=")[1],
            )
            task_id = find_task_id(index)

        if task_id:
            filename = get_artifact_url(task_id, 'public/parameters.yml')
        f = urllib.urlopen(filename)

    if filename.endswith('.yml'):
        kwargs = yaml.load_stream(f)
    elif filename.endswith('.json'):
        kwargs = json.load(f)
    else:
        raise TypeError("Parameters file `{}` is not JSON or YAML".format(filename))

    kwargs.update(overrides)

    return Parameters(strict=strict, **kwargs)


def parameters_loader(filename, strict=True, overrides=None):
    def get_parameters(graph_config):
        parameters = load_parameters_file(
            filename,
            strict=strict,
            overrides=overrides,
            trust_domain=graph_config["trust-domain"],
        )
        parameters.check()
        return parameters
    return get_parameters
