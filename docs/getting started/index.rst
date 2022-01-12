Getting Started
===============

Taskgraph is a Python library to generate graphs of tasks for the `Taskcluster CI <https://taskcluster.net/>`_ service. It is
the recommended approach for configuring your tasks once your project outgrows a single `.taskcluster.yml` file.

If you're new to Taskgraph its recommended to start with the :ref:`intro-to-taskgraph` section. If you understand the basics
and want to use it in a project, you can jump to the :ref:`using-taskgraph` section.

Common tasks pertaining to contributing to Taskgraph can be found below.

Installation
------------

Taskgraph supports Python 3.6 and up, and can be installed from Pypi:

```
$ pip install taskcluster-taskgraph
```

Alternatively, the repo can be cloned and installed directly:

```
$ hg clone https://hg.mozilla.org/ci/taskgraph
$ cd taskgraph
$ python setup.py install
```

In both cases, it's recommended to use a Python [virtual environment][2]. Refer to the
[usage docs][3] for tips on how to get started with Taskgraph.

[2]: https://docs.python.org/3/tutorial/venv.html
[3]: https://taskcluster-taskgraph.readthedocs.io/en/latest/usage/using_taskgraph.html

.. _working-on-taskgraph:

Working on Taskgraph
--------------------

To contribute to Taskgraph or use the debugging tools, you'll need to clone the repository, activate a virtualenv and install
dependencies:

```
$ hg clone https://hg.mozilla.org/ci/taskgraph
$ cd taskgraph
# Feel free to use whatever virtualenv management tool you are comfortable with here.
$ python -m venv taskgraph && source taskgraph/bin/activate
$ pip install -r requirements/dev.txt
$ python setup.py develop
```

Running Tests and Linters
-------------------------

Tests are run with the [pytest][4] framework:

```
$ pytest src
```

We also enforce the [black][5] formatter and [flake8][6] linter in Taskgraph's CI:

```
# run black
$ black .

# run flake8
$ flake8
```

[4]: https://docs.pytest.org
[5]: https://black.readthedocs.io
[6]: https://flake8.pycqa.org/en/latest/


Managing Dependencies
---------------------

WARNING: Ensure you always update packages using the minimum supported Python. Otherwise you may
break the workflow of people trying to develop Taskgraph with an older version of Python. The
[pyenv][7] tool can help with managing multiple Python versions at once.

To help lock dependencies, Taskgraph uses a tool called [pip-compile-multi][8]. To add or update a
dependency first edit the relevant `.in` file under the `requirements` directory. If the dependency
is needed by the actual Taskgraph library, edit `requirements/base.in`. If it's required by the CI
system, edit `requirements/test.in`. And if it's only needed for developing Taskgraph, edit
`requirements/dev.in`.

Next run the following command from the repository root:

```
$ pip-compile-multi -g base -g test -g dev --allow-unsafe -P <package>
```

Where `<package>` is the name of the package you added or updated. Note the `-P` flag can be passed
multiple times if multiple dependencies were changed.

[7]: https://github.com/pyenv/pyenv
[8]: https://pip-compile-multi.readthedocs.io/en/latest/


Working with Documentation
--------------------------

The Taskgraph repo uses [Sphinx][9] to generate the documentation. To work on the docs, run:

```
$ make livehtml
```

This will start a live server that automatically re-generates when you edit a documentation file.
Alternatively you can generate static docs under the `docs/_build` directory:

```
$ make html
```

Taskgraph also uses the `autodoc` extension to generate an API reference. When new modules are
created, the API docs need to be regenerated using the following command:

```
$ sphinx-apidoc -o docs/source --ext-autodoc -H "API Reference" src/taskgraph "src/taskgraph/test"
```

[9]: https://www.sphinx-doc.org

