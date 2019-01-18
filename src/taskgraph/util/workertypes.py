# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

WORKER_TYPES = {
    'aws-provisioner-v1/gecko-misc': ('docker-worker', 'linux'),
}


def worker_type_implementation(worker_type):
    """Get the worker implementation and OS for the given workerType, where the
    OS represents the host system, not the target OS, in the case of
    cross-compiles."""
    # assume that worker types for all levels are the same implementation
    worker_type = worker_type.replace('{level}', '1')
    return WORKER_TYPES[worker_type]
