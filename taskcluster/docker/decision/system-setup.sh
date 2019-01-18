#!/usr/bin/env bash

set -v -e

test "$(whoami)" == 'root'

apt-get update
apt-get install -y --force-yes --no-install-recommends \
    ca-certificates \
    python \
    python3 \
    python-pip \
    python-setuptools \
    python-wheel \
    sudo

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

cd /
rm -rf $BUILD
apt-get clean
apt-get autoclean
rm -rf /var/lib/apt/lists/
rm -rf /setup
