#!/usr/bin/env bash

set -v -e

test "$(whoami)" == 'root'

apt-get update
apt-get install -y --force-yes --no-install-recommends \
    ca-certificates \
    openssh-client \
    python3 \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    sudo \
    unzip \
    curl \
    ucf \
    mercurial \
    git

apt-get clean
apt-get autoclean
rm -rf /var/lib/apt/lists/
rm -rf /setup
