# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Expand symbolic Python versions into concrete versions. The supported range
is derived from the repository's ``pyproject.toml``.
"""

import re

try:
    import tomllib
except ImportError:
    # Python < 3.11, provided by the `tomli` dev dependency.
    import tomli as tomllib

from taskgraph.transforms.base import TransformSequence

transforms = TransformSequence()

CLASSIFIER_PREFIX = "Programming Language :: Python :: "
LITERAL_VERSION_RE = re.compile(r"\d+\.\d+t?")


def _parse(version):
    major, minor = version.strip().split(".")[:2]
    return int(major), int(minor)


def _endpoints(graph_config):
    """Return the major version and min/max minor versions from
    ``pyproject.toml``."""
    pyproject = graph_config.vcs_root / "pyproject.toml"
    with open(pyproject, "rb") as fh:
        project = tomllib.load(fh)["project"]

    lower = [
        spec.strip()[2:]
        for spec in project["requires-python"].split(",")
        if spec.strip().startswith(">=")
    ]
    if len(lower) != 1:
        raise ValueError(
            f"expected a single '>=' bound in requires-python in {pyproject}"
        )
    min_major, min_minor = _parse(lower[0])

    versions = [
        _parse(c.removeprefix(CLASSIFIER_PREFIX))
        for c in project["classifiers"]
        if c.startswith(CLASSIFIER_PREFIX) and "." in c.removeprefix(CLASSIFIER_PREFIX)
    ]
    if not versions:
        raise ValueError(f"no '{CLASSIFIER_PREFIX}X.Y' classifiers in {pyproject}")
    max_major, max_minor = max(versions)

    if min_major != max_major or min_minor > max_minor:
        raise ValueError(
            f"invalid python version range {min_major}.{min_minor} to "
            f"{max_major}.{max_minor} derived from {pyproject}"
        )
    return min_major, {"min": min_minor, "max": max_minor}


@transforms.add
def expand_python_versions(config, tasks):
    major, endpoints = _endpoints(config.graph_config)

    def resolve(symbol):
        """Return the (minor version, suffix) for a symbol."""
        name, suffix = (symbol[:-1], "t") if symbol.endswith("t") else (symbol, "")
        if name not in endpoints:
            valid = ", ".join(f"{e}, {e}t" for e in endpoints)
            raise ValueError(
                f"unknown python version symbol '{symbol}', expected one of: {valid}"
            )
        return endpoints[name], suffix

    def expand(value, sep=""):
        start, _, end = value.partition("..")
        start, start_suffix = resolve(start)
        end, end_suffix = resolve(end) if end else (start, start_suffix)
        if start_suffix != end_suffix:
            raise ValueError(
                f"invalid python version range '{value}': endpoints must both "
                "be free-threaded or not"
            )
        step = 1 if end >= start else -1
        return [
            f"{major}{sep}{minor}{start_suffix}"
            for minor in range(start, end + step, step)
        ]

    def expand_list(values):
        return [v for value in values for v in expand(value)]

    def expand_args(value):
        versions = []
        for token in value.split():
            if LITERAL_VERSION_RE.fullmatch(token):
                versions.append(token)
            else:
                versions.extend(expand(token, sep="."))
        return " ".join(versions)

    for task in tasks:
        matrix = task.get("matrix", {})
        if "python" in matrix:
            matrix["python"] = expand_list(matrix["python"])

        expanded_rules = []
        for rule in matrix.get("exclude", []):
            if "python" not in rule:
                expanded_rules.append(rule)
                continue
            for v in expand(rule["python"]):
                expanded_rules.append({**rule, "python": v})
        if expanded_rules:
            matrix["exclude"] = expanded_rules

        with_attributes = task.get("from-deps", {}).get("with-attributes", {})
        if "python" in with_attributes:
            with_attributes["python"] = expand_list(with_attributes["python"])

        if config.kind == "docker-image":
            args = task.get("args", {})
            if "PYTHON_VERSIONS" in args:
                args["PYTHON_VERSIONS"] = expand_args(args["PYTHON_VERSIONS"])

        yield task
