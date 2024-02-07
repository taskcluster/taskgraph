#!/bin/sh
set -e -x

test $NAME
test $VERSION
test $DOCKER_REPO
test $MOZ_FETCHES_DIR
test $TASKCLUSTER_ROOT_URL
test $TASK_ID
test $VCS_HEAD_REPOSITORY
test $VCS_HEAD_REV

echo "=== Generating dockercfg ==="
PASSWORD_URL="http://taskcluster/secrets/v1/secret/project/taskgraph/level-3/dockerhub"
install -m 600 /dev/null $HOME/.dockercfg
curl $PASSWORD_URL | jq '.secret.dockercfg' > $HOME/.dockercfg

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
skopeo copy oci:${NAME}:final docker://$DOCKER_REPO:$DOCKER_TAG
skopeo inspect docker://$DOCKER_REPO:$DOCKER_TAG

echo "=== Clean up ==="
rm -rf $HOME/.docker
