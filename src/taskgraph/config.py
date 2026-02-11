# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Union

from .util.caches import CACHES
from .util.python_path import find_object
from .util.schema import (
    Schema,
    TaskPriority,
    optionally_keyed_by,
    validate_schema,
)
from .util.vcs import get_repository
from .util.yaml import load_yaml

logger = logging.getLogger(__name__)

# CacheName type for valid cache names
CacheName = Literal[tuple(CACHES.keys())]


class WorkerAliasSchema(Schema):
    """Worker alias configuration."""

    provisioner: optionally_keyed_by("level", str, use_msgspec=True)  # type: ignore
    implementation: str
    os: str
    worker_type: optionally_keyed_by("level", str, use_msgspec=True)  # type: ignore


class WorkersSchema(Schema, rename=None):
    """Workers configuration."""

    aliases: dict[str, WorkerAliasSchema]


class Repository(Schema, forbid_unknown_fields=False):
    """Repository configuration.

    This schema allows extra fields for repository-specific configuration.
    """

    # Required fields first
    name: str

    # Optional fields
    project_regex: Optional[str] = None  # Maps from "project-regex"
    ssh_secret_name: Optional[str] = None  # Maps from "ssh-secret-name"


class RunConfig(Schema):
    """Run transforms configuration."""

    # List of caches to enable, or a boolean to enable/disable all of them.
    use_caches: Optional[Union[bool, list[str]]] = None  # Maps from "use-caches"

    def __post_init__(self):
        """Validate that cache names are valid."""
        if isinstance(self.use_caches, list):
            invalid = set(self.use_caches) - set(CACHES.keys())
            if invalid:
                raise ValueError(
                    f"Invalid cache names: {invalid}. "
                    f"Valid names are: {list(CACHES.keys())}"
                )


class TaskGraphSchema(Schema):
    """Taskgraph specific configuration."""

    # Required fields first
    repositories: dict[str, Repository]

    # Optional fields
    # Python function to call to register extensions.
    register: Optional[str] = None
    decision_parameters: Optional[str] = None  # Maps from "decision-parameters"
    # The taskcluster index prefix to use for caching tasks. Defaults to `trust-domain`.
    cached_task_prefix: Optional[str] = None  # Maps from "cached-task-prefix"
    # Should tasks from pull requests populate the cache
    cache_pull_requests: Optional[bool] = None  # Maps from "cache-pull-requests"
    # Regular expressions matching index paths to be summarized.
    index_path_regexes: Optional[list[str]] = None  # Maps from "index-path-regexes"
    # Configuration related to the 'run' transforms.
    run: Optional[RunConfig] = None


class GraphConfigSchema(Schema, forbid_unknown_fields=False):
    """Main graph configuration schema.

    This schema allows extra fields for flexibility in graph configuration.
    """

    # Required fields first
    # The trust-domain for this graph.
    # (See https://firefox-source-docs.mozilla.org/taskcluster/taskcluster/taskgraph.html#taskgraph-trust-domain)
    trust_domain: str  # Maps from "trust-domain"
    task_priority: optionally_keyed_by(
        "project", "level", TaskPriority, use_msgspec=True
    )  # type: ignore
    workers: WorkersSchema
    taskgraph: TaskGraphSchema

    # Optional fields
    # Name of the docker image kind (default: docker-image)
    docker_image_kind: Optional[str] = None  # Maps from "docker-image-kind"
    # Default 'deadline' for tasks, in relative date format. Eg: '1 week'
    task_deadline_after: Optional[
        optionally_keyed_by("project", str, use_msgspec=True)  # pyright: ignore[reportInvalidTypeForm]
    ] = None
    # Default 'expires-after' for level 1 tasks, in relative date format. Eg: '90 days'
    task_expires_after: Optional[str] = None  # Maps from "task-expires-after"


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
    """Validate graph configuration using msgspec."""
    validate_schema(GraphConfigSchema, config, "Invalid graph configuration:")


def load_graph_config(root_dir):
    config_yml = os.path.join(root_dir, "config.yml")
    if not os.path.exists(config_yml):
        raise Exception(f"Couldn't find taskgraph configuration: {config_yml}")

    logger.debug(f"loading config from `{config_yml}`")
    config = load_yaml(config_yml)

    validate_graph_config(config)
    return GraphConfig(config, root_dir=root_dir)
