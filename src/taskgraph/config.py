# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

from .util.python_path import find_object
from .util.schema import Schema, optionally_keyed_by, validate_schema
from .util.vcs import get_repository
from .util.yaml import load_yaml

logger = logging.getLogger(__name__)


# TaskPriority type for the priority levels
TaskPriority = Literal[
    "highest", "very-high", "high", "medium", "low", "very-low", "lowest"
]


class WorkerAlias(Schema):
    """Worker alias configuration."""

    provisioner: optionally_keyed_by("level", str)  # type: ignore
    implementation: str
    os: str
    worker_type: optionally_keyed_by("level", str)  # type: ignore


class Workers(Schema, rename=None):
    """Workers configuration."""

    aliases: Dict[str, WorkerAlias]


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

    use_caches: Optional[Union[bool, List[str]]] = None  # Maps from "use-caches"


class TaskGraphConfig(Schema):
    """Taskgraph specific configuration."""

    # Required fields first
    repositories: Dict[str, Repository]

    # Optional fields
    register: Optional[str] = None
    decision_parameters: Optional[str] = None  # Maps from "decision-parameters"
    cached_task_prefix: Optional[str] = None  # Maps from "cached-task-prefix"
    cache_pull_requests: Optional[bool] = None  # Maps from "cache-pull-requests"
    index_path_regexes: Optional[List[str]] = None  # Maps from "index-path-regexes"
    run: Optional[RunConfig] = None


class GraphConfigSchema(Schema, forbid_unknown_fields=False):
    """Main graph configuration schema.

    This schema allows extra fields for flexibility in graph configuration.
    """

    # Required fields first
    trust_domain: str  # Maps from "trust-domain"
    task_priority: optionally_keyed_by("project", "level", TaskPriority)  # type: ignore
    workers: Workers
    taskgraph: TaskGraphConfig

    # Optional fields
    docker_image_kind: Optional[str] = None  # Maps from "docker-image-kind"
    task_deadline_after: Optional[optionally_keyed_by("project", str)] = None  # type: ignore
    task_expires_after: Optional[str] = None  # Maps from "task-expires-after"


@dataclass(frozen=True, eq=False)
class GraphConfig:
    _config: Dict
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
            find_object(register_path)(self)

    @property
    def vcs_root(self):
        try:
            repo = get_repository(os.getcwd())
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
    # With rename="kebab", msgspec handles the conversion automatically
    validate_schema(GraphConfigSchema, config, "Invalid graph configuration:")


def load_graph_config(root_dir):
    config_yml = os.path.join(root_dir, "config.yml")
    if not os.path.exists(config_yml):
        raise Exception(f"Couldn't find taskgraph configuration: {config_yml}")

    logger.debug(f"loading config from `{config_yml}`")
    config = load_yaml(config_yml)

    validate_graph_config(config)
    return GraphConfig(config, root_dir=root_dir)
