# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
These transformations take a task description and turn it into a TaskCluster
task definition (along with attributes, label, etc.).  The input to these
transformations is generic to any kind of task, but abstracts away some of the
complexities of worker implementations, scopes, and treeherder annotations.
"""

from __future__ import absolute_import, print_function, unicode_literals

import hashlib
import os
import re
import time
from six import text_type

import attr

from taskgraph.util.hash import hash_path
from taskgraph.util.keyed_by import evaluate_keyed_by
from taskgraph.util.memoize import memoize
from taskgraph.util.treeherder import split_symbol
from taskgraph.transforms.base import TransformSequence
from taskgraph.util.schema import (
    validate_schema,
    Schema,
    optionally_keyed_by,
    resolve_keyed_by,
    OptimizationSchema,
    taskref_or_string,
)
from taskgraph.util.workertypes import worker_type_implementation
from voluptuous import Any, Required, Optional, Extra
from taskgraph import MAX_DEPENDENCIES
from ..util import docker as dockerutil
from ..util.workertypes import get_worker_type

RUN_TASK = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'run-task', 'run-task')


@memoize
def _run_task_suffix():
    """String to append to cache names under control of run-task."""
    return hash_path(RUN_TASK)[0:20]


# A task description is a general description of a TaskCluster task
task_description_schema = Schema({
    # the label for this task
    Required('label'): basestring,

    # description of the task (for metadata)
    Required('description'): basestring,

    # attributes for this task
    Optional('attributes'): {basestring: object},

    # relative path (from config.path) to the file task was defined in
    Optional('job-from'): basestring,

    # dependencies of this task, keyed by name; these are passed through
    # verbatim and subject to the interpretation of the Task's get_dependencies
    # method.
    Optional('dependencies'): {basestring: object},

    # Soft dependencies of this task, as a list of tasks labels
    Optional('soft-dependencies'): [basestring],

    Optional('requires'): Any('all-completed', 'all-resolved'),

    # expiration and deadline times, relative to task creation, with units
    # (e.g., "14 days").  Defaults are set based on the project.
    Optional('expires-after'): basestring,
    Optional('deadline-after'): basestring,

    # custom routes for this task; the default treeherder routes will be added
    # automatically
    Optional('routes'): [basestring],

    # custom scopes for this task; any scopes required for the worker will be
    # added automatically. The following parameters will be substituted in each
    # scope:
    #  {level} -- the scm level of this push
    #  {project} -- the project of this push
    Optional('scopes'): [basestring],

    # Tags
    Optional('tags'): {basestring: basestring},

    # custom "task.extra" content
    Optional('extra'): {basestring: object},

    # treeherder-related information; see
    # https://schemas.taskcluster.net/taskcluster-treeherder/v1/task-treeherder-config.json
    # If not specified, no treeherder extra information or routes will be
    # added to the task
    Optional('treeherder'): {
        # either a bare symbol, or "grp(sym)".
        'symbol': basestring,

        # the job kind
        'kind': Any('build', 'test', 'other'),

        # tier for this task
        'tier': int,

        # task platform, in the form platform/collection, used to set
        # treeherder.machine.platform and treeherder.collection or
        # treeherder.labels
        'platform': basestring,
    },

    # information for indexing this build so its artifacts can be discovered;
    # if omitted, the build will not be indexed.
    Optional('index'): {
        # the name of the product this build produces
        'product': basestring,

        # the names to use for this job in the TaskCluster index
        'job-name': basestring,

        # Type of gecko v2 index to use
        'type': Any('generic'),

        # The rank that the task will receive in the TaskCluster
        # index.  A newly completed task supercedes the currently
        # indexed task iff it has a higher rank.  If unspecified,
        # 'by-tier' behavior will be used.
        'rank': Any(
            # Rank is equal the timestamp of the build_date for tier-1
            # tasks, and zero for non-tier-1.  This sorts tier-{2,3}
            # builds below tier-1 in the index.
            'by-tier',

            # Rank is given as an integer constant (e.g. zero to make
            # sure a task is last in the index).
            int,

            # Rank is equal to the timestamp of the build_date.  This
            # option can be used to override the 'by-tier' behavior
            # for non-tier-1 tasks.
            'build_date',
        ),
    },

    # The `run_on_projects` attribute, defaulting to "all".  This dictates the
    # projects on which this task should be included in the target task set.
    # See the attributes documentation for details.
    Optional('run-on-projects'): optionally_keyed_by('build-platform', [basestring]),

    # Like `run_on_projects`, `run-on-hg-branches` defaults to "all".
    Optional('run-on-hg-branches'): optionally_keyed_by('project', [basestring]),

    # The `always-target` attribute will cause the task to be included in the
    # target_task_graph regardless of filtering. Tasks included in this manner
    # will be candidates for optimization even when `optimize_target_tasks` is
    # False, unless the task was also explicitly chosen by the target_tasks
    # method.
    Required('always-target'): bool,

    # Optimization to perform on this task during the optimization phase.
    # Optimizations are defined in taskcluster/taskgraph/optimize.py.
    Required('optimization'): OptimizationSchema,

    # the provisioner-id/worker-type for the task.  The following parameters will
    # be substituted in this string:
    #  {level} -- the scm level of this push
    'worker-type': basestring,

    # Whether the job should use sccache compiler caching.
    Required('needs-sccache'): bool,

    # information specific to the worker implementation that will run this task
    Optional('worker'): {
        Required('implementation'): basestring,
        Extra: object,
    }
})

TC_TREEHERDER_SCHEMA_URL = 'https://github.com/taskcluster/taskcluster-treeherder/' \
                           'blob/master/schemas/task-treeherder-config.yml'


UNKNOWN_GROUP_NAME = "Treeherder group {} (from {}) has no name; " \
                     "add it to taskcluster/ci/config.yml"

V2_ROUTE_TEMPLATES = [
    "index.{trust-domain}.v2.{project}.latest.{product}.{job-name}",
    "index.{trust-domain}.v2.{project}.pushdate.{build_date_long}.{product}.{job-name}",
    "index.{trust-domain}.v2.{project}.pushlog-id.{pushlog_id}.{product}.{job-name}",
    "index.{trust-domain}.v2.{project}.revision.{branch_rev}.{product}.{job-name}",
]

# the roots of the treeherder routes
TREEHERDER_ROUTE_ROOT = 'tc-treeherder'


def get_branch_rev(config):
    return config.params['head_rev']


@memoize
def get_default_priority(graph_config, project):
    return evaluate_keyed_by(
        graph_config['task-priority'],
        "Graph Config",
        {'project': project}
    )


# define a collection of payload builders, depending on the worker implementation
payload_builders = {}


@attr.s(frozen=True)
class PayloadBuilder(object):
    schema = attr.ib(type=Schema)
    builder = attr.ib()


def payload_builder(name, schema):
    schema = Schema({Required('implementation'): name, Optional('os'): text_type}).extend(schema)

    def wrap(func):
        payload_builders[name] = PayloadBuilder(schema, func)
        return func
    return wrap


# define a collection of index builders, depending on the type implementation
index_builders = {}


def index_builder(name):
    def wrap(func):
        index_builders[name] = func
        return func
    return wrap


UNSUPPORTED_INDEX_PRODUCT_ERROR = """\
The index product {product} is not in the list of configured products in
`taskcluster/ci/config.yml'.
"""


def verify_index(config, index):
    product = index['product']
    if product not in config.graph_config['index']['products']:
        raise Exception(UNSUPPORTED_INDEX_PRODUCT_ERROR.format(product=product))


@payload_builder('docker-worker', schema={
    Required('os'): 'linux',

    # For tasks that will run in docker-worker, this is the name of the docker
    # image or in-tree docker image to run the task in.  If in-tree, then a
    # dependency will be created automatically.  This is generally
    # `desktop-test`, or an image that acts an awful lot like it.
    Required('docker-image'): Any(
        # a raw Docker image path (repo/image:tag)
        basestring,
        # an in-tree generated docker image (from `taskcluster/docker/<name>`)
        {'in-tree': basestring},
        # an indexed docker image
        {'indexed': basestring},
    ),

    # worker features that should be enabled
    Required('relengapi-proxy'): bool,
    Required('chain-of-trust'): bool,
    Required('taskcluster-proxy'): bool,
    Required('allow-ptrace'): bool,
    Required('loopback-video'): bool,
    Required('loopback-audio'): bool,
    Required('docker-in-docker'): bool,  # (aka 'dind')
    Required('privileged'): bool,

    # Paths to Docker volumes.
    #
    # For in-tree Docker images, volumes can be parsed from Dockerfile.
    # This only works for the Dockerfile itself: if a volume is defined in
    # a base image, it will need to be declared here. Out-of-tree Docker
    # images will also require explicit volume annotation.
    #
    # Caches are often mounted to the same path as Docker volumes. In this
    # case, they take precedence over a Docker volume. But a volume still
    # needs to be declared for the path.
    Optional('volumes'): [basestring],

    # caches to set up for the task
    Optional('caches'): [{
        # only one type is supported by any of the workers right now
        'type': 'persistent',

        # name of the cache, allowing re-use by subsequent tasks naming the
        # same cache
        'name': basestring,

        # location in the task image where the cache will be mounted
        'mount-point': basestring,

        # Whether the cache is not used in untrusted environments
        # (like the Try repo).
        Optional('skip-untrusted'): bool,
    }],

    # artifacts to extract from the task image after completion
    Optional('artifacts'): [{
        # type of artifact -- simple file, or recursive directory
        'type': Any('file', 'directory'),

        # task image path from which to read artifact
        'path': basestring,

        # name of the produced artifact (root of the names for
        # type=directory)
        'name': basestring,
    }],

    # environment variables
    Required('env'): {basestring: taskref_or_string},

    # the command to run; if not given, docker-worker will default to the
    # command in the docker image
    Optional('command'): [taskref_or_string],

    # the maximum time to run, in seconds
    Required('max-run-time'): int,

    # the exit status code(s) that indicates the task should be retried
    Optional('retry-exit-status'): [int],

    # the exit status code(s) that indicates the caches used by the task
    # should be purged
    Optional('purge-caches-exit-status'): [int],

    # Wether any artifacts are assigned to this worker
    Optional('skip-artifacts'): bool,
})
def build_docker_worker_payload(config, task, task_def):
    worker = task['worker']
    level = int(config.params['level'])

    image = worker['docker-image']
    if isinstance(image, dict):
        if 'in-tree' in image:
            name = image['in-tree']
            docker_image_task = 'build-docker-image-' + image['in-tree']
            task.setdefault('dependencies', {})['docker-image'] = docker_image_task

            image = {
                "path": "public/image.tar.zst",
                "taskId": {"task-reference": "<docker-image>"},
                "type": "task-image",
            }

            # Find VOLUME in Dockerfile.
            volumes = dockerutil.parse_volumes(name)
            for v in sorted(volumes):
                if v in worker['volumes']:
                    raise Exception('volume %s already defined; '
                                    'if it is defined in a Dockerfile, '
                                    'it does not need to be specified in the '
                                    'worker definition' % v)

                worker['volumes'].append(v)

        elif 'indexed' in image:
            image = {
                "path": "public/image.tar.zst",
                "namespace": image['indexed'],
                "type": "indexed-image",
            }
        else:
            raise Exception("unknown docker image type")

    features = {}

    if worker.get('relengapi-proxy'):
        features['relengAPIProxy'] = True

    if worker.get('taskcluster-proxy'):
        features['taskclusterProxy'] = True

    if worker.get('allow-ptrace'):
        features['allowPtrace'] = True
        task_def['scopes'].append('docker-worker:feature:allowPtrace')

    if worker.get('chain-of-trust'):
        features['chainOfTrust'] = True

    if worker.get('docker-in-docker'):
        features['dind'] = True

    if task.get('needs-sccache'):
        features['taskclusterProxy'] = True
        task_def['scopes'].append(
            'assume:project:taskcluster:{trust_domain}:level-{level}-sccache-buckets'.format(
                trust_domain=config.graph_config['trust-domain'],
                level=config.params['level'])
        )
        worker['env']['USE_SCCACHE'] = '1'
        # Disable sccache idle shutdown.
        worker['env']['SCCACHE_IDLE_TIMEOUT'] = '0'
    else:
        worker['env']['SCCACHE_DISABLE'] = '1'

    capabilities = {}

    for lo in 'audio', 'video':
        if worker.get('loopback-' + lo):
            capitalized = 'loopback' + lo.capitalize()
            devices = capabilities.setdefault('devices', {})
            devices[capitalized] = True
            task_def['scopes'].append('docker-worker:capability:device:' + capitalized)

    if worker.get('privileged'):
        capabilities['privileged'] = True
        task_def['scopes'].append('docker-worker:capability:privileged')

    task_def['payload'] = payload = {
        'image': image,
        'env': worker['env'],
    }
    if 'command' in worker:
        payload['command'] = worker['command']

    if 'max-run-time' in worker:
        payload['maxRunTime'] = worker['max-run-time']

    run_task = payload.get('command', [''])[0].endswith('run-task')

    # run-task exits EXIT_PURGE_CACHES if there is a problem with caches.
    # Automatically retry the tasks and purge caches if we see this exit
    # code.
    # TODO move this closer to code adding run-task once bug 1469697 is
    # addressed.
    if run_task:
        worker.setdefault('retry-exit-status', []).append(72)
        worker.setdefault('purge-caches-exit-status', []).append(72)

    payload['onExitStatus'] = {}
    if 'retry-exit-status' in worker:
        payload['onExitStatus']['retry'] = worker['retry-exit-status']
    if 'purge-caches-exit-status' in worker:
        payload['onExitStatus']['purgeCaches'] = worker['purge-caches-exit-status']

    if 'artifacts' in worker:
        artifacts = {}
        for artifact in worker['artifacts']:
            artifacts[artifact['name']] = {
                'path': artifact['path'],
                'type': artifact['type'],
                'expires': task_def['expires'],  # always expire with the task
            }
        payload['artifacts'] = artifacts

    if isinstance(worker.get('docker-image'), basestring):
        out_of_tree_image = worker['docker-image']
        run_task = run_task or out_of_tree_image.startswith(
            'taskcluster/image_builder')
    else:
        out_of_tree_image = None
        image = worker.get('docker-image', {}).get('in-tree')
        run_task = run_task or image == 'image_builder'

    if 'caches' in worker:
        caches = {}

        # run-task knows how to validate caches.
        #
        # To help ensure new run-task features and bug fixes don't interfere
        # with existing caches, we seed the hash of run-task into cache names.
        # So, any time run-task changes, we should get a fresh set of caches.
        # This means run-task can make changes to cache interaction at any time
        # without regards for backwards or future compatibility.
        #
        # But this mechanism only works for in-tree Docker images that are built
        # with the current run-task! For out-of-tree Docker images, we have no
        # way of knowing their content of run-task. So, in addition to varying
        # cache names by the contents of run-task, we also take the Docker image
        # name into consideration. This means that different Docker images will
        # never share the same cache. This is a bit unfortunate. But it is the
        # safest thing to do. Fortunately, most images are defined in-tree.
        #
        # For out-of-tree Docker images, we don't strictly need to incorporate
        # the run-task content into the cache name. However, doing so preserves
        # the mechanism whereby changing run-task results in new caches
        # everywhere.

        # As an additional mechanism to force the use of different caches, the
        # string literal in the variable below can be changed. This is
        # preferred to changing run-task because it doesn't require images
        # to be rebuilt.
        cache_version = 'v3'

        if run_task:
            suffix = '{}-{}'.format(cache_version, _run_task_suffix())

            if out_of_tree_image:
                name_hash = hashlib.sha256(out_of_tree_image).hexdigest()
                suffix += name_hash[0:12]

        else:
            suffix = cache_version

        skip_untrusted = config.params.is_try() or level == 1

        for cache in worker['caches']:
            # Some caches aren't enabled in environments where we can't
            # guarantee certain behavior. Filter those out.
            if cache.get('skip-untrusted') and skip_untrusted:
                continue

            name = '{trust_domain}-level-{level}-{name}-{suffix}'.format(
                trust_domain=config.graph_config['trust-domain'],
                level=config.params['level'],
                name=cache['name'],
                suffix=suffix,
            )
            caches[name] = cache['mount-point']
            task_def['scopes'].append('docker-worker:cache:%s' % name)

        # Assertion: only run-task is interested in this.
        if run_task:
            payload['env']['TASKCLUSTER_CACHES'] = ';'.join(sorted(
                caches.values()))

        payload['cache'] = caches

    # And send down volumes information to run-task as well.
    if run_task and worker.get('volumes'):
        payload['env']['TASKCLUSTER_VOLUMES'] = ';'.join(
            sorted(worker['volumes']))

    if payload.get('cache') and skip_untrusted:
        payload['env']['TASKCLUSTER_UNTRUSTED_CACHES'] = '1'

    if features:
        payload['features'] = features
    if capabilities:
        payload['capabilities'] = capabilities

    check_caches_are_volumes(task)


@payload_builder('invalid', schema={
    # an invalid task is one which should never actually be created; this is used in
    # release automation on branches where the task just doesn't make sense
    Extra: object,
})
def build_invalid_payload(config, task, task_def):
    task_def['payload'] = 'invalid task - should never be created'


@payload_builder('always-optimized', schema={
    Extra: object,
})
@payload_builder('succeed', schema={
})
def build_dummy_payload(config, task, task_def):
    task_def['payload'] = {}


transforms = TransformSequence()


@transforms.add
def set_implementation(config, tasks):
    """
    Set the worker implementation based on the worker-type alias.
    """
    for task in tasks:
        if 'implementation' in task['worker']:
            yield task
            continue

        impl, os = worker_type_implementation(config.graph_config, task['worker-type'])

        tags = task.setdefault('tags', {})
        tags['worker-implementation'] = impl
        if os:
            task['tags']['os'] = os
        worker = task.setdefault('worker', {})
        worker['implementation'] = impl
        if os:
            worker['os'] = os

        yield task


@transforms.add
def set_defaults(config, tasks):
    for task in tasks:
        task.setdefault('always-target', False)
        task.setdefault('optimization', None)
        task.setdefault('needs-sccache', False)

        worker = task['worker']
        if worker['implementation'] in ('docker-worker',):
            worker.setdefault('relengapi-proxy', False)
            worker.setdefault('chain-of-trust', False)
            worker.setdefault('taskcluster-proxy', False)
            worker.setdefault('allow-ptrace', False)
            worker.setdefault('loopback-video', False)
            worker.setdefault('loopback-audio', False)
            worker.setdefault('docker-in-docker', False)
            worker.setdefault('privileged', False)
            worker.setdefault('volumes', [])
            worker.setdefault('env', {})
            if 'caches' in worker:
                for c in worker['caches']:
                    c.setdefault('skip-untrusted', False)
        elif worker['implementation'] == 'generic-worker':
            worker.setdefault('env', {})
            worker.setdefault('os-groups', [])
            if worker['os-groups'] and worker['os'] != 'windows':
                raise Exception('os-groups feature of generic-worker is only supported on '
                                'Windows, not on {}'.format(worker['os']))
            worker.setdefault('chain-of-trust', False)
        elif worker['implementation'] in (
            'scriptworker-signing', 'beetmover', 'beetmover-push-to-release', 'beetmover-maven',
        ):
            worker.setdefault('max-run-time', 600)
        elif worker['implementation'] == 'push-apk':
            worker.setdefault('commit', False)

        yield task


@transforms.add
def task_name_from_label(config, tasks):
    for task in tasks:
        if 'label' not in task:
            if 'name' not in task:
                raise Exception("task has neither a name nor a label")
            task['label'] = '{}-{}'.format(config.kind, task['name'])
        if task.get('name'):
            del task['name']
        yield task


@transforms.add
def validate(config, tasks):
    for task in tasks:
        validate_schema(
            task_description_schema, task,
            "In task {!r}:".format(task.get('label', '?no-label?')))
        validate_schema(
           payload_builders[task['worker']['implementation']].schema,
           task['worker'],
           "In task.run {!r}:".format(task.get('label', '?no-label?')))
        yield task


@index_builder('generic')
def add_generic_index_routes(config, task):
    index = task.get('index')
    routes = task.setdefault('routes', [])

    verify_index(config, index)

    subs = config.params.copy()
    subs['job-name'] = index['job-name']
    subs['build_date_long'] = time.strftime("%Y.%m.%d.%Y%m%d%H%M%S",
                                            time.gmtime(config.params['build_date']))
    subs['product'] = index['product']
    subs['trust-domain'] = config.graph_config['trust-domain']
    subs['branch_rev'] = get_branch_rev(config)

    for tpl in V2_ROUTE_TEMPLATES:
        routes.append(tpl.format(**subs))

    return task


@transforms.add
def add_index_routes(config, tasks):
    for task in tasks:
        index = task.get('index', {})

        # The default behavior is to rank tasks according to their tier
        extra_index = task.setdefault('extra', {}).setdefault('index', {})
        rank = index.get('rank', 'by-tier')

        if rank == 'by-tier':
            # rank is zero for non-tier-1 tasks and based on pushid for others;
            # this sorts tier-{2,3} builds below tier-1 in the index
            tier = task.get('treeherder', {}).get('tier', 3)
            extra_index['rank'] = 0 if tier > 1 else int(config.params['build_date'])
        elif rank == 'build_date':
            extra_index['rank'] = int(config.params['build_date'])
        else:
            extra_index['rank'] = rank

        if not index:
            yield task
            continue

        index_type = index.get('type', 'generic')
        task = index_builders[index_type](config, task)

        del task['index']
        yield task


@transforms.add
def build_task(config, tasks):
    for task in tasks:
        level = str(config.params['level'])

        provisioner_id, worker_type = get_worker_type(
            config.graph_config,
            task['worker-type'],
            level,
        )
        task['worker-type'] = '/'.join([provisioner_id, worker_type])
        project = config.params['project']

        routes = task.get('routes', [])
        scopes = [s.format(level=level, project=project) for s in task.get('scopes', [])]

        # set up extra
        extra = task.get('extra', {})
        extra['parent'] = os.environ.get('TASK_ID', '')
        task_th = task.get('treeherder')
        if task_th:
            extra.setdefault('treeherder-platform', task_th['platform'])
            treeherder = extra.setdefault('treeherder', {})

            machine_platform, collection = task_th['platform'].split('/', 1)
            treeherder['machine'] = {'platform': machine_platform}
            treeherder['collection'] = {collection: True}

            group_names = config.graph_config['treeherder']['group-names']
            groupSymbol, symbol = split_symbol(task_th['symbol'])
            if groupSymbol != '?':
                treeherder['groupSymbol'] = groupSymbol
                if groupSymbol not in group_names:
                    path = os.path.join(config.path, task.get('job-from', ''))
                    raise Exception(UNKNOWN_GROUP_NAME.format(groupSymbol, path))
                treeherder['groupName'] = group_names[groupSymbol]
            treeherder['symbol'] = symbol
            if len(symbol) > 25 or len(groupSymbol) > 25:
                raise RuntimeError("Treeherder group and symbol names must not be longer than "
                                   "25 characters: {} (see {})".format(
                                       task_th['symbol'],
                                       TC_TREEHERDER_SCHEMA_URL,
                                       ))
            treeherder['jobKind'] = task_th['kind']
            treeherder['tier'] = task_th['tier']

            branch_rev = get_branch_rev(config)

            routes.append(
                '{}.v2.{}.{}.{}'.format(TREEHERDER_ROUTE_ROOT,
                                        config.params['project'],
                                        branch_rev,
                                        config.params['pushlog_id'])
            )

        if 'expires-after' not in task:
            task['expires-after'] = '28 days' if config.params.is_try() else '1 year'

        if 'deadline-after' not in task:
            task['deadline-after'] = '1 day'

        if 'priority' not in task:
            task['priority'] = get_default_priority(config.graph_config, config.params['project'])

        tags = task.get('tags', {})
        tags.update({
            'createdForUser': config.params['owner'],
            'kind': config.kind,
            'label': task['label'],
        })

        task_def = {
            'provisionerId': provisioner_id,
            'workerType': worker_type,
            'routes': routes,
            'created': {'relative-datestamp': '0 seconds'},
            'deadline': {'relative-datestamp': task['deadline-after']},
            'expires': {'relative-datestamp': task['expires-after']},
            'scopes': scopes,
            'metadata': {
                'description': task['description'],
                'name': task['label'],
                'owner': config.params['owner'],
                'source': config.params.file_url(config.path, pretty=True),
            },
            'extra': extra,
            'tags': tags,
            'priority': task['priority'],
        }

        if task.get('requires', None):
            task_def['requires'] = task['requires']

        if task_th:
            # link back to treeherder in description
            th_push_link = 'https://treeherder.mozilla.org/#/jobs?repo={}&revision={}'.format(
                config.params['project'], branch_rev)
            task_def['metadata']['description'] += ' ([Treeherder push]({}))'.format(
                th_push_link)

        # add the payload and adjust anything else as required (e.g., scopes)
        payload_builders[task['worker']['implementation']].builder(config, task, task_def)

        attributes = task.get('attributes', {})
        # Resolve run-on-projects
        build_platform = attributes.get('build_platform')
        resolve_keyed_by(task, 'run-on-projects', item_name=task['label'],
                         **{'build-platform': build_platform})
        attributes['run_on_projects'] = task.get('run-on-projects', ['all'])
        attributes['always_target'] = task['always-target']

        # Set MOZ_AUTOMATION on all jobs.
        if task['worker']['implementation'] in (
            'generic-worker',
            'docker-worker',
        ):
            payload = task_def.get('payload')
            if payload:
                env = payload.setdefault('env', {})
                env['MOZ_AUTOMATION'] = '1'

        yield {
            'label': task['label'],
            'task': task_def,
            'dependencies': task.get('dependencies', {}),
            'soft-dependencies': task.get('soft-dependencies', []),
            'attributes': attributes,
            'optimization': task.get('optimization', None),
        }


@transforms.add
def chain_of_trust(config, tasks):
    for task in tasks:
        if task['task'].get('payload', {}).get('features', {}).get('chainOfTrust'):
            image = task.get('dependencies', {}).get('docker-image')
            if image:
                cot = task['task'].setdefault('extra', {}).setdefault('chainOfTrust', {})
                cot.setdefault('inputs', {})['docker-image'] = {
                    'task-reference': '<docker-image>'
                }
        yield task


@transforms.add
def check_task_identifiers(config, tasks):
    """Ensures that all tasks have well defined identifiers:
       ^[a-zA-Z0-9_-]{1,22}$
    """
    e = re.compile("^[a-zA-Z0-9_-]{1,22}$")
    for task in tasks:
        for attrib in ('workerType', 'provisionerId'):
            if not e.match(task['task'][attrib]):
                raise Exception(
                    'task {}.{} is not a valid identifier: {}'.format(
                        task['label'], attrib, task['task'][attrib]))
        yield task


@transforms.add
def check_task_dependencies(config, tasks):
    """Ensures that tasks don't have more than 100 dependencies."""
    for task in tasks:
        if len(task['dependencies']) > MAX_DEPENDENCIES:
            raise Exception(
                    'task {}/{} has too many dependencies ({} > {})'.format(
                        config.kind, task['label'], len(task['dependencies']),
                        MAX_DEPENDENCIES))
        yield task


def check_caches_are_volumes(task):
    """Ensures that all cache paths are defined as volumes.

    Caches and volumes are the only filesystem locations whose content
    isn't defined by the Docker image itself. Some caches are optional
    depending on the job environment. We want paths that are potentially
    caches to have as similar behavior regardless of whether a cache is
    used. To help enforce this, we require that all paths used as caches
    to be declared as Docker volumes. This check won't catch all offenders.
    But it is better than nothing.
    """
    volumes = set(task['worker']['volumes'])
    paths = set(c['mount-point'] for c in task['worker'].get('caches', []))
    missing = paths - volumes

    if not missing:
        return

    raise Exception('task %s (image %s) has caches that are not declared as '
                    'Docker volumes: %s '
                    '(have you added them as VOLUMEs in the Dockerfile?)'
                    % (task['label'], task['worker']['docker-image'],
                       ', '.join(sorted(missing))))


@transforms.add
def check_run_task_caches(config, tasks):
    """Audit for caches requiring run-task.

    run-task manages caches in certain ways. If a cache managed by run-task
    is used by a non run-task task, it could cause problems. So we audit for
    that and make sure certain cache names are exclusive to run-task.

    IF YOU ARE TEMPTED TO MAKE EXCLUSIONS TO THIS POLICY, YOU ARE LIKELY
    CONTRIBUTING TECHNICAL DEBT AND WILL HAVE TO SOLVE MANY OF THE PROBLEMS
    THAT RUN-TASK ALREADY SOLVES. THINK LONG AND HARD BEFORE DOING THAT.
    """
    re_reserved_caches = re.compile('''^
        (checkouts|tooltool-cache)
    ''', re.VERBOSE)

    cache_prefix = '{trust_domain}-level-{level}-'.format(
        trust_domain=config.graph_config['trust-domain'],
        level=config.params['level'],
    )

    suffix = _run_task_suffix()

    for task in tasks:
        payload = task['task'].get('payload', {})
        command = payload.get('command') or ['']

        main_command = command[0] if isinstance(command[0], basestring) else ''
        run_task = main_command.endswith('run-task')

        for cache in payload.get('cache', {}):
            if not cache.startswith(cache_prefix):
                raise Exception(
                    '{} is using a cache ({}) which is not appropriate '
                    'for its trust-domain and level. It should start with {}.'
                    .format(task['label'], cache, cache_prefix)
                )

            cache = cache[len(cache_prefix):]

            if not re_reserved_caches.match(cache):
                continue

            if not run_task:
                raise Exception(
                    '%s is using a cache (%s) reserved for run-task '
                    'change the task to use run-task or use a different '
                    'cache name' % (task['label'], cache))

            if not cache.endswith(suffix):
                raise Exception(
                    '%s is using a cache (%s) reserved for run-task '
                    'but the cache name is not dependent on the contents '
                    'of run-task; change the cache name to conform to the '
                    'naming requirements' % (task['label'], cache))

        yield task
