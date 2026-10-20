# Multi-seat debate harness in a container.
#
# The image carries Python, git and the OpenCode CLI only. Provider credentials
# and the opencode config stay outside and are mounted at run time, so this
# image never contains an API key and never writes to your host config.
#
# Pinned: the harness was validated against OpenCode 2.0.30. Override with
#   docker compose build --build-arg OPENCODE_VERSION=2.0.32
ARG OPENCODE_VERSION=2.0.30

FROM node:22-bookworm-slim

ARG OPENCODE_VERSION
# Debian mirror. The default is upstream; point it at a local mirror when
# deb.debian.org is slow or unreachable from your network:
#   docker compose build --build-arg DEBIAN_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG DEBIAN_MIRROR=deb.debian.org

# node:22-bookworm-slim ships no Python and no git. Both are installed before
# the CLI so a failure here is reported as a missing distro package, not as a
# broken npm install.
RUN sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g; s|security.debian.org|${DEBIAN_MIRROR}|g" \
        /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git python3 \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g "@opencode/cli@${OPENCODE_VERSION}" \
 && opencode --version \
 && python3 --version \
 && rm -rf /root/.npm

# Match the usual first host uid so files written into the mounted project are
# not root-owned. The base image already ships a uid 1000 account (`node`), so
# reuse and rename it; a fresh account is only created when the uid is free.
ARG UID=1000
ARG GID=1000
RUN set -eux; \
    if getent passwd "${UID}" >/dev/null; then \
        existing="$(getent passwd "${UID}" | cut -d: -f1)"; \
        groupname="$(id -gn "${existing}")"; \
        usermod --login debate --home /home/debate --move-home "${existing}"; \
        if [ "${groupname}" != "debate" ]; then groupmod --new-name debate "${groupname}"; fi; \
    else \
        groupadd -g "${GID}" debate; \
        useradd -m -u "${UID}" -g "${GID}" -s /bin/bash debate; \
    fi; \
    mkdir -p /home/debate/.config/opencode /home/debate/.local/share/opencode /home/debate/.local/state; \
    chown -R "${UID}:${GID}" /home/debate

# Entrypoint goes in while still root: /usr/local/bin is not writable later.
# `opencode run` exits 1 when a websearch call is cancelled; the driver does not
# use the exit code as the success signal.
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/debate-entrypoint

WORKDIR /work
COPY --chown=debate:debate . /work

USER debate
ENV HOME=/home/debate \
    OPENCODE_CONFIG_DIR=/home/debate/.config/opencode \
    XDG_DATA_HOME=/home/debate/.local/share \
    XDG_STATE_HOME=/home/debate/.local/state \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Keep output unbuffered so logs stream in `docker compose logs -f`.
ENTRYPOINT ["/usr/local/bin/debate-entrypoint", "python3", "run_debate.py"]
CMD ["all"]
