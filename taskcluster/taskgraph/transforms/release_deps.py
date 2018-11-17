# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Add dependencies to release tasks.
"""

from __future__ import absolute_import, print_function, unicode_literals

from taskgraph.transforms.base import TransformSequence

PHASES = ['build', 'promote', 'push', 'ship']

transforms = TransformSequence()


@transforms.add
def add_dependencies(config, jobs):
    for job in jobs:
        dependencies = {}
        # Add any kind_dependencies_tasks with matching product as dependencies
        product = job.get('shipping-product')
        phase = job.get('shipping-phase')
        if product is None:
            continue

        for dep_task in config.kind_dependencies_tasks:
            # Weed out unwanted tasks.
            # XXX we have run-on-projects which specifies the on-push behavior;
            # we need another attribute that specifies release promotion,
            # possibly which action(s) each task belongs in.
            if product == 'fennec':
                # Don't ship single locale fennec anymore - Bug 1408083
                attr = dep_task.attributes.get
                if attr("locale") or attr("chunk_locales"):
                    continue
            # We can only depend on tasks in the current or previous phases
            dep_phase = dep_task.attributes.get('shipping_phase')
            if dep_phase and PHASES.index(dep_phase) > PHASES.index(phase):
                continue

            if dep_task.attributes.get("build_platform") and \
               job.get("attributes", {}).get("build_platform"):
                if dep_task.attributes["build_platform"] != job["attributes"]["build_platform"]:
                    continue
            # Add matching product tasks to deps
            if dep_task.task.get('shipping-product') == product or \
                    dep_task.attributes.get('shipping_product') == product:
                dependencies[dep_task.label] = dep_task.label

        job.setdefault('dependencies', {}).update(dependencies)

        yield job
