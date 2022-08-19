FROM python:3.10-slim-bullseye

LABEL org.label-schema.vendor="ScaleVector" \
    org.label-schema.url="https://scalevector.ai" \
    org.label-schema.name="Axie Infinity DLT Demo" \
    org.label-schema.description="DLT Pipeline Script to get Axie Infinity smart contracts data on Ronin Network into BigQuery/Redshift"


RUN mkdir -p /src/app

WORKDIR /src/app

# add build labels and envs to be logged
ARG COMMIT_SHA=""
ARG IMAGE_VERSION=""
LABEL commit_sha = ${COMMIT_SHA}
LABEL version=${IMAGE_VERSION}
ENV COMMIT_SHA=${COMMIT_SHA}
ENV IMAGE_VERSION=${IMAGE_VERSION}

