ARG DOCKER_IMAGE_PARENT
FROM $DOCKER_IMAGE_PARENT

RUN apt-get update
RUN apt-get install -y --force-yes --no-install-recommends \
    # We need java 8 for sdkmanager
    openjdk-8-jdk-headless \
    openjdk-11-jdk-headless
RUN apt-get clean
RUN apt-get autoclean
