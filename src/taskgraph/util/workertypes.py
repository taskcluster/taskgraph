# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

from .keyed_by import evaluate_keyed_by
from .memoize import memoize


@memoize
def worker_type_implementation(graph_config, worker_type):
    """Get the worker implementation and OS for the given workerType, where the
    OS represents the host system, not the target OS, in the case of
    cross-compiles."""
    worker_config = evaluate_keyed_by(
        {"by-worker-type": graph_config["workers"]["aliases"]},
        "worker-types.yml",
        {'worker-type': worker_type},
    )
    return worker_config['implementation'], worker_config.get('os')


@memoize
def get_worker_type(graph_config, worker_type, level):
    """
    Get the worker type based, evaluating aliases from the graph config.
    """
    level = str(level)
    worker_config = evaluate_keyed_by(
        {"by-worker-type": graph_config["workers"]["aliases"]},
        "worker-types.yml",
        {"worker-type": worker_type},
    )
    worker_type = evaluate_keyed_by(
        worker_config["worker-type"],
        worker_type,
        {"level": level},
    ).format(level=level, alias=worker_type)
    return worker_config["provisioner"], worker_type
