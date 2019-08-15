# %ARG DOCKER_IMAGE_PARENT
FROM $DOCKER_IMAGE_PARENT

RUN apt-get update
RUN apt-get install -y --force-yes --no-install-recommends \
    openjdk-8-jdk-headless
RUN apt-get clean
RUN apt-get autoclean
