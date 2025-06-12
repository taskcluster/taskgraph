FROM $DOCKER_IMAGE_PARENT
LABEL maintainer="Release Engineering <release+taskgraph@mozilla.com>"

# %include src
# %include packages
# %include README.rst
# %include pyproject.toml
# %include uv.lock
COPY topsrcdir/ /setup/taskgraph/

ADD system-setup.sh /setup/system-setup.sh
RUN bash /setup/system-setup.sh

# Set a default command useful for debugging
CMD ["/bin/bash", "--login"]
