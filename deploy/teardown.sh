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
# Remove everything this demo created, in dependency order.
#
# Only touches resources whose names come from .env, so it will not disturb a
# pre-existing gateway that this demo did not create. Prints the plan and asks
# before doing anything.
#
# Usage:  ./deploy/teardown.sh [--yes]

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a

PROJECT_ID="${GCP_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT in .env}}"
LOCATION="${GATEWAY_LOCATION:-us-central1}"
VS_LOCATION="${VS_LOCATION:-us-central1}"
EGRESS_GATEWAY="${EGRESS_GATEWAY:-geap-aigw-demo-egress}"
INGRESS_GATEWAY="${INGRESS_GATEWAY:-geap-aigw-demo-ingress}"
VS_COLLECTION_ID="${VS_COLLECTION_ID:-geap-aigw-catalog}"

cat <<EOF
This will delete, in project ${PROJECT_ID}:

  - the deployed Agent Runtime instance (via deploy/deployer.py --delete)
  - authz policies + extensions for ${EGRESS_GATEWAY} and ${INGRESS_GATEWAY}
  - agent gateways ${EGRESS_GATEWAY} and ${INGRESS_GATEWAY}
  - Agent Registry services created by deploy/register.sh (ep-* and mcp-*)
  - Agent Retrieval collection ${VS_COLLECTION_ID}

It will NOT touch any other gateway, collection or registry entry.
EOF

if [ "${1:-}" != "--yes" ]; then
  read -r -p $'\nProceed? [y/N] ' reply
  [ "$reply" = "y" ] || { echo "Aborted."; exit 0; }
fi

echo
echo "==> Agent Runtime instance"
python3 "$HERE/deployer.py" --delete <<<"y" || echo "    (skipped)"

# Policies reference extensions, extensions reference gateways: delete inward.
for name in "$EGRESS_GATEWAY" "$INGRESS_GATEWAY"; do
  echo "==> authz policy ${name}-iap-authzpolicy"
  gcloud beta network-security authz-policies delete "${name}-iap-authzpolicy" \
    --location="$LOCATION" --project="$PROJECT_ID" --quiet 2>&1 | tail -1

  echo "==> authz extension ${name}-iap-authzextension"
  gcloud beta service-extensions authz-extensions delete "${name}-iap-authzextension" \
    --location="$LOCATION" --project="$PROJECT_ID" --quiet 2>&1 | tail -1

  echo "==> agent gateway ${name}"
  gcloud network-services agent-gateways delete "$name" \
    --location="$LOCATION" --project="$PROJECT_ID" --quiet 2>&1 | tail -1
done

echo "==> Agent Registry services"
for svc in $(gcloud agent-registry services list \
      --project="$PROJECT_ID" --location="$LOCATION" \
      --format="value(name.basename())" 2>/dev/null \
      | grep -E '^(ep-|mcp-)'); do
  echo "    ${svc}"
  gcloud agent-registry services delete "$svc" \
    --project="$PROJECT_ID" --location="$LOCATION" --quiet 2>&1 | tail -1
done

echo "==> Agent Retrieval collection ${VS_COLLECTION_ID}"
gcloud beta vector-search collections delete "$VS_COLLECTION_ID" \
  --location="$VS_LOCATION" --project="$PROJECT_ID" --quiet 2>&1 | tail -1

echo
echo "Teardown complete."
