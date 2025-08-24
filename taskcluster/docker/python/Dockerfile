# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

FROM debian:bookworm-slim
LABEL maintainer="Release Engineering <release@mozilla.com>"

VOLUME /builds/worker/checkouts
VOLUME /builds/worker/.task-cache/uv

# Add worker user
RUN mkdir -p /builds && \
    useradd -d /builds/worker -s /bin/bash -m worker && \
    mkdir /builds/worker/artifacts && \
    chown -R worker:worker /builds/worker

# %include-run-task

RUN apt-get update \
 && apt-get install -y --reinstall ca-certificates \
 && apt-get install -y --force-yes --no-install-recommends \
    build-essential \
    mercurial \
    git


ENV SHELL=/bin/bash \
    HOME=/builds/worker \
    PATH=/builds/worker/.local/bin:$PATH

# %ARG UV_VERSION
COPY --from=ghcr.io/astral-sh/uv:$UV_VERSION /uv /bin/uv
# %ARG PYTHON_VERSIONS
RUN uv python install $PYTHON_VERSIONS

# Set a default command useful for debugging
CMD ["/bin/bash", "--login"]
