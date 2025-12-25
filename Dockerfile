# syntax = docker/dockerfile:1

FROM --platform=$BUILDPLATFORM python:3.12 AS python-build

COPY . /app/

# See https://github.com/rust-lang/cargo/issues/8719#issuecomment-1207488994
RUN --mount=type=tmpfs,target=/root/.cargo \
    apt-get update && \
    apt-get install -y gettext librsync-dev rustc cargo && \
    pip install poetry==2.2.1 && \
    cd /app && \
    poetry install && \
    poetry build

FROM alpine:3.22

# See https://github.com/rust-lang/cargo/issues/8719#issuecomment-1207488994
RUN --mount=from=python-build,source=/app/,target=/mnt --mount=type=tmpfs,target=/root/.cargo \
    apk add --no-cache python3 tini librsync gnupg && \
    apk add --no-cache --virtual .build-deps py3-pip gcc python3-dev musl-dev gettext librsync-dev rust cargo && \
    # NOTE: These flags are important, otherwise requests is removed with pip
    pip3 install --prefix /usr/local -I /mnt/dist/*.whl && \
    echo "#!/bin/sh" >> /usr/local/bin/backup && \
    echo "exec duplyvolume backup" >> /usr/local/bin/backup && \
    chmod +x /usr/local/bin/backup && \
    echo "#!/bin/sh" >> /usr/local/bin/healthcheck && \
    echo "exec duplyvolume healthcheck" >> /usr/local/bin/healthcheck && \
    chmod +x /usr/local/bin/healthcheck && \
    echo "#!/bin/sh" >> /usr/local/bin/cancel && \
    echo "exec duplyvolume cancel" >> /usr/local/bin/cancel && \
    chmod +x /usr/local/bin/cancel && \
    echo "#!/bin/sh" >> /usr/local/bin/restore && \
    echo "exec duplyvolume restore" >> /usr/local/bin/restore && \
    chmod +x /usr/local/bin/restore && \
    apk del --no-cache .build-deps && \
    rm -rf /root/.cache
    # NOTE: Don't create /target. This way the backup will fail without a mount.

ENV PYTHONPATH="/usr/local/lib/python3.12/site-packages"

# Has to match value in control_tasks.py
ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/duplyvolume"]

HEALTHCHECK --interval=5m --timeout=10s CMD healthcheck

CMD ["control"]
