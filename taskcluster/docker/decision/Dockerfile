FROM debian:12-slim
MAINTAINER Release Engineering <release@mozilla.com>

# Add worker user
RUN mkdir /builds && \
    useradd -d /builds/worker -s /bin/bash -m worker && \
    mkdir /builds/worker/artifacts && \
    chown worker:worker /builds/worker/artifacts

# %include src/taskgraph
ADD topsrcdir/src/taskgraph /setup/taskgraph/src/taskgraph
# %include setup.py
ADD topsrcdir/setup.py /setup/taskgraph/setup.py
# %include requirements/base.in
ADD topsrcdir/requirements/base.in /setup/taskgraph/requirements/base.in
# %include requirements/base.txt
ADD topsrcdir/requirements/base.txt /setup/requirements.txt

ADD system-setup.sh /setup/system-setup.sh
RUN bash /setup/system-setup.sh

ENV PATH=/builds/worker/bin:$PATH \
    SHELL=/bin/bash \
    HOME=/builds/worker

# Set a default command useful for debugging
CMD ["/bin/bash", "--login"]
