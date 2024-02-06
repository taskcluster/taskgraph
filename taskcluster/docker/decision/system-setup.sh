#!/usr/bin/env bash

set -v -e

test "$(whoami)" == 'root'

apt-get update
apt-get install -y --force-yes --no-install-recommends \
    ca-certificates \
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

# mercurial setup
CERT_PATH=/etc/ssl/certs/ca-certificates.crt
cat >/etc/mercurial/hgrc.d/cacerts.rc <<EOF
[web]
cacerts = ${CERT_PATH}
EOF
chmod 644 /etc/mercurial/hgrc.d/cacerts.rc

# Clone the repo in the decision image
python3 -mpip install --break-system-packages -r /setup/requirements.txt
python3 -mpip install --break-system-packages --no-deps /setup/taskgraph

# Same files as include-run-task
cp /setup/taskgraph/src/taskgraph/run-task/run-task /usr/local/bin/run-task
chmod 744 /usr/local/bin/run-task
cp /setup/taskgraph/src/taskgraph/run-task/fetch-content /usr/local/bin/fetch-content
chmod 744 /usr/local/bin/fetch-content
cp /setup/taskgraph/src/taskgraph/run-task/hgrc /etc/mercurial/hgrc.d/mozilla.rc
chmod 644 /etc/mercurial/hgrc.d/mozilla.rc
cp /setup/taskgraph/src/taskgraph/run-task/robustcheckout.py /opt/robustcheckout.py
chmod 644 /opt/robustcheckout.py

apt-get clean
apt-get autoclean
rm -rf /var/lib/apt/lists/
rm -rf /setup
