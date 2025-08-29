# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Convert a run description into a task description.

Run descriptions are similar to task descriptions, but they specify how to run
the task at a higher level, using a "run" field that can be interpreted by
run-using handlers in `taskcluster/taskgraph/transforms/run`.
"""

import copy
import logging
from typing import Any, Dict, List, Union
from typing import Optional as TOptional

import msgspec

from taskgraph.transforms.base import TransformSequence
from taskgraph.transforms.cached_tasks import order_tasks
from taskgraph.util import json
from taskgraph.util import path as mozpath
from taskgraph.util.python_path import import_sibling_modules
from taskgraph.util.schema import Schema, validate_schema
from taskgraph.util.taskcluster import get_artifact_prefix
from taskgraph.util.workertypes import worker_type_implementation

logger = logging.getLogger(__name__)


# Fetches schema using msgspec
class FetchesSchema(Schema):
    """Schema for fetch configuration."""

    artifact: str
    dest: TOptional[str] = None
    extract: bool = False
    verify_hash: bool = False


# When configuration using msgspec
class WhenConfig(Schema):
    """Configuration for when a task should be included."""

    files_changed: List[str] = msgspec.field(default_factory=list)


# Run configuration using msgspec
class RunConfig(Schema, rename=None):
    """Configuration for how to run a task."""

    using: str
    workdir: TOptional[str] = None
    # Allow any extra fields for run implementation-specific config
    __extras__: Dict[str, Any] = msgspec.field(default_factory=dict)


# Run description schema using msgspec
class RunDescriptionSchema(Schema):
    """Schema for run transforms."""

    # Required fields first
    description: str
    run: RunConfig
    worker_type: str

    # Optional fields
    # The name of the task. At least one of 'name' or 'label' must be
    # specified. If 'label' is not provided, it will be generated from
    # the 'name' by prepending the kind.
    name: TOptional[str] = None
    # The label of the task. At least one of 'name' or 'label' must be
    # specified. If 'label' is not provided, it will be generated from
    # the 'name' by prepending the kind.
    label: TOptional[str] = None

    # Optional fields from task description
    priority: TOptional[str] = None
    attributes: Dict[str, Any] = msgspec.field(default_factory=dict)
    task_from: TOptional[str] = None
    dependencies: Dict[str, Any] = msgspec.field(default_factory=dict)
    soft_dependencies: List[str] = msgspec.field(default_factory=list)
    if_dependencies: List[str] = msgspec.field(default_factory=list)
    requires: str = "all-completed"
    deadline_after: TOptional[str] = None
    expires_after: TOptional[str] = None
    routes: List[str] = msgspec.field(default_factory=list)
    scopes: List[str] = msgspec.field(default_factory=list)
    tags: Dict[str, str] = msgspec.field(default_factory=dict)
    extra: Dict[str, Any] = msgspec.field(default_factory=dict)
    treeherder: Any = None
    index: Any = None
    run_on_projects: Any = None
    run_on_tasks_for: List[str] = msgspec.field(default_factory=list)
    run_on_git_branches: List[str] = msgspec.field(default_factory=list)
    shipping_phase: TOptional[str] = None
    always_target: bool = False
    optimization: Any = None
    needs_sccache: bool = False
    when: TOptional[WhenConfig] = None
    fetches: Dict[str, List[Union[str, FetchesSchema]]] = msgspec.field(
        default_factory=dict
    )
    worker: Dict[str, Any] = msgspec.field(default_factory=dict)


# Use the msgspec class directly for fetches
fetches_schema = FetchesSchema

#: Schema for a run transforms - now using msgspec
run_description_schema = RunDescriptionSchema


transforms = TransformSequence()
transforms.add_validate(run_description_schema)


@transforms.add
def rewrite_when_to_optimization(config, tasks):
    for task in tasks:
        when = task.pop("when", {})
        if not when:
            yield task
            continue

        files_changed = when.get("files-changed")

        # implicitly add task config directory.
        files_changed.append(f"{config.path}/kind.yml")
        if task.get("task-from") and task["task-from"] != "kind.yml":
            files_changed.append(f"{config.path}/{task['task-from']}")

        # "only when files changed" implies "skip if files have not changed"
        task["optimization"] = {"skip-unless-changed": files_changed}

        assert "when" not in task
        yield task


@transforms.add
def set_implementation(config, tasks):
    for task in tasks:
        impl, os = worker_type_implementation(config.graph_config, task["worker-type"])
        if os:
            task.setdefault("tags", {})["os"] = os
        if impl:
            task.setdefault("tags", {})["worker-implementation"] = impl
        worker = task.setdefault("worker", {})
        assert "implementation" not in worker
        worker["implementation"] = impl
        if os:
            worker["os"] = os
        yield task


@transforms.add
def set_label(config, tasks):
    for task in tasks:
        if "label" not in task:
            if "name" not in task:
                raise Exception("task has neither a name nor a label")
            task["label"] = "{}-{}".format(config.kind, task["name"])
        if task.get("name"):
            del task["name"]
        yield task


def get_attribute(dict, key, attributes, attribute_name):
    """Get `attribute_name` from the given `attributes` dict, and if there
    is a corresponding value, set `key` in `dict` to that value."""
    value = attributes.get(attribute_name)
    if value:
        dict[key] = value


@transforms.add
def use_fetches(config, tasks):
    artifact_names = {}
    aliases = {}
    extra_env = {}

    if config.kind in ("toolchain", "fetch"):
        tasks = list(tasks)
        for task in tasks:
            run = task.get("run", {})
            label = task["label"]
            get_attribute(artifact_names, label, run, "toolchain-artifact")
            value = run.get(f"{config.kind}-alias")
            if value:
                aliases[f"{config.kind}-{value}"] = label

    for task in config.kind_dependencies_tasks.values():
        if task.kind in ("fetch", "toolchain"):
            get_attribute(
                artifact_names,
                task.label,
                task.attributes,
                f"{task.kind}-artifact",
            )
            get_attribute(extra_env, task.label, task.attributes, f"{task.kind}-env")
            value = task.attributes.get(f"{task.kind}-alias")
            if value:
                aliases[f"{task.kind}-{value}"] = task.label

    artifact_prefixes = {}
    for task in order_tasks(config, tasks):
        artifact_prefixes[task["label"]] = get_artifact_prefix(task)

        fetches = task.pop("fetches", None)
        if not fetches:
            yield task
            continue

        task_fetches = []
        name = task.get("name", task.get("label"))
        dependencies = task.setdefault("dependencies", {})
        worker = task.setdefault("worker", {})
        env = worker.setdefault("env", {})
        prefix = get_artifact_prefix(task)
        for kind in sorted(fetches):
            artifacts = fetches[kind]
            if kind in ("fetch", "toolchain"):
                for artifact in sorted(
                    artifacts, key=lambda a: a if isinstance(a, str) else a["artifact"]
                ):
                    # Convert name only fetch entries to full fledged ones for
                    # easier processing.
                    if isinstance(artifact, str):
                        artifact = {
                            "artifact": artifact,
                        }

                    fetch_name = artifact["artifact"]
                    label = f"{kind}-{fetch_name}"
                    label = aliases.get(label, label)
                    if label not in artifact_names:
                        raise Exception(
                            f"Missing fetch task for {config.kind}-{name}: {fetch_name}"
                        )
                    if label in extra_env:
                        env.update(extra_env[label])

                    path = artifact_names[label]
                    dest = artifact.get("dest", None)
                    extract = artifact.get("extract", True)
                    verify_hash = artifact.get("verify-hash", False)

                    dependencies[label] = label
                    fetch = {
                        "artifact": path,
                        "task": f"<{label}>",
                        "extract": extract,
                    }
                    if dest is not None:
                        fetch["dest"] = dest
                    if verify_hash:
                        fetch["verify-hash"] = verify_hash
                    task_fetches.append(fetch)
            else:
                if kind not in dependencies:
                    raise Exception(
                        f"{name} can't fetch {kind} artifacts because "
                        f"it has no {kind} dependencies!"
                    )
                dep_label = dependencies[kind]
                if dep_label in artifact_prefixes:
                    prefix = artifact_prefixes[dep_label]
                else:
                    dep_tasks = [
                        task
                        for label, task in config.kind_dependencies_tasks.items()
                        if label == dep_label
                    ]
                    if len(dep_tasks) != 1:
                        raise Exception(
                            "{name} can't fetch {kind} artifacts because "
                            "there are {tasks} with label {label} in kind dependencies!\n"
                            "Available tasks:"
                            "\n - {labels}".format(
                                name=name,
                                kind=kind,
                                label=dependencies[kind],
                                tasks=(
                                    "no tasks"
                                    if len(dep_tasks) == 0
                                    else "multiple tasks"
                                ),
                                labels="\n - ".join(
                                    config.kind_dependencies_tasks.keys()
                                ),
                            )
                        )

                    prefix = get_artifact_prefix(dep_tasks[0])

                def cmp_artifacts(a):
                    if isinstance(a, str):
                        return a
                    else:
                        return a["artifact"]

                for artifact in sorted(artifacts, key=cmp_artifacts):
                    if isinstance(artifact, str):
                        path = artifact
                        dest = None
                        extract = True
                        verify_hash = False
                    else:
                        path = artifact["artifact"]
                        dest = artifact.get("dest")
                        extract = artifact.get("extract", True)
                        verify_hash = artifact.get("verify-hash", False)

                    fetch = {
                        "artifact": f"{prefix}/{path}",
                        "task": f"<{kind}>",
                        "extract": extract,
                    }
                    if dest is not None:
                        fetch["dest"] = dest
                    if verify_hash:
                        fetch["verify-hash"] = verify_hash
                    task_fetches.append(fetch)

        task_artifact_prefixes = {
            mozpath.dirname(fetch["artifact"])
            for fetch in task_fetches
            if not fetch["artifact"].startswith("public/")
        }
        if task_artifact_prefixes:
            # Use taskcluster-proxy and request appropriate scope.  For example, add
            # 'scopes: [queue:get-artifact:path/to/*]' for 'path/to/artifact.tar.xz'.
            worker["taskcluster-proxy"] = True
            for prefix in sorted(task_artifact_prefixes):
                scope = f"queue:get-artifact:{prefix}/*"
                if scope not in task.setdefault("scopes", []):
                    task["scopes"].append(scope)

        env["MOZ_FETCHES"] = {
            "task-reference": json.dumps(task_fetches, sort_keys=True)
        }

        env.setdefault("MOZ_FETCHES_DIR", "fetches")

        yield task


@transforms.add
def make_task_description(config, tasks):
    """Given a build description, create a task description"""
    # import plugin modules first, before iterating over tasks
    import_sibling_modules(exceptions=("common.py",))

    for task in tasks:
        # always-optimized tasks never execute, so have no workdir
        if task["worker"]["implementation"] in ("docker-worker", "generic-worker"):
            task["run"].setdefault("workdir", "/builds/worker")

        taskdesc = copy.deepcopy(task)

        # fill in some empty defaults to make run implementations easier
        taskdesc.setdefault("attributes", {})
        taskdesc.setdefault("dependencies", {})
        taskdesc.setdefault("soft-dependencies", [])
        taskdesc.setdefault("routes", [])
        taskdesc.setdefault("scopes", [])
        taskdesc.setdefault("extra", {})

        # give the function for task.run.using on this worker implementation a
        # chance to set up the task description.
        configure_taskdesc_for_run(
            config, task, taskdesc, task["worker"]["implementation"]
        )
        del taskdesc["run"]

        # yield only the task description, discarding the task description
        yield taskdesc


# A registry of all functions decorated with run_task_using
registry = {}


def run_task_using(worker_implementation, run_using, schema=None, defaults={}):
    """Register the decorated function as able to set up a task description for
    tasks with the given worker implementation and `run.using` property.  If
    `schema` is given, the task's run field will be verified to match it.

    The decorated function should have the signature `using_foo(config, task, taskdesc)`
    and should modify the task description in-place.  The skeleton of
    the task description is already set up, but without a payload."""

    def wrap(func):
        for_run_using = registry.setdefault(run_using, {})
        if worker_implementation in for_run_using:
            raise Exception(
                f"run_task_using({run_using!r}, {worker_implementation!r}) already exists: {for_run_using[worker_implementation]!r}"
            )
        for_run_using[worker_implementation] = (func, schema, defaults)
        return func

    return wrap


# Simple schema for always-optimized
class AlwaysOptimizedRunSchema(Schema, omit_defaults=False):
    """Schema for always-optimized run tasks."""

    using: str = "always-optimized"


@run_task_using("always-optimized", "always-optimized", AlwaysOptimizedRunSchema)
def always_optimized(config, task, taskdesc):
    pass


def configure_taskdesc_for_run(config, task, taskdesc, worker_implementation):
    """
    Run the appropriate function for this task against the given task
    description.

    This will raise an appropriate error if no function exists, or if the task's
    run is not valid according to the schema.
    """
    run_using = task["run"]["using"]
    if run_using not in registry:
        raise Exception(f"no functions for run.using {run_using!r}")

    if worker_implementation not in registry[run_using]:
        raise Exception(
            f"no functions for run.using {run_using!r} on {worker_implementation!r}"
        )

    func, schema, defaults = registry[run_using][worker_implementation]
    for k, v in defaults.items():
        task["run"].setdefault(k, v)

    if schema:
        validate_schema(
            schema,
            task["run"],
            "In task.run using {!r}/{!r} for task {!r}:".format(
                task["run"]["using"], worker_implementation, task["label"]
            ),
        )
    func(config, task, taskdesc)
