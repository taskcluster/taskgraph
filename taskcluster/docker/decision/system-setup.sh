#!/usr/bin/env bash

set -v -e

test "$(whoami)" == 'root'

# Python 2 is still needed for mercurial 5.3.1
apt-get update
apt-get install -y --force-yes --no-install-recommends \
    ca-certificates \
    openssh-client \
    python \
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

BUILD=/root/build
mkdir "$BUILD"

tooltool_fetch() {
    cat >manifest.tt
    python3 /setup/tooltool.py fetch
    rm manifest.tt
}

cd $BUILD

# mercurial setup
CERT_PATH=/etc/ssl/certs/ca-certificates.crt
cat >/etc/mercurial/hgrc.d/cacerts.rc <<EOF
[web]
cacerts = ${CERT_PATH}
EOF
chmod 644 /etc/mercurial/hgrc.d/cacerts.rc
chmod 644 /usr/local/mercurial/robustcheckout.py

# Using pip3 directly results in a warning that a "very old" wrapper is being
# used, and that support for this will be deprecated.
python3 -mpip install --upgrade pip~=21.1.3
python3 -mpip install -r /setup/requirements.txt

cd /
rm -rf $BUILD
apt-get clean
apt-get autoclean
rm -rf /var/lib/apt/lists/
rm -rf /setup
