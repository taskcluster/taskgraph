Debugging and Testing
=====================

When you first get started you'll notice that pushing changes to your PR (or testing branch) then waiting for all tasks to complete is a slow and wasteful way to iterate.
Luckily there are several tools you can use locally to verify that changes you make to kinds and custom transforms or loaders
(if used), don't error out due to bugs.

Tools for Local Development
---------------------------

There are several debugging tools built into Taskgraph that can be used to either view a diff of changes or to generate a local graph based on pre-defined parameters. 
See :ref:`working-on-taskgraph` for local setup instructions.
 
To generate a local graph, cd into your project (make sure its in Taskgraphs PATH) and download a parameters.yml file from a recent Decision task (click
into the Taskgraph UI and click on a Decision tasks Artifacts list). Parameters are passed to a Decision task and provide project and task details,
such as what type of tasks to run (default, nightly, beta or release.)

Run this command to generate the local graph. You'll see the `kinds` it will generate and will throw
errors if you are missing required attributes in yaml files or if there is a schema validation bug. 

.. code-block::

  taskgraph target-graph -p <path-to-your-parameters.yml> 
  taskgraph target-graph -p task-id=<decision task id> # alternatively, you pass the decision task id with the parameters you want to use

One of the most useful aspects of this command, is that you can use it to verify that you are generating the 
correct graph of tasks by changing the `target_tasks_method` from `default` to `release` or `nightly` (assuming you have this type of support already set up).

You can also use the `--diff` flag to generate and view diffs (as json blobs) of multiple taskgraphs e.g. github releases, [nightly] cron, [release promotion] actions, github-push, and pull-requests and see
exactly what the differences are. This can be useful to track down an issue where, for example, github releases is broken but everything else is running smoothly, and to verify that any fix you
make to the release graph hasn't broken something in the other graphs. If you want to diff against multiple parameters at a time, simply pass `--parameters` multiple times (or pass a directory containing parameters files).

Retriggering and Rerunning Tasks
--------------------------------

These can either be triggered in the Taskcluster UI (by clicking into the appropriate task, and hoovering over the bubble in the bottom right corner), via the Taskcluster CLI
or in the Treeherder UI (currently only pushes on `main` and `master` are consumed and displayed).

Staging Repositories
--------------------

Release Engineering typically creates a staging repository of Github projects that use Taskgraph. These clones of production projects live in `mozilla-releng <https://github.com/mozilla-releng>`_ 
and are managed by Release Engineering. 

These staging repos have historically been created for Releng use, but we are now opening them up for members of each project to also use (if your Mozilla project uses Taskgraph/Taskcluster and does not
currently have a staging repo you can access, please reach out to someone on the Releng team).

These staging repos are very useful for testing changes to secrets (with the caveat, you need to be careful you're not also affecting production secrets),
or simulating release actions, such as pushing apks to the Google Play Store without actually doing so.

Something to note, is that the scriptworker-scripts that are used for certain tasks (defined in a projects `taskcluster/ci/config.yml` file) will still point to production scriptworkers unless you modfiy the config file
to point to <some-scriptworker>-dev (be sure to change it back before pushing to a production repository). You can see all of the available dev options `here <https://scriptworker-scripts.readthedocs.io/en/latest/README.html#overview-of-existing-workers>`_.
