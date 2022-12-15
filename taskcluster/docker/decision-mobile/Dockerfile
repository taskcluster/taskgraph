ARG DOCKER_IMAGE_PARENT
FROM $DOCKER_IMAGE_PARENT

RUN apt-get update && \
    apt-get install -y --force-yes --no-install-recommends \
    # We need java 8 for sdkmanager
    openjdk-8-jdk-headless \
    openjdk-11-jdk-headless \
    && \
    apt-get clean && \
    apt-get autoclean
