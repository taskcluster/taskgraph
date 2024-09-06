#!/usr/bin/env bash

set -v -e

test "$(whoami)" == 'root'

apt-get update
apt-get install -y --force-yes --no-install-recommends \
    python3-pip

pushd /setup/taskgraph
uv export --no-dev > /setup/requirements.txt
uv pip install --system --break-system-packages -r /setup/requirements.txt
popd

apt-get clean
apt-get autoclean
rm -rf /var/lib/apt/lists/
rm -rf /setup
