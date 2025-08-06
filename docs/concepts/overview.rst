What is Taskgraph?
==================

Taskgraph is a binary that reads configuration files, and applies logic to them
in order to generate and schedule tasks for the `Taskcluster`_ task execution
framework.

A common misconception is that Taskgraph is part of Taskcluster, and the names
are sometimes mistakenly used interchangeably. But Taskgraph and Taskcluster are two
very different pieces of software, performing different roles. If Taskcluster
is the chef in the kitchen preparing all the meals, then Taskgraph is the person
who designed the recipes and organized them into a menu.

But to really understand how Taskgraph and Taskcluster relate to one another, it's
important to understand a bit more about Taskcluster.

.. _Taskcluster: https://taskcluster.net/

What is Taskcluster?
--------------------

Taskcluster at its core, is a collection of microservices that each provide a
series of powerful APIs for the purposes of executing tasks. Some of these
microservices include the `queue service`_ which provides a mechanism to place
tasks on a queue, as well as claim tasks off of it. There's an `auth
service`_ which validates credentials. There's a `hooks service`_ to provide
integration points (both internal and external). And there's the
`worker-manager service`_ which interfaces with various cloud providers to spin
up VM instances (which can then claim work off the queue).

It may be tempting to call Taskcluster a CI system, as that's what it's
primarily used for. But it would be more accurate to say that Taskcluster is a
set of building blocks, which you can assemble into anything that fits the mold
of a queue of work items and workers that execute them. This could be a bespoke
CI system designed specifically for your use case. But you could also assemble
it into an AI training pipeline, or a web crawler or a distributed
parallelization framework. You get the idea.

.. _queue service: https://docs.taskcluster.net/docs/reference/platform/queue
.. _auth service: https://docs.taskcluster.net/docs/reference/platform/auth
.. _hooks service: https://docs.taskcluster.net/docs/reference/core/hooks
.. _worker-manager service: https://docs.taskcluster.net/docs/reference/core/worker-manager

How to Create Tasks
-------------------

All these microservices come together in a powerful way, but as a user you
might be wondering something. How do you create tasks in the first place?

I hinted that the queue service allows you to push tasks onto a queue, and
indeed there's a `createTask`_ API which accomplishes this. There's also a
`Github service`_ which can read a ``.taskcluster.yml`` file from the root of a
Github repository, render it with context from a Github event, and implicitly
create tasks on your behalf (much like how the ``.github/workflows`` directory
works for Github actions).

But both these methods still require you to define your tasks somehow. You need
to specify where your task runs, what it should do, which environment variables
should be set, etc. For simple projects with only a handful of tasks, it might
be feasible to simply write out the entire task definition inside your
``createTask`` API calls, or the ``.taskcluster.yml`` file at the root of your
repo.

But for more complicated projects, it's not hard to imagine how quickly
hardcoding all your task definitions will turn into a maintenance nightmare!
Consider that as of this writing the Firefox project has ~40k tasks defined,
stuffing all that into a single yaml file would not be a fun time for anyone.

.. _Github service: https://docs.taskcluster.net/docs/reference/integrations/github
.. _createTask: https://docs.taskcluster.net/docs/reference/platform/queue/api#createTask

Taskgraph to the Rescue
-----------------------

This finally brings us back to Taskgraph. There are still input yaml files, but
instead of one there can be as many as you like. Then you can layer on
programmatic logic on top of these inputs to "transform" them into actual task
definitions. This logic can be as simple or complex as you need. It can layer
in powerful features, query external services or even duplicate a single task
into many.

What was previously a large block of hardcoded yaml, can be turned into some
concise yaml files along with a few well written transform functions. When you
invoke the ``taskgraph`` binary, these inputs and transforms combine to create
valid task definitions that conform to Taskcluster's `task schema`_.

.. note::

   It's worth noting that the `task schema`_ acts as an interface boundary
   between Taskgraph and Taskcluster. It's not necessary to use Taskgraph if
   you don't want to, you could instead write your own tool that generates
   valid task definitions.

   Conversely while Taskgraph generates definitions that are compatible with
   Taskcluster, in theory it could generate tasks that conform to any other
   task execution framework, such as `Gitlab Pipelines`_.

.. _task schema: https://docs.taskcluster.net/docs/reference/platform/queue/task-schema
.. _Gitlab Pipelines: https://docs.gitlab.com/ci/pipelines/

What is the Relationship Between Taskgraph and Taskcluster?
-----------------------------------------------------------

In the end, Taskgraph is a consumer of Taskcluster. It uses the ``createTask``
API to place tasks on the queue, just like the Github service does, or maybe
you'd be doing in a script if you weren't using either the Github service or
Taskgraph.

Assuming you have the proper credentials, you could invoke ``taskgraph`` from
your terminal and this would cause all the generated tasks to run! But that's
not very convenient from a CI perspective, so instead you can invoke
``taskgraph`` from inside a task itself using the Github service.

Remember that ``.taskcluster.yml`` file where you can hardcode task definitions
and how trying to define lots of tasks in there becomes a maintenance
nightmare? Well defining a single task isn't *too* bad. By `convention`_, we
call this single task a *Decision Task* and it's responsible for invoking the
Taskgraph binary.

When you put all of this together, here are the full steps from making a push
to a Github repo, to running tasks:

#. You push a commit to your Github repo.
#. Github emits a webhook event for your push, containing the event context.
#. Taskcluster's Github service receives this event and uses it to render the
   ``.taskcluster.yml`` file at the root of your repo. If you aren't using
   Taskgraph and just have a couple tasks defined in this file, they'd get
   created and you'd be done. But if you're using Taskgraph because you have
   more complex CI needs, rendering this file will result in a single task
   called the *Decision Task*.
#. Inside this *Decision Task*, Taskgraph reads a bunch of input yaml files and
   applies transform logic to them, ultimately resulting in valid Taskcluster
   task definitions.
#. Taskgraph calls the ``createTask`` API to place them on the queue, and you're
   golden!

Hopefully you now have a slightly better understanding of what exactly Taskgraph
and Taskcluster are, and of the differences between them.

.. _convention: https://docs.taskcluster.net/docs/manual/design/conventions/decision-task
