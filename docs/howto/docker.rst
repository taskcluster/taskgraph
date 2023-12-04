Use Docker Images
=================

Containerization is a key component of any CI system. Taskcluster provides a
built-in worker implementation called `docker-worker`_ which makes running
tasks with docker easy!

.. note::

   Taskcluster's generic-worker implementation can also run docker images and
   will eventually replace the older docker-worker. But for now docker-worker
   provides a better experience with docker.

The `docker-worker payload`_ supports specifying images as a string (to be
pulled from DockerHub), an index to an image built by another task, or the name
of an image built in-project. Let's take a look at how each one works.

.. _docker-worker: https://docs.taskcluster.net/docs/reference/workers/docker-worker
.. _docker-worker payload: https://docs.taskcluster.net/docs/reference/workers/docker-worker/payload

Using Images from a Registry
----------------------------

As one might expect, tasks using ``docker-worker`` can specify an image on
DockerHub like so:

.. code-block:: yaml

   my-task:
     worker:
        docker-image: "ubuntu:latest"

This method is easy and convenient, but has a few drawbacks. Namely if you need
a custom image, you'll have to maintain a separate release process for it that
involves versioning and pushing to DockerHub.

.. note::

    When pulling images from a registry it's *highly* recommended to pin the image to a
    hash for security and reproducibility reasons:

    .. parsed-literal::

        my-task:
          worker:
            docker-image: "ubuntu@sha256:cd3d86f1fb368c6a53659d467560010ab9e0695528127ea336fe32f68f7ba09f"

    The sha256 of the image can be found in the image's digest on DockerHub or
    locally via the "Id" field in ``docker inspect <image name>``.

Using Images from an Index
--------------------------

Alternatively, you can build images in a task (even outside of your project)
and upload the image as an artifact. Then tasks can reference this "image builder"
task by an index like so:

.. code-block:: yaml

   my-task:
     worker:
       docker-image:
         indexed: "myproject.cache.level-3.docker.v2.custom.latest"

This will automatically download and use the ``public/image.tar.zst`` artifact
from the task pointed to by the specified index.

Using In-Project Images
-----------------------

The last method of using docker images is to build the image using a task within
the project. This has some very powerful benefits:

1. Images are in the same repository, so they can be modified in the same commit
   as the code that depends on those modifications.
2. Images are built once and then cached until modified, reducing latency.
3. No need to worry about versioning or publishing (e.g to DockerHub or an index).
4. No reliance on an external service (e.g DockerHub).
5. Changes to images can easily be rolled back.

For these reasons, using in-project images is the recommended way to go if you
need custom images (and sometimes even if you don't).

The task definition is just as simple as the other two methods:

.. code-block:: yaml

   my-task:
     worker:
       docker-image:
         in-tree: "custom"

This tells your task to use the in-project image called "custom".

Creating In-Project Docker Images
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Taskcluster docker images are defined in the source directory under
``taskcluster/docker``. Each directory therein contains the name of an
image used as part of the task graph. So in the example above, we'd create
a ``taskcluster/docker/custom/Dockerfile`` in the repository.

This ``Dockerfile`` mostly follows the standard `Dockerfile specification`_.
For example, it may look like:

.. code-block::

    FROM debian:11

    ### Add worker user and setup its workspace.
    RUN mkdir /builds && \
        groupadd -g 1000 worker && \
        useradd -u 1000 -g 1000 -d /builds/worker -s /bin/bash -m worker && \
        mkdir -p /builds/worker/workspace && \
        chown -R worker:worker /builds

    # Declare default working folder
    WORKDIR /builds/worker

    RUN apt-get update && \
        apt-get install -y \
          gnupg \
          bzip2 \
          git \
          openssh-client \
          python3-requests \
          python3-zstd \
          unzip

    # %include src/taskgraph/run-task/run-task
    ADD topsrcdir/src/taskgraph/run-task/run-task /usr/local/bin/run-task

    # %include src/taskgraph/run-task/fetch-content
    ADD topsrcdir/src/taskgraph/run-task/fetch-content /usr/local/bin/fetch-content

The astute observer may notice the bizarre ``# %include`` comments towards the
bottom. Taskgraph Dockerfiles support an optional extended syntax which adds
some convenient features!

.. _Dockerfile specification: https://docs.docker.com/engine/reference/builder/

Special Dockerfile Syntax
.........................

Dockerfile syntax has been extended to allow *any* file from the
source checkout to be added to the image build *context*. (Traditionally
you can only ``ADD`` files from the same directory as the Dockerfile.)

Simply add the following syntax as a comment in a Dockerfile::

   # %include <path>

e.g.

.. code-block::

   # %include config.json
   ADD topsrcdir/config.json /config/config.json

   # %include data/manifests
   ADD topsrcdir/data/manifests /data/manifests

The argument to ``# %include`` is a relative path from the root level of
the source directory. It can be a file or a directory. If a file, only that
file will be added. If a directory, every file under that directory will be
added (even files that are untracked or ignored by version control).

Files added using ``# %include`` syntax are available inside the build
context under the ``topsrcdir/`` path.

Files are added as they exist on disk. e.g. executable flags should be
preserved. However, the file owner/group is changed to ``root`` and the
``mtime`` of the file is normalized.

Adding Image Builder Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~

Once the ``Dockerfile`` is created, a task will need to be added that builds
and uploads the image as an artifact. Luckily Taskgraph comes with the
transforms necessary to set these up, so all that's needed is adding a
barebones ``kind.yml`` file. For example, assuming you want to name your kind
``docker-image``, you'd create a ``taskcluster/kinds/docker-image/kind.yml`` file
with the following contents:

.. code-block:: yaml

   loader: taskgraph.loader.transform:loader

   transforms:
       - taskgraph.transforms.docker_image:transforms
       - taskgraph.transforms.cached_tasks:transforms
       - taskgraph.transforms.task:transforms

   tasks:
       custom:
           symbol: I(custom-image)

And that's it! The :mod:`~taskgraph.transforms.docker_image` transforms will
process the ``Dockerfile`` and handle the special syntax. Whereas the
:mod:`~taskgraph.transforms.cached_tasks` transforms will ensure the image is
only generated once and then re-used by all subsequent pushes until the image
is modified.

Context Directory Hashing
~~~~~~~~~~~~~~~~~~~~~~~~~

To determine whether an in-project image needs to be rebuilt or not, Decision
tasks will calculate the sha256 hash of the contents of the image directory and
will determine if the image already exists for the current context or if a new
image must be built and indexed.

The decision task will:

1. Recursively collect the paths of all files within the context directory
2. Sort the filenames alphabetically to ensure the hash is consistently calculated
3. Generate a sha256 hash of the contents of each file
4. All file hashes will then be combined with their path and used to update the
   hash of the context directory

This ensures that the hash is consistently calculated and path changes will result
in different hashes being generated.

Task Image Index Namespace
~~~~~~~~~~~~~~~~~~~~~~~~~~

Images that are built on push and uploaded as an artifact of a task will be indexed under the
following namespaces.

.. parsed-literal::

   {project}.cache.level-{level}.docker.v2.{name}.hash.{digest}
   {project}.cache.level-{level}.docker.v2.{name}.latest
   {project}.cache.level-{level}.docker.v2.{name}.pushdate.{year}.{month}-{day}-{pushtime}

Not only can images be browsed by the pushdate and context hash, but the 'latest' namespace
is meant to view the latest built image. This functions similarly to the 'latest' tag
for docker images that are pushed to a registry. Tasks can use these images as specified in
`Using Images from an Index`_ above.

Working with Images Locally
---------------------------

Taskgraph provides some command line utilities to facilitate working with images locally.
These are:

* ``taskgraph build-image <name>`` - Builds an in-project image locally.
* ``taskgraph load-image --task-id <task-id>`` - Loads an image built by the
  specified task locally.
* ``taskgraph image-digest <name>`` - Prints the digest of the specified image.

See the :doc:`/reference/cli` reference for more details.
