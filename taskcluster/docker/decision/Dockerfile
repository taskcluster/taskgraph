FROM $DOCKER_IMAGE_PARENT
LABEL maintainer="Release Engineering <release+taskgraph-ci@mozilla.com>"

# %include src/taskgraph
ADD topsrcdir/src/taskgraph /setup/taskgraph/src/taskgraph
# %include setup.py
ADD topsrcdir/setup.py /setup/taskgraph/setup.py
# %include README.rst
ADD topsrcdir/README.rst /setup/taskgraph/README.rst
# %include requirements/base.in
ADD topsrcdir/requirements/base.in /setup/taskgraph/requirements/base.in
# %include requirements/base.txt
ADD topsrcdir/requirements/base.txt /setup/requirements.txt

ADD system-setup.sh /setup/system-setup.sh
RUN bash /setup/system-setup.sh

# Set a default command useful for debugging
CMD ["/bin/bash", "--login"]
