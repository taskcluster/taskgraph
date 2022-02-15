Concepts
========

.. _decision task:

.. rubric:: Decision Task

The decision task for pushes is defined in the .taskcluster.yml file. That task
description invokes ``taskgraph_decision`` with some metadata about the push
and determines the optimized task graph, then calls the TaskCluster API to
create the tasks.

.. rubric:: Kinds

Kinds are the focal point of this system. They provide an interface between the
large-scale graph-generation process and the small-scale task-definition needs
of different kinds of tasks. A kind.yml file contains data about the kind, as
well as referring to a Python class implementing the kind in its implementation
key. These Python classes can either be part of standard Taskgraph, or custom
transforms that extend Taskgraph functionality.

Certain attributes - such as `kind-dependencies` - can be used to determine
which kind should be loaded before another. This is useful when the kind will
use the list of already-created tasks to determine which tasks to create, for
example loading an `android-toolchain` (to install sdk and accept licenses)
before every (android) build task. In some cases, you'll need to use a custom
loader to avoid scheduling a task until the task it depends on is completed.

But dependencies can also be used to schedule follow-up work such as
summarizing test results. In the latter case, the summarization task will “pull
in” all of the tasks it depends on, even if those tasks might otherwise be
optimized away.

.. seealso:: `Further reading on Taskgraph <https://johanlorenzo.github.io/blog/2019/10/24/taskgraph-is-now-deployed-to-the-biggest-mozilla-mobile-projects.html>`_

.. toctree::
   :maxdepth: 2
   :caption: More Concepts

   taskcluster
   glossary
