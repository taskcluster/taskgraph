# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from taskgraph.transforms.base import TransformSequence

transforms = TransformSequence()


@transforms.add
def add_pr_route(config, tasks):
    """Adds pull request index routes when applicable."""
    if not (pr_number := config.params.get("pull_request_number")):
        yield from tasks
        return

    PR_ROUTE = (
        "index.{trust-domain}.v2.{project}-pr.{pr-number}.latest.{kind}.{task-name}"
    )
    subs = {
        "trust-domain": config.graph_config["trust-domain"],
        "project": config.params["project"],
        "pr-number": pr_number,
        "kind": config.kind,
    }

    for task in tasks:
        subs["task-name"] = task.get("name") or task["label"][len(config.kind) + 1 :]
        routes = task.setdefault("routes", [])
        routes.append(PR_ROUTE.format(**subs))
        yield task
