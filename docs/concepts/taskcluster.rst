Relation to Taskcluster
=======================

`Taskcluster`_ executes the actual tasks (JSON objects) and places them on a
queue. A worker later claims that task, executes it, and updates the task with
the results. Tasks can be created, re-run, retriggered or cancelled via the
Taskcluster libraries, the firefox-ci or community UIs or Treeherder. In a code
base, tasks can be created via a `.taskcluster.yml`_ file.

The Taskgraph library is separate from the Taskcluster platform, but works
synergistically with it; it delegates to the decision task which manages task
creation and dependencies. For example, it’ll determine that a signing task
should wait until a build task has been completed before running or that
android installation dependencies should always run before an android build
starts. It can be used to fetch secrets for a testing platform as part of a
ui-test task.

.. _Taskcluster: https://taskcluster.net
.. _.taskcluster.yml: https://docs.taskcluster.net/docs/reference/integrations/github/taskcluster-yml-v1

.. seealso:: `Taskcluster documentation <https://docs.taskcluster.net/docs/tutorial>`_

Why Taskcluster
---------------

There are tens of thousands of tasks that are needed to build, test and release
Firefox and most off the shelf solutions aren't designed with this kind of
scale in mind. In addition to scaling efficiently, Taskcluster is able to
handle complex task scheduling, support any external providers (e.g Bitrise)
and provides sophisticated caching and optimization techniques. Security
features like `Chain of Trust`_ and a fine-grained permissions system (called
"scopes") allows Mozilla to maintain full control of signing keys and
certificates.

.. _Chain of Trust: https://scriptworker.readthedocs.io/en/latest/chain_of_trust.html
