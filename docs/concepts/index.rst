Concepts
========

.. _decision task:

.. rubric:: Decision Task

The decision task for pushes is defined in the .taskcluster.yml file. That task
description invokes ``taskgraph_decision`` with some metadata about the push
and determines the optimized task graph, then calls the TaskCluster API to
create the tasks.

.. seealso:: `Further reading on Taskgraph <https://johanlorenzo.github.io/blog/2019/10/24/taskgraph-is-now-deployed-to-the-biggest-mozilla-mobile-projects.html>`_

.. toctree::
   :maxdepth: 2
   :caption: More Concepts

   task-graphs
   taskcluster
   kind
   loading
   transforms
   optimization
   Scopes <scopes>
