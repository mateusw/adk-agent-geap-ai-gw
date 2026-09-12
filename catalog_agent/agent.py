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

"""The catalog agent: one LlmAgent, three tools, three egress paths.

Deliberately flat. There are no sub-agents, no memory and no pipeline, because
none of that would help prove the ADK <-> Agent Gateway <-> Agent Retrieval
integration. The only structural choice that matters is holding all three
retrieval tools at once, so a single session can exercise each path in turn.
"""

from google.adk.agents.llm_agent import LlmAgent

from common.config import MODEL_ID
from common.vs_mcp_tool import build_mcp_toolset
from common.vs_rest_tool import search_catalog_rest
from common.vs_sdk_tool import search_catalog_sdk

from . import prompts

root_agent = LlmAgent(
    model=MODEL_ID,
    name="catalog_agent",
    description=(
        "Searches a product catalog held in Agent Retrieval, over either the "
        "direct client library or the remote MCP server."
    ),
    instruction=prompts.instruction(),
    tools=[
        search_catalog_sdk,  # path A: gRPC
        build_mcp_toolset(),  # path B: MCP over HTTPS
        search_catalog_rest,  # path C: plain HTTPS/REST
    ],
)
