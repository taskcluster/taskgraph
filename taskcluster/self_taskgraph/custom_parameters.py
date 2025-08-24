# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


def decision_parameters(graph_config, parameters):
    if parameters["tasks_for"] == "github-release":
        parameters["target_tasks_method"] = "release"
