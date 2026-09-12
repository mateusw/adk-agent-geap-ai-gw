#!/usr/bin/env python3
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

"""Print what the gateways inspected.

MCP requests carry the parsed method and tool name; REST and gRPC show a
hostname only.

Usage:
    python scripts/gateway_logs.py [--minutes N] [--gateway NAME]
                                   [--mcp-only] [--raw]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
load_dotenv(os.path.join(_ROOT, ".env"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from google.cloud import logging as cloud_logging  # noqa: E402

from common.config import (  # noqa: E402
    EGRESS_GATEWAY,
    GATEWAY_LOCATION,
    INGRESS_GATEWAY,
    PROJECT_ID,
)

def _summarize(payload: dict) -> str:
    """One line per request.

    The emitted schema is not the published one: entries are
    LoadBalancerLogEntry, there is no serviceExtensionsInfo, and authorization
    appears as authzPolicyInfo.
    """
    info = payload.get("agentGatewayInfo", {}) or {}
    policy = payload.get("enforcedGatewaySecurityPolicy", {}) or {}

    host = payload.get("tlsSniHostname") or policy.get("hostname") or "?"

    mcp = info.get("mcpInfo") or {}
    if mcp:
        method = mcp.get("method", "?")
        # The tool name lives in "parameter", not "name" or "toolName".
        tool = mcp.get("parameter") or ""
        what = f"MCP {method} {tool}".rstrip()
    else:
        what = "non-MCP (host only)"

    # Whether the request was allowed, and by which layer.
    verdict = (payload.get("authzPolicyInfo", {}) or {}).get("result")
    if not verdict:
        rules = policy.get("matchedRules") or [{}]
        verdict = rules[0].get("action") or rules[0].get("name") or "?"

    registry = info.get("agentRegistryResource", "")
    kind = ""
    if registry:
        parts = registry.split("/")
        kind = f" via {parts[-2][:-1]}" if len(parts) > 1 else ""

    return f"{verdict:8} {host:45} {what}{kind}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=int, default=30)
    parser.add_argument(
        "--gateway",
        action="append",
        help="gateway name; repeatable. Defaults to both.",
    )
    parser.add_argument("--raw", action="store_true", help="dump jsonPayload")
    parser.add_argument(
        "--mcp-only",
        action="store_true",
        help="only requests the gateway parsed as MCP",
    )
    args = parser.parse_args()

    if not PROJECT_ID:
        sys.exit("ERROR: GOOGLE_CLOUD_PROJECT is not set (check .env).")

    gateways = args.gateway or [EGRESS_GATEWAY, INGRESS_GATEWAY]
    since = (
        datetime.now(timezone.utc) - timedelta(minutes=args.minutes)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    client = cloud_logging.Client(project=PROJECT_ID)

    for gateway in gateways:
        # Monitored resource type for Agent Gateway.
        log_filter = (
            'resource.type="networkservices.googleapis.com/Gateway"\n'
            f'resource.labels.location="{GATEWAY_LOCATION}"\n'
            f'resource.labels.gateway_name="{gateway}"\n'
            f'timestamp>="{since}"'
        )
        print(f"\n=== {gateway} (last {args.minutes}m) ===")

        found = 0
        for entry in client.list_entries(
            filter_=log_filter, order_by=cloud_logging.DESCENDING, max_results=50
        ):
            payload = entry.payload if isinstance(entry.payload, dict) else {}
            if args.mcp_only and not (
                payload.get("agentGatewayInfo", {}) or {}
            ).get("mcpInfo"):
                continue
            found += 1
            stamp = entry.timestamp.strftime("%H:%M:%S") if entry.timestamp else "?"
            if args.raw:
                print(f"\n[{stamp}]")
                print(json.dumps(payload, indent=1)[:2000])
            else:
                print(f"[{stamp}] {_summarize(payload)}")

        if not found:
            print(
                "  no entries. Traffic only reaches a gateway from a DEPLOYED\n"
                "  agent — a local run is not routed through it."
            )


if __name__ == "__main__":
    main()
