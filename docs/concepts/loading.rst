Loading Tasks
=============

Graph generation involves creating tasks for each kind. :doc:`kind` are ordered
to satisfy ``kind-dependencies``, and then the :term:`Loader` specified in
``kind.yml`` is used to obtain the initial set of tasks for that kind.

In short, loaders are responsible for turning the ``kind.yml`` file into an
initial set of tasks that can then be passed down into the :term:`transforms
<Transform>`.

What is a Loader?
-----------------

Loaders are Python functions with the following signature:

.. code-block:: python

   def loader(cls, kind, path, config, parameters, loaded_tasks):
       pass

``kind`` is the name of the kind.

``path`` is the path to the configuration directory for the kind. This
can be used to load extra data, templates, etc.

``config`` is a dict containing the contents of the ``kind.yml`` file.

``parameters`` give details on which to base the task generation. See
:doc:`/reference/parameters` for details.

``loaded_tasks`` contains all tasks that have already been loaded (which is
guaranteed to contain all kinds of tasks listed in the ``kind-dependencies``
key).

The return value is a list of inputs to the transforms listed in the kind's
``transforms`` property. The specific format for the input depends on the first
transform - whatever it expects.

Available Loaders
-----------------

Taskgraph provides two loaders, although in truth they are virtually identical:

The :mod:`Transform Loader<taskgraph.loader.transform>` is a barebones loader.

The :mod:`Default Loader<taskgraph.loader.default>` does everything that the
Transform Loader does, and additionally ensures that the
:mod:`Run <taskgraph.transforms.run>` and :mod:`Task<taskgraph.transforms.task>`
transforms are used on every task it loads.

Projects may optionally provide their own loaders that support different
behavior.
