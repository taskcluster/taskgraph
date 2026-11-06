FROM node:26-alpine@sha256:8996bb5821d62a8fd9bb27c1cb07462f3fdce6e47d640c6a881ead0b064ce216

ENV       NODE_ENV        production
RUN       mkdir /app
ADD       insert-indexes.js   /app/
ADD       package.json        /app/
ADD       yarn.lock           /app/
WORKDIR   /app
RUN       yarn --frozen-lockfile && yarn cache clean

ENTRYPOINT ["node"]
