# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import logging
import itertools

from . import base
from .. import files_changed
from ..util.python_path import find_object
from ..util.templates import merge
from ..util.yaml import load_yaml
from ..util.seta import is_low_value_task

from ..transforms.base import TransformSequence, TransformConfig

logger = logging.getLogger(__name__)


class TransformTask(base.Task):
    """
    Tasks of this class are generated by applying transformations to a sequence
    of input entities.  By default, it gets those inputs from YAML data in the
    kind directory, but subclasses may override `get_inputs` to produce them in
    some other way.
    """

    @classmethod
    def get_inputs(cls, kind, path, config, params, loaded_tasks):
        """
        Get the input elements that will be transformed into tasks.  The
        elements themselves are free-form, and become the input to the first
        transform.

        By default, this reads jobs from the `jobs` key, or from yaml files
        named by `jobs-from`.  The entities are read from mappings, and the
        keys to those mappings are added in the `name` key of each entity.

        If there is a `job-defaults` config, then every job is merged with it.
        This provides a simple way to set default values for all jobs of a
        kind.  More complex defaults should be implemented with custom
        transforms.

        This method can be overridden in subclasses that need to perform more
        complex calculations to generate the list of inputs.
        """
        def jobs():
            defaults = config.get('job-defaults')
            jobs = config.get('jobs', {}).iteritems()
            jobs_from = itertools.chain.from_iterable(
                load_yaml(path, filename).iteritems()
                for filename in config.get('jobs-from', {}))
            for name, job in itertools.chain(jobs, jobs_from):
                if defaults:
                    job = merge(defaults, job)
                yield name, job

        for name, job in jobs():
            job['name'] = name
            logger.debug("Generating tasks for {} {}".format(kind, name))
            yield job

    @classmethod
    def load_tasks(cls, kind, path, config, params, loaded_tasks):
        inputs = cls.get_inputs(kind, path, config, params, loaded_tasks)

        transforms = TransformSequence()
        for xform_path in config['transforms']:
            transform = find_object(xform_path)
            transforms.add(transform)

        # perform the transformations
        trans_config = TransformConfig(kind, path, config, params)
        tasks = [cls(kind, t) for t in transforms(trans_config, inputs)]
        return tasks

    def __init__(self, kind, task):
        self.dependencies = task['dependencies']
        self.when = task['when']
        super(TransformTask, self).__init__(kind, task['label'],
                                            task['attributes'], task['task'],
                                            index_paths=task.get('index-paths'))

    def get_dependencies(self, taskgraph):
        return [(label, name) for name, label in self.dependencies.items()]

    def optimize(self, params):
        bbb_task = False

        if self.index_paths:
            optimized, taskId = super(TransformTask, self).optimize(params)
            if optimized:
                return optimized, taskId

        elif 'files-changed' in self.when:
            changed = files_changed.check(
                params, self.when['files-changed'])
            if not changed:
                logger.debug('no files found matching a pattern in `when.files-changed` for ' +
                             self.label)
                return True, None

        # no need to call SETA for build jobs
        if self.task.get('extra', {}).get('treeherder', {}).get('jobKind', '') == 'build':
            return False, None

        # for bbb tasks we need to send in the buildbot buildername
        if self.task.get('provisionerId', '') == 'buildbot-bridge':
            self.label = self.task.get('payload').get('buildername')
            bbb_task = True

        # we would like to return 'False, None' while it's high_value_task
        # and we wouldn't optimize it. Otherwise, it will return 'True, None'
        if is_low_value_task(self.label,
                             params.get('project'),
                             params.get('pushlog_id'),
                             params.get('pushdate'),
                             bbb_task):
            # Always optimize away low-value tasks
            return True, None
        else:
            return False, None

    @classmethod
    def from_json(cls, task_dict):
        # when reading back from JSON, we lose the "when" information
        task_dict['when'] = {}
        return cls(task_dict['attributes']['kind'], task_dict)
