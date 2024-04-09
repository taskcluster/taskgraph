Migration Guide
===============

This page can help when migrating Taskgraph across major versions.

7.x -> 8.x
----------

* Replace all references to ``taskgraph.files_changed``. Instead, use one of:

  * The ``files_changed`` parameter
  * The ``get_files_changed`` method on an instance of ``taskgraph.util.vcs.Repository``
  * Mercurial repositories relying on hgmo's ``json-automationrelevance``
    endpoint will need to in-line this logic into their own custom Taskgraph
    logic
* In tasks using the ``from_deps`` transforms, remove ``from-deps.set-name`` if
  it is set to ``true``
* Update any references to pull request cached task indexes from
  ``{cache_prefix}.cache.head.{head_ref}...`` to ``{cache_prefix}.cache.pr...``
  (i.e, add ``pr`` and remove the ``head.{head_ref}``)

6.x -> 7.x
----------

* Upgrade to Python 3.8 or higher
* Ensure ``root_dir`` now points to ``taskcluster`` instead of
  ``taskcluster/ci``. Typically this value is not passed in explicitly by
  consumers, but updates are likely required if you have custom code that
  uses any of the following objects:

  * ``taskgraph.config.GraphConfig``
  * ``taskgraph.config.load_graph_config``
  * ``taskgraph.generator.TaskGraphGenerator``
  * ``taskgraph.generator.load_tasks_for_kinds``
  * The ``-r/--root`` flag on the ``taskgraph`` binary
* Rename the ``run_job_using`` decorator to ``run_task_using``
* Move ``config.yml`` from ``taskcluster/ci`` to ``taskcluster``
* Rename the ``taskcluster/ci`` directory to ``taskcluster/kinds``
* Replace references to ``taskgraph.transforms.job`` with ``taskgraph.transforms.run``
* Replace references to ``taskgraph.transforms.release_notifications`` with ``taskgraph.transforms.notify``
* Replace references to ``taskgraph.target_tasks._target_task`` with ``taskgraph.target_tasks.register_target_task``
* Stop using or inline ``taskgraph.util.decision.make_decision_task``
* Stop using the ``decision-mobile`` docker image
* Ensure MacOS workers that need Mercurial have ``hg`` on their ``PATH``

5.x -> 6.x
----------

* Replace all uses of ``command-context` with the more generalized ``task-context``

4.x -> 5.x
----------

* Upgrade to Python 3.7 or higher

3.x -> 4.x
----------

* Remove all uses of the ``disable-seccomp`` key in the ``worker`` section of task definitions.

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
