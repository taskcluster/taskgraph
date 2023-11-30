Migration Guide
===============

This page can help when migrating Taskgraph across major versions.

6.x -> 7.x
----------

* Upgrade to Python 3.8 or higher

5.x -> 6.x
----------

* Replace all uses of `command-context` with the more generalized `task-context`

4.x -> 5.x
----------

* Upgrade to Python 3.7 or higher

3.x -> 4.x
----------

* Remove all uses of the `disable-seccomp` key in the `worker` section of task definitions.

2.x -> 3.x
----------

* Use a `decision image <https://hub.docker.com/r/mozillareleases/taskgraph/tags>`_ at least as recent as `this one <https://hub.docker.com/layers/taskgraph/mozillareleases/taskgraph/decision-e878f3e1534b0fd8584921db9eb0f194c243566649667eedaf21ed5055f06a42/images/sha256-4c8cf846d6be5dfd61624121f75d62d828b0e5fcbd49950fce23bf5389720a70>`_.
* Rename ``config.kind_dependencies_tasks`` to ``config.kind_dependencies_tasks.values()``.
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
