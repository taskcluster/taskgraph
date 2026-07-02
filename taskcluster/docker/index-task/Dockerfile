FROM node:24-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd

ENV       NODE_ENV        production
RUN       mkdir /app
ADD       insert-indexes.js   /app/
ADD       package.json        /app/
ADD       yarn.lock           /app/
WORKDIR   /app
RUN       yarn --frozen-lockfile && yarn cache clean

ENTRYPOINT ["node"]
