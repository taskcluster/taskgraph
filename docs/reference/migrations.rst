Migration Guide
===============

This page can help when migrating Taskgraph across major versions.

14.x -> 15.x
------------

* `get_primary_dependency` now requires a `primary-dependency-label` to be set
  on the task it is passed instead of `primary-kind-dependency`. Update any tasks
  you were calling this for to set this attribute. (If your only usage of this
  is indirectly through `from_deps`, no change is needed: `from-deps` generated
  tasks will set this for you.)

13.x -> 14.x
------------

* The `{task_workdir}` string in environment variables no longer gets
  interpolated by `run-task`. This is backing out a feature introduced in
  version 13.x, so this release introduces no new backwards incompatibilities
  with version 12.x or earlier.

12.x -> 13.x
------------

* Remove all ``run.cache-dotcache`` keys. If it was set to ``true``, replace it
  with:

  .. code-block:: yaml

     run:
       use-caches: [checkout, <caches>]

  Where caches can be any of ``cargo``, ``pip``, ``uv`` or ``npm``. If the task
  was setting up ``.cache`` for another tool, a mount will need to be created
  for it manually. If ``use-caches`` was previously set to ``false``, omit
  ``checkout`` in the example above. If ``use-caches`` was previously set to
  ``true``, replace ``true`` with the value above (including ``checkout``).

  In Dockerfiles, replace `VOLUME /builds/worker/.cache` by
  `VOLUME /builds/worker/.task-cache/{uv, cargo, pip, npm}` as necessary.

* Invert any usage of the dict keys and values returned by `get_ancestors`:

  For example, if you were using:

  .. code-block:: python

    for label, taskid in get_ancestors(...):
      ...

  Change it to:

  .. code-block:: python

    for taskid, label in get_ancestors(...):
      ...

  Note that due to this change `get_ancestors` may return multiple tasks with
  the same label now, which your code may need to deal with.

11.x -> 12.x
------------

* Add ``target_tasks_method`` to the front of the ``filters`` parameter wherever
  you are also using a custom filter.

  For example, if you are passing in:

  .. code-block:: yaml

     filters: ["my_custom_filter"]

  Change it to:

  .. code-block:: yaml

     filters: ["target_tasks_method", "my_custom_filter"]

  No action is necessary if the ``filters`` parameter was empty.
* Change all references from ``build-docker-image`` to ``docker-image``.

10.x -> 11.x
------------

* A hardcoded path to a Python installation was removed for MacOS
  generic-workers. If Mac tasks start failing after upgrade and you are able to
  change the worker environment, ensure the ``python3`` binary is available on
  the ``$PATH``. If you cannot change the worker environment, add the following
  to the definitions of the failing tasks:

  .. code-block:: yaml

     run:
       run-task-command: ["/tools/python36/bin/python3", "run-task"]
* When defining custom actions with
  ``taskgraph.actions.registry.register_callback_action``, make the following
  changes:

  * If you are passing ``generic=True`` to the function, remove this argument.
  * If the argument isn't present, or you are passing ``generic=False``, then
    add a new argument called ``permission=<cb_name>``, where ``<cb_name>`` is
    the value of whatever you are passing to the ``cb_name`` argument.

9.x -> 10.x
-----------

* Directories listed as VOLUME in Dockerfiles are created before any other
  instructions, so those instructions may need to be updated (e.g. `RUN mkdir`)
* `fetch-content` no longer relies on file extension to detect archives, so you.
  may need to explicitly disable `extract` for some fetches.

8.x -> 9.x
----------

* Replace references to ``taskgraph.util.memoize.memoize`` with
  ``functools.cache``. E.g, change ``@memoize`` to ``@cache``. If using Python
  3.8, use ``@functools.lru_cache(maxsize=None)`` instead.
* Pay close attention to tasks that use ``task-defaults`` to merge
  configuration containing ``by-<attribute>`` keys. The
  :func:`taskgraph.util.templates.merge` function will no longer attempt to merge
  keys containing these attributes, which may result in changes to your graph.
  You can use the :ref:`diff feature <diffing graphs>` to help detect possible
  changes.

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

* Replace all uses of ``command-context`` with the more generalized ``task-context``

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
