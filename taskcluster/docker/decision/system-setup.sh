#!/usr/bin/env bash

set -v -e

test "$(whoami)" == 'root'

apt-get update
apt-get install -y --force-yes --no-install-recommends \
    python3-pip \
    python3-setuptools \
    python3-wheel \

python3 -mpip install --break-system-packages -r /setup/requirements.txt
python3 -mpip install --break-system-packages --no-deps /setup/taskgraph

apt-get clean
apt-get autoclean
rm -rf /var/lib/apt/lists/
rm -rf /setup
