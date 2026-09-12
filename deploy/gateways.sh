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
# Create the egress + ingress gateway pair, each with an IAP authz extension
# and policy. Defaults to DRY_RUN: an enforcing gateway with an incomplete
# allowlist fails every invocation with a 498.
#
# Usage:  ./deploy/gateways.sh [--dry-run] [--enforce] [--v2]

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a

PROJECT_ID="${GCP_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT in .env}}"
LOCATION="${GATEWAY_LOCATION:-us-central1}"
EGRESS_GATEWAY="${EGRESS_GATEWAY:-geap-aigw-demo-egress}"
INGRESS_GATEWAY="${INGRESS_GATEWAY:-geap-aigw-demo-ingress}"

ENFORCE_MODE="DRY_RUN"
FAIL_OPEN="true"
PLAN_ONLY=0

# V1 reads the roles/iap.egressor bindings register.sh grants. V2 does not:
# under V2 + enforcement every egress was denied despite correct bindings.
IAP_POLICY_VERSION="${IAP_POLICY_VERSION:-V1}"

for arg in "$@"; do
  case "$arg" in
    --enforce) ENFORCE_MODE=""; FAIL_OPEN="false" ;;
    --dry-run) PLAN_ONLY=1 ;;
    --v2) IAP_POLICY_VERSION="V2" ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

# Generated YAML carries the project id; git-ignored.
GEN="$HERE/_generated"
mkdir -p "$GEN"

REGISTRY="//agentregistry.googleapis.com/projects/${PROJECT_ID}/locations/${LOCATION}"

echo "project=${PROJECT_ID} location=${LOCATION}" \
     "iap_mode=${ENFORCE_MODE:-ENFORCED} failOpen=${FAIL_OPEN}" \
     "policyVersion=${IAP_POLICY_VERSION}"

run() {
  if [ "$PLAN_ONLY" = "1" ]; then
    echo "  [dry-run] $*"
  else
    "$@"
  fi
}

# MCP is the only accepted value of `protocols` (the API rejects GRPC), and it
# is what makes the gateway log the method and tool name. HTTPS still passes,
# attributed by hostname only; gRPC does not pass at all under enforcement.

cat >"$GEN/gateway-egress.yaml" <<EOF
name: ${EGRESS_GATEWAY}
protocols:
  - MCP
googleManaged:
  governedAccessPath: AGENT_TO_ANYWHERE
registries:
  - ${REGISTRY}
EOF

cat >"$GEN/gateway-ingress.yaml" <<EOF
name: ${INGRESS_GATEWAY}
protocols:
  - MCP
googleManaged:
  governedAccessPath: CLIENT_TO_AGENT
EOF

for pair in "${EGRESS_GATEWAY}:gateway-egress.yaml" "${INGRESS_GATEWAY}:gateway-ingress.yaml"; do
  name="${pair%%:*}"; file="${pair##*:}"
  echo "==> agent gateway ${name}"
  run gcloud network-services agent-gateways import "$name" \
    --source="$GEN/$file" --location="$LOCATION" --project="$PROJECT_ID"
done

# failOpen keeps a gateway-side failure from taking the agent down while the
# allowlist is still being built out.

for name in "$EGRESS_GATEWAY" "$INGRESS_GATEWAY"; do
  ext="${name}-iap-authzextension"
  pol="${name}-iap-authzpolicy"

  {
    echo "name: ${ext}"
    echo "service: iap.googleapis.com"
    echo "failOpen: ${FAIL_OPEN}"
    echo "timeout: 10s"
    echo "metadata:"
    echo "  iapPolicyVersion: \"${IAP_POLICY_VERSION}\""
    [ -n "$ENFORCE_MODE" ] && echo "  iamEnforcementMode: \"${ENFORCE_MODE}\""
  } >"$GEN/${ext}.yaml"

  cat >"$GEN/${pol}.yaml" <<EOF
name: ${pol}
target:
  resources:
    - "projects/${PROJECT_ID}/locations/${LOCATION}/agentGateways/${name}"
policyProfile: REQUEST_AUTHZ
action: CUSTOM
customProvider:
  authzExtension:
    resources:
      - "projects/${PROJECT_ID}/locations/${LOCATION}/authzExtensions/${ext}"
EOF

  echo "==> authz extension ${ext}"
  run gcloud beta service-extensions authz-extensions import "$ext" \
    --source="$GEN/${ext}.yaml" --location="$LOCATION" --project="$PROJECT_ID"

  echo "==> authz policy ${pol}"
  run gcloud beta network-security authz-policies import "$pol" \
    --source="$GEN/${pol}.yaml" --location="$LOCATION" --project="$PROJECT_ID"
done

echo
echo "Gateways ready. Next: ./deploy/register.sh, then deploy/deployer.py."
[ -n "$ENFORCE_MODE" ] && echo "IAP is in ${ENFORCE_MODE}: decisions are logged, nothing is blocked."
