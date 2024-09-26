FROM $DOCKER_IMAGE_PARENT
LABEL maintainer="Release Engineering <release+taskgraph@mozilla.com>"

# %ARG UV_VERSION
COPY --from=ghcr.io/astral-sh/uv:$UV_VERSION /uv /bin/uv

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
