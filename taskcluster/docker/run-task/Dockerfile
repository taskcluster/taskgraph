FROM debian:13-slim@sha256:28de0877c2189802884ccd20f15ee41c203573bd87bb6b883f5f46362d24c5c2
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

# dummy

# Set a default command useful for debugging
CMD ["/bin/bash", "--login"]
