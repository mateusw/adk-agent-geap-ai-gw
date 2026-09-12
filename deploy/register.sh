#!/usr/bin/env bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Not an official Google product. Demonstration code only: it may
# contain bugs and is not intended for production use.
#
# Register egress destinations and grant the agent identity access to them.
#
# Egress is default-deny on two axes: the destination must be in Agent Registry
# AND the identity needs roles/iap.egressor on it. Hostname matching is exact -
# no wildcards, and every regional and .mtls variant needs its own entry.
#
# Usage:
#   ./deploy/register.sh
#   ./deploy/register.sh --grant ENGINE_ID

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a

PROJECT_ID="${GCP_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT in .env}}"
LOCATION="${GATEWAY_LOCATION:-us-central1}"

ENGINE_ID=""
if [ "${1:-}" = "--grant" ]; then
  ENGINE_ID="${2:?--grant needs a reasoning engine id}"
fi

# The destination under test: the Google-hosted Agent Retrieval MCP server.
# Registered as an MCP server so the gateway applies MCP-aware policy to it.
MCP_HOST="vectorsearch.googleapis.com"

# Platform hosts the container itself needs; omitting them breaks the agent
# once IAP enforces. The vectorsearch entries serve the REST tool - they do NOT
# make the gRPC tool work under enforcement, on any protocolBinding.
ENDPOINT_HOSTS=(
  "vectorsearch.googleapis.com"
  "vectorsearch.mtls.googleapis.com"
  "aiplatform.googleapis.com"
  "aiplatform.mtls.googleapis.com"
  "${LOCATION}-aiplatform.googleapis.com"
  "${LOCATION}-aiplatform.mtls.googleapis.com"
  "aiplatform.${LOCATION}.rep.googleapis.com"
  "agentregistry.googleapis.com"
  "logging.googleapis.com"
  "logging.mtls.googleapis.com"
  "telemetry.googleapis.com"
  "telemetry.mtls.googleapis.com"
  "cloudtrace.googleapis.com"
  "cloudtrace.mtls.googleapis.com"
  "monitoring.googleapis.com"
  "monitoring.mtls.googleapis.com"
  "iamcredentials.googleapis.com"
  "iamcredentials.mtls.googleapis.com"
  "cloudresourcemanager.googleapis.com"
  "cloudresourcemanager.mtls.googleapis.com"
)

# Registry service ids must be DNS-ish; derive one from the hostname.
slug() { echo "$1" | tr '.' '-'; }

# protocolBinding accepts only grpc | http-json | jsonrpc. MCP streamable HTTP
# is JSON-RPC over HTTP, so "jsonrpc" is the correct binding for it.

register_mcp() {
  local host="$1" id
  id="mcp-$(slug "$host")"
  echo "==> MCP server ${host}"
  gcloud agent-registry services create "$id" \
    --project="$PROJECT_ID" --location="$LOCATION" \
    --display-name="Agent Retrieval MCP" \
    --mcp-server-spec-type=no-spec \
    --interfaces="url=https://${host}/mcp,protocolBinding=jsonrpc" \
    2>&1 | sed 's/^/    /' || echo "    (already registered)"
}

register_endpoint() {
  local host="$1" id
  id="ep-$(slug "$host")"
  echo "==> endpoint ${host}"
  gcloud agent-registry services create "$id" \
    --project="$PROJECT_ID" --location="$LOCATION" \
    --display-name="$host" \
    --endpoint-spec-type=no-spec \
    --interfaces="url=https://${host},protocolBinding=http-json" \
    2>&1 | sed 's/^/    /' || echo "    (already registered)"
}

register_mcp "$MCP_HOST"
for host in "${ENDPOINT_HOSTS[@]}"; do
  register_endpoint "$host"
done

echo
gcloud agent-registry services list --project="$PROJECT_ID" --location="$LOCATION" \
  --format="table(name.basename(), displayName)" || true

if [ -z "$ENGINE_ID" ]; then
  cat <<EOF

Destinations registered. Egress is still denied until the agent identity holds
roles/iap.egressor on them. Deploy the agent first, then re-run:

    ./deploy/register.sh --grant <REASONING_ENGINE_ID>

EOF
  exit 0
fi

# The principal is the agent's workload identity, not a service account.

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

# Ingress needs the AGENT registered, by its mTLS reasoning-engine URL.
echo "==> registering the agent itself for ingress"
gcloud agent-registry services create "agent-${ENGINE_ID}" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --display-name="GEAP AI Gateway Probe" \
  --endpoint-spec-type=no-spec \
  --interfaces="url=https://${LOCATION}-aiplatform.mtls.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/reasoningEngines/${ENGINE_ID},protocolBinding=jsonrpc" \
  2>&1 | tail -2 | sed 's/^/    /' || echo "    (already registered)"

ORG_ID="$(gcloud projects get-ancestors "$PROJECT_ID" --format='value(id,type)' \
          | awk '$2=="organization"{print $1}')"

if [ -z "$ORG_ID" ]; then
  echo "Could not resolve the organization id; cannot build the trust domain." >&2
  exit 1
fi

TRUST_DOMAIN="agents.global.org-${ORG_ID}.system.id.goog"
MEMBER="principal://${TRUST_DOMAIN}/resources/aiplatform/projects/${PROJECT_NUMBER}/locations/${LOCATION}/reasoningEngines/${ENGINE_ID}"

# A Service projects into an endpoint/mcpServer with a server-generated id.
# IAM binds against that, not the service id we chose.
projected_id() {
  local kind="$1" display="$2"
  gcloud agent-registry "$kind" list \
    --project="$PROJECT_ID" --location="$LOCATION" \
    --filter="displayName=\"${display}\"" \
    --format="value(name.basename())" | head -1
}

echo "==> granting roles/iap.egressor on the MCP server"
MCP_ID="$(projected_id mcp-servers "Agent Retrieval MCP")"
if [ -z "$MCP_ID" ]; then
  echo "    could not resolve the projected mcpServer id" >&2
else
  gcloud iap web add-iam-policy-binding \
    --resource-type=agent-registry \
    --mcp-server="$MCP_ID" \
    --region="$LOCATION" --project="$PROJECT_ID" \
    --member="$MEMBER" --role="roles/iap.egressor" \
    2>&1 | tail -2 | sed 's/^/    /'
fi

for host in "${ENDPOINT_HOSTS[@]}"; do
  echo "==> granting roles/iap.egressor on ${host}"
  EP_ID="$(projected_id endpoints "$host")"
  if [ -z "$EP_ID" ]; then
    echo "    could not resolve the projected endpoint id" >&2
    continue
  fi
  gcloud iap web add-iam-policy-binding \
    --resource-type=agent-registry \
    --endpoint="$EP_ID" \
    --region="$LOCATION" --project="$PROJECT_ID" \
    --member="$MEMBER" --role="roles/iap.egressor" \
    2>&1 | tail -1 | sed 's/^/    /'
done

# Separate gate from iap.egressor above: that governs REACHING the destination,
# these govern USING the API. AGENT_IDENTITY starts with no data access, so
# without them tools 403 even when the gateway allowed the call.

for role in roles/vectorsearch.viewer roles/mcp.toolUser; do
  echo "==> granting ${role} on the project"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="$MEMBER" --role="$role" --condition=None \
    --format="value(etag)" >/dev/null 2>&1 \
    && echo "    ok" || echo "    FAILED"
done

echo
echo "Done. The gateway will allow this agent to reach the registered hosts,"
echo "and the agent identity can now call Vector Search."
