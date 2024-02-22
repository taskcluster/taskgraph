#!/bin/env bash
set -e -x

test $NAME
test $VERSION
test $DOCKER_REPO
test $MOZ_FETCHES_DIR
test $TASKCLUSTER_ROOT_URL
test $TASK_ID
test $VCS_HEAD_REPOSITORY
test $VCS_HEAD_REV

function cleanup() {
    echo "=== Clean up ==="
    rm -rf $HOME/.docker
}
trap cleanup EXIT

echo "=== Generating dockercfg ==="
PASSWORD_URL="http://taskcluster/secrets/v1/secret/project/taskgraph/level-3/dockerhub"
install -m 600 /dev/null $HOME/.dockercfg
# Note: If there's a scoping error, this will not fail, causing the skopeo copy command to fail
curl $PASSWORD_URL | jq '.secret.dockercfg' > $HOME/.dockercfg

export REGISTRY_AUTH_FILE=$HOME/.dockercfg

cd $MOZ_FETCHES_DIR
unzstd image.tar.zst

echo "=== Inserting version.json into image ==="
# Create an OCI copy of image in order umoci can patch it
skopeo copy docker-archive:image.tar oci:${NAME}:final

cat > version.json <<EOF
{
    "commit": "${VCS_HEAD_REV}",
    "version": "${VERSION}",
    "source": "${VCS_HEAD_REPOSITORY}",
    "build": "${TASKCLUSTER_ROOT_URL}/tasks/${TASK_ID}"
}
EOF

umoci insert --image ${NAME}:final version.json /version.json

echo "=== Pushing to docker hub ==="
DOCKER_TAG="${NAME}-v${VERSION}"

# Get all remote tags | jq filter only starting with ${NAME}-v
REMOTE_TAGS=$(skopeo list-tags docker://$DOCKER_REPO | jq ".Tags[] | select(. | test(\"^${NAME}-v\\\\d\"))" -r)

# If remote tag already exists, bail out.
if [[ $REMOTE_TAGS =~ (^|[[:space:]])$DOCKER_TAG($|[[:space:]]) ]]; then
    echo "Docker tag '$DOCKER_REPO:$DOCKER_TAG' already exists, aborting!"
    exit 1
fi

skopeo copy oci:${NAME}:final docker://$DOCKER_REPO:$DOCKER_TAG
skopeo inspect docker://$DOCKER_REPO:$DOCKER_TAG

# Get latest remote tag | Sort by version | Get the last one
LATEST_REMOTE_VERSION=$(printf "$REMOTE_TAGS" | sort -V | tail -1)

# This bit is intentionally verbose so it's easier to track when we override the latest tag
if [ "${LATEST_REMOTE_VERSION}" = "" ]; then
    echo "Couldn't find a remote version. Tagging as latest."
    skopeo copy oci:${NAME}:final docker://$DOCKER_REPO:$NAME-latest
else
    # Printf the latest remote version and the current tag | Sort by version | Get the last one
    LATEST_VERSION=$(printf "$LATEST_REMOTE_VERSION\n$DOCKER_TAG" | sort -V | tail -1)
    # If current tag > latest remote, then we should tag as latest
    if [ "${LATEST_VERSION}" != "${LATEST_REMOTE_VERSION}" ]; then
        echo "Updating latest tag, the current version is higher than the remote."
        skopeo copy oci:${NAME}:final docker://$DOCKER_REPO:$NAME-latest
    else
        echo "Skipped tagging as current tag is not higher than the remote's latest."
    fi
fi
