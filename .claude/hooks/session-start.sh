#!/bin/bash
set -euo pipefail

# Only run in remote Claude Code environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Wire up GitHub credentials so git push works if GITHUB_TOKEN is set
if [ -n "${GITHUB_TOKEN:-}" ]; then
  git config --global url."https://${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
fi

# Install API Python dependencies
cd "${CLAUDE_PROJECT_DIR}/apps/api"
pip install -q -e ".[youtube,postgres,dev]"

# Install web Node dependencies
cd "${CLAUDE_PROJECT_DIR}/apps/web"
npm install --prefer-offline --no-audit --no-fund 2>&1 | tail -3
