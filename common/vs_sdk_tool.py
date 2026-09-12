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

"""Tool C: catalog search over the Agent Retrieval client library (gRPC).

The conventional way to query Agent Retrieval. Note that this path is DENIED by
an enforcing Agent Gateway: gRPC framing does not survive enforcement.

vectorsearch_v1beta is pre-GA, so the response is parsed defensively.
"""

from __future__ import annotations

from google.cloud import vectorsearch_v1beta
from google.protobuf.json_format import MessageToDict

from .config import VS_EMBED_FIELD, VS_QUERY_TASK_TYPE, vs_collection_parent

# Lazy gRPC channel — safe to construct at import, reused across invocations.
_search_client = vectorsearch_v1beta.DataObjectSearchServiceClient()

# Catalog fields worth handing back to the model.
_CATALOG_FIELDS = (
    "sku",
    "name",
    "category",
    "material",
    "room",
    "description",
    "price_usd",
)


def _parse_hit(item: dict) -> dict:
    """Pull the catalog fields plus a relevance score out of one raw hit.

    The API field is named ``distance`` but behaves as a similarity score:
    results arrive best-first and the leading hit carries the HIGHEST value.
    It is surfaced as ``_score`` so the model is not misled by the name.
    """
    obj = item.get("data_object", item)
    data = obj.get("data", {}) or {}
    hit = {k: data.get(k) for k in _CATALOG_FIELDS if k in data}
    if not hit:  # unexpected shape — hand back whatever data arrived
        hit = data
    hit["_score"] = item.get("distance")
    return hit


def search_catalog_sdk(query: str, top_k: int = 5) -> dict:
    """Search the product catalog using the direct Vector Search client library.

    Use this when the user asks to search "via SDK", or when no path is named.

    Args:
        query: A natural-language description of the product wanted.
        top_k: How many products to return.

    Returns:
        A dict with the matching products and their distance scores, or an
        "error" key if the search failed.
    """
    request = vectorsearch_v1beta.SearchDataObjectsRequest(
        parent=vs_collection_parent(),
        semantic_search=vectorsearch_v1beta.SemanticSearch(
            search_text=query,
            search_field=VS_EMBED_FIELD,
            task_type=VS_QUERY_TASK_TYPE,
            top_k=max(1, top_k),
            output_fields=vectorsearch_v1beta.OutputFields(
                data_fields=list(_CATALOG_FIELDS)
            ),
        ),
    )

    try:
        response = _search_client.search_data_objects(request=request)
    except Exception as exc:  # pylint: disable=broad-except
        return {"error": f"Catalog search failed: {exc}", "results": []}

    raw = MessageToDict(response._pb, preserving_proto_field_name=True)
    hits = [_parse_hit(item) for item in raw.get("results") or []]
    return {"path": "sdk", "query": query, "count": len(hits), "results": hits}
