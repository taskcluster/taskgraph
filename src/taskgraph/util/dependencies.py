# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from taskgraph.util.schema import Schema

# Define a collection of group_by functions
GROUP_BY_MAP = {}


def group_by(name, schema=None):
    def wrapper(func):
        GROUP_BY_MAP[name] = func
        func.schema = schema
        return func

    return wrapper


@group_by("single")
def group_by_single(config, tasks):
    for task in tasks:
        yield [task]


@group_by("attribute", schema=Schema(str))
def group_by_attribute(config, tasks, attr):
    groups = {}
    for task in tasks:
        val = task.attributes.get(attr)
        if not val:
            continue
        groups.setdefault(val, []).append(task)

    return groups.values()
