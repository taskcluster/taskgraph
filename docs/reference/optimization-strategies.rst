Optimization Strategies
=======================

Taskgraph provides some built-in strategies that can be used during the
:doc:`optimzation process </concepts/optimization>`.

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

Given a list of index paths, this strategy will replace the target task with
the first one that exists.

Example:

.. code-block:: yaml

   my-task:
     optimization:
       index-search:
         - my.index.route
