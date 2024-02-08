FROM debian:12-slim
MAINTAINER Release Engineering <release@mozilla.com>

### Add worker user and setup its workspace.
RUN mkdir /builds && \
    groupadd -g 1000 worker && \
    useradd -u 1000 -g 1000 -d /builds/worker -s /bin/bash -m worker && \
    mkdir -p /builds/worker/workspace && \
    chown -R worker:worker /builds

# Declare default working folder
WORKDIR /builds/worker

RUN apt-get update && \
    apt-get install -y \
      gnupg \
      bzip2 \
      git \
      openssh-client \
      python3-requests \
      python3-zstd \
      unzip

# %include src/taskgraph/run-task/run-task
ADD topsrcdir/src/taskgraph/run-task/run-task /usr/local/bin/run-task

# %include src/taskgraph/run-task/fetch-content
ADD topsrcdir/src/taskgraph/run-task/fetch-content /usr/local/bin/fetch-content
