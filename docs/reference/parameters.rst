Parameters
==========

Taskgraph generation takes a collection of :term:`Parameters` as input, in the form of
a JSON or YAML file. Below are the parameters that Taskgraph supports.

.. note::

   Projects may define additional parameters on top of these ones.

Push Information
----------------

These parameters describe metadata associated with the push that triggered the
:term:`Decision Task`.

base_repository
~~~~~~~~~~~~~~~
   The repository from which to do an initial clone.

head_repository
~~~~~~~~~~~~~~~
   The repository containing the changeset to be built. This may differ from
   ``base_repository`` in cases where ``base_repository`` is likely to be cached
   and only a few additional commits are needed from ``head_repository``.

base_rev
~~~~~~~~
   The previous revision before ``head_rev`` got merged into. This can be a short revision string.

head_rev
~~~~~~~~
   The revision to check out, this can be a short revision string.

base_ref
~~~~~~~~
   Reference where ``head_rev`` got merged into. It is usually a branch or a tag.

head_ref
~~~~~~~~
   Reference that contains the ``head_rev``. It defaults to the current branch,
   then to the current revision if no branch is found.

head_tag
~~~~~~~~
   The tag attached to the revision, if any.

files_changed
~~~~~~~~~~~~~
   The list of all files added or modified by the push.

owner
~~~~~
   Email address indicating the person who made the push. Note that this
   value may be forged and *must not* be relied on for authentication.

pushlog_id
~~~~~~~~~~
   The ID from the ``hg.mozilla.org`` pushlog or 0.

pushdate
~~~~~~~~
   The timestamp of the push to the repository that triggered this decision
   task. Expressed as an integer in seconds since the UNIX epoch.

build_date
~~~~~~~~~~
   The timestamp of the build date. Defaults to ``pushdate`` and falls back to
   present time of taskgraph invocation. Expressed as an integer seconds since
   the UNIX epoch.

moz_build_date
~~~~~~~~~~~~~~
   A formatted timestamp of ``build_date``. Expressed as a string with the following
   format: %Y%m%d%H%M%S

repository_type
~~~~~~~~~~~~~~~
   The type of repository, either ``hg`` or ``git``.

tasks_for
~~~~~~~~~
   The ``tasks_for`` value used to generate the decision task.

Project Information
-------------------

These parameters describe the "project" (or repository) that triggered the :term:`Decision
Task`.

project
~~~~~~~
   Another name for what may otherwise be called repository. At Mozilla this
   may also be referred to as tree or branch. This is the unqualified name,
   such as ``mozilla-central`` or ``fenix``.

level
~~~~~
   The `SCM level`_ associated with this tree.

.. _SCM level: https://www.mozilla.org/en-US/about/governance/policies/commit/access-policy/

Target Set
----------

These parameters are used at the ``target_task`` phase of :ref:`graph generation
<Graph Generation>`.

enable_always_target
~~~~~~~~~~~~~~~~~~~~

   Can either be a boolean or a list of kinds.

   When ``True``, any task with the ``always_target`` attribute will be included
   in the ``target_task_graph`` regardless of whether they were filtered out by
   the ``target_tasks_method`` or not. Because they are not part of the
   ``target_set``, they will still be eligible for optimization when the
   ``optimize_target_tasks`` parameter is ``False``.

   When specified as a list of kinds, only tasks with a matching kind will be
   eligible for addition to the graph.

filters
~~~~~~~
    List of filter functions (from ``taskcluster/gecko_taskgraph/filter_tasks.py``) to
    apply. This is usually defined internally, as filters are typically
    global.

target_tasks_method
~~~~~~~~~~~~~~~~~~~
    The method to use to determine the target task set.  This is the suffix of
    one of the functions in ``taskcluster/gecko_taskgraph/target_tasks.py``.

Optimization
------------

These parameters are used at the ``optimization`` phase of :ref:`graph generation
<Graph Generation>`.

optimize_strategies
~~~~~~~~~~~~~~~~~~~
   A Python path of the form ``<module>:<object>`` pointing to a dictionary of
   optimization strategies to use, overwriting the defaults.

optimize_target_tasks
~~~~~~~~~~~~~~~~~~~~~
   If true, then target tasks are eligible for optimization.

do_not_optimize
~~~~~~~~~~~~~~~
   Specify tasks to not optimize out of the graph. This is a list of labels.
   Any tasks in the graph matching one of the labels will not be optimized out
   of the graph.

existing_tasks
~~~~~~~~~~~~~~
   Specify tasks to optimize out of the graph. This is a dictionary of label to taskId.
   Any tasks in the graph matching one of the labels will use the previously-run
   taskId rather than submitting a new task.

Code Review
-----------

These parameters are used by Mozilla's `code review bot`_.

code-review.phabricator-build-target
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
   The code review process needs to know the Phabricator Differential diff that
   started the analysis. This parameter must start with `PHID-DIFF-`

.. _code review bot: https://github.com/mozilla/code-review

Local Configuration
-------------------

These parameters only apply when :doc:`generating Taskgraph locally
</howto/run-locally>`.

target-kind
~~~~~~~~~~~
  Generate only the given kind and its kind-dependencies. This is used for
  local inspection of the graph and is not supported at run-time.
