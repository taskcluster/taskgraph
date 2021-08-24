FROM          ubuntu:18.04
MAINTAINER Tom Prince <mozilla@hocat.ca>

# Add worker user
RUN mkdir /builds && \
    useradd -d /builds/worker -s /bin/bash -m worker && \
    mkdir /builds/worker/artifacts && \
    chown worker:worker /builds/worker/artifacts

# %include-run-task

# %include taskcluster/scripts/external_tools/tooltool.py
ADD topsrcdir/taskcluster/scripts/external_tools/tooltool.py /setup/tooltool.py

# %include taskcluster/docker/recipes/install-mercurial.sh
ADD topsrcdir/taskcluster/docker/recipes/install-mercurial.sh /setup/install-mercurial.sh

# Add taskgraph package.
# %include requirements/base.py3.txt
ADD topsrcdir/requirements/base.py3.txt /setup/requirements.py3.txt

ADD system-setup.sh /setup/system-setup.sh
RUN bash /setup/system-setup.sh

ENV PATH=/builds/worker/bin:$PATH \
    SHELL=/bin/bash \
    HOME=/builds/worker

# Set a default command useful for debugging
CMD ["/bin/bash", "--login"]
