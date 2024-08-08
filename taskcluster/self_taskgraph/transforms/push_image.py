# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Set environment variables for the skopeo push-image command
"""

import taskgraph
from taskgraph.transforms.base import TransformSequence

transforms = TransformSequence()


@transforms.add
def set_push_environment(config, tasks):
    """Set the environment variables for the push to docker hub task."""

    for task in tasks:
        env = task["worker"].setdefault("env", {})
        env.update(
            {
                "NAME": task["name"],
                "VERSION": taskgraph.__version__,
                "VCS_HEAD_REPOSITORY": config.params["head_repository"],
                "VCS_HEAD_REV": config.params["head_rev"],
            }
        )
        yield task
