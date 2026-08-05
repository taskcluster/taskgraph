FROM node:24-alpine@sha256:d32cdf619f63fe0471182d08996dd516c6275bb5fd31ae06e55a570bd9e1ad43

ENV       NODE_ENV        production
RUN       mkdir /app
ADD       insert-indexes.js   /app/
ADD       package.json        /app/
ADD       yarn.lock           /app/
WORKDIR   /app
RUN       yarn --frozen-lockfile && yarn cache clean

ENTRYPOINT ["node"]
