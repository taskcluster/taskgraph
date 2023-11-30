#!/usr/bin/env bash

set -x
set -e

PIN_COMMAND='
set -e
pip install -q -U pip pip-compile-multi
pip-compile-multi -u \
    -g base -g test -g dev -g docs
'

PIN_PYTHON=3.8
docker run -t -v $PWD:/src -w /src python:$PIN_PYTHON bash -c "${PIN_COMMAND}"

set +x
echo "###########################################################"
echo "# Running tests on different python versions              #"
echo "# Pinned packages already saved. You may skip with CTRL+C #"
echo "###########################################################"
set -x

# Don't quit if a version fails
set +e
failed=0
for version in 3.8 3.9 3.10 3.11 3.12; do
    docker run -t -v $PWD:/src -w /src python:$version bash -c "pip install -q -r requirements/dev.txt"
    rt=$?
    if [ $rt -gt 0 ]; then
        failed=$rt
    fi
done

if [ $failed -gt 0 ]; then
    echo "Found errors testing different python versions, check the logs." 1>&2
fi
exit $failed
