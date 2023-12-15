Optimization Strategies
=======================

Taskgraph provides some built-in strategies that can be used during the
:doc:`optimization process </concepts/optimization>`.

Strategies for Removing Tasks
-----------------------------

skip-unless-changed
~~~~~~~~~~~~~~~~~~~

.. note::

   This strategy is only implemented for Mercurial repositories hosted on
   ``hg.mozilla.org``.

The :class:`skip-unless-changed
<taskgraph.optimize.strategies.SkipUnlessChanged>` strategy will optimize the
target task away *unless* a specified file is modified. Glob patterns are
supported.

Example:

.. code-block:: yaml

   my-task:
     optimization:
       skip-unless-changed:
         - some/file.txt
         - docs/**

Strategies for Replacing Tasks
------------------------------

index-search
~~~~~~~~~~~~

Given a list of index paths, the :class:`index-search
<taskgraph.optimize.strategies.IndexSearch>` strategy will replace the target
task with the first one that exists.

In order for the indexed task to be considered for replacement, it must:

1. Exist.
2. Not have a ``state`` of ``failed`` or ``exception``.
3. Not expire before the earliest deadline of all tasks depending on it.

Example:

.. code-block:: yaml

   my-task:
     optimization:
       index-search:
         - my.index.route

Composite Strategies
--------------------

These strategies operate on one or more substrategies. Composite
strategies may contain other composite strategies.

Alias
~~~~~

The :class:`~taskgraph.optimize.base.Alias` strategy contains a single
substrategy and provides an alternative name for it. This can be useful for
swapping the strategy used for a particular set of tasks without needing to
modify all of their task definitions.

All
~~~

The :class:`~taskgraph.optimize.base.All` strategy will only optimize a task if
all of its substrategies say to optimize it.

Any
~~~

The :class:`~taskgraph.optimize.base.Any` strategy will optimize a task if any
of its substrategies say to optimize it.

Not
~~~

The :class:`~taskgraph.optimize.base.Not` strategy contains a single substrategy
and will negate it.
