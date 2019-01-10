# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Common support for various job types.  These functions are all named after the
worker implementation they operate on, and take the same three parameters, for
consistency.
"""

from __future__ import absolute_import, print_function, unicode_literals

from taskgraph.util.taskcluster import get_artifact_prefix


def docker_worker_add_workspace_cache(config, job, taskdesc, extra=None):
    """Add the workspace cache.

    ``extra`` is an optional kwarg passed in that supports extending the cache
    key name to avoid undesired conflicts with other caches."""
    taskdesc['worker'].setdefault('caches', []).append({
        'type': 'persistent',
        'name': 'level-{}-{}-build-{}-{}-workspace'.format(
            config.params['level'], config.params['project'],
            taskdesc['attributes']['build_platform'],
            taskdesc['attributes']['build_type'],
        ),
        'mount-point': "{workdir}/workspace".format(**job['run']),
        # Don't enable the workspace cache when we can't guarantee its
        # behavior, like on Try.
        'skip-untrusted': True,
    })
    if extra:
        taskdesc['worker']['caches'][-1]['name'] += '-{}'.format(
            extra
        )


def add_artifacts(config, job, taskdesc, path):
    taskdesc['worker'].setdefault('artifacts', []).append({
        'name': get_artifact_prefix(taskdesc),
        'path': path,
        'type': 'directory',
    })


def docker_worker_add_artifacts(config, job, taskdesc):
    """ Adds an artifact directory to the task """
    add_artifacts(config, job, taskdesc, path='{workdir}/artifacts/'.format(**job['run']))


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

    level = config.params['level']
    # native-engine and generic-worker do not support caches (yet), so we just
    # do a full clone every time :(
    if worker['implementation'] in ('docker-worker'):
        name = 'level-%s-checkouts' % level

        # Sparse checkouts need their own cache because they can interfere
        # with clients that aren't sparse aware.
        if sparse:
            name += '-sparse'

        taskdesc['worker'].setdefault('caches', []).append({
            'type': 'persistent',
            'name': name,
            'mount-point': checkoutdir,
        })

    taskdesc['worker'].setdefault('env', {}).update({
        'VCS_BASE_REPOSITORY': config.params['base_repository'],
        'VCS_HEAD_REPOSITORY': config.params['head_repository'],
        'VCS_HEAD_REV': config.params['head_rev'],
        'VCS_PATH': vcsdir,
        'HG_STORE_PATH': hgstore,
    })

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
