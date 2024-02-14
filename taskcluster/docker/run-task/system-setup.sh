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

apt-get clean
apt-get autoclean
rm -rf /var/lib/apt/lists/
rm -rf /setup
