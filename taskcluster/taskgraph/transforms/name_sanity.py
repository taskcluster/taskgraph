# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Generate labels for tasks without names, consistently.
Uses attributes from 'dependent-task'.
"""

from __future__ import absolute_import, print_function, unicode_literals

from taskgraph.transforms.base import TransformSequence


transforms = TransformSequence()


@transforms.add
def make_label(config, jobs):
    """ Generate a sane label for a new task constructed from a dependency
    Using attributes from the dependent job and the current task kind"""
    for job in jobs:
        dep_job = job['dependent-task']
        attr = dep_job.attributes.get
        if attr('locale'):
            template = "{kind}-{locale}-{build_platform}/{build_type}"
        else:
            template = "{kind}-{build_platform}/{build_type}"
        job['label'] = template.format(
            kind=config.kind,
            build_platform=attr('build_platform'),
            build_type=attr('build_type'),
            locale=attr('locale', '')  # Locale can be absent
        )

        yield job
