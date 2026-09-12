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

"""Deploy the catalog agent to Agent Runtime, bound to both gateways.

Deployment is what puts the agent behind a gateway; a local run is never
routed through one.

identity_type and the gateway bindings must be set AT CREATION - patching them
later has no effect. Redeploys match on display name and update in place, so
the engine id and its IAM bindings survive.

Usage:
    python deploy/deployer.py [--no-gateway | --list | --delete]
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
load_dotenv(os.path.join(_ROOT, ".env"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import agentplatform  # noqa: E402
from agentplatform._genai.types.common import IdentityType  # noqa: E402
from agentplatform.frameworks.adk import AdkApp  # noqa: E402

from catalog_agent import create_app  # noqa: E402
from common.config import (  # noqa: E402
    AGENT_DISPLAY_NAME,
    AGENT_ENGINE_LOCATION,
    EGRESS_GATEWAY,
    GENAI_LOCATION,
    INGRESS_GATEWAY,
    MODEL_ID,
    PROJECT_ID,
    STAGING_BUCKET,
    VS_COLLECTION_ID,
    VS_LOCATION,
    gateway_path,
)

_REQUIREMENTS_FILE = os.path.join(_ROOT, "requirements.txt")


def _requirements() -> list[str]:
    """requirements.txt as a clean list.

    The SDK treats each element as a dependency specifier, so comments and
    blank lines have to go — passing the raw file makes it try to parse '#'
    lines as constraints.
    """
    with open(_REQUIREMENTS_FILE) as f:
        lines = [line.split("#", 1)[0].strip() for line in f]
    return [line for line in lines if line]


def _client() -> agentplatform.Client:
    return agentplatform.Client(
        project=PROJECT_ID, location=AGENT_ENGINE_LOCATION
    )


def _find(client: agentplatform.Client):
    """Locate an existing instance by display name, or None.

    The display name lives on `.api_resource`, not on the Runtime wrapper.
    """
    for runtime in client.runtimes.list():
        if getattr(runtime.api_resource, "display_name", None) == AGENT_DISPLAY_NAME:
            return runtime
    return None


def _config(with_gateway: bool) -> dict:
    if not STAGING_BUCKET:
        sys.exit(
            "ERROR: STAGING_BUCKET is not set. Point it at an existing GCS\n"
            "bucket in this project (no gs:// prefix) — see .env.example."
        )

    cfg: dict = {
        "staging_bucket": f"gs://{STAGING_BUCKET}",
        "display_name": AGENT_DISPLAY_NAME,
        "description": (
            "ADK agent probing Agent Gateway ingress/egress inspection over "
            "Agent Retrieval."
        ),
        "requirements": _requirements(),
        # Relative to the project root (main() chdirs there); absolute paths
        # package with their full prefix and fail to import in the container.
        "extra_packages": ["common", "catalog_agent"],
        "env_vars": {
            # Container gets the project NUMBER; forward the ID.
            "GCP_PROJECT_ID": PROJECT_ID,
            "GOOGLE_CLOUD_LOCATION": GENAI_LOCATION,
            "VS_LOCATION": VS_LOCATION,
            "VS_COLLECTION_ID": VS_COLLECTION_ID,
            "MODEL_ID": MODEL_ID,
            # gRPC ignores the system trust store, so point it at the CA the
            # gateway's TLS interception uses. Tested: does NOT unblock gRPC
            # egress - the block is the transport, not the certificate.
            "GRPC_DEFAULT_SSL_ROOTS_FILE_PATH": (
                "/etc/ssl/certs/ca-certificates.crt"
            ),
        },
    }

    if with_gateway:
        cfg["agent_gateway_config"] = {
            "agent_to_anywhere_config": {
                "agent_gateway": gateway_path(EGRESS_GATEWAY)
            },
            "client_to_agent_config": {
                "agent_gateway": gateway_path(INGRESS_GATEWAY)
            },
        }
        # Must be set at creation to be meaningful.
        cfg["identity_type"] = IdentityType.AGENT_IDENTITY

    return cfg


def deploy(with_gateway: bool) -> None:
    client = _client()
    existing = _find(client)
    config = _config(with_gateway)

    # Agent Runtime needs an object exposing query/stream_query, not a bare App.
    deployable = AdkApp(app=create_app())

    if existing:
        print(
            f"Updating '{AGENT_DISPLAY_NAME}' in place "
            f"({existing.api_resource.name})..."
        )
        result = client.runtimes.update(
            name=existing.api_resource.name, agent=deployable, config=config
        )
    else:
        print(f"Creating '{AGENT_DISPLAY_NAME}'...")
        result = client.runtimes.create(agent=deployable, config=config)

    name = result.api_resource.name
    print(f"\nDeployed: {name}")
    print(f"Engine id: {name.rsplit('/', 1)[-1]}")
    if with_gateway:
        print("\nBound to:")
        print(f"  egress  {gateway_path(EGRESS_GATEWAY)}")
        print(f"  ingress {gateway_path(INGRESS_GATEWAY)}")
        print(
            "\nEgress is still denied until the agent identity is granted"
            "\nroles/iap.egressor. Run:"
            f"\n    ./deploy/register.sh --grant {name.rsplit('/', 1)[-1]}"
        )
    else:
        print("\nDeployed WITHOUT gateway bindings (ungoverned baseline).")


def list_engines() -> None:
    for runtime in _client().runtimes.list():
        resource = runtime.api_resource
        name = getattr(resource, "display_name", None) or "?"
        print(f"{name:45} {resource.name}")
        spec = getattr(resource, "spec", None)
        deployment = getattr(spec, "deployment_spec", None)
        binding = getattr(deployment, "agent_gateway_config", None)
        if binding is not None:
            print(f"{'':45} gateway: {binding}")


def delete() -> None:
    client = _client()
    existing = _find(client)
    if not existing:
        print(f"No instance named '{AGENT_DISPLAY_NAME}'.")
        return
    name = existing.api_resource.name
    confirm = input(f"Delete {name}? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return
    client.runtimes.delete(name=name, force=True)
    print("Deleted.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list instances")
    parser.add_argument("--delete", action="store_true", help="delete this one")
    parser.add_argument(
        "--no-gateway",
        action="store_true",
        help="deploy without gateway bindings, as an ungoverned baseline",
    )
    args = parser.parse_args()

    if not PROJECT_ID:
        sys.exit("ERROR: GOOGLE_CLOUD_PROJECT is not set (check .env).")

    # extra_packages are resolved relative to the working directory.
    os.chdir(_ROOT)

    if args.list:
        list_engines()
    elif args.delete:
        delete()
    else:
        deploy(with_gateway=not args.no_gateway)


if __name__ == "__main__":
    main()
