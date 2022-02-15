.. _intro-to-taskgraph:

Intro to Taskgraph and TaskCluster
==================================

Overview
--------
Taskgraph is a library that generates graphs of tasks in response to all types of events - such as opening a pull request or creating a release - and submits the graph to Taskcluster, Mozilla's in-house CI. 
The graph is built by linking different kinds of tasks together, pruning out tasks that are not required, and then optimizing by replacing subgraphs with links to already-completed tasks.

How Taskgraph relates to Taskcluster
------------------------------------
`Taskcluster <https://taskcluster.net>`_ executes the actual tasks (JSON objects) and places them on a queue. A worker later claims that task, executes it, and updates the task with the results. 
Tasks can be created, re-run, retriggered or cancelled via the Taskcluster libraries, the firefox-ci or community UIs or Treeherder. In a code base, tasks can be created via a `.taskcluster.yml <https://docs.taskcluster.net/docs/reference/integrations/github/taskcluster-yml-v1>`_ file.

The Taskgraph library is separate from the Taskcluster platform, but works synergistically with it; it delegates to the decision task which manages task creation and dependencies. For example, it’ll determine that a signing task
should wait until a build task has been completed before running or that android installation dependencies should always run before an android build starts. It can be used to fetch secrets for a testing platform as part of a ui-test task.


.. seealso:: `Taskcluster documentation <https://docs.taskcluster.net/docs/tutorial>`_

Why Taskcluster
------------------
There are tens of thousands of tasks that are needed to build, test and release Firefox and most off the shelf solutions aren't designed with this kind of scale in mind. 
In addition to scaling efficiently, Taskcluster is able to handle complex task scheduling, support any external providers (e.g Bitrise) and provides sophisticated caching and optimization techniques. 
Security features like `Chain of Trust <https://scriptworker.readthedocs.io/en/latest/chain_of_trust.html>`_ and a fine-grained permissions system (called "scopes") allows Mozilla to maintain full control of signing keys and certificates.


Glossary of Terms
-----------------
.. glossary::

  Task
    Code containing repository data and commands to run, called the `task definition`, that is submitted to Taskcluster for execution.

  Decision task
    The decision task is the first task created when a new graph begins. It is responsible for creating the rest of the task graph.

  Kind
    Tasks of the same `kind` have substantial similarities or share common processing logic and are grouped together in a kind.yml file.

  Loader
    Parses each of the kinds, applies logic in the transforms, and determines the order in which to create and schedule tasks.

  Transform
    Applies logic to the kind tasks in response to task attributes. This can involve things like executing a script in response to certain attribute values in a kind file, 
    or creating a payload to submit to a scriptworker to perform a specific action.

  Scriptworker
    `Scripts <https://github.com/mozilla-releng/scriptworker-scripts>`_ controlled by Release Engineering that perform certain actions required to complete a kind task, 
    such as signing binaries to pushing packages to the Google Play store or to Mozilla archives.

  Trust Domains
    These consist of scopes, routes and worker pools that are grouped roughly by product so as to minimize security risks and manage resources. The smaller the trust domain,
    the more secure but the harder it is to maintain and manage resources.
  
  Scopes
    Taskcluster permissions required to perform a particular action. Each task has a set of these permissions determining what it can do.


Decision Task
-------------
The decision task for pushes is defined in the .taskcluster.yml file. That task description invokes ``taskgraph_decision`` with some metadata about the push and 
determines the optimized task graph, then calls the TaskCluster API to create the tasks.


Kinds
----------
Kinds are the focal point of this system. They provide an interface between the large-scale graph-generation process and 
the small-scale task-definition needs of different kinds of tasks. A kind.yml file contains data about the kind, as well as referring
to a Python class implementing the kind in its implementation key. These Python classes can either be part of standard Taskgraph, or custom transforms that extend Taskgraph functionality.

Certain attributes - such as `kind-dependencies` - can be used to determine which kind should be loaded before another. This is useful when the kind will use the list of already-created
tasks to determine which tasks to create, for example loading an `android-toolchain` (to install sdk and accept licenses) before every (android) build task. In some cases, you'll need to use a custom loader to avoid scheduling a
task until the task it depends on is completed.

But dependencies can also be used to schedule follow-up work such as summarizing test results. In the latter case, the summarization task will “pull in” all of the tasks it depends on, 
even if those tasks might otherwise be optimized away.

.. seealso:: `Further reading on Taskgraph <https://johanlorenzo.github.io/blog/2019/10/24/taskgraph-is-now-deployed-to-the-biggest-mozilla-mobile-projects.html>`_