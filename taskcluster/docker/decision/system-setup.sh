#!/usr/bin/env bash

set -v -e

test "$(whoami)" == 'root'

apt-get update
apt-get install -y --force-yes --no-install-recommends \
    ca-certificates \
    openssh-client \
    python \
    python-pip \
    python-setuptools \
    python-wheel \
    python3 \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    sudo \
    unzip \
    curl \
    git

BUILD=/root/build
mkdir "$BUILD"

tooltool_fetch() {
    cat >manifest.tt
    python2.7 /setup/tooltool.py fetch
    rm manifest.tt
}

cd $BUILD
# shellcheck disable=SC1091
. /setup/install-mercurial.sh

pip install -r /setup/requirements.txt
pip3 install -r /setup/requirements.py3.txt

cd /
rm -rf $BUILD
apt-get clean
apt-get autoclean
rm -rf /var/lib/apt/lists/
rm -rf /setup
