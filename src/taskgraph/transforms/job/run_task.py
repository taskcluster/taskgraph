# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Support for running jobs that are invoked via the `run-task` script.
"""

from __future__ import absolute_import, print_function, unicode_literals

import os
from six import text_type

from taskgraph.transforms.task import taskref_or_string
from taskgraph.transforms.job import run_job_using
from taskgraph.util import path
from taskgraph.util.schema import Schema
from taskgraph.transforms.job.common import support_vcs_checkout
from voluptuous import Required, Any, Optional

run_task_schema = Schema({
    Required('using'): 'run-task',

    # if true, add a cache at ~worker/.cache, which is where things like pip
    # tend to hide their caches.  This cache is never added for level-1 jobs.
    # TODO Once bug 1526028 is fixed, this and 'use-caches' should be merged.
    Required('cache-dotcache'): bool,

    # Whether or not to use caches.
    Optional('use-caches'): bool,

    # if true (the default), perform a checkout on the worker
    Required('checkout'): bool,

    Optional(
        "cwd",
        description="Path to run command in. If a checkout is present, the path "
        "to the checkout will be interpolated with the key `checkout`",
    ): text_type,

    # The sparse checkout profile to use. Value is the filename relative to the
    # directory where sparse profiles are defined (build/sparse-profiles/).
    Required('sparse-profile'): Any(basestring, None),

    # The command arguments to pass to the `run-task` script, after the
    # checkout arguments.  If a list, it will be passed directly; otherwise
    # it will be included in a single argument to `bash -cx`.
    Required('command'): Any([taskref_or_string], taskref_or_string),

    # Base work directory used to set up the task.
    Required('workdir'): basestring,

    # Whether to run as root. (defaults to False)
    Optional('run-as-root'): bool,
})


def common_setup(config, job, taskdesc, command):
    run = job['run']
    if run['checkout']:
        support_vcs_checkout(config, job, taskdesc,
                             sparse=bool(run['sparse-profile']))
        repositories = config.graph_config['taskgraph']['repositories']
        repo_prefix = repositories.keys()[0]

        vcs_path = taskdesc['worker']['env']['{}_PATH'.format(repo_prefix.upper())]
        command.append('--{}-checkout={}'.format(repo_prefix, vcs_path))

        if run['sparse-profile']:
            command.append('--{}-sparse-profile=build/sparse-profiles/{}'.format(
                repo_prefix,
                run['sparse-profile'],
            ))

        if 'cwd' in run:
            run['cwd'] = path.normpath(run['cwd'].format(checkout=vcs_path))
    elif 'cwd' in run and "{checkout}" in run['cwd']:
        raise Exception(
            "Found `{{checkout}}` interpolation in `cwd` for task {name} "
            "but the task doesn't have a checkout: {cwd}".format(
                cwd=run['cwd'], name=job.get("name", job.get("label"))
            )
        )

    if 'cwd' in run:
        command.extend(('--task-cwd', run['cwd']))

    taskdesc['worker'].setdefault('env', {})['MOZ_SCM_LEVEL'] = config.params['level']


worker_defaults = {
    'cache-dotcache': False,
    'checkout': True,
    'sparse-profile': None,
    'run-as-root': False,
}


def script_url(config, script):
    # This logic is a bit of a hack, and should be replaced by something better.
    # TASK_ID is used as a proxy for running in automation.  In that case, we
    # want to use the run-task/fetch-content corresponding to the taskgraph
    # version we are running, and otherwise, we aren't going to run the task we
    # generate, so the exact version doesn't matter.
    # If we checked out the taskgraph code with run-task in the decision task,
    # we can use TASKGRAPH_* to find the right version, which covers the
    # existing use case.
    if 'TASK_ID' in os.environ:
        if (
            'TASKGRAPH_HEAD_REPOSITORY' not in os.environ
            or 'TASKGRAPH_HEAD_REV' not in os.environ
        ):
            raise Exception(
                "Must specify 'TASKGRAPH_HEAD_REPOSITORY' and 'TASKGRAPH_HEAD_REV' "
                "to use run-task on generic-worker."
            )
    taskgraph_repo = os.environ.get(
        'TASKGRAPH_HEAD_REPOSITORY', 'https://hg.mozilla.org/ci/taskgraph'
    )
    taskgraph_rev = os.environ.get('TASKGRAPH_HEAD_REV', 'default')
    return '{}/raw-file/{}/src/taskgraph/run-task/{}'.format(taskgraph_repo, taskgraph_rev, script)


@run_job_using("docker-worker", "run-task", schema=run_task_schema, defaults=worker_defaults)
def docker_worker_run_task(config, job, taskdesc):
    run = job['run']
    worker = taskdesc['worker'] = job['worker']
    command = ['/usr/local/bin/run-task']
    common_setup(config, job, taskdesc, command)

    if run.get('cache-dotcache'):
        worker['caches'].append({
            'type': 'persistent',
            'name': '{project}-dotcache'.format(**config.params),
            'mount-point': '{workdir}/.cache'.format(**run),
            'skip-untrusted': True,
        })

    run_command = run['command']

    # dict is for the case of `{'task-reference': basestring}`.
    if isinstance(run_command, (basestring, dict)):
        run_command = ['bash', '-cx', run_command]
    command.append('--fetch-hgfingerprint')
    if run['run-as-root']:
        command.extend(('--user', 'root', '--group', 'root'))
    command.append('--')
    command.extend(run_command)
    worker['command'] = command


@run_job_using("generic-worker", "run-task", schema=run_task_schema, defaults=worker_defaults)
def generic_worker_run_task(config, job, taskdesc):
    run = job['run']
    worker = taskdesc['worker'] = job['worker']
    is_win = worker['os'] == 'windows'
    is_mac = worker['os'] == 'macosx'
    is_bitbar = worker['os'] == 'linux-bitbar'

    if is_win:
        command = ['C:/mozilla-build/python3/python3.exe', 'run-task']
    elif is_mac:
        command = ['/tools/python36/bin/python3', 'run-task']
    else:
        command = ['./run-task']

    common_setup(config, job, taskdesc, command)

    worker.setdefault('mounts', [])
    if run.get('cache-dotcache'):
        worker['mounts'].append({
            'cache-name': '{project}-dotcache'.format(**config.params),
            'directory': '{workdir}/.cache'.format(**run),
        })
    worker['mounts'].append({
        'content': {
            'url': script_url(config, 'run-task'),
        },
        'file': './run-task',
    })
    if worker.get('env', {}).get('MOZ_FETCHES'):
        worker['mounts'].append({
            'content': {
                'url': script_url(config, 'fetch-content'),
            },
            'file': './fetch-content',
        })

    run_command = run['command']

    if isinstance(run_command, basestring):
        if is_win:
            run_command = '"{}"'.format(run_command)
        run_command = ['bash', '-cx', run_command]

    if run['run-as-root']:
        command.extend(('--user', 'root', '--group', 'root'))
    command.append('--')
    if is_bitbar:
        # Use the bitbar wrapper script which sets up the device and adb
        # environment variables
        command.append('/builds/taskcluster/script.py')
    command.extend(run_command)

    if is_win:
        worker['command'] = [' '.join(command)]
    else:
        worker['command'] = [
            ['chmod', '+x', 'run-task'],
            command,
        ]