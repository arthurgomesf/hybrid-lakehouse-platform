#!/usr/bin/env bash
set -euo pipefail

if [ -z "${AZP_URL:-}" ]; then
  echo "AZP_URL is required"
  exit 1
fi

if [ -z "${AZP_TOKEN:-}" ]; then
  echo "AZP_TOKEN is required"
  exit 1
fi

if [ -z "${AZP_POOL:-}" ]; then
  echo "AZP_POOL is required"
  exit 1
fi

AZP_AGENT_NAME="${AZP_AGENT_NAME:-$(hostname)}"

cleanup() {
  if [ -f ./config.sh ]; then
    ./config.sh remove --unattended --auth PAT --token "$AZP_TOKEN" || true
  fi
}

trap cleanup EXIT

AGENT_VERSION=$(curl -fsSL https://api.github.com/repos/microsoft/azure-pipelines-agent/releases/latest | jq -r ".tag_name" | sed "s/^v//")
curl -fsSL -o agent.tar.gz "https://download.agent.dev.azure.com/agent/${AGENT_VERSION}/vsts-agent-linux-x64-${AGENT_VERSION}.tar.gz"

tar zxf agent.tar.gz
rm agent.tar.gz

./config.sh --unattended \
  --agent "$AZP_AGENT_NAME" \
  --url "$AZP_URL" \
  --auth PAT \
  --token "$AZP_TOKEN" \
  --pool "$AZP_POOL" \
  --replace \
  --acceptTeeEula

./run.sh
