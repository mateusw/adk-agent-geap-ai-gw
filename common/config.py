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

"""Configuration. Every value honours an env-var override; set them in .env."""

import os

MODEL_ID = os.environ.get("MODEL_ID", "gemini-3.8-flash")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIMENSIONS = 768

# A deployed container gets GOOGLE_CLOUD_PROJECT as the project NUMBER, which
# resource paths reject; the deployer forwards the ID as GCP_PROJECT_ID.
PROJECT_ID = os.environ.get("GCP_PROJECT_ID") or os.environ.get(
    "GOOGLE_CLOUD_PROJECT", ""
)

# The Gemini SDK accepts "global"; the gateways need a concrete region, and it
# must match the agent's.
GENAI_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
AGENT_ENGINE_LOCATION = os.environ.get("AGENT_ENGINE_LOCATION", "us-central1")
VS_LOCATION = os.environ.get("VS_LOCATION", "us-central1")

VS_COLLECTION_ID = os.environ.get("VS_COLLECTION_ID", "geap-aigw-catalog")
VS_EMBED_FIELD = "content_embedding"
VS_QUERY_TASK_TYPE = "QUESTION_ANSWERING"


def vs_collection_parent() -> str:
    return (
        f"projects/{PROJECT_ID}/locations/{VS_LOCATION}"
        f"/collections/{VS_COLLECTION_ID}"
    )


def vs_location_parent() -> str:
    return f"projects/{PROJECT_ID}/locations/{VS_LOCATION}"


MCP_ENDPOINT = "https://vectorsearch.googleapis.com/mcp"
MCP_PROTOCOL_VERSION = "2026-07-28"
MCP_SEARCH_TOOL = "search_data_objects"

# One gateway serves one direction, hence two.
EGRESS_GATEWAY = os.environ.get("EGRESS_GATEWAY", "geap-aigw-demo-egress")
INGRESS_GATEWAY = os.environ.get("INGRESS_GATEWAY", "geap-aigw-demo-ingress")
GATEWAY_LOCATION = os.environ.get("GATEWAY_LOCATION", "us-central1")


def gateway_path(name: str) -> str:
    return (
        f"projects/{PROJECT_ID}/locations/{GATEWAY_LOCATION}"
        f"/agentGateways/{name}"
    )


def agent_registry_uri() -> str:
    return (
        "//agentregistry.googleapis.com"
        f"/projects/{PROJECT_ID}/locations/{GATEWAY_LOCATION}"
    )


# Matched by display name so redeploys update in place, keeping the engine id
# and the IAM bindings against it valid.
AGENT_DISPLAY_NAME = os.environ.get(
    "AGENT_DISPLAY_NAME", "GEAP AI Gateway Probe (Demo)"
)
APP_NAME = "geap_aigw_probe"
STAGING_BUCKET = os.environ.get("STAGING_BUCKET", "")
