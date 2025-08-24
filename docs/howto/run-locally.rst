Run Taskgraph Locally
=====================

When first starting out with Taskgraph, it's tempting to test changes by
pushing to a pull request (or try server) and checking whether your
modifications have the desired effect on the impacted task(s). This isn't ideal
because the turn around time is slow, you may hit easily preventable errors in
the :term:`Decision Task`, and it wastes money running tasks that are
irrelevant to your changes.

So before you even push your changes, it's best practice to verify whether
graph generation succeeds as well as to sanity check that your changes are
having the desired effect.

Generating Graphs
-----------------

.. note::

   If you haven't done so already, make sure :ref:`Taskgraph is installed
   <installation>`.

Graphs can be generated via the ``taskgraph`` binary. This binary provides
subcommands that correspond to the :ref:`phases of graph generation <graph
generation>`. For instance:

* Running ``taskgraph full`` produces the ``full_task_graph``.
* Running ``taskgraph target`` produces the ``target_task_graph``.
* etc.

For a list of available sub-commands, see:

.. code-block:: shell

   taskgraph --help

.. _useful arguments:

Useful Arguments
~~~~~~~~~~~~~~~~

Here are some useful arguments accepted by most ``taskgraph`` subcommands. For
a full reference, see :doc:`/reference/cli`.

``-J/--json``
+++++++++++++

By default only the task labels are displayed as output, but when ``-J/--json``
is used, the full JSON representation of all task definitions are displayed.

.. note::

   Using ``-J/--json`` can often result in a massive amount of output. Consider
   using the ``--tasks`` and/or ``--target-kind`` flags in conjunction to
   filter the result down to a manageable level.

``--tasks/--tasks-regex``
+++++++++++++++++++++++++

A regular expression that matches against task labels. Useful for filtering
down the output to only display desired tasks.

``-k/--target-kind``
++++++++++++++++++++

Only generate tasks of the given ``kind`` or any kinds listed in that kind's
``kind-dependencies`` key. Can be passed in multiple times.

``-p/--parameters``
+++++++++++++++++++

Generate the graph with the specified :term:`parameter set <Parameters>`. The
following formats are accepted:

* Path to a ``parameters.yml`` file.
* A value of ``task-id=<decision task id>``. The ``parameters.yml`` artifact
  from the decision task specified by ``<decision task id>`` will be downloaded
  and used.
* A value of ``project=<project>``. The ``parameters.yml`` artifact from the
  latest decision task on ``<project>`` will be downloaded and used.
* A value of ``index=<index>``. The ``parameters.yml`` artifact will be
  downloaded from the decision task pointed to by the specified index path.
* Path to a directory containing multiple parameter files. Any ``.yml`` file in
  the directory will be considered a parameter set.

The ``-p/--parameters`` flag can be passed in multiple times. If passed in
multiple times, or if a directory containing more than one parameter set is
specified, then one graph generation per parameter set will occur in parallel.
Log generation will be disabled and output will be captured and emitted at the
end under parameter specific headings. This feature is primarily useful for
:ref:`diffing graphs`.

.. note::

   If you do not specify parameters, the default values for each parameter will
   be used instead. This may result in a different graph than what is generated
   in CI.

``--fast``
++++++++++

Skip schema validation and other extraneous checks. This results in a faster
generation at the expense of correctness.

.. note::

   When using ``--fast`` you may miss errors that will cause the decision task
   to fail in CI.

Validating Your Changes
-----------------------

Most changes to your Taskgraph configuration will likely fall under one of two
buckets:

1. Modifications to the task definitions. This involves changes to the ``kind.yml``
   files or any transform files that it references.
2. Modifications to where the task runs. This is a subset of the above, but
   occurs when you modify values that affect the ``target_task`` phase, such as
   the ``run-on-projects`` or ``run-on-tasks-for`` keys.

Different testing approaches are needed to validate each type.

Validating Changes to Task Definitions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you're only modifying the definition of tasks, then you want to generate the
``full_task_graph``. This is because task definitions are frozen (with minor
exceptions) after this phase. You'll also want to use the ``-J/--json`` flag and
likely also the ``--tasks`` flag to filter down the result.

For example, let's say you modify a task called ``build-android``. Then you
would run the following command:

.. code-block:: shell

   taskgraph full -J --tasks "build-android"

Then you can inspect the resulting task definition and validate that everything
is configured as you expect.

Validating Changes to Where Tasks Run
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you're modifying *where* a task runs, e.g by changing a key that impacts the
``target_tasks_method`` parameter (such as ``run-on-projects`` or
``run-on-tasks-for``), you'll want to generate up until the
``target_task_graph`` phase.

Unlike when modifying the definition, we don't care about the contents of the
task so passing the ``-J/--json`` flag is unnecessary. Instead, we can simply
inspect whether the label exists or not. However it *is* important to make sure
we're generating under the appropriate context(s) via the ``-p/--parameters``
flag.

For example, let's say you want to modify the ``test-sensitive`` task so it
runs on pushes to the ``main`` branch, but *does not* run on pull requests
(because it needs sensitive secrets you don't want to expose to PRs). First you
would go to the main branch, find a decision task and copy it's ``taskId``.

Then you would run:

.. code-block:: shell

   taskgraph target -p task-id=<decision taskId from main push>

Now you would verify that the ``test-sensitive`` label shows up in the
resulting output.

Next you would go to a pull request, find a decision task, and again
copy its ``taskId``. Then you'd again run:

.. code-block:: shell

   taskgraph target -p task-id=<decision taskId from PR>

This time, you'd verify that the label *does not* show up.

.. note::

   If there are certain parameter sets you find yourself needing over and over,
   consider checking them into your repo under ``taskcluster/test/params``,
   like the `Fenix repository does`_. This way you can pass a path to the
   appropriate parameters file rather than searching for a decision task.

.. _Fenix repository does: https://github.com/mozilla-mobile/fenix/tree/main/taskcluster/test/params

.. _diffing graphs:

Diffing Graphs
--------------

Another strategy for testing your changes is to generate a graph with and
without your changes, and then diffing the output of the two. Taskgraph has a
built-in ``--diff`` flag that makes this process simple. Both Mercurial and Git
are supported.

Because the ``--diff`` flag will actually update your VCS's current directory,
make sure you don't have any uncommitted changes (the ``taskgraph`` binary will
error out if you do). Then run:

.. code-block:: shell

   taskgraph full -p <params> --diff

Taskgraph will automatically determine which revision to diff against
(defaulting to your entire local stack). But you may optionally pass in a
revision specifier, e.g:

.. code-block:: shell

   # git
   taskgraph full -p <params> --diff HEAD~1

   # hg
   taskgraph full -p <params> --diff .~1

Instead of the normal output (either labels or json), a diff will be displayed.

.. note::

   The ``--diff`` flag composes with every other flag on the ``taskgraph``
   binary. Meaning you can still filter using ``--tasks`` or ``--target-kind``.
   It can also diff any output format (labels or json).

Excluding Keys from the Diff
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sometimes you might be making changes that impact many tasks (in the case of
Firefox's CI, this is often thousands). You might have some expected changes
you know you made, but you want to check that there aren't any *additional*
changes beyond that. You can pass in the ``--exclude-key`` flag to filter out
certain properties of the task definition.

For example, let's say you added an environment variable called "FOO" to every
task. You now want to make sure that you didn't make any changes beyond this, but
the diff is so large this is difficult. You can run:

.. code-block:: shell

   taskgraph full -p <params> --diff --exclude-key "task.payload.env.FOO"

This will first remove the ``task.payload.env.FOO`` key from every task before
performing the diff. Ensuring that the only differences left over are the ones
you didn't expect.
