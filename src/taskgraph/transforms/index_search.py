# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
This transform allows including indexed tasks from other projects in the
current taskgraph.  The transform takes a list of indexes, and the optimization
phase will replace the task with the task from the other graph.
"""

from __future__ import absolute_import, print_function, unicode_literals

from six import text_type

from taskgraph.transforms.base import TransformSequence
from taskgraph.util.schema import Schema

from voluptuous import Required, Optional

transforms = TransformSequence()

schema = Schema(
    {
        Required("name"): text_type,
        Required("description"): text_type,
        Required(
            "index-search",
            "A list of indexes in decreasing order of priority at which to lookup for this "
            "task. This is interpolated with the graph parameters.",
        ): [text_type],
        Optional('job-from'): text_type,
    }
)

transforms.add_validate(schema)


@transforms.add
def fill_template(config, tasks):
    for task in tasks:
        taskdesc = {
            "name": task["name"],
            "description": task["description"],
            "optimization": {
                "index-search": [
                    index.format(**config.params) for index in task["index-search"]
                ]
            },
            "worker-type": "always-optimized",
        }

        yield taskdesc
