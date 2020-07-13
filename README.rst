Taskgraph
=========

Taskgraph at high-level
-----------------------

Taskgraph first originated in taskcluster’s `section`_ in our main gecko
repo, to enhance and automate the generation of our CI automation. Then,
because the results were great, parts of it have been extracted into a
standalone module which is no longer gecko-chained to be used in other
projects as well. Its new home has been set to `this repo`_ and is kept
at sync continuously to what we have in Gecko. We now use it in all our
mobile repositories now for automation (android-components, Fenix, RB,
etc). Johan wrote a great `blogpost`_ summarizing its basic usage and
functionalities.

In practice for singular graphs
-------------------------------

Taskgraph is nice as it allows to break the graph generations at
different levels. Whether that’s just before submission to the TC Queue
or earlier.

Gecko-world
~~~~~~~~~~~

For the gecko-baked one, all the logic is part of the
``mach taskgraph`` command in the root of the gecko tree.

::

   $ ./mach taskgraph --help
   usage: mach [global arguments] taskgraph subcommand [subcommand arguments]

   The taskgraph subcommands all relate to the generation of task graphs
   for Gecko continuous integration.  A task graph is a set of tasks linked
   by dependencies: for example, a binary must be built before it is tested,
   and that build may further depend on various toolchains, libraries, etc.
   ...
   Sub Commands:
     actions               Write actions.json to stdout
     decision              Run the decision task
     optimized             Show the optimized taskgraph
     target-graph          Show the target taskgraph
   ...

Each time one needs to touch existing tasks or add new ones, one usually
runs a clean slate of taskgraph to dump the existing state of the
graphs. Then make the intended changes. Then rerun taskgraph and diff
the results. Pretty much the same thing as version control.

Example, should one wanted to make changes to the Firefox beta tree.
First, find the decision task for the beta -
e.g. ``V9fiJZ7BRaaZ5AJCD4U9IQ`` for a beta graph. After the decision
task runs, it prints out a file ``parameters.yml`` (example of latest
beta
`here <https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/V9fiJZ7BRaaZ5AJCD4U9IQ/runs/0/artifacts/public/parameters.yml>`__)
that holds most of the configuration that was generated. That can be
used locally to feed taskgraph to get that graph:

::

   $ # hop on mozilla-beta on local machine
   $ ./mach taskgraph target-graph -p parameters.yml --json > clean.json
   $ # make changes/amendments to some of the tasks in the taskcluster section
   $ ./mach taskgraph target-graph -p parameters.yml --json > dirty.json
   $ diff clean.json dirty.json to inspect what has changed

Github-world
~~~~~~~~~~~~

Outside of gecko, one has to use the `standalone`_ version. The
repository first needs to be cloned and then install the ``taskgraph``
within the virtual environment.

::

   $ hg clone https://hg.mozilla.org/ci/taskgraph/
   $ cd <location-where-taskgraph-has-been-cloned>
   $ mkvirtualenv taskgraph
   # ensure we get the development version of it locally to be able to work with it
   $ (taskgraph) pip install -e .
   # now one can change directory to the github project that needs taskgraph, e.g. Fenix
   $ (taskgraph) cd <location-where-fenix-has-been-cloned>
   $ (taskgraph) taskgraph --help

In practice with automation for multiple graphs
-----------------------------------------------

Sometimes the changes are minimal and isolated to a certain
product/branch (e.g. we know for sure the change should impact only
Devedition/beta). But sometimes the changes might impact more trees than
we think. So ideally we could test our changes against all possible
graphs that exist in the gecko world. For that we use a cmd line tool
called **taskgraph-diff** that resides `here`_. RelEng constantly
updates that repo to reflect what changes in the projects using
taskgraph (gecko, mobile repos, etc). Basically it’s a collection of all
parameters files for all possible trees that we have. We apply the
previous aforementioned step on top of all of them via taskgraph. That
shows us any potential change in any graphs that we currently hold in
production.

What one usually runs is similar to the point above, but this time
directly with taskgraph-diff. Before making any changes, run a clean
slate of taskgraph-diff to get the clean version of them.

::

   $ hg clone https://hg.mozilla.org/build/braindump/ <here>
   $ pushd <here>/taskcluster/taskgraph-diff
   $ pushd <your firefox gecko tree>
   $ ~1/taskgraph-gen.py -j4 --full --params-dir ~1/params --overwrite --halt-on-failure clean
   $ # make changes into the taskgraph
   $ ~1/taskgraph-gen.py -j4 --full --params-dir ~1/params --overwrite --halt-on-failure dirty
   $ git diff --histogram ~1/json/clean ~1/json/dirty

Results will show everything that changes in all the graphs that we
currently use in production. This helps us catch any potential unwanted
side-effect whenever we touch any of the kids.

.. _section: https://hg.mozilla.org/mozilla-central/file/tip/taskcluster
.. _this repo: https://hg.mozilla.org/ci/taskgraph/
.. _blogpost: https://johanlorenzo.github.io/blog/2019/10/24/taskgraph-is-now-deployed-to-the-biggest-mozilla-mobile-projects.html
.. _standalone: https://hg.mozilla.org/ci/taskgraph/
.. _here: https://hg.mozilla.org/build/braindump/file/tip/taskcluster/taskgraph-diff
