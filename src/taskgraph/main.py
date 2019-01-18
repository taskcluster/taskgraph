# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import os
import sys
import traceback
import argparse
import logging
import json
import yaml

_commands = []


def command(*args, **kwargs):
    defaults = kwargs.pop("defaults", {})

    def decorator(func):
        func.command = (args, kwargs, defaults)
        _commands.append(func)
        return func

    return decorator


def argument(*args, **kwargs):
    def decorator(func):
        if not hasattr(func, "args"):
            func.args = []
        func.args.append((args, kwargs))
        return func

    return decorator


def show_taskgraph_labels(taskgraph):
    for index in taskgraph.graph.visit_postorder():
        print(taskgraph.tasks[index].label)


def show_taskgraph_json(taskgraph):
    print(
        json.dumps(
            taskgraph.to_json(), sort_keys=True, indent=2, separators=(",", ": ")
        )
    )


def show_taskgraph_yaml(taskgraph):
    print(yaml.safe_dump(taskgraph.to_json()))


SHOW_METHODS = {
    "labels": show_taskgraph_labels,
    "json": show_taskgraph_json,
    "yaml": show_taskgraph_yaml,
}


@command("full", description="", defaults={"graph_attr": "full_task_graph"})
@argument("--root", "-r", help="root of the taskgraph definition relative to topsrcdir")
@argument("--quiet", "-q", action="store_true", help="suppress all logging output")
@argument(
    "--verbose", "-v", action="store_true", help="include debug-level logging output"
)
@argument(
    "--json",
    "-J",
    action="store_const",
    dest="format",
    const="json",
    help="Output task graph as a JSON object",
)
@argument(
    "--yaml",
    "-Y",
    action="store_const",
    dest="format",
    const="yaml",
    help="Output task graph as a YAML object",
)
@argument(
    "--labels",
    "-L",
    action="store_const",
    dest="format",
    const="labels",
    help="Output the label for each task in the task graph (default)",
)
@argument(
    "--parameters",
    "-p",
    default="",
    help="parameters file (.yml or .json; see " "`taskcluster/docs/parameters.rst`)`",
)
@argument(
    "--no-optimize",
    dest="optimize",
    action="store_false",
    default="true",
    help="do not remove tasks from the graph that are found in the "
    "index (a.k.a. ptimize the graph)",
)
@argument(
    "--tasks-regex",
    "--tasks",
    default=None,
    help="only return tasks with labels matching this regular " "expression.",
)
@argument(
    "-F",
    "--fast",
    dest="fast",
    default=False,
    action="store_true",
    help="enable fast task generation for local debugging.",
)
def show_taskgraph(options):
    import taskgraph.parameters
    import taskgraph.target_tasks
    import taskgraph.generator
    import taskgraph

    if options["fast"]:
        taskgraph.fast = True

    try:
        parameters = taskgraph.parameters.load_parameters_file(
            options["parameters"], strict=False
        )
        parameters.check()

        tgg = taskgraph.generator.TaskGraphGenerator(
            root_dir=options.get("root"), parameters=parameters
        )

        tg = getattr(tgg, options["graph_attr"])

        show_method = SHOW_METHODS.get(options["format"] or "labels")
        # tg = get_filtered_taskgraph(tg, options["tasks_regex"])
        show_method(tg)
    except Exception:
        traceback.print_exc()
        sys.exit(1)


@command("build-image", description="Build a Docker image")
@argument("image_name", help="Name of the image to build")
@argument(
    "-t", "--tag", help="tag that the image should be built as.", metavar="name:tag"
)
@argument(
    "--context-only",
    help="File name the context tarball should be written to."
    "with this option it will only build the context.tar.",
    metavar="context.tar",
)
def build_image(args):
    from taskgraph.docker import build_image, build_context

    if args["context_only"] is None:
        build_image(args["image_name"], args["tag"], os.environ)
    else:
        build_context(args["image_name"], args["context_only"], os.environ)


@command(
    "load-image",
    help="Load a pre-built Docker image. Note that you need to "
    "have docker installed and running for this to work.",
)
@argument(
    "--task-id",
    help="Load the image at public/image.tar.zst in this task, "
    "rather than searching the index",
)
@argument(
    "-t",
    "--tag",
    help="tag that the image should be loaded as. If not "
    "image will be loaded with tag from the tarball",
    metavar="name:tag",
)
@argument(
    "image_name",
    nargs="?",
    help="Load the image of this name based on the current "
    "contents of the tree (as built for mozilla-central "
    "or mozilla-inbound)",
)
def load_image(args):
    from taskgraph.docker import load_image_by_name, load_image_by_task_id

    if not args.get("image_name") and not args.get("task_id"):
        print("Specify either IMAGE-NAME or TASK-ID")
        sys.exit(1)
    try:
        if args["task_id"]:
            ok = load_image_by_task_id(args["task_id"], args.get("tag"))
        else:
            ok = load_image_by_name(args["image_name"], args.get("tag"))
        if not ok:
            sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)


def create_parser():
    parser = argparse.ArgumentParser(description="Interact with taskgraph")
    subparsers = parser.add_subparsers()
    for func in _commands:
        subparser = subparsers.add_parser(*func.command[0], **func.command[1])
        for arg in func.args:
            subparser.add_argument(*arg[0], **arg[1])
        subparser.set_defaults(command=func, **func.command[2])
    return parser


def main():
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    parser = create_parser()
    args = parser.parse_args()
    try:
        args.command(vars(args))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
