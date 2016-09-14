# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Common support for various job types.  These functions are all named after the
worker implementation they operate on, and take the same three parameters, for
consistency.
"""

from __future__ import absolute_import, print_function, unicode_literals

SECRET_SCOPE = 'secrets:get:project/releng/gecko/{}/level-{}/{}'


def docker_worker_add_workspace_cache(config, job, taskdesc):
    """Add the workspace cache based on the build platform/type and level,
    except on try where workspace caches are not used."""
    if config.params['project'] == 'try':
        return

    taskdesc['worker'].setdefault('caches', []).append({
        'type': 'persistent',
        'name': 'level-{}-{}-build-{}-{}-workspace'.format(
            config.params['level'], config.params['project'],
            taskdesc['attributes']['build_platform'],
            taskdesc['attributes']['build_type'],
        ),
        'mount-point': "/home/worker/workspace",
    })


def docker_worker_add_tc_vcs_cache(config, job, taskdesc):
    taskdesc['worker'].setdefault('caches', []).append({
        'type': 'persistent',
        'name': 'level-{}-{}-tc-vcs'.format(
            config.params['level'], config.params['project']),
        'mount-point': "/home/worker/.tc-vcs",
    })


def docker_worker_add_public_artifacts(config, job, taskdesc):
    taskdesc['worker'].setdefault('artifacts', []).append({
        'name': 'public/build',
        'path': '/home/worker/artifacts/',
        'type': 'directory',
    })


def docker_worker_add_gecko_vcs_env_vars(config, job, taskdesc):
    """Add the GECKO_BASE_* and GECKO_HEAD_* env vars to the worker."""
    env = taskdesc['worker'].setdefault('env', {})
    env.update({
        'GECKO_BASE_REPOSITORY': config.params['base_repository'],
        'GECKO_HEAD_REF': config.params['head_rev'],
        'GECKO_HEAD_REPOSITORY': config.params['head_repository'],
        'GECKO_HEAD_REV': config.params['head_rev'],
    })


def docker_worker_setup_secrets(config, job, taskdesc):
    """Set up access to secrets via taskcluster-proxy.  The value of
    run['secrets'] should be a boolean or a list of secret names that
    can be accessed."""
    if not job['run'].get('secrets'):
        return

    taskdesc['worker']['taskcluster-proxy'] = True
    secrets = job['run']['secrets']
    if secrets is True:
        secrets = ['*']
    for sec in secrets:
        taskdesc['scopes'].append(SECRET_SCOPE.format(
            job['treeherder']['kind'], config.params['level'], sec))
