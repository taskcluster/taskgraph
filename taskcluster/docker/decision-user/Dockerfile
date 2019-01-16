# %ARG DOCKER_IMAGE_PARENT
FROM $DOCKER_IMAGE_PARENT
MAINTAINER Tom Prince <mozilla@hocat.ca>

# %include requirements/base.in
# %include setup.py
# %include src
ADD topsrcdir /setup/
RUN pip install --no-deps /setup
RUN rm -rf /setup
