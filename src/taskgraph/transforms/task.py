# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
These transformations take a task description and turn it into a TaskCluster
task definition (along with attributes, label, etc.).  The input to these
transformations is generic to any kind of task, but abstracts away some of the
complexities of worker implementations, scopes, and treeherder annotations.
"""

import functools
import hashlib
import os
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Literal, Optional, Union

from taskgraph.transforms.base import TransformSequence
from taskgraph.util.hash import hash_path
from taskgraph.util.keyed_by import evaluate_keyed_by
from taskgraph.util.schema import (
    IndexSchema,
    OptimizationType,
    Schema,
    TaskPriority,
    TreeherderConfig,
    optionally_keyed_by,
    resolve_keyed_by,
    taskref_or_string_msgspec,
    validate_schema,
)
from taskgraph.util.treeherder import split_symbol, treeherder_defaults
from taskgraph.util.workertypes import worker_type_implementation

from ..util import docker as dockerutil
from ..util.workertypes import get_worker_type

RUN_TASK = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "run-task", "run-task"
)


@functools.cache
def run_task_suffix():
    """String to append to cache names under control of run-task."""
    return hash_path(RUN_TASK)[0:20]


class WorkerSchema(Schema, forbid_unknown_fields=False, kw_only=True):
    # The worker implementation type.
    implementation: str


#: Schema for the task transforms
class TaskDescriptionSchema(Schema):
    # The label for this task.
    label: str
    # Description of the task (for metadata).
    description: str
    # The `always-target` attribute will cause the task to be included in
    # the target_task_graph regardless of filtering.
    #
    # Tasks included in this manner will be candidates for
    # optimization even when `optimize_target_tasks` is False, unless
    # the task was also explicitly chosen by the target_tasks method.
    always_target: bool
    # Optimization to perform on this task during the optimization phase.
    # Defined in taskcluster/taskgraph/optimize.py.
    optimization: OptimizationType
    # The provisioner-id/worker-type for the task. The following
    # parameters will be substituted in this string:
    #
    #   {level} -- the scm level of this push.
    worker_type: str
    # Whether the task should use sccache compiler caching.
    needs_sccache: bool
    # Attributes for this task.
    attributes: Optional[dict[str, object]] = None
    # Relative path (from config.path) to the file task was defined in.
    task_from: Optional[str] = None
    # Dependencies of this task, keyed by name; these are passed through
    # verbatim and subject to the interpretation of the Task's
    # get_dependencies method.
    dependencies: Optional[dict[str, object]] = None
    # Priority of the task.
    priority: Optional[TaskPriority] = None
    # Soft dependencies of this task, as a list of task labels.
    soft_dependencies: Optional[list[str]] = None
    # Dependencies that must be scheduled in order for this task to run.
    if_dependencies: Optional[list[str]] = None
    # Specifies the condition for task execution.
    requires: Optional[Literal["all-completed", "all-resolved"]] = None
    # Expiration time relative to task creation, with units (e.g.,
    # '14 days'). Defaults are set based on the project.
    expires_after: Optional[str] = None
    # Deadline time relative to task creation, with units (e.g.,
    # '14 days'). Defaults are set based on the project.
    deadline_after: Optional[str] = None
    # Custom routes for this task; the default treeherder routes will
    # be added automatically.
    routes: Optional[list[str]] = None
    # Custom scopes for this task; any scopes required for the worker
    # will be added automatically. The following parameters will be
    # substituted in each scope:
    #
    #     {level} -- the scm level of this push
    #     {project} -- the project of this push.
    scopes: Optional[list[str]] = None
    # Tags for this task.
    tags: Optional[dict[str, str]] = None
    # Custom 'task.extra' content.
    extra: Optional[dict[str, object]] = None
    # Treeherder-related information. Can be a simple `true` to
    # auto-generate information or a dictionary with specific keys.
    treeherder: Optional[Union[bool, TreeherderConfig]] = None
    # Information for indexing this build so its artifacts can be
    # discovered. If omitted, the build will not be indexed.
    index: Optional[IndexSchema] = None
    # The `run_on_projects` attribute, defaulting to 'all'. Dictates
    # the projects on which this task should be included in the
    # target task set. See the attributes documentation for details.
    run_on_projects: Optional[
        optionally_keyed_by("build-platform", list[str], use_msgspec=True)  # type: ignore
    ] = None
    # Specifies tasks for which this task should run.
    run_on_tasks_for: Optional[list[str]] = None
    # Specifies git branches for which this task should run.
    run_on_git_branches: Optional[list[str]] = None
    # The `shipping_phase` attribute, defaulting to None. Specifies
    # the release promotion phase that this task belongs to.
    shipping_phase: Optional[Literal["build", "promote", "push", "ship"]] = None
    # Information specific to the worker implementation that will run this task.
    worker: Optional[WorkerSchema] = None

    def __post_init__(self):
        if self.dependencies:
            for key in self.dependencies:
                if key in ("self", "decision"):
                    raise ValueError(
                        "Can't use 'self' or 'decision' as dependency names."
                    )


task_description_schema = TaskDescriptionSchema

TC_TREEHERDER_SCHEMA_URL = (
    "https://github.com/taskcluster/taskcluster-treeherder/"
    "blob/master/schemas/task-treeherder-config.yml"
)


UNKNOWN_GROUP_NAME = (
    "Treeherder group {} (from {}) has no name; add it to taskcluster/config.yml"
)

V2_ROUTE_TEMPLATES = [
    "index.{trust-domain}.v2.{project}.latest.{product}.{job-name}",
    "index.{trust-domain}.v2.{project}.pushdate.{build_date_long}.{product}.{job-name}",
    "index.{trust-domain}.v2.{project}.pushlog-id.{pushlog_id}.{product}.{job-name}",
    "index.{trust-domain}.v2.{project}.revision.{branch_rev}.{product}.{job-name}",
]

# the roots of the treeherder routes
TREEHERDER_ROUTE_ROOT = "tc-treeherder"


def get_branch_rev(config):
    return config.params["head_rev"]


@functools.cache
def get_default_priority(graph_config, project):
    return evaluate_keyed_by(
        graph_config["task-priority"], "Graph Config", {"project": project}
    )


@functools.cache
def get_default_deadline(graph_config, project):
    return evaluate_keyed_by(
        graph_config["task-deadline-after"], "Graph Config", {"project": project}
    )


# define a collection of payload builders, depending on the worker implementation
payload_builders = {}


@dataclass(frozen=True)
class PayloadBuilder:
    schema: object
    builder: Callable


def payload_builder(name, schema):
    def wrap(func):
        assert name not in payload_builders, f"duplicate payload builder name {name}"
        payload_builders[name] = PayloadBuilder(schema, func)
        return func

    return wrap


# define a collection of index builders, depending on the type implementation
index_builders = {}


def index_builder(name):
    def wrap(func):
        assert name not in index_builders, f"duplicate index builder name {name}"
        index_builders[name] = func
        return func

    return wrap


UNSUPPORTED_INDEX_PRODUCT_ERROR = """\
The index product {product} is not in the list of configured products in
`taskcluster/config.yml'.
"""


def verify_index(config, index):
    product = index["product"]
    if product not in config.graph_config["index"]["products"]:
        raise Exception(UNSUPPORTED_INDEX_PRODUCT_ERROR.format(product=product))


DockerImage = Union[str, dict[str, str]]


class DockerWorkerCacheEntry(Schema):
    # only one type is supported by any of the workers right now
    type: Literal["persistent"]
    # name of the cache, allowing reuse by subsequent tasks naming the same cache
    name: str
    # location in the task image where the cache will be mounted
    mount_point: str
    # Whether the cache is not used in untrusted environments (like the Try repo).
    skip_untrusted: Optional[bool] = None


class DockerWorkerArtifact(Schema):
    # type of artifact -- simple file, or recursive directory, or a volume mounted directory.
    type: Literal["file", "directory", "volume"]
    # task image path from which to read artifact
    path: str
    # name of the produced artifact (root of the names for type=directory)
    name: str


class DockerWorkerPayloadSchema(Schema, forbid_unknown_fields=False, kw_only=True):
    implementation: Literal["docker-worker"]
    os: Literal["linux"]
    # For tasks that will run in docker-worker, this is the name of the docker
    # image or in-tree docker image to run the task in.
    docker_image: DockerImage
    # worker features that should be enabled
    relengapi_proxy: bool
    chain_of_trust: bool
    taskcluster_proxy: bool
    allow_ptrace: bool
    loopback_video: bool
    loopback_audio: bool
    docker_in_docker: bool  # (aka 'dind')
    privileged: bool
    # environment variables
    env: dict[str, taskref_or_string_msgspec]
    # the maximum time to run, in seconds
    max_run_time: int
    # Paths to Docker volumes.
    volumes: Optional[list[str]] = None
    # caches to set up for the task
    caches: Optional[list[DockerWorkerCacheEntry]] = None
    # artifacts to extract from the task image after completion
    artifacts: Optional[list[DockerWorkerArtifact]] = None
    # the command to run; if not given, docker-worker will default to the
    # command in the docker image
    command: Optional[list[taskref_or_string_msgspec]] = None
    # the exit status code(s) that indicates the task should be retried
    retry_exit_status: Optional[list[int]] = None
    # the exit status code(s) that indicates the caches used by the task
    # should be purged
    purge_caches_exit_status: Optional[list[int]] = None
    # Whether any artifacts are assigned to this worker
    skip_artifacts: Optional[bool] = None


@payload_builder("docker-worker", schema=DockerWorkerPayloadSchema)
def build_docker_worker_payload(config, task, task_def):
    worker = task["worker"]
    level = int(config.params["level"])

    image = worker["docker-image"]
    if isinstance(image, dict):
        if "in-tree" in image:
            name = image["in-tree"]
            docker_image_task = "docker-image-" + image["in-tree"]
            assert "docker-image" not in task.get("dependencies", ()), (
                "docker-image key in dependencies object is reserved"
            )
            task.setdefault("dependencies", {})["docker-image"] = docker_image_task

            image = {
                "path": "public/image.tar.zst",
                "taskId": {"task-reference": "<docker-image>"},
                "type": "task-image",
            }

            # Find VOLUME in Dockerfile.
            volumes = dockerutil.parse_volumes(name, config.graph_config)
            for v in sorted(volumes):
                if v in worker["volumes"]:
                    raise Exception(
                        f"volume {v} already defined; "
                        "if it is defined in a Dockerfile, "
                        "it does not need to be specified in the "
                        "worker definition"
                    )

                worker["volumes"].append(v)

        elif "indexed" in image:
            image = {
                "path": "public/image.tar.zst",
                "namespace": image["indexed"],
                "type": "indexed-image",
            }
        else:
            raise Exception("unknown docker image type")

    features = {}

    if worker.get("relengapi-proxy"):
        features["relengAPIProxy"] = True

    if worker.get("taskcluster-proxy"):
        features["taskclusterProxy"] = True

    if worker.get("allow-ptrace"):
        features["allowPtrace"] = True
        task_def["scopes"].append("docker-worker:feature:allowPtrace")

    if worker.get("chain-of-trust"):
        features["chainOfTrust"] = True

    if worker.get("docker-in-docker"):
        features["dind"] = True

    if task.get("needs-sccache"):
        features["taskclusterProxy"] = True
        task_def["scopes"].append(
            "assume:project:taskcluster:{trust_domain}:level-{level}-sccache-buckets".format(
                trust_domain=config.graph_config["trust-domain"],
                level=config.params["level"],
            )
        )
        worker["env"]["USE_SCCACHE"] = "1"
        # Disable sccache idle shutdown.
        worker["env"]["SCCACHE_IDLE_TIMEOUT"] = "0"
    else:
        worker["env"]["SCCACHE_DISABLE"] = "1"

    capabilities = {}

    for lo in "audio", "video":
        if worker.get("loopback-" + lo):
            capitalized = "loopback" + lo.capitalize()
            devices = capabilities.setdefault("devices", {})
            devices[capitalized] = True
            task_def["scopes"].append("docker-worker:capability:device:" + capitalized)

    if worker.get("privileged"):
        capabilities["privileged"] = True
        task_def["scopes"].append("docker-worker:capability:privileged")

    task_def["payload"] = payload = {
        "image": image,
        "env": worker["env"],
    }
    if "command" in worker:
        payload["command"] = worker["command"]

    if "max-run-time" in worker:
        payload["maxRunTime"] = worker["max-run-time"]

    run_task = os.path.basename(payload.get("command", [""])[0]).startswith("run-task")

    # run-task exits EXIT_PURGE_CACHES if there is a problem with caches.
    # Automatically retry the tasks and purge caches if we see this exit
    # code.
    # TODO move this closer to code adding run-task once bug 1469697 is
    # addressed.
    if run_task:
        worker.setdefault("retry-exit-status", []).append(72)
        worker.setdefault("purge-caches-exit-status", []).append(72)

    payload["onExitStatus"] = {}
    if "retry-exit-status" in worker:
        payload["onExitStatus"]["retry"] = worker["retry-exit-status"]
    if "purge-caches-exit-status" in worker:
        payload["onExitStatus"]["purgeCaches"] = worker["purge-caches-exit-status"]

    if "artifacts" in worker:
        artifacts = {}
        for artifact in worker["artifacts"]:
            artifacts[artifact["name"]] = {
                "path": artifact["path"],
                "type": artifact["type"],
                "expires": task_def["expires"],  # always expire with the task
            }
        payload["artifacts"] = artifacts

    if isinstance(worker.get("docker-image"), str):
        out_of_tree_image = worker["docker-image"]
    else:
        out_of_tree_image = None
        image = worker.get("docker-image", {}).get("in-tree")

    if "caches" in worker:
        caches = {}

        # run-task knows how to validate caches.
        #
        # To help ensure new run-task features and bug fixes, as well as the
        # versions of tools such as mercurial or git, don't interfere with
        # existing caches, we seed the underlying docker-image task id into
        # cache names, for tasks using in-tree Docker images.
        #
        # But this mechanism only works for in-tree Docker images that are built
        # with the current run-task! For out-of-tree Docker images, we have no
        # way of knowing their content of run-task. So, in addition to varying
        # cache names by the contents of run-task, we also take the Docker image
        # name into consideration.
        #
        # This means that different Docker images will never share the same
        # cache.  This is a bit unfortunate, but is the safest thing to do.
        #
        # For out-of-tree Docker images, we don't strictly need to incorporate
        # the run-task content into the cache name. However, doing so preserves
        # the mechanism whereby changing run-task results in new caches
        # everywhere.

        # As an additional mechanism to force the use of different caches, the
        # string literal in the variable below can be changed. This is
        # preferred to changing run-task because it doesn't require images
        # to be rebuilt.
        cache_version = "v3"

        if run_task:
            suffix = f"{cache_version}-{run_task_suffix()}"

            if out_of_tree_image:
                name_hash = hashlib.sha256(
                    out_of_tree_image.encode("utf-8")
                ).hexdigest()
                suffix += name_hash[0:12]
            else:
                suffix += "-<docker-image>"

        else:
            suffix = cache_version

        skip_untrusted = config.params.is_try() or level == 1

        for cache in worker["caches"]:
            # Some caches aren't enabled in environments where we can't
            # guarantee certain behavior. Filter those out.
            if cache.get("skip-untrusted") and skip_untrusted:
                continue

            name = "{trust_domain}-level-{level}-{name}-{suffix}".format(
                trust_domain=config.graph_config["trust-domain"],
                level=config.params["level"],
                name=cache["name"],
                suffix=suffix,
            )
            caches[name] = cache["mount-point"]
            task_def["scopes"].append({"task-reference": f"docker-worker:cache:{name}"})

        # Assertion: only run-task is interested in this.
        if run_task:
            payload["env"]["TASKCLUSTER_CACHES"] = ";".join(sorted(caches.values()))

        payload["cache"] = {"task-reference": caches}

    # And send down volumes information to run-task as well.
    if run_task and worker.get("volumes"):
        payload["env"]["TASKCLUSTER_VOLUMES"] = ";".join(sorted(worker["volumes"]))

    if payload.get("cache") and skip_untrusted:  # type: ignore
        payload["env"]["TASKCLUSTER_UNTRUSTED_CACHES"] = "1"

    if features:
        payload["features"] = features
    if capabilities:
        payload["capabilities"] = capabilities


class GenericWorkerArtifact(Schema):
    # type of artifact -- simple file, or recursive directory
    type: Literal["file", "directory"]
    # filesystem path from which to read artifact
    path: str
    # if not specified, path is used for artifact name
    name: Optional[str] = None


class MountContentSchema(Schema):
    # Artifact name that contains the content.
    artifact: Optional[str] = None
    # Task ID that has the artifact that contains the content.
    task_id: Optional[taskref_or_string_msgspec] = None
    # URL that supplies the content in response to an unauthenticated GET request.
    url: Optional[str] = None


class MountSchema(Schema):
    # A unique name for the cache volume.
    cache_name: Optional[str] = None
    # Optional content for pre-loading cache, or mandatory content for
    # read-only file or directory.
    content: Optional[MountContentSchema] = None
    # If mounting a cache or read-only directory.
    directory: Optional[str] = None
    # If mounting a file.
    file: Optional[str] = None
    # Archive format of the content.
    format: Optional[Literal["rar", "tar.bz2", "tar.gz", "zip"]] = None


class GenericWorkerPayloadSchema(Schema, forbid_unknown_fields=False, kw_only=True):
    implementation: Literal["generic-worker"]
    os: Literal["windows", "macosx", "linux", "linux-bitbar"]
    # command is a list of commands to run, sequentially
    # On Windows, each command is a string; on Linux/OS X, each command is a string array
    command: list
    # environment variables
    env: dict[str, taskref_or_string_msgspec]
    # the maximum time to run, in seconds
    max_run_time: int
    # optional features
    chain_of_trust: bool
    # artifacts to extract from the task image after completion
    artifacts: Optional[list[GenericWorkerArtifact]] = None
    # Directories and/or files to be mounted.
    mounts: Optional[list[MountSchema]] = None
    # the exit status code(s) that indicates the task should be retried
    retry_exit_status: Optional[list[int]] = None
    # the exit status code(s) that indicates the caches used by the task
    # should be purged
    purge_caches_exit_status: Optional[list[int]] = None
    # os user groups for test task workers
    os_groups: Optional[list[str]] = None
    # feature for test task to run as administrator
    run_as_administrator: Optional[bool] = None
    # feature for task to run as current OS user
    run_task_as_current_user: Optional[bool] = None
    taskcluster_proxy: Optional[bool] = None
    # Whether any artifacts are assigned to this worker
    skip_artifacts: Optional[bool] = None


@payload_builder("generic-worker", schema=GenericWorkerPayloadSchema)
def build_generic_worker_payload(config, task, task_def):
    worker = task["worker"]

    task_def["payload"] = {
        "command": worker["command"],
        "maxRunTime": worker["max-run-time"],
    }

    on_exit_status = {}
    if "retry-exit-status" in worker:
        on_exit_status["retry"] = worker["retry-exit-status"]
    if "purge-caches-exit-status" in worker:
        on_exit_status["purgeCaches"] = worker["purge-caches-exit-status"]
    if worker["os"] == "windows":
        on_exit_status.setdefault("retry", []).extend(
            [
                # These codes (on windows) indicate a process interruption,
                # rather than a task run failure. See bug 1544403.
                1073807364,  # process force-killed due to system shutdown
                3221225786,  # sigint (any interrupt)
            ]
        )
    if on_exit_status:
        task_def["payload"]["onExitStatus"] = on_exit_status

    env = worker.get("env", {})

    if task.get("needs-sccache"):
        env["USE_SCCACHE"] = "1"
        # Disable sccache idle shutdown.
        env["SCCACHE_IDLE_TIMEOUT"] = "0"
    else:
        env["SCCACHE_DISABLE"] = "1"

    if env:
        task_def["payload"]["env"] = env

    artifacts = []

    for artifact in worker.get("artifacts", []):
        a = {
            "path": artifact["path"],
            "type": artifact["type"],
        }
        if "name" in artifact:
            a["name"] = artifact["name"]
        artifacts.append(a)

    if artifacts:
        task_def["payload"]["artifacts"] = artifacts

    # Need to copy over mounts, but rename keys to respect naming convention
    #   * 'cache-name' -> 'cacheName'
    #   * 'task-id'    -> 'taskId'
    # All other key names are already suitable, and don't need renaming.
    mounts = deepcopy(worker.get("mounts", []))
    for mount in mounts:
        if "cache-name" in mount:
            mount["cacheName"] = "{trust_domain}-level-{level}-{name}".format(
                trust_domain=config.graph_config["trust-domain"],
                level=config.params["level"],
                name=mount.pop("cache-name"),
            )
            task_def["scopes"].append(
                "generic-worker:cache:{}".format(mount["cacheName"])
            )
        if "content" in mount:
            if "task-id" in mount["content"]:
                mount["content"]["taskId"] = mount["content"].pop("task-id")
            if "artifact" in mount["content"]:
                if not mount["content"]["artifact"].startswith("public/"):
                    task_def["scopes"].append(
                        "queue:get-artifact:{}".format(mount["content"]["artifact"])
                    )

    if mounts:
        task_def["payload"]["mounts"] = mounts

    if worker.get("os-groups"):
        task_def["payload"]["osGroups"] = worker["os-groups"]
        task_def["scopes"].extend(
            [
                "generic-worker:os-group:{}/{}".format(task["worker-type"], group)
                for group in worker["os-groups"]
            ]
        )

    features = {}

    if worker.get("chain-of-trust"):
        features["chainOfTrust"] = True

    if worker.get("taskcluster-proxy"):
        features["taskclusterProxy"] = True

    if worker.get("run-as-administrator", False):
        features["runAsAdministrator"] = True
        task_def["scopes"].append(
            "generic-worker:run-as-administrator:{}".format(task["worker-type"]),
        )

    if worker.get("run-task-as-current-user", False):
        features["runTaskAsCurrentUser"] = True
        task_def["scopes"].append(
            "generic-worker:run-task-as-current-user:{}".format(task["worker-type"]),
        )

    if features:
        task_def["payload"]["features"] = features


class ReleaseProperties(Schema):
    app_name: str
    app_version: str
    branch: str
    build_id: str
    hash_type: str
    platform: str


class UpstreamArtifact(Schema, rename="camel"):
    # taskId of the task with the artifact
    task_id: taskref_or_string_msgspec
    # type of signing task (for CoT)
    task_type: str
    # Paths to the artifacts to sign
    paths: list[str]
    # locale is used to map upload path and allow for duplicate simple names
    locale: str


class BeetmoverPayloadSchema(Schema, forbid_unknown_fields=False, kw_only=True):
    implementation: Literal["beetmover"]
    # the maximum time to run, in seconds
    max_run_time: int
    # release properties
    release_properties: ReleaseProperties
    # list of artifact URLs for the artifacts that should be beetmoved
    upstream_artifacts: list[UpstreamArtifact]
    # locale key, if this is a locale beetmover task
    locale: Optional[str] = None
    partner_public: Optional[bool] = None
    artifact_map: Optional[object] = None


@payload_builder("beetmover", schema=BeetmoverPayloadSchema)
def build_beetmover_payload(config, task, task_def):
    worker = task["worker"]
    release_properties = worker["release-properties"]

    task_def["payload"] = {
        "maxRunTime": worker["max-run-time"],
        "releaseProperties": {
            "appName": release_properties["app-name"],
            "appVersion": release_properties["app-version"],
            "branch": release_properties["branch"],
            "buildid": release_properties["build-id"],
            "hashType": release_properties["hash-type"],
            "platform": release_properties["platform"],
        },
        "upload_date": config.params["build_date"],
        "upstreamArtifacts": worker["upstream-artifacts"],
    }
    if worker.get("locale"):
        task_def["payload"]["locale"] = worker["locale"]
    if worker.get("artifact-map"):
        task_def["payload"]["artifactMap"] = worker["artifact-map"]
    if worker.get("partner-public"):
        task_def["payload"]["is_partner_repack_public"] = worker["partner-public"]


class InvalidPayloadSchema(Schema, forbid_unknown_fields=False, kw_only=True):
    # an invalid task is one which should never actually be created; this is used in
    # release automation on branches where the task just doesn't make sense
    implementation: Literal["invalid"]


@payload_builder("invalid", schema=InvalidPayloadSchema)
def build_invalid_payload(config, task, task_def):
    task_def["payload"] = "invalid task - should never be created"


class AlwaysOptimizedPayloadSchema(Schema, forbid_unknown_fields=False, kw_only=True):
    implementation: Literal["always-optimized"]


class SucceedPayloadSchema(Schema):
    implementation: Literal["succeed"]


@payload_builder("always-optimized", schema=AlwaysOptimizedPayloadSchema)
@payload_builder("succeed", schema=SucceedPayloadSchema)
def build_dummy_payload(config, task, task_def):
    task_def["payload"] = {}


transforms = TransformSequence()


@transforms.add
def set_implementation(config, tasks):
    """
    Set the worker implementation based on the worker-type alias.
    """
    for task in tasks:
        worker = task.setdefault("worker", {})
        if "implementation" in task["worker"]:
            yield task
            continue

        impl, os = worker_type_implementation(config.graph_config, task["worker-type"])

        tags = task.setdefault("tags", {})
        tags["worker-implementation"] = impl
        if os:
            task["tags"]["os"] = os
        worker["implementation"] = impl
        if os:
            worker["os"] = os

        yield task


@transforms.add
def set_defaults(config, tasks):
    for task in tasks:
        task.setdefault("always-target", False)
        task.setdefault("optimization", None)
        task.setdefault("needs-sccache", False)

        worker = task["worker"]
        if worker["implementation"] in ("docker-worker",):
            worker.setdefault("relengapi-proxy", False)
            worker.setdefault("chain-of-trust", False)
            worker.setdefault("taskcluster-proxy", False)
            worker.setdefault("allow-ptrace", False)
            worker.setdefault("loopback-video", False)
            worker.setdefault("loopback-audio", False)
            worker.setdefault("docker-in-docker", False)
            worker.setdefault("privileged", False)
            worker.setdefault("volumes", [])
            worker.setdefault("env", {})
            if "caches" in worker:
                for c in worker["caches"]:
                    c.setdefault("skip-untrusted", False)
        elif worker["implementation"] == "generic-worker":
            worker.setdefault("env", {})
            worker.setdefault("os-groups", [])
            worker.setdefault("chain-of-trust", False)
        elif worker["implementation"] in (
            "scriptworker-signing",
            "beetmover",
            "beetmover-push-to-release",
            "beetmover-maven",
        ):
            worker.setdefault("max-run-time", 600)
        elif worker["implementation"] == "push-apk":
            worker.setdefault("commit", False)

        yield task


@transforms.add
def task_name_from_label(config, tasks):
    for task in tasks:
        if "label" not in task:
            if "name" not in task:
                raise Exception("task has neither a name nor a label")
            task["label"] = "{}-{}".format(config.kind, task["name"])
        if task.get("name"):
            del task["name"]
        yield task


@transforms.add
def validate(config, tasks):
    for task in tasks:
        validate_schema(
            task_description_schema,
            task,
            "In task {!r}:".format(task.get("label", "?no-label?")),
        )
        validate_schema(
            payload_builders[task["worker"]["implementation"]].schema,
            task["worker"],
            "In task.run {!r}:".format(task.get("label", "?no-label?")),
        )
        yield task


@index_builder("generic")
def add_generic_index_routes(config, task):
    index = task.get("index")
    routes = task.setdefault("routes", [])

    verify_index(config, index)

    subs = config.params.copy()
    subs["job-name"] = index["job-name"]
    subs["build_date_long"] = time.strftime(
        "%Y.%m.%d.%Y%m%d%H%M%S", time.gmtime(config.params["build_date"])
    )
    subs["product"] = index["product"]
    subs["trust-domain"] = config.graph_config["trust-domain"]
    subs["branch_rev"] = get_branch_rev(config)

    for tpl in V2_ROUTE_TEMPLATES:
        routes.append(tpl.format(**subs))

    return task


@transforms.add
def process_treeherder_metadata(config, tasks):
    for task in tasks:
        routes = task.get("routes", [])
        extra = task.get("extra", {})
        task_th = task.get("treeherder")

        if task_th:
            # This `merged_th` object is just an intermediary that combines
            # the defaults and whatever is in the task. Ultimately, the task
            # transforms this data a bit in the `treeherder` object that is
            # eventually set in the task.
            merged_th = treeherder_defaults(config.kind, task["label"])
            if isinstance(task_th, dict):
                merged_th.update(task_th)

            treeherder = extra.setdefault("treeherder", {})
            extra.setdefault("treeherder-platform", merged_th["platform"])

            machine_platform, collection = merged_th["platform"].split("/", 1)
            treeherder["machine"] = {"platform": machine_platform}
            treeherder["collection"] = {collection: True}

            group_names = config.graph_config["treeherder"]["group-names"]
            groupSymbol, symbol = split_symbol(merged_th["symbol"])
            if groupSymbol != "?":
                treeherder["groupSymbol"] = groupSymbol
                if groupSymbol not in group_names:
                    path = os.path.join(config.path, task.get("task-from", ""))
                    raise Exception(UNKNOWN_GROUP_NAME.format(groupSymbol, path))
                treeherder["groupName"] = group_names[groupSymbol]
            treeherder["symbol"] = symbol
            if len(symbol) > 25 or len(groupSymbol) > 25:
                raise RuntimeError(
                    "Treeherder group and symbol names must not be longer than "
                    "25 characters: {} (see {})".format(
                        treeherder["symbol"],
                        TC_TREEHERDER_SCHEMA_URL,
                    )
                )
            treeherder["jobKind"] = merged_th["kind"]
            treeherder["tier"] = merged_th["tier"]

            branch_rev = get_branch_rev(config)

            if config.params["tasks_for"].startswith("github-pull-request"):
                # In the past we used `project` for this, but that ends up being
                # set to the repository name of the _head_ repo, which is not correct
                # (and causes scope issues) if it doesn't match the name of the
                # base repo
                base_project = config.params["base_repository"].split("/")[-1]
                if base_project.endswith(".git"):
                    base_project = base_project[:-4]
                th_project_suffix = "-pr"
            else:
                base_project = config.params["project"]
                th_project_suffix = ""

            routes.append(
                "{}.v2.{}.{}.{}".format(
                    TREEHERDER_ROUTE_ROOT,
                    base_project + th_project_suffix,
                    branch_rev,
                    config.params["pushlog_id"],
                )
            )

        task["routes"] = routes
        task["extra"] = extra
        yield task


@transforms.add
def add_index_routes(config, tasks):
    for task in tasks:
        index = task.get("index", {})

        # The default behavior is to rank tasks according to their tier
        extra_index = task.setdefault("extra", {}).setdefault("index", {})
        rank = index.get("rank", "by-tier")

        if rank == "by-tier":
            # rank is zero for non-tier-1 tasks and based on pushid for others;
            # this sorts tier-{2,3} builds below tier-1 in the index
            tier = task.get("extra", {}).get("treeherder", {}).get("tier", 3)
            extra_index["rank"] = 0 if tier > 1 else int(config.params["build_date"])
        elif rank == "build_date":
            extra_index["rank"] = int(config.params["build_date"])
        else:
            extra_index["rank"] = rank

        if not index:
            yield task
            continue

        index_type = index.get("type", "generic")
        if index_type not in index_builders:
            raise ValueError(f"Unknown index-type {index_type}")
        task = index_builders[index_type](config, task)

        del task["index"]
        yield task


@transforms.add
def build_task(config, tasks):
    for task in tasks:
        level = str(config.params["level"])

        provisioner_id, worker_type = get_worker_type(
            config.graph_config,
            task["worker-type"],
            level,
        )
        task["worker-type"] = "/".join([provisioner_id, worker_type])
        project = config.params["project"]

        routes = task.get("routes", [])
        scopes = [
            s.format(level=level, project=project) for s in task.get("scopes", [])
        ]

        # set up extra
        extra = task.get("extra", {})
        extra["parent"] = os.environ.get("TASK_ID", "")

        if "expires-after" not in task:
            task["expires-after"] = (
                config.graph_config._config.get("task-expires-after", "28 days")
                if config.params.is_try()
                else "1 year"
            )

        if "deadline-after" not in task:
            if "task-deadline-after" in config.graph_config:
                task["deadline-after"] = get_default_deadline(
                    config.graph_config, config.params["project"]
                )
            else:
                task["deadline-after"] = "1 day"

        if "priority" not in task:
            task["priority"] = get_default_priority(
                config.graph_config, config.params["project"]
            )

        tags = task.get("tags", {})
        tags.update(
            {
                "createdForUser": config.params["owner"],
                "kind": config.kind,
                "label": task["label"],
                "project": config.params["project"],
                "trust-domain": config.graph_config["trust-domain"],
            }
        )

        task_def = {
            "provisionerId": provisioner_id,
            "workerType": worker_type,
            "routes": routes,
            "created": {"relative-datestamp": "0 seconds"},
            "deadline": {"relative-datestamp": task["deadline-after"]},
            "expires": {"relative-datestamp": task["expires-after"]},
            "scopes": scopes,
            "metadata": {
                "description": task["description"],
                "name": task["label"],
                "owner": config.params["owner"],
                "source": config.params.file_url(config.path, pretty=True),
            },
            "extra": extra,
            "tags": tags,
            "priority": task["priority"],
        }

        if task.get("requires", None):
            task_def["requires"] = task["requires"]

        if task.get("extra", {}).get("treeherder"):
            branch_rev = get_branch_rev(config)
            if config.params["tasks_for"].startswith("github-pull-request"):
                # In the past we used `project` for this, but that ends up being
                # set to the repository name of the _head_ repo, which is not correct
                # (and causes scope issues) if it doesn't match the name of the
                # base repo
                base_project = config.params["base_repository"].split("/")[-1]
                if base_project.endswith(".git"):
                    base_project = base_project[:-4]
                th_project_suffix = "-pr"
            else:
                base_project = config.params["project"]
                th_project_suffix = ""

            # link back to treeherder in description
            th_push_link = (
                "https://treeherder.mozilla.org/#/jobs?repo={}&revision={}".format(
                    config.params["project"] + th_project_suffix, branch_rev
                )
            )
            task_def["metadata"]["description"] += (
                f" ([Treeherder push]({th_push_link}))"
            )

        # add the payload and adjust anything else as required (e.g., scopes)
        payload_builders[task["worker"]["implementation"]].builder(
            config, task, task_def
        )

        attributes = task.get("attributes", {})
        # Resolve run-on-projects
        build_platform = attributes.get("build_platform")
        resolve_keyed_by(
            task,
            "run-on-projects",
            item_name=task["label"],
            **{"build-platform": build_platform},
        )
        attributes["run_on_projects"] = task.get("run-on-projects", ["all"])
        attributes["run_on_tasks_for"] = task.get("run-on-tasks-for", ["all"])
        # We don't want to pollute non git repos with this attribute. Moreover, target_tasks
        # already assumes the default value is ['all']
        if task.get("run-on-git-branches"):
            attributes["run_on_git_branches"] = task["run-on-git-branches"]

        attributes["always_target"] = task["always-target"]
        # This logic is here since downstream tasks don't always match their
        # upstream dependency's shipping_phase.
        # A text_type task['shipping-phase'] takes precedence, then
        # an existing attributes['shipping_phase'], then fall back to None.
        if task.get("shipping-phase") is not None:
            attributes["shipping_phase"] = task["shipping-phase"]
        else:
            attributes.setdefault("shipping_phase", None)

        # Set MOZ_AUTOMATION on all jobs.
        if task["worker"]["implementation"] in (
            "generic-worker",
            "docker-worker",
        ):
            payload = task_def.get("payload")
            if payload:
                env = payload.setdefault("env", {})
                env["MOZ_AUTOMATION"] = "1"

        dependencies = task.get("dependencies", {})
        if_dependencies = task.get("if-dependencies", [])
        if if_dependencies:
            for i, dep in enumerate(if_dependencies):
                if dep in dependencies:
                    if_dependencies[i] = dependencies[dep]
                    continue

                raise Exception(
                    "{label} specifies '{dep}' in if-dependencies, "
                    "but {dep} is not a dependency!".format(
                        label=task["label"], dep=dep
                    )
                )

        yield {
            "label": task["label"],
            "description": task["description"],
            "task": task_def,
            "dependencies": dependencies,
            "if-dependencies": if_dependencies,
            "soft-dependencies": task.get("soft-dependencies", []),
            "attributes": attributes,
            "optimization": task.get("optimization", None),
        }


@transforms.add
def add_github_checks(config, tasks):
    """
    For git repositories, add checks route to all tasks.

    This will be replaced by a configurable option in the future.
    """
    if config.params["repository_type"] != "git":
        for task in tasks:
            yield task

    for task in tasks:
        task["task"]["routes"].append("checks")
        yield task


@transforms.add
def chain_of_trust(config, tasks):
    for task in tasks:
        if task["task"].get("payload", {}).get("features", {}).get("chainOfTrust"):
            image = task.get("dependencies", {}).get("docker-image")
            if image:
                cot = (
                    task["task"].setdefault("extra", {}).setdefault("chainOfTrust", {})
                )
                cot.setdefault("inputs", {})["docker-image"] = {
                    "task-reference": "<docker-image>"
                }
        yield task
