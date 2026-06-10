# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
from typing import Annotated, Optional

import msgspec

from taskgraph.parameters import extend_parameters_schema
from taskgraph.util.schema import Schema


def get_defaults(repo_root):
    return {
        "pull_request_number": None,
    }


CustomParametersSchema = Schema.from_dict(
    {"pull_request_number": Optional[Annotated[int, msgspec.Meta(ge=1)]]},
    name="CustomParametersSchema",
)


extend_parameters_schema(CustomParametersSchema, defaults_fn=get_defaults)


def decision_parameters(graph_config, parameters):
    if parameters["tasks_for"] == "github-release":
        parameters["target_tasks_method"] = "release"

    pr_number = os.environ.get("TASKGRAPH_PULL_REQUEST_NUMBER", None)
    parameters["pull_request_number"] = None if pr_number is None else int(pr_number)
