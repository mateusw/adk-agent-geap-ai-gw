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

"""Tool A: catalog search over the Agent Retrieval remote MCP server.

Same data as vs_sdk_tool and vs_rest_tool, over MCP. The gateway parses MCP and
logs the method and tool name, so egress policy can be per tool, not per host.

This path survives enforcement because it is HTTP/JSON; the gRPC one does not.
"""

from __future__ import annotations

import google.auth
import google.auth.transport.requests
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)

from .config import MCP_ENDPOINT, MCP_SEARCH_TOOL, VS_LOCATION

_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

# In a deployed container these resolve to the agent identity.
_credentials, _ = google.auth.default(scopes=[_SCOPE])
_auth_request = google.auth.transport.requests.Request()


def _headers(readonly_context=None) -> dict[str, str]:
    """Bearer token plus the two routing headers tools/call requires."""
    if not _credentials.valid:
        _credentials.refresh(_auth_request)
    return {
        "Authorization": f"Bearer {_credentials.token}",
        "Mcp-Name": MCP_SEARCH_TOOL,
        "Mcp-Param-Region": VS_LOCATION,
    }


def build_mcp_toolset() -> McpToolset:
    """The endpoint exposes nine tools; surface only the search one.

    The static Mcp-Name header is valid only because of this single-tool
    filter: ADK gives every tool in a toolset the same header_provider.
    """
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=MCP_ENDPOINT),
        tool_filter=[MCP_SEARCH_TOOL],
        header_provider=_headers,
    )
