# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import os
import logging
import attr
from .util import path

from .util.schema import validate_schema, Schema, optionally_keyed_by
from voluptuous import Required, Extra, Any
from .util.yaml import load_yaml

logger = logging.getLogger(__name__)

graph_config_schema = Schema({
    # The trust-domain for this graph.
    # (See https://firefox-source-docs.mozilla.org/taskcluster/taskcluster/taskgraph.html#taskgraph-trust-domain)  # noqa
    Required('trust-domain'): basestring,
    Required('task-priority'): optionally_keyed_by('project', Any(
        'highest',
        'very-high',
        'high',
        'medium',
        'low',
        'very-low',
        'lowest',
    )),
    Extra: object,
})


@attr.s(frozen=True, cmp=False)
class GraphConfig(object):
    _config = attr.ib()
    root_dir = attr.ib()

    def __getitem__(self, name):
        return self._config[name]

    @property
    def taskcluster_yml(self):
        if path.split(self.root_dir)[-2:] != ['taskcluster', 'ci']:
            raise Exception(
                "Not guessing path to `.taskcluster.yml`. "
                "Graph config in non-standard location."
            )
        return os.path.join(
            os.path.dirname(os.path.dirname(self.root_dir)),
            ".taskcluster.yml",
        )


def validate_graph_config(config):
    validate_schema(graph_config_schema, config, "Invalid graph configuration:")


def load_graph_config(root_dir):
    config_yml = os.path.join(root_dir, "config.yml")
    if not os.path.exists(config_yml):
        raise Exception("Couldn't find taskgraph configuration: {}".format(config_yml))

    logger.debug("loading config from `{}`".format(config_yml))
    config = load_yaml(config_yml)

    validate_graph_config(config)
    return GraphConfig(config=config, root_dir=root_dir)
