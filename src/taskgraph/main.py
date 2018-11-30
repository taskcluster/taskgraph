# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import sys
import traceback
import argparse
import logging

_commands = []


def command(*args, **kwargs):
    def decorator(func):
        func.command = (args, kwargs)
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


def create_parser():
    parser = argparse.ArgumentParser(description="Interact with taskgraph")
    subparsers = parser.add_subparsers()
    for func in _commands:
        subparser = subparsers.add_parser(*func.command[0], **func.command[1])
        for arg in func.args:
            subparser.add_argument(*arg[0], **arg[1])
        subparser.set_defaults(command=func)
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
