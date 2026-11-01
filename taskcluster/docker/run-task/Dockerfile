FROM debian:13-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4
LABEL maintainer="Release Engineering <release+taskgraph-ci@mozilla.com>"

# Add worker user
RUN mkdir -p /builds && \
    useradd -d /builds/worker -s /bin/bash -m worker && \
    mkdir /builds/worker/artifacts && \
    chown worker:worker /builds/worker/artifacts

# %include-run-task

ADD system-setup.sh /setup/system-setup.sh
RUN bash /setup/system-setup.sh

ENV PATH=/builds/worker/bin:$PATH \
    SHELL=/bin/bash \
    HOME=/builds/worker

# %ARG UV_VERSION
COPY --from=ghcr.io/astral-sh/uv:$UV_VERSION /uv /bin/uv

# Set a default command useful for debugging
CMD ["/bin/bash", "--login"]
