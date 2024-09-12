FROM $DOCKER_IMAGE_PARENT
LABEL maintainer="Release Engineering <release+taskgraph@mozilla.com>"

# Keep uv version in sync with python image
COPY --from=ghcr.io/astral-sh/uv:0.4.9 /uv /bin/uv

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
