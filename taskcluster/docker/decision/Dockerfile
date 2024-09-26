FROM $DOCKER_IMAGE_PARENT
LABEL maintainer="Release Engineering <release+taskgraph@mozilla.com>"

ENV UV_PROJECT_ENVIRONMENT=/setup/taskgraph

# %include src
# %include .hatch_build.py
# %include README.rst
# %include pyproject.toml
# %include uv.lock
COPY topsrcdir/ /setup/taskgraph/

ADD system-setup.sh /setup/system-setup.sh
RUN bash /setup/system-setup.sh

# Set a default command useful for debugging
CMD ["/bin/bash", "--login"]
