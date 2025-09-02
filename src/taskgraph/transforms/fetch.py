# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Support for running tasks that download remote content and re-export
# it as task artifacts.


import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import msgspec

import taskgraph

from ..util import path
from ..util.cached_tasks import add_optimization
from ..util.schema import Schema
from ..util.treeherder import join_symbol
from .base import TransformSequence

CACHE_TYPE = "content.v1"


#: Schema for fetch transforms
class FetchConfig(Schema, rename=None, omit_defaults=False):
    """Configuration for a fetch task type."""

    type: str
    # Additional fields handled dynamically by fetch builders


class FetchSchema(Schema):
    # Required fields
    # Name of the task.
    name: str
    # Description of the task.
    description: str
    # Fetch configuration with type and additional fields.
    fetch: Dict[str, Any]  # Must have 'type' key, other keys depend on type

    # Optional fields
    # Relative path (from config.path) to the file the task was defined in.
    task_from: Optional[str] = None
    # When the task expires.
    expires_after: Optional[str] = None
    # Docker image configuration.
    docker_image: Optional[Any] = None
    # An alias that can be used instead of the real fetch task name in
    # fetch stanzas for tasks.
    fetch_alias: Optional[str] = None
    # The prefix of the taskcluster artifact being uploaded.
    # Defaults to `public/`; if it starts with something other than
    # `public/` the artifact will require scopes to access.
    artifact_prefix: Optional[str] = None
    # Task attributes.
    attributes: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        # Validate that fetch has a 'type' field
        if not isinstance(self.fetch, dict) or "type" not in self.fetch:
            raise msgspec.ValidationError("fetch must be a dict with a 'type' field")


# Backward compatibility
FETCH_SCHEMA = FetchSchema

# define a collection of payload builders, depending on the worker implementation
fetch_builders = {}


@dataclass(frozen=True)
class FetchBuilder:
    schema: Any  # Either msgspec.Struct type or validation function
    builder: Callable


def fetch_builder(name, schema):
    # schema should be a msgspec.Struct type
    def wrap(func):
        fetch_builders[name] = FetchBuilder(schema, func)  # type: ignore
        return func

    return wrap


transforms = TransformSequence()
transforms.add_validate(FetchSchema)


@transforms.add
def process_fetch_task(config, tasks):
    # Converts fetch-url entries to the run schema.
    for task in tasks:
        typ = task["fetch"]["type"]
        name = task["name"]
        fetch = task.pop("fetch")

        if typ not in fetch_builders:
            raise Exception(f"Unknown fetch type {typ} in fetch {name}")
        # Validate fetch config using msgspec
        try:
            msgspec.convert(fetch, fetch_builders[typ].schema)
        except msgspec.ValidationError as e:
            raise Exception(f"In task.fetch {name!r}: {e}")

        task.update(configure_fetch(config, typ, name, fetch))

        yield task


def configure_fetch(config, typ, name, fetch):
    if typ not in fetch_builders:
        raise Exception(f"No fetch type {typ} in fetch {name}")
    # Validate fetch config using msgspec
    try:
        msgspec.convert(fetch, fetch_builders[typ].schema)
    except msgspec.ValidationError as e:
        raise Exception(f"In task.fetch {name!r}: {e}")

    return fetch_builders[typ].builder(config, name, fetch)


@transforms.add
def make_task(config, tasks):
    # Fetch tasks are idempotent and immutable. Have them live for
    # essentially forever.
    if config.params["level"] == "3":
        expires = "1000 years"
    else:
        expires = config.graph_config._config.get("task-expires-after", "28 days")

    for task in tasks:
        name = task["name"]
        artifact_prefix = task.get("artifact-prefix", "public")
        env = task.get("env", {})
        env.update({"UPLOAD_DIR": "/builds/worker/artifacts"})
        attributes = task.get("attributes", {})
        attributes["fetch-artifact"] = path.join(artifact_prefix, task["artifact_name"])
        alias = task.get("fetch-alias")
        if alias:
            attributes["fetch-alias"] = alias

        task_desc = {
            "attributes": attributes,
            "name": name,
            "description": task["description"],
            "expires-after": task.get("expires-after", expires),
            "label": f"fetch-{name}",
            "run-on-projects": [],
            "run": {
                "using": "run-task",
                "checkout": False,
                "command": task["command"],
            },
            "worker-type": "images",
            "worker": {
                "chain-of-trust": True,
                "docker-image": task.get("docker-image", {"in-tree": "fetch"}),
                "env": env,
                "max-run-time": 900,
                "artifacts": [
                    {
                        "type": "directory",
                        "name": artifact_prefix,
                        "path": "/builds/worker/artifacts",
                    }
                ],
            },
        }

        if "treeherder" in config.graph_config:
            task_desc["treeherder"] = {
                "symbol": join_symbol("Fetch", name),
                "kind": "build",
                "platform": "fetch/opt",
                "tier": 1,
            }

        if task.get("secret", None):
            task_desc["scopes"] = ["secrets:get:" + task.get("secret")]
            task_desc["worker"]["taskcluster-proxy"] = True

        if not taskgraph.fast:
            cache_name = task_desc["label"].replace(f"{config.kind}-", "", 1)

            # This adds the level to the index path automatically.
            add_optimization(
                config,
                task_desc,
                cache_type=CACHE_TYPE,
                cache_name=cache_name,
                digest_data=task["digest_data"],
            )
        yield task_desc


class GPGSignatureConfig(Schema):
    """GPG signature verification configuration."""

    # URL where GPG signature document can be obtained. Can contain the
    # value ``{url}``, which will be substituted with the value from ``url``.
    sig_url: str
    # Path to file containing GPG public key(s) used to validate download.
    key_path: str


class StaticUrlFetchConfig(Schema, rename="kebab"):
    """Configuration for static-url fetch type."""

    type: str
    # The URL to download.
    url: str
    # The SHA-256 of the downloaded content.
    sha256: str
    # Size of the downloaded entity, in bytes.
    size: int
    # GPG signature verification.
    gpg_signature: Optional[GPGSignatureConfig] = None
    # The name to give to the generated artifact. Defaults to the file
    # portion of the URL. Using a different extension converts the
    # archive to the given type. Only conversion to .tar.zst is supported.
    artifact_name: Optional[str] = None
    # Strip the given number of path components at the beginning of
    # each file entry in the archive.
    # Requires an artifact-name ending with .tar.zst.
    strip_components: Optional[int] = None
    # Add the given prefix to each file entry in the archive.
    # Requires an artifact-name ending with .tar.zst.
    add_prefix: Optional[str] = None
    # Headers to pass alongside the request.
    headers: Optional[Dict[str, str]] = None
    # IMPORTANT: when adding anything that changes the behavior of the task,
    # it is important to update the digest data used to compute cache hits.


@fetch_builder("static-url", StaticUrlFetchConfig)
def create_fetch_url_task(config, name, fetch):
    artifact_name = fetch.get("artifact-name")
    if not artifact_name:
        artifact_name = fetch["url"].split("/")[-1]

    command = [
        "fetch-content",
        "static-url",
    ]

    # Arguments that matter to the cache digest
    args = [
        "--sha256",
        fetch["sha256"],
        "--size",
        f"{fetch['size']}",
    ]

    if fetch.get("strip-components"):
        args.extend(["--strip-components", f"{fetch['strip-components']}"])

    if fetch.get("add-prefix"):
        args.extend(["--add-prefix", fetch["add-prefix"]])

    command.extend(args)

    env = {}

    if "gpg-signature" in fetch:
        sig_url = fetch["gpg-signature"]["sig-url"].format(url=fetch["url"])
        key_path = os.path.join(taskgraph.GECKO, fetch["gpg-signature"]["key-path"])  # type: ignore

        with open(key_path) as fh:
            gpg_key = fh.read()

        env["FETCH_GPG_KEY"] = gpg_key
        command.extend(
            [
                "--gpg-sig-url",
                sig_url,
                "--gpg-key-env",
                "FETCH_GPG_KEY",
            ]
        )

    if "headers" in fetch:
        for k, v in fetch["headers"].items():
            command.extend(["-H", f"{k}:{v}"])

    command.extend([fetch["url"], f"/builds/worker/artifacts/{artifact_name}"])

    return {
        "command": command,
        "artifact_name": artifact_name,
        "env": env,
        # We don't include the GPG signature in the digest because it isn't
        # materially important for caching: GPG signatures are supplemental
        # trust checking beyond what the shasum already provides.
        "digest_data": args + [artifact_name],
    }


class GitFetchConfig(Schema):
    """Configuration for git fetch type."""

    type: str
    repo: str
    revision: str
    include_dot_git: Optional[bool] = None
    artifact_name: Optional[str] = None
    path_prefix: Optional[str] = None
    # ssh-key is a taskcluster secret path (e.g. project/civet/github-deploy-key)
    # In the secret dictionary, the key should be specified as
    #  "ssh_privkey": "-----BEGIN OPENSSH PRIVATE KEY-----\nkfksnb3jc..."
    # n.b. The OpenSSH private key file format requires a newline at the end of the file.
    ssh_key: Optional[str] = None


@fetch_builder("git", GitFetchConfig)
def create_git_fetch_task(config, name, fetch):
    path_prefix = fetch.get("path-prefix")
    if not path_prefix:
        path_prefix = fetch["repo"].rstrip("/").rsplit("/", 1)[-1]
    artifact_name = fetch.get("artifact-name")
    if not artifact_name:
        artifact_name = f"{path_prefix}.tar.zst"

    if not re.match(r"[0-9a-fA-F]{40}", fetch["revision"]):
        raise Exception(f'Revision is not a sha1 in fetch task "{name}"')

    args = [
        "fetch-content",
        "git-checkout-archive",
        "--path-prefix",
        path_prefix,
        fetch["repo"],
        fetch["revision"],
        f"/builds/worker/artifacts/{artifact_name}",
    ]

    ssh_key = fetch.get("ssh-key")
    if ssh_key:
        args.append("--ssh-key-secret")
        args.append(ssh_key)

    digest_data = [fetch["revision"], path_prefix, artifact_name]
    if fetch.get("include-dot-git", False):
        args.append("--include-dot-git")
        digest_data.append(".git")

    return {
        "command": args,
        "artifact_name": artifact_name,
        "digest_data": digest_data,
        "secret": ssh_key,
    }
