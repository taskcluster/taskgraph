# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

FROM $DOCKER_IMAGE_PARENT
LABEL maintainer="Release Engineering <release@mozilla.com>"

VOLUME /builds/worker/checkouts
VOLUME /builds/worker/.task-cache/uv

RUN apt-get update \
 && apt-get install -y --force-yes --no-install-recommends \
    build-essential

ENV PATH=/builds/worker/.local/bin:$PATH

# %ARG PYTHON_VERSIONS
RUN uv python install $PYTHON_VERSIONS
