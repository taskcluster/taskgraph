# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

FROM golang:1.27@sha256:2920bb124f1a2e12a1d39f0cab756ae0068441ee1da7655dec7f5e374944095b as skopeo

WORKDIR /go/src/
RUN ["/usr/bin/git", "clone", "--no-checkout", "--depth=1", "--branch=v1.1.0", "https://github.com/containers/skopeo", "."]
RUN ["/usr/bin/git", "checkout", "63085f5bef1131aa9ec0907a5c8d66b67de7c4b2"]
ENV GO111MODULE=on CGO_ENABLED=0
RUN ["/usr/local/go/bin/go", "build", \
    "-mod=vendor", "-o", "out/skopeo", \
    "-tags", "exclude_graphdriver_devicemapper exclude_graphdriver_btrfs containers_image_openpgp", \
    "-ldflags", "-extldflags \"-static\" -w -s", \
    "./cmd/skopeo"]


FROM golang:1.27@sha256:2920bb124f1a2e12a1d39f0cab756ae0068441ee1da7655dec7f5e374944095b as umoci

WORKDIR /go/src/
RUN ["/usr/bin/git", "clone", "--no-checkout", "--depth=1", "--branch=v0.4.6", "https://github.com/opencontainers/umoci", "."]
RUN ["/usr/bin/git", "checkout", "5efa06acfb3bb4e65d2711cf5255970948e047cf"]
ENV GO111MODULE=on CGO_ENABLED=0
RUN ["/usr/local/go/bin/go", "build", \
    "-mod=vendor", "-o", "out/umoci", \
    "-ldflags", "-extldflags \"-static\" -w -s", \
    "./cmd/umoci"]


FROM debian:13-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4
MAINTAINER Release Engineering <release@mozilla.com>

# %include-run-task

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq \
    && apt-get dist-upgrade -y \
    && apt-get install -y jq zstd python3-minimal curl \
    && apt-get clean

COPY push_image.sh /usr/local/bin/
COPY policy.json /etc/containers/policy.json
RUN chmod a+x /usr/local/bin/push_image.sh
COPY --from=skopeo /go/src/out/skopeo /usr/local/bin/
COPY --from=umoci /go/src/out/umoci /usr/local/bin/

# Add worker user
RUN mkdir /builds && \
    groupadd -g 1000 -o worker && \
    useradd -d /builds/worker -s /bin/bash -m worker -g 1000 -o -u 1000 && \
    mkdir /builds/worker/artifacts && \
    chown worker:worker /builds/worker/artifacts

USER worker
ENV SHELL=/bin/bash \
    HOME=/builds/worker \
    USER=worker

WORKDIR /builds/worker
# Set a default command useful for debugging
CMD ["/bin/bash", "--login"]
