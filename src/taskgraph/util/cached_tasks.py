# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import hashlib
import time

TARGET_CACHE_INDEX = "{cache_prefix}.cache.level-{level}.{type}.{name}.hash.{digest}"
TARGET_PR_CACHE_INDEX = "{cache_prefix}.cache.pr.{type}.{name}.hash.{digest}"
EXTRA_CACHE_INDEXES = [
    "{cache_prefix}.cache.level-{level}.{type}.{name}.latest",
    "{cache_prefix}.cache.level-{level}.{type}.{name}.pushdate.{build_date_long}",
]


def add_optimization(
    config, taskdesc, cache_type, cache_name, digest=None, digest_data=None
):
    """
    Allow the results of this task to be cached. This adds index routes to the
    task so it can be looked up for future runs, and optimization hints so that
    cached artifacts can be found. Exactly one of `digest` and `digest_data`
    must be passed.

    :param TransformConfig config: The configuration for the kind being transformed.
    :param dict taskdesc: The description of the current task.
    :param str cache_type: The type of task result being cached.
    :param str cache_name: The name of the object being cached.
    :param digest: A unique string identifying this version of the artifacts
        being generated. Typically this will be the hash of inputs to the task.
    :type digest: bytes or None
    :param digest_data: A list of bytes representing the inputs of this task.
        They will be concatenated and hashed to create the digest for this
        task.
    :type digest_data: list of bytes or None
    """
    if (digest is None) == (digest_data is None):
        raise Exception("Must pass exactly one of `digest` and `digest_data`.")
    if digest is None:
        digest = hashlib.sha256("\n".join(digest_data).encode("utf-8")).hexdigest()  # type: ignore

    if "cached-task-prefix" in config.graph_config["taskgraph"]:
        cache_prefix = config.graph_config["taskgraph"]["cached-task-prefix"]
    else:
        cache_prefix = config.graph_config["trust-domain"]

    subs = {
        "cache_prefix": cache_prefix,
        "type": cache_type,
        "name": cache_name,
        "digest": digest,
    }

    # We'll try to find a cached version of the toolchain at levels above and
    # including the current level, starting at the highest level.
    index_routes = []
    min_level = int(config.params["level"])
    for level in reversed(range(min_level, 4)):
        subs["level"] = level
        index_routes.append(TARGET_CACHE_INDEX.format(**subs))

    # Pull requests use a different target cache index route. This way we can
    # be confident they won't be used by anything other than the pull request
    # that created the cache in the first place.
    if config.params["tasks_for"].startswith(
        "github-pull-request"
    ) and config.graph_config["taskgraph"].get("cache-pull-requests", True):
        subs["head_ref"] = config.params["head_ref"]
        if subs["head_ref"].startswith("refs/heads/"):
            subs["head_ref"] = subs["head_ref"][11:]
        index_routes.append(TARGET_PR_CACHE_INDEX.format(**subs))

    taskdesc["optimization"] = {"index-search": index_routes}

    # ... and cache at the lowest level.
    subs["level"] = config.params["level"]

    if config.params["tasks_for"].startswith("github-pull-request"):
        if config.graph_config["taskgraph"].get("cache-pull-requests", True):
            taskdesc.setdefault("routes", []).append(
                f"index.{TARGET_PR_CACHE_INDEX.format(**subs)}"
            )
    else:
        taskdesc.setdefault("routes", []).append(
            f"index.{TARGET_CACHE_INDEX.format(**subs)}"
        )

        # ... and add some extra routes for humans
        subs["build_date_long"] = time.strftime(
            "%Y.%m.%d.%Y%m%d%H%M%S", time.gmtime(config.params["build_date"])
        )
        taskdesc["routes"].extend(
            [f"index.{route.format(**subs)}" for route in EXTRA_CACHE_INDEXES]
        )

    taskdesc["attributes"]["cached_task"] = {
        "type": cache_type,
        "name": cache_name,
        "digest": digest,
    }
