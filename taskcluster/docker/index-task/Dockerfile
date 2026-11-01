FROM node:24-alpine@sha256:8a32c8cf649a49915a66e81e7a609223c708d0adabf288ee3f4077d765542f85

ENV       NODE_ENV        production
RUN       mkdir /app
ADD       insert-indexes.js   /app/
ADD       package.json        /app/
ADD       yarn.lock           /app/
WORKDIR   /app
RUN       yarn --frozen-lockfile && yarn cache clean

ENTRYPOINT ["node"]
