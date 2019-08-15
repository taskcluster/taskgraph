# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Common support for various job types.  These functions are all named after the
worker implementation they operate on, and take the same three parameters, for
consistency.
"""

from __future__ import absolute_import, print_function, unicode_literals

import json

from taskgraph.util.taskcluster import get_artifact_prefix


def add_cache(job, taskdesc, name, mount_point, skip_untrusted=False):
    """Adds a cache based on the worker's implementation.

    Args:
        job (dict): Task's job description.
        taskdesc (dict): Target task description to modify.
        name (str): Name of the cache.
        mount_point (path): Path on the host to mount the cache.
        skip_untrusted (bool): Whether cache is used in untrusted environments
            (default: False). Only applies to docker-worker.
    """
    if not job['run'].get('use-caches', True):
        return

    worker = job['worker']

    if worker['implementation'] == 'docker-worker':
        taskdesc['worker'].setdefault('caches', []).append({
            'type': 'persistent',
            'name': name,
            'mount-point': mount_point,
            'skip-untrusted': skip_untrusted,
        })

    elif worker['implementation'] == 'generic-worker':
        taskdesc['worker'].setdefault('mounts', []).append({
            'cache-name': name,
            'directory': mount_point,
        })

    else:
        # Caches not implemented
        pass


def docker_worker_add_workspace_cache(config, job, taskdesc, extra=None):
    """Add the workspace cache.

    Args:
        config (TransformConfig): Transform configuration object.
        job (dict): Task's job description.
        taskdesc (dict): Target task description to modify.
        extra (str): Optional context passed in that supports extending the cache
            key name to avoid undesired conflicts with other caches.
    """
    cache_name = '{}-build-{}-{}-workspace'.format(
        config.params['project'],
        taskdesc['attributes']['build_platform'],
        taskdesc['attributes']['build_type'],
    )
    if extra:
        cache_name = '{}-{}'.format(cache_name, extra)

    mount_point = "{workdir}/workspace".format(**job['run'])

    # Don't enable the workspace cache when we can't guarantee its
    # behavior, like on Try.
    add_cache(job, taskdesc, cache_name, mount_point, skip_untrusted=True)


def add_artifacts(config, job, taskdesc, path):
    taskdesc['worker'].setdefault('artifacts', []).append({
        'name': get_artifact_prefix(taskdesc),
        'path': path,
        'type': 'directory',
    })


def docker_worker_add_artifacts(config, job, taskdesc):
    """ Adds an artifact directory to the task """
    path = '{workdir}/artifacts/'.format(**job['run'])
    taskdesc['worker']['env']['UPLOAD_DIR'] = path
    add_artifacts(config, job, taskdesc, path)


def generic_worker_add_artifacts(config, job, taskdesc):
    """ Adds an artifact directory to the task """
    # The path is the location on disk; it doesn't necessarily
    # mean the artifacts will be public or private; that is set via the name
    # attribute in add_artifacts.
    add_artifacts(config, job, taskdesc, path=get_artifact_prefix(taskdesc))


def support_vcs_checkout(config, job, taskdesc, sparse=False):
    """Update a job/task with parameters to enable a VCS checkout.

    This can only be used with ``run-task`` tasks, as the cache name is
    reserved for ``run-task`` tasks.
    """
    worker = job['worker']
    is_win = worker['os'] == 'windows'
    is_linux = worker['os'] == 'linux'
    assert is_win or is_linux

    if is_win:
        checkoutdir = './build'
        vcsdir = '{}/src'.format(checkoutdir)
        hgstore = 'y:/hg-shared'
    else:
        checkoutdir = '{workdir}/checkouts'.format(**job['run'])
        vcsdir = '{}/src'.format(checkoutdir)
        hgstore = '{}/hg-store'.format(checkoutdir)

    cache_name = 'checkouts'

    # Sparse checkouts need their own cache because they can interfere
    # with clients that aren't sparse aware.
    if sparse:
        cache_name += '-sparse'

    add_cache(job, taskdesc, cache_name, checkoutdir)

    repositories = config.graph_config['taskgraph']['repositories']
    taskdesc['worker'].setdefault('env', {}).update({
        'HG_STORE_PATH': hgstore,
        'REPOSITORIES': json.dumps({
            repo: repo_config['name'] for repo, repo_config in repositories.items()
        }),
    })
    repo_prefix = next(repositories.iterkeys())
    taskdesc['worker'].setdefault('env', {}).update({
        '{}_{}'.format(repo_prefix.upper(), key): value for key, value in {
            'BASE_REPOSITORY'.format(repo_prefix): config.params['base_repository'],
            'HEAD_REPOSITORY'.format(repo_prefix): config.params['head_repository'],
            'HEAD_REV': config.params['head_rev'],
            'PATH': vcsdir,
            'REPOSITORY_TYPE': config.params['repository_type'],
        }.items()
    })

    if config.params['repository_type'] == 'hg':
        # Give task access to hgfingerprint secret so it can pin the certificate
        # for hg.mozilla.org.
        taskdesc['scopes'].append('secrets:get:project/taskcluster/gecko/hgfingerprint')

    # only some worker platforms have taskcluster-proxy enabled
    if job['worker']['implementation'] in ('docker-worker',):
        taskdesc['worker']['taskcluster-proxy'] = True


def generic_worker_hg_commands(base_repo, head_repo, head_rev, path):
    """Obtain commands needed to obtain a Mercurial checkout on generic-worker.

    Returns two command strings. One performs the checkout. Another logs.
    """
    args = [
        r'"c:\Program Files\Mercurial\hg.exe"',
        'robustcheckout',
        '--sharebase', r'y:\hg-shared',
        '--purge',
        '--upstream', base_repo,
        '--revision', head_rev,
        head_repo,
        path,
    ]

    logging_args = [
        b":: TinderboxPrint:<a href={source_repo}/rev/{revision} "
        b"title='Built from {repo_name} revision {revision}'>{revision}</a>"
        b"\n".format(
            revision=head_rev,
            source_repo=head_repo,
            repo_name=head_repo.split('/')[-1]),
    ]

    return [' '.join(args), ' '.join(logging_args)]
