ARG DOCKER_IMAGE_PARENT
FROM $DOCKER_IMAGE_PARENT

RUN apt-get update && \
    apt-get install -y --force-yes --no-install-recommends \
    openjdk-17-jdk-headless \
    && \
    apt-get clean && \
    apt-get autoclean
