#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -f opencode.json ]]; then
  echo 'Configure this folder first: python3 debate_tools.py setup' >&2
  exit 1
fi
python3 debate_tools.py doctor
python3 run_debate.py all
