FROM ubuntu:18.04

# %include taskcluster/scripts/external_tools/tooltool.py
ADD topsrcdir/taskcluster/scripts/external_tools/tooltool.py /setup/tooltool.py

# %include taskcluster/docker/recipes/common.sh
ADD topsrcdir/taskcluster/docker/recipes/common.sh /setup/common.sh

# %include taskcluster/docker/recipes/install-mercurial.sh
ADD topsrcdir/taskcluster/docker/recipes/install-mercurial.sh /setup/install-mercurial.sh

# Can't use %include-run-task to bootstrap new versions
# %include src/taskgraph/run-task/run-task
# %include src/taskgraph/run-task/robustcheckout.py
# %include src/taskgraph/run-task/hgrc
COPY topsrcdir/src/taskgraph/run-task/run-task /usr/local/bin/run-task
COPY topsrcdir/src/taskgraph/run-task/robustcheckout.py /usr/local/mercurial/robustcheckout.py
COPY topsrcdir/src/taskgraph/run-task/hgrc /etc/mercurial/hgrc.d/mozilla.rc

# Add taskgraph package. (Limit package parts to avoid churn)
# %include setup.py
# %include src/taskgraph/__init__.py
# %include src/taskgraph/docker.py
# %include src/taskgraph/main.py
# %include src/taskgraph/task.py
# %include src/taskgraph/util/
# %include requirements/base.in
# %include requirements/base.txt
ADD topsrcdir /setup/src/

# Add and run setup script
ADD build-image.sh      /usr/local/bin/build-image.sh
ADD download-and-compress /usr/local/bin/download-and-compress
ADD setup.sh            /setup/setup.sh
RUN bash /setup/setup.sh


# Setup a workspace that won't use AUFS.
VOLUME /builds/worker/checkouts
VOLUME /builds/worker/workspace

# Set variable normally configured at login, by the shells parent process, these
# are taken from GNU su manual
ENV           HOME          /builds/worker
ENV           SHELL         /bin/bash
ENV           USER          worker
ENV           LOGNAME       worker
ENV           HOSTNAME      taskcluster-worker
ENV           LC_ALL        C

# Create worker user
RUN useradd -d /builds/worker -s /bin/bash -m worker

# Set some sane defaults
WORKDIR /builds/worker/
CMD     build-image.sh
