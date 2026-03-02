# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
import inspect
import logging
import multiprocessing
import os
import platform
from concurrent.futures import (
    FIRST_COMPLETED,
    ProcessPoolExecutor,
    wait,
)
from dataclasses import dataclass
from typing import Callable, Optional, Union

from . import filter_tasks
from .config import GraphConfig, load_graph_config
from .graph import Graph
from .morph import morph
from .optimize.base import optimize_task_graph
from .parameters import Parameters, parameters_loader
from .task import Task
from .taskgraph import TaskGraph
from .transforms.base import TransformConfig, TransformSequence
from .util.python_path import find_object
from .util.verify import verifications
from .util.yaml import load_yaml

logger = logging.getLogger(__name__)


class KindNotFound(Exception):
    """
    Raised when trying to load kind from a directory without a kind.yml.
    """


@dataclass(frozen=True)
class Kind:
    name: str
    path: str
    config: dict
    graph_config: GraphConfig

    def _get_loader(self) -> Callable:
        try:
            loader_path = self.config["loader"]
        except KeyError:
            loader_path = "taskgraph.loader.default:loader"
        loader = find_object(loader_path)
        assert callable(loader)
        return loader

    def load_tasks(self, parameters, kind_dependencies_tasks, write_artifacts):
        logger.debug(f"Loading tasks for kind {self.name}")

        parameters = Parameters(**parameters)
        loader = self._get_loader()
        config = copy.deepcopy(self.config)

        if "write_artifacts" in inspect.signature(loader).parameters:
            extra_args = (write_artifacts,)
        else:
            extra_args = ()
        inputs = loader(
            self.name,
            self.path,
            config,
            parameters,
            list(kind_dependencies_tasks.values()),
            *extra_args,
        )

        transforms = TransformSequence()
        for xform_path in config["transforms"]:
            if ":" not in xform_path:
                xform_path = f"{xform_path}:transforms"

            transform = find_object(xform_path)
            transforms.add(transform)

        # perform the transformations on the loaded inputs
        trans_config = TransformConfig(
            self.name,
            self.path,
            config,
            parameters,
            kind_dependencies_tasks,
            self.graph_config,
            write_artifacts=write_artifacts,
        )
        tasks = [
            Task(
                self.name,
                label=task_dict["label"],
                description=task_dict["description"],
                attributes=task_dict["attributes"],
                task=task_dict["task"],
                optimization=task_dict.get("optimization"),
                dependencies=task_dict.get("dependencies", {}),
                soft_dependencies=task_dict.get("soft-dependencies", []),
                if_dependencies=task_dict.get("if-dependencies", []),
            )
            for task_dict in transforms(trans_config, inputs)
        ]
        logger.info(f"Generated {len(tasks)} tasks for kind {self.name}")
        return tasks

    @classmethod
    def load(cls, root_dir, graph_config, kind_name):
        path = os.path.join(root_dir, "kinds", kind_name)
        kind_yml = os.path.join(path, "kind.yml")
        if not os.path.exists(kind_yml):
            raise KindNotFound(kind_yml)

        logger.debug(f"loading kind `{kind_name}` from `{path}`")
        config = load_yaml(kind_yml)

        return cls(kind_name, path, config, graph_config)


class TaskGraphGenerator:
    """
    The central controller for taskgraph.  This handles all phases of graph
    generation.  The task is generated from all of the kinds defined in
    subdirectories of the generator's root directory.

    Access to the results of this generation, as well as intermediate values at
    various phases of generation, is available via properties.  This encourages
    the provision of all generation inputs at instance construction time.
    """

    # Task-graph generation is implemented as a Python generator that yields
    # each "phase" of generation.  This allows some mach subcommands to short-
    # circuit generation of the entire graph by never completing the generator.

    def __init__(
        self,
        root_dir: Optional[str],
        parameters: Union[Parameters, Callable[[GraphConfig], Parameters]],
        decision_task_id: str = "DECISION-TASK",
        write_artifacts: bool = False,
        enable_verifications: bool = True,
    ):
        """
        @param root_dir: root directory containing the Taskgraph config.yml file
        @param parameters: parameters for this task-graph generation, or callable
            taking a `GraphConfig` and returning parameters
        @type parameters: Union[Parameters, Callable[[GraphConfig], Parameters]]
        """
        if root_dir is None:
            root_dir = "taskcluster"
        self.root_dir = root_dir
        self._parameters_input = parameters
        self._decision_task_id = decision_task_id
        self._write_artifacts = write_artifacts
        self._enable_verifications = enable_verifications
        self._graph_config = None
        self._parameters = None
        self._kinds = None
        self._kind_graph = None
        self._full_task_set = None
        self._full_task_graph = None
        self._target_task_set = None
        self._target_task_graph = None
        self._optimized_task_graph = None
        self._morphed_task_graph = None
        self._label_to_taskid = None

    @property
    def graph_config(self):
        """
        The configuration for this graph.

        @type: TaskGraph
        """
        if self._graph_config:
            return self._graph_config

        logger.info("Loading graph configuration.")
        self._graph_config = load_graph_config(self.root_dir)
        self._graph_config.register()
        # Initial verifications that don't depend on any generation state.
        self.verify("initial")
        self.verify("graph_config", self._graph_config)

        return self._graph_config

    @property
    def parameters(self):
        """
        The properties used for this graph.

        @type: Properties
        """
        if self._parameters:
            return self._parameters

        if callable(self._parameters_input):
            parameters = self._parameters_input(self.graph_config)
        else:
            parameters = self._parameters_input

        logger.info(f"Using {self._parameters}")
        logger.debug(f"Dumping parameters:\n{repr(self._parameters)}")

        self.verify("parameters", parameters)
        self._parameters = parameters
        return parameters

    @property
    def kinds(self):
        if self._kinds:
            return self._kinds
        logger.info("Loading kinds")
        # put the kinds into a graph and sort topologically so that kinds are loaded
        # in post-order
        target_kinds = sorted(self.parameters.get("target-kinds", []))
        if target_kinds:
            logger.info(
                "Limiting kinds to following kinds and dependencies: {}".format(
                    ", ".join(target_kinds)
                )
            )
        self._kinds = {
            kind.name: kind
            for kind in self._load_kinds(self.graph_config, target_kinds)
        }
        self.verify("kinds", self._kinds)
        return self._kinds

    @property
    def kind_graph(self):
        """
        The dependency graph of kinds.

        @type: Graph
        """
        if self._kind_graph:
            return self._kind_graph
        edges = set()
        for kind in self.kinds.values():
            for dep in kind.config.get("kind-dependencies", []):
                edges.add((kind.name, dep, "kind-dependency"))
        self._kind_graph = Graph(frozenset(self.kinds), frozenset(edges))

        target_kinds = sorted(self.parameters.get("target-kinds", []))
        if target_kinds:
            self._kind_graph = self._kind_graph.transitive_closure(
                set(target_kinds) | {"docker-image"}
            )

        return self._kind_graph

    @property
    def full_task_set(self):
        """
        The full task set: all tasks defined by any kind (a graph without edges)

        @type: TaskGraph
        """
        if self._full_task_set:
            return self._full_task_set

        logger.info("Generating full task set")
        # The short version of the below is: we only support parallel kind
        # processing on Linux.
        #
        # Current parallel generation relies on multiprocessing, and more
        # specifically: the "fork" multiprocessing method. This is not supported
        # at all on Windows (it uses "spawn"). Forking is supported on macOS,
        # but no longer works reliably in all cases, and our usage of it here
        # causes crashes. See https://github.com/python/cpython/issues/77906
        # and http://sealiesoftware.com/blog/archive/2017/6/5/Objective-C_and_fork_in_macOS_1013.html
        # for more details on that.
        # Other methods of multiprocessing (both "spawn" and "forkserver")
        # do not work for our use case, because they cause global variables
        # to be reinitialized, which are sometimes modified earlier in graph
        # generation. These issues can theoretically be worked around by
        # eliminating all reliance on globals as part of task generation, but
        # is far from a small amount of work in users like Gecko/Firefox.
        # In the long term, the better path forward is likely to be switching
        # to threading with a free-threaded python to achieve similar parallel
        # processing.
        if platform.system() != "Linux" or os.environ.get("TASKGRAPH_SERIAL"):
            all_tasks = self._load_tasks_serial(
                self.kinds, self.kind_graph, self.parameters
            )
        else:
            all_tasks = self._load_tasks_parallel(
                self.kinds, self.kind_graph, self.parameters
            )

        full_task_set = TaskGraph(all_tasks, Graph(frozenset(all_tasks), frozenset()))
        self.verify("full_task_set", full_task_set, self.graph_config, self.parameters)
        self._full_task_set = full_task_set
        return self._full_task_set

    @property
    def full_task_graph(self):
        """
        The full task graph: the full task set, with edges representing
        dependencies.

        @type: TaskGraph
        """
        if self._full_task_graph:
            return self._full_task_graph

        all_tasks = self.full_task_set.tasks
        logger.info("Generating full task graph")
        edges = set()
        for t in self.full_task_set:
            for depname, dep in t.dependencies.items():
                if dep not in all_tasks.keys():
                    raise Exception(
                        f"Task '{t.label}' lists a dependency that does not exist: '{dep}'"
                    )
                edges.add((t.label, dep, depname))

        full_task_graph = TaskGraph(
            all_tasks,
            Graph(frozenset(self.full_task_set.graph.nodes), frozenset(edges)),
        )
        logger.info(
            f"Full task graph contains {len(self.full_task_set.graph.nodes)} tasks and {len(edges)} dependencies"
        )
        self.verify(
            "full_task_graph", full_task_graph, self.graph_config, self.parameters
        )
        self._full_task_graph = full_task_graph
        return full_task_graph

    @property
    def target_task_set(self):
        """
        The set of targeted tasks (a graph without edges)

        @type: TaskGraph
        """
        if self._target_task_set:
            return self._target_task_set

        all_tasks = self.full_task_set.tasks
        logger.info("Generating target task set")
        target_task_set = TaskGraph(
            dict(all_tasks),
            Graph(frozenset(all_tasks.keys()), frozenset()),
        )
        filters = self.parameters.get("filters", [])
        if not filters:
            # Default to target_tasks_method if none specified.
            filters.append("target_tasks_method")
        filters = [filter_tasks.filter_task_functions[f] for f in filters]

        for fltr in filters:
            old_len = len(target_task_set.graph.nodes)
            target_tasks = set(
                fltr(self._target_task_set, self.parameters, self.graph_config)
            )
            self._target_task_set = TaskGraph(
                {l: all_tasks[l] for l in target_tasks},
                Graph(frozenset(target_tasks), frozenset()),
            )
            logger.info(
                f"Filter {fltr.__name__} pruned {old_len - len(target_tasks)} tasks ({len(target_tasks)} remain)"
            )

        self.verify(
            "target_task_set", target_task_set, self.graph_config, self.parameters
        )
        self._target_task_set = target_task_set
        return target_task_set

    @property
    def target_task_graph(self):
        """
        The set of targeted tasks and all of their dependencies

        @type: TaskGraph
        """
        if self._target_task_graph:
            return self._target_task_graph

        logger.info("Generating target task graph")
        # include all tasks with `always_target` set
        if self.parameters["enable_always_target"]:
            always_target_tasks = {
                t.label
                for t in self.full_task_graph.tasks.values()
                if t.attributes.get("always_target")
                if self.parameters["enable_always_target"] is True
                or t.kind in self.parameters["enable_always_target"]
            }
        else:
            always_target_tasks = set()

        target_tasks = set(self.target_task_set.tasks)
        logger.info(
            f"Adding {len(always_target_tasks) - len(always_target_tasks & target_tasks)} tasks with `always_target` attribute"  # type: ignore
        )
        requested_tasks = target_tasks | always_target_tasks  # type: ignore
        target_graph = self.full_task_graph.graph.transitive_closure(requested_tasks)
        all_tasks = self.full_task_set.tasks
        target_task_graph = TaskGraph(
            {l: all_tasks[l] for l in target_graph.nodes},
            target_graph,
        )
        self.verify(
            "target_task_graph", target_task_graph, self.graph_config, self.parameters
        )
        self._target_task_graph = target_task_graph
        return target_task_graph

    @property
    def optimized_task_graph(self):
        """
        The set of targeted tasks and all of their dependencies; tasks that
        have been optimized out are either omitted or replaced with a Task
        instance containing only a task_id.

        @type: TaskGraph
        """
        if self._optimized_task_graph:
            return self._optimized_task_graph

        logger.info("Generating optimized task graph")
        existing_tasks = self.parameters.get("existing_tasks")
        do_not_optimize = set(self.parameters.get("do_not_optimize", []))
        if not self.parameters.get("optimize_target_tasks", True):
            do_not_optimize = set(self.target_task_set.graph.nodes).union(
                do_not_optimize
            )

        # this is used for testing experimental optimization strategies
        strategies = os.environ.get(
            "TASKGRAPH_OPTIMIZE_STRATEGIES", self.parameters.get("optimize_strategies")
        )
        if strategies:
            strategies = find_object(strategies)

        if self.parameters["enable_always_target"]:
            always_target_tasks = {
                t.label
                for t in self.full_task_graph.tasks.values()
                if t.attributes.get("always_target")
                if self.parameters["enable_always_target"] is True
                or t.kind in self.parameters["enable_always_target"]
            }
        else:
            always_target_tasks = set()
        target_tasks = set(self.target_task_set.tasks)
        requested_tasks = target_tasks | always_target_tasks  # type: ignore

        optimized_task_graph, label_to_taskid = optimize_task_graph(
            self.target_task_graph,
            requested_tasks,
            self.parameters,
            do_not_optimize,
            self._decision_task_id,
            existing_tasks=existing_tasks,
            strategy_override=strategies,
        )

        self.verify(
            "optimized_task_graph",
            optimized_task_graph,
            self.graph_config,
            self.parameters,
        )
        self._optimized_task_graph = optimized_task_graph
        self._label_to_taskid = label_to_taskid
        return optimized_task_graph

    @property
    def label_to_taskid(self):
        """
        A dictionary mapping task label to assigned taskId.  This property helps
        in interpreting `optimized_task_graph`.

        @type: dictionary
        """
        if self._label_to_taskid:
            return self._label_to_taskid

        # ensure _label_to_taskid is populated before returning it
        # don't run any further than necessary though
        self.optimized_task_graph
        return self._label_to_taskid

    @property
    def morphed_task_graph(self):
        """
        The optimized task graph, with any subsequent morphs applied. This graph
        will have the same meaning as the optimized task graph, but be in a form
        more palatable to TaskCluster.

        @type: TaskGraph
        """
        morphed_task_graph, label_to_taskid = morph(
            self.optimized_task_graph,
            self.label_to_taskid,
            self.parameters,
            self.graph_config,
        )

        self.verify(
            "morphed_task_graph", morphed_task_graph, self.graph_config, self.parameters
        )
        self._morphed_task_graph = morphed_task_graph
        self._label_to_taskid = label_to_taskid
        return morphed_task_graph

    def _load_kinds(self, graph_config, target_kinds=None):
        if target_kinds:
            # docker-image is an implicit dependency that never appears in
            # kind-dependencies.
            queue = target_kinds + ["docker-image"]
            seen_kinds = set()
            while queue:
                kind_name = queue.pop()
                if kind_name in seen_kinds:
                    continue
                seen_kinds.add(kind_name)
                kind = Kind.load(self.root_dir, graph_config, kind_name)
                yield kind
                queue.extend(kind.config.get("kind-dependencies", []))
        else:
            for kind_name in os.listdir(os.path.join(self.root_dir, "kinds")):
                try:
                    yield Kind.load(self.root_dir, graph_config, kind_name)
                except KindNotFound:
                    continue

    def _load_tasks_serial(self, kinds, kind_graph, parameters):
        all_tasks = {}
        for kind_name in kind_graph.visit_postorder():
            logger.debug(f"Loading tasks for kind {kind_name}")

            kind = kinds.get(kind_name)
            if not kind:
                message = f'Could not find the kind "{kind_name}"\nAvailable kinds:\n'
                for k in sorted(kinds):
                    message += f' - "{k}"\n'
                raise Exception(message)

            try:
                new_tasks = kind.load_tasks(
                    parameters,
                    {
                        k: t
                        for k, t in all_tasks.items()
                        if t.kind in kind.config.get("kind-dependencies", [])
                    },
                    self._write_artifacts,
                )
            except Exception:
                logger.exception(f"Error loading tasks for kind {kind_name}:")
                raise
            for task in new_tasks:
                if task.label in all_tasks:
                    raise Exception("duplicate tasks with label " + task.label)
                all_tasks[task.label] = task

        return all_tasks

    def _load_tasks_parallel(self, kinds, kind_graph, parameters):
        all_tasks = {}
        futures_to_kind = {}
        futures = set()
        edges = set(kind_graph.edges)

        with ProcessPoolExecutor(
            mp_context=multiprocessing.get_context("fork")
        ) as executor:

            def submit_ready_kinds():
                """Create the next batch of tasks for kinds without dependencies."""
                nonlocal kinds, edges, futures
                loaded_tasks = all_tasks.copy()
                kinds_with_deps = {edge[0] for edge in edges}
                ready_kinds = (
                    set(kinds) - kinds_with_deps - set(futures_to_kind.values())
                )
                for name in ready_kinds:
                    kind = kinds.get(name)
                    if not kind:
                        message = (
                            f'Could not find the kind "{name}"\nAvailable kinds:\n'
                        )
                        for k in sorted(kinds):
                            message += f' - "{k}"\n'
                        raise Exception(message)

                    future = executor.submit(
                        kind.load_tasks,
                        dict(parameters),
                        {
                            k: t
                            for k, t in loaded_tasks.items()
                            if t.kind in kind.config.get("kind-dependencies", [])
                        },
                        self._write_artifacts,
                    )
                    futures.add(future)
                    futures_to_kind[future] = name

            submit_ready_kinds()
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    if exc := future.exception():
                        executor.shutdown(wait=False, cancel_futures=True)
                        raise exc
                    kind = futures_to_kind.pop(future)
                    futures.remove(future)

                    for task in future.result():
                        if task.label in all_tasks:
                            raise Exception("duplicate tasks with label " + task.label)
                        all_tasks[task.label] = task

                    # Update state for next batch of futures.
                    del kinds[kind]
                    edges = {e for e in edges if e[1] != kind}

                # Submit any newly unblocked kinds
                submit_ready_kinds()

        return all_tasks

    def verify(self, name, *args, **kwargs):
        if self._enable_verifications:
            verifications(name, *args, **kwargs)
        if args:
            return name, args[0]


def load_tasks_for_kinds(
    parameters, kinds, root_dir=None, graph_attr=None, **tgg_kwargs
):
    """
    Get all the tasks of the given kinds.

    This function is designed to be called from outside of taskgraph.
    """
    graph_attr = graph_attr or "full_task_set"

    # make parameters read-write
    parameters = dict(parameters)
    parameters["target-kinds"] = kinds
    parameters = parameters_loader(spec=None, strict=False, overrides=parameters)
    tgg = TaskGraphGenerator(root_dir=root_dir, parameters=parameters, **tgg_kwargs)
    return {
        task.task["metadata"]["name"]: task
        for task in getattr(tgg, graph_attr)
        if task.kind in kinds
    }


def load_tasks_for_kind(parameters, kind, root_dir=None, **tgg_kwargs):
    """
    Get all the tasks of a given kind.

    This function is designed to be called from outside of taskgraph.
    """
    return load_tasks_for_kinds(parameters, [kind], root_dir, **tgg_kwargs)
