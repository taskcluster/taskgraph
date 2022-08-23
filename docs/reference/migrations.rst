Migration Guide
===============

This page can help when migrating Taskgraph across major versions.


2.x -> 3.x
----------

* Rename ``config.kind_dependencies_tasks`` to ``config.kind_dependencies_tasks.values()``
* Rename ``vcs.head_ref`` to ``vcs.head_rev``. ``vcs.head_ref`` still exists but points to the actual reference instead of the revision.
* Rename ``vcs.base_ref`` to ``vcs.base_rev``. Same rationale as above.


1.x -> 2.x
----------

* For all kinds using the :mod:`transform loader <taskgraph.loader.transform>`,
  rename the following keys in both the ``kind.yml`` file and any files referenced
  in ``jobs-from``::

    jobs -> tasks
    jobs-from -> tasks-from
    job-defaults -> task-defaults

* Rename ``taskgraph.util.schema.WHITELISTED_SCHEMA_IDENTIFIERS`` to
  ``taskgraph.util.schema.EXCEPTED_SCHEMA_IDENTIFIERS``.

* Rename any instances of ``taskgraph.optimize.Either`` to
  ``taskgraph.optimize.Any``.

* Add a ``deadline`` parameter as the third argument to any custom optimization
  strategies'
  :func:`~taskgraph.optimize.OptimizationStrategy.should_replace_task`
  function. For migration purposes it doesn't need to be used.

* Replace ``taskgraph.util.taskcluster.status_task`` with
  ``taskgraph.util.taskcluster.state_task``.
