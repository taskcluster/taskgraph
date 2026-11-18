# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .util.python_path import find_object
from .util.schema import Schema, TaskPriority, optionally_keyed_by, validate_schema
from .util.vcs import get_repository
from .util.yaml import load_yaml

logger = logging.getLogger(__name__)

CacheType = Literal["cargo", "checkout", "npm", "pip", "uv"]


class WorkerAlias(Schema):
    provisioner: optionally_keyed_by("level", str, use_msgspec=True)  # type: ignore
    implementation: str
    os: str
    worker_type: optionally_keyed_by("level", str, use_msgspec=True)  # type: ignore


class WorkersConfig(Schema):
    aliases: dict[str, WorkerAlias]


class RunConfig(Schema):
    #: List of caches to enable, or a boolean to enable/disable all of them.
    use_caches: bool | list[CacheType] | None = None


class RepositoryConfig(Schema, forbid_unknown_fields=False, kw_only=True):
    name: str
    project_regex: str | None = None
    ssh_secret_name: str | None = None
    # FIXME: Extra keys allowed via forbid_unknown_fields=False


class TaskgraphConfig(Schema):
    repositories: dict[str, RepositoryConfig]
    #: Python function to call to register extensions.
    register: str | None = None
    decision_parameters: str | None = None
    #: The taskcluster index prefix to use for caching tasks.
    #: Defaults to `trust-domain`.
    cached_task_prefix: str | None = None
    #: Should tasks from pull requests populate the cache
    cache_pull_requests: bool | None = None
    #: Regular expressions matching index paths to be summarized.
    index_path_regexes: list[str] | None = None
    #: Configuration related to the 'run' transforms.
    run: RunConfig | None = None
    #: List of action `cb_name`s to omit from `actions.json`,
    #: e.g. `["retrigger", "retrigger-disabled", "rerun"]`.
    disabled_actions: list[str] | None = None

    def __post_init__(self):
        # Validate repositories has at least 1 entry (was All(..., Length(min=1)))
        if not self.repositories:
            raise ValueError("'repositories' must have at least one entry")


#: Schema for the graph config
class GraphConfigSchema(Schema, forbid_unknown_fields=False, kw_only=True):
    #: The trust-domain for this graph.
    trust_domain: str
    task_priority: optionally_keyed_by(  # type: ignore
        "project", "level", TaskPriority, use_msgspec=True
    )
    workers: WorkersConfig
    taskgraph: TaskgraphConfig
    #: Name of the docker image kind (default: docker-image)
    docker_image_kind: str | None = None
    #: Default 'deadline' for tasks, in relative date format. Eg: '1 week'
    task_deadline_after: (
        optionally_keyed_by("project", str, use_msgspec=True) | None  # type: ignore
    ) = None
    #: Default 'expires-after' for level 1 tasks, in relative date format.
    #: Eg: '90 days'
    task_expires_after: str | None = None


graph_config_schema = GraphConfigSchema


@dataclass(frozen=True, eq=False)
class GraphConfig:
    _config: dict
    root_dir: str

    _PATH_MODIFIED = False

    def __post_init__(self):
        # ensure we have an absolute path; this is required for assumptions
        # made later, such as the `vcs_root` being a directory above `root_dir`
        object.__setattr__(self, "root_dir", os.path.abspath(self.root_dir))

    def __getitem__(self, name):
        return self._config[name]

    def __contains__(self, name):
        return name in self._config

    def get(self, name, default=None):
        return self._config.get(name, default)

    def register(self):
        """
        Add the project's taskgraph directory to the python path, and register
        any extensions present.
        """
        if GraphConfig._PATH_MODIFIED:
            if GraphConfig._PATH_MODIFIED == self.root_dir:
                # Already modified path with the same root_dir.
                # We currently need to do this to enable actions to call
                # taskgraph_decision, e.g. relpro.
                return
            raise Exception("Can't register multiple directories on python path.")
        GraphConfig._PATH_MODIFIED = self.root_dir
        sys.path.insert(0, self.root_dir)
        register_path = self["taskgraph"].get("register")
        if register_path:
            register = find_object(register_path)
            assert callable(register)
            register(self)

    @property
    def vcs_root(self):
        try:
            repo = get_repository(self.root_dir)
            return Path(repo.path)
        except RuntimeError:
            root = Path(self.root_dir)
            if root.parts[-1:] != ("taskcluster",):
                raise Exception(
                    "Not guessing path to vcs root. Graph config in non-standard location."
                )
            return root.parent

    @property
    def taskcluster_yml(self):
        return os.path.join(self.vcs_root, ".taskcluster.yml")

    @property
    def docker_dir(self):
        return os.path.join(self.root_dir, "docker")

    @property
    def kinds_dir(self):
        return os.path.join(self.root_dir, "kinds")


def validate_graph_config(config):
    validate_schema(graph_config_schema, config, "Invalid graph configuration:")


def load_graph_config(root_dir):
    config_yml = os.path.join(root_dir, "config.yml")
    if not os.path.exists(config_yml):
        raise Exception(f"Couldn't find taskgraph configuration: {config_yml}")

    logger.debug(f"loading config from `{config_yml}`")
    config = load_yaml(config_yml)

    validate_graph_config(config)
    return GraphConfig(config, root_dir=root_dir)
