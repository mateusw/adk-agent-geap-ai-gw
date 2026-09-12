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

"""Query the deployed agent, the only way to generate gateway traffic.

Calls REST :streamQuery directly: ingress governs query and streamQuery and
nothing else, and the runtimes client wrapper exposes no query method.

Usage:
    python scripts/query_deployed.py [--all] "a rug for a patio"
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import google.auth
import google.auth.transport.requests
import requests
from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
load_dotenv(os.path.join(_ROOT, ".env"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import agentplatform  # noqa: E402

from common.config import (  # noqa: E402
    AGENT_DISPLAY_NAME,
    AGENT_ENGINE_LOCATION,
    PROJECT_ID,
)

_USER_ID = "gateway-probe"
_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

# The phrasings prompts.py keys off to pin the transport. gRPC last, so an
# enforcing gateway denies the run's final call and leaves it on screen.
_PATHS = ("MCP", "REST", "SDK")


def _engine_name() -> str:
    """Full resource name of the deployed instance, found by display name."""
    client = agentplatform.Client(
        project=PROJECT_ID, location=AGENT_ENGINE_LOCATION
    )
    # display_name lives on .api_resource, not on the Runtime wrapper.
    for runtime in client.runtimes.list():
        resource = runtime.api_resource
        if getattr(resource, "display_name", None) == AGENT_DISPLAY_NAME:
            return resource.name
    sys.exit(f"No deployed instance named '{AGENT_DISPLAY_NAME}'.")


def _token() -> str:
    credentials, _ = google.auth.default(scopes=[_SCOPE])
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token


def ask(engine: str, token: str, text: str) -> None:
    print(f"\n>>> {text}")
    url = (
        f"https://{AGENT_ENGINE_LOCATION}-aiplatform.googleapis.com/v1/"
        f"{engine}:streamQuery?alt=sse"
    )
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "class_method": "stream_query",
            "input": {"message": text, "user_id": _USER_ID},
        },
        stream=True,
        timeout=300,
    )
    response.raise_for_status()

    for line in response.iter_lines():
        if not line:
            continue
        try:
            event = json.loads(line.decode("utf-8").removeprefix("data: "))
        except json.JSONDecodeError:
            continue
        for part in event.get("content", {}).get("parts", []):
            if "function_call" in part:
                print(f"  [tool call] {part['function_call'].get('name')}")
            if "function_response" in part:
                payload = part["function_response"].get("response", {})
                if isinstance(payload, dict) and "error" in payload:
                    print(f"  [tool error] {str(payload['error'])[:200]}")
            if part.get("text"):
                print(part["text"], end="")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="*", default=["a rug for a patio"])
    parser.add_argument(
        "--all", action="store_true", help="run the query down all three paths"
    )
    args = parser.parse_args()

    if not PROJECT_ID:
        sys.exit("ERROR: GOOGLE_CLOUD_PROJECT is not set (check .env).")

    engine = _engine_name()
    token = _token()
    query = " ".join(args.query) or "a rug for a patio"

    if args.all:
        for path in _PATHS:
            ask(engine, token, f"{query} via {path}")
    else:
        ask(engine, token, query)

    print("\nNow run: python scripts/gateway_logs.py")


if __name__ == "__main__":
    main()
