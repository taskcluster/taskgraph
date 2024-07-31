#!/usr/bin/env bash

script_dir=$(dirname "$(realpath "$0")")
if ! command -v uv &> /dev/null; then
    cat <<EOF
uv not found!

See the installation instructions:
https://github.com/astral-sh/uv?tab=readme-ov-file#getting-started
EOF
    exit 1
fi

min_python_version="3.8"

pushd $script_dir

for requirement_in in *.in; do
    uv pip compile "$requirement_in" --python-version $min_python_version --universal --generate-hashes --output-file "${requirement_in%.*}.txt"
done

popd
