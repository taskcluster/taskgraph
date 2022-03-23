Debug Taskgraph
===============

There are several approaches you could take when you need to debug changes
in Taskgraph.

Print Debugging
---------------

It's possible to add print statements to transforms which will show up in the
log. Just beware that because transforms tend to loop over every task, it can
be difficult to tell which output was generated from the task(s) you're trying
to debug.

Here's an example pattern you can use to limit debug output:

.. code-block:: python

   @transforms.add
   def some_transform(config, tasks):
       for task in tasks:
           def debug(msg):
               # Note "name" is not a standard field, use whatever field
               # is appropriate here.
               if task["name"] == "my-task":
                   print(msg, file=sys.stderr)

           # Will only be printed when "my-task" is being processed.
           debug("FOO")

pdb
---

It's also possible to use the built-in Python debugger, `pdb`_. Simply add
calls to ``pdb.set_trace()`` and run the ``taskgraph`` binary as normal. Note
that as with print debugging, you'll want to ensure that breakpoints are only
triggered on the tasks you are aiming to debug:

.. code-block:: python

   @transforms.add
   def some_transform(config, tasks):
       import pdb
       for task in tasks:
           # Note "name" is not a standard field, use whatever field
           # is appropriate here.
           if task["name"] == "my-task":
               pdb.set_trace()

.. _pdb: https://docs.python.org/3/library/pdb.html

debugpy
-------

`Debugpy`_ is the Python debugger that comes bundled with VSCode. But it can be
used with other editors as well, such as Neovim via the `nvim-dap-python`_
plugin. The advantage of ``debugpy`` is that you can set breakpoints directly
via your editor (so you don't need to edit your source). You can trigger new
runs from within your editor as well.

How to setup ``debugpy`` varies editor by editor and is out of scope for these
docs. But typically there will be a way of defining a "launch config". For
``taskgraph`` it should look similar to:

.. code-block::

  {
      "name": "Taskgraph Full",
      "type": "python",
      "request": "launch",
      "program": "/path/to/bin/taskgraph",
      "args": ["full"],
      "console": "integratedTerminal",
      "justMyCode": false
  }

Make sure to adjust "program" to point to your ``taskgraph`` binary. Also
be sure to tweak args as you see fit. See :ref:`useful arguments` for more
information on available arguments.

.. _debugpy: https://github.com/microsoft/debugpy
.. _nvim-dap-python: https://github.com/mfussenegger/nvim-dap-python
