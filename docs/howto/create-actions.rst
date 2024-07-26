Create Actions
==============

This page demonstrates how to define an action in-tree such that it shows up in
supported user interfaces like Treeherder or Taskcluster web.

At a high level, the process looks like this:

 * The :term:`Decision task` produces an artifact, ``public/actions.json``,
   indicating what actions are available. The format of this file is described
   in the `actions.json spec`_.

 * A user interface (for example, Treeherder or the Taskcluster web UI) consults
   ``actions.json`` and presents appropriate choices to the user, if necessary
   gathering additional data from the user, such as the number of times to
   re-trigger a task.

 * The user interface follows the action description to carry out the action.
   In most cases that entails creating an "action
   task" encapsulating the provided information. The action task is responsible
   for carrying out the named action, and may create new sub-tasks if necessary
   (for example, to re-trigger a task).

.. note::

    You can generate ``actions.json`` locally by running ``taskgraph actions``.


Defining Action Tasks
---------------------

Taskgraph provides a built-in mechanism for defining action tasks called
*callback actions*. These are actions that call back into in-tree logic.

First an action is registered with a name, title, description, context, input
schema and a Python callback function. When the action is triggered in a user
interface, input matching the schema is collected, passed to a new task which
then calls your Python callback. This system is powerful and enables actions
to perform a wide range of operations.

Suppose we want to create a new "Hello World" action. First, create a file
``taskcluster/project_taskgraph/actions/hello_world.py``. It should look
something like:

.. code-block:: python

  from taskgraph.actions.registry import register_callback_action

  @register_callback_action(
      name='hello',
      title='Say Hello',
      symbol='hello-world',  # Symbol to display in Treeherder.
      description="Says hello",
      order=10000,  # Order in which it should appear relative to other actions
  )
  def hello_world_action(parameters, graph_config, input, task_group_id, task_id, task):
      print(f"Hello from {task_group_id}!")

The arguments passed into this function are:

``parameters``
  an instance of :class:`taskgraph.parameters.Parameters`, carrying Decision task
  parameters from the original decision task.

``graph_config``
  an instance of :class:`taskgraph.config.GraphConfig`, carrying configuration
  for this tree

``input``
  the input from the user triggering the action (if any)

``task_group_id``
  the target task group on which this action should operate

``task_id``
  the target task on which this action should operate (or None if it is operating on the whole group)

``task``
  the definition of the target task (or None, as for ``task_id``)

The ``order`` value is the sort key defining the order of actions in the
resulting ``actions.json`` file. If multiple actions have the same name and
match the same task, the action with the smallest ``order`` will be used.

Setting the Action Context
..........................

The example above defines an action that is available in the context-menu for
the entire task group (result-set or push in Treeherder terminology). To create
an action that shows up in the context menu for a task we would specify the
*context* argument.

The context argument should be a list of tag-sets, such as
``context=[{"platform": "linux"}]``, which will make the action show up in the
context-menu for any task with ``task.tags.platform = 'linux'``. Below is
some examples of context arguments and the resulting conditions on
``task.tags`` (tags used below are just illustrative).

``context=[{"platform": "linux"}]``:
  Requires ``task.tags.platform = 'linux'``.
``context=[{"kind": "test", "platform": "linux"}]``:
  Requires ``task.tags.platform = 'linux'`` **and** ``task.tags.kind = 'test'``.
``context=[{"kind": "test"}, {"platform": "linux"}]``:
  Requires ``task.tags.platform = 'linux'`` **or** ``task.tags.kind = 'test'``.
``context=[{}]``:
  Requires nothing and the action will show up in the context menu for all tasks.
``context=[]``:
  Is the same as not setting the context parameter, which will make the action
  show up in the context menu for the task-group.
  (i.e., the action is not specific to some task)

The example action below will be shown in the context-menu for tasks with
``task.tags.platform = 'linux'``:

.. code-block:: python

   from taskgraph.actions.registry import register_callback_action

   @register_callback_action(
       name='retrigger',
       title='Retrigger',
       symbol='rt',  # Show the callback task in Treeherder as 'rt'
       description="Create a clone of the task",
       order=1,
       context=[{'platform': 'linux'}]
   )
   def retrigger_action(parameters, graph_config, input, task_group_id, task_id, task):
       # input will be None
       print(f"Retriggering: {task_id}")
       # code to perform the re-trigger

When the ``context`` parameter is set, the ``task_id`` and ``task`` parameters
will be provided to the callback. In this case the ``task_id`` and ``task``
parameters will be the ``taskId`` and *task definition* of the task whose
context-menu the action was triggered on.

Typically, the ``context`` parameter is used for actions that operate on
tasks, such as retriggering, running a specific test case, creating a loaner,
bisection, etc. You can think of the context as a place the action should
appear, but it's also very much a form of input the action can use.

It's also possible to pass a function which takes the set of parameters as input
and returns the context as output:

.. code-block:: python

    context=lambda params:
        [{}] if int(params['level']) < 3 else [{'worker-implementation': 'docker-worker'}],

Specifying an Input Schema
..........................

In all the examples so far the ``input`` argument for the callbacks has been
``None``. To make an action that takes input you must specify an input schema.
This is done by passing a JSON schema as the ``schema`` argument.

When designing a schema for the input it is important to exploit as many of the
JSON schema validation features as reasonably possible. Furthermore, it is
*strongly* encouraged that the ``title`` and ``description`` properties in JSON
schemas be used to provide a detailed explanation of what the input value will
do. Authors can reasonably expect JSON schema ``description`` properties to be
rendered as markdown before being presented (though this may not be guaranteed
for all interfaces).

The example below illustrates how to specify an input schema. Notice that while
this example doesn't specify a ``context`` it is perfectly legal to specify
both ``input`` and ``context``:

.. code-block:: python

   from taskgraph.actions.registry import register_callback_action

   @register_callback_action(
       name='run-missing',
       title='Run Missing Tasks',
       symbol='rm',  # Show the callback task in Treeherder as 'rm'
       description="Run tasks that have been optimized away.",
       order=1,
       input={
           'title': 'Action Options',
           'description': 'Options for how you wish to run missing tasks',
           'properties': {
               'priority': {
                   'title': 'priority'
                   'description': 'Priority that should be given to the tasks',
                   'type': 'string',
                   'enum': ['low', 'normal', 'high'],
                   'default': 'low',
               },
               'runAll': {
                   'title': 'Run Missing'
                   'description': 'When set also re-trigger tasks non-missing tasks',
                   'type': 'boolean',
                   'default': 'false',
               }
           },
           'required': ['priority', 'runAll'],
           'additionalProperties': False,
       },
   )
   def retrigger_action(parameters, graph_config, input, task_group_id, task_id, task):
       word = "all" if input["runAll"] else "missing"
       print(f"Run {word} tasks with priority '{input['priority']}'")
       # code to run tasks

The format of the schema follows the `json-schema specification`_.

When the ``schema`` argument is given the callback will always be called with
an ``input`` argument that satisfies the previously given JSON schema. It is
encouraged to set ``additionalProperties: false``, as well as specifying all
properties as ``required`` in the JSON schema. Furthermore, it's good practice
to provide ``default`` values for properties, as user interface generators will
often take advantage of such properties.

It is possible to specify the ``schema`` parameter as a callable that returns
the JSON schema. It will be called with a keyword parameter ``graph_config``
with the `graph configuration <taskgraph-graph-config>` of the current
taskgraph.

Once you have specified input and context as applicable for your action you can
do pretty much anything you want from within your callback. Whether you want
to create one or more tasks or run a specific piece of code like a test.

.. _json-schema specification: https://json-schema.org/

Conditional Availability
........................

The decision :class:`parameters <taskgraph.parameters.Parameters>` passed to
the callback are also available when the decision task generates the list of
actions to be displayed in the user interface. When registering an action
callback the ``availability`` option can be used to specify a callable
which, given the decision parameters, determines if the action should be available.
The feature is illustrated below:

.. code-block:: python

   from taskgraph.actions.registry import register_callback_action

   @register_callback_action(
       name='hello',
       title='Say Hello',
       symbol='hw',  # Show the callback task in treeherder as 'hw'
       description="Simple **proof-of-concept** callback action",
       order=2,
       # Define an action that is only included if this is a pull request.
       available=lambda params: params["tasks_for"] == "github-pull-request",
   )
   def try_only_action(parameters, graph_config, input, task_group_id, task_id, task):
       print "My try-only action"

See :doc:`/reference/parameters` for a reference on the available parameters.

Permissions
...........

Actions can be grouped together with a "permission" string. Scopes can then be
granted to use these actions in the `fxci-config repo`_. By default, actions
have the "generic" permission. Any actions with this default "generic" permission,
can be run in contexts where ``action:generic`` is granted in ``fxci-config``.

But if certain actions are more sensitive, or should be granted in *different* contexts
than the "generic" ones, you can pass in the ``permission`` argument to ``register_callback_action``:

.. code-block:: python

   from taskgraph.actions.registry import register_callback_action

   @register_callback_action(
       name='hello',
       title='Say Hello',
       symbol='hw',
       description="Simple **proof-of-concept** callback action",
       permission="sensitive"
   )
   def try_only_action(parameters, graph_config, input, task_group_id, task_id, task):
       pass

Now, this action can only be run in contexts where ``fxci-config`` grants
``action:sensitive``. Presumably in more restricted places than
``action:generic``.

.. _fxci-config repo: https://github.com/mozilla-releng/fxci-config

Creating Tasks
--------------

Actions often involve creating other tasks in some fashion.
The :func:`~taskgraph.create.create_tasks` utility function provides a full-featured way to create
new tasks. Its features include creating prerequisite tasks, operating in a
"testing" mode with ``./mach taskgraph test-action-callback``, and generating
artifacts that can be used by later action tasks to figure out what happened.
See the source for more detailed documentation.

The artifacts it can produce are:

``task-graph.json`` (or ``task-graph-<suffix>.json``:
  The graph of all tasks created by the action task. Includes tasks
  created to satisfy requirements.
``to-run.json`` (or ``to-run-<suffix>.json``:
  The set of tasks that the action task requested to build. This does not
  include the requirements.
``label-to-taskid.json`` (or ``label-to-taskid-<suffix>.json``:
  This is the mapping from label to ``taskid`` for all tasks involved in
  the task-graph. This includes dependencies.

Testing Actions
---------------

If you are working on an action task and wish to test it out locally, use the
``taskgraph test-action-callback`` command, e.g:

.. code-block:: bash

    taskgraph test-action-callback \
        --task-id I4gu9KDmSZWu3KHx6ba6tw --task-group-id sMO4ybV9Qb2tmcI1sDHClQ \
        --input input.yml hello_world_action

This invocation will run the hello world callback with the given inputs and
print any created tasks to stdout, rather than actually creating them.

Scopes and More Information
---------------------------

As with most things, triggering actions need to satisfy a scope expression. If
you are creating a new action and getting scope errors, or are getting scope
errors when trying to trigger one; talk to your Taskcluster administrator.

For further details on actions in general, see the `actions.json spec`_.

.. _actions.json spec: https://docs.taskcluster.net/docs/manual/design/conventions/actions/spec
.. _ci-admin: http://hg.mozilla.org/ci/ci-admin/
.. _ci-configuration: http://hg.mozilla.org/ci/ci-configuration/
