#!/bin/sh
# Run as the host user so files written into the mounted project are not
# root-owned. The image is built with one non-root user (uid 1000); override
# with `docker compose run --user $(id -u):$(id -g)` when your uid differs.
set -eu

if [ -n "${HOME:-}" ]; then
    export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
    export XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
    export OPENCODE_CONFIG_DIR="${OPENCODE_CONFIG_DIR:-$HOME/.config/opencode}"
fi

# The CLI keeps a background service under XDG_STATE_HOME; a bind mount that
# covers only .local/share leaves that path missing and every command fails
# with "Background service failed to start".
mkdir -p "$OPENCODE_CONFIG_DIR" "$XDG_DATA_HOME" "$XDG_STATE_HOME" 2>/dev/null || true

if [ ! -f opencode.json ]; then
    echo "No opencode.json in /work." >&2
    echo "Run setup first:" >&2
    echo "  docker compose run --rm setup" >&2
    echo "which uses the model IDs already configured in your mounted OpenCode config." >&2
    exit 1
fi

if [ -z "$(ls -A "$OPENCODE_CONFIG_DIR" 2>/dev/null)" ]; then
    echo "Error: $OPENCODE_CONFIG_DIR is empty." >&2
    echo "Set OPENCODE_CONFIG in .env to the directory holding your opencode.json" >&2
    echo "and provider credentials (copy .env.example first), or pass provider keys" >&2
    echo "as environment variables (see README, Docker section)." >&2
    exit 1
fi

exec "$@"
