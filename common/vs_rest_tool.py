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

"""Tool B: the same catalog search over plain HTTPS/REST.

Same host, collection and query as the gRPC tool; only the transport differs.
That makes the pair a controlled test of what an enforcing gateway blocks:
this one passes, the gRPC one does not.
"""

from __future__ import annotations

import google.auth
import google.auth.transport.requests
import requests

from .config import (
    VS_EMBED_FIELD,
    VS_QUERY_TASK_TYPE,
    vs_collection_parent,
)

_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_API_ROOT = "https://vectorsearch.googleapis.com/v1beta"

_credentials, _ = google.auth.default(scopes=[_SCOPE])
_auth_request = google.auth.transport.requests.Request()

_CATALOG_FIELDS = (
    "sku",
    "name",
    "category",
    "material",
    "room",
    "description",
    "price_usd",
)


def _token() -> str:
    if not _credentials.valid:
        _credentials.refresh(_auth_request)
    return _credentials.token


def search_catalog_rest(query: str, top_k: int = 5) -> dict:
    """Search the product catalog over the REST/HTTPS API.

    Use this when the user asks to search "via REST".

    Args:
        query: A natural-language description of the product wanted.
        top_k: How many products to return.

    Returns:
        A dict with the matching products, or an "error" key on failure.
    """
    url = f"{_API_ROOT}/{vs_collection_parent()}/dataObjects:search"
    body = {
        "semanticSearch": {
            "searchText": query,
            "searchField": VS_EMBED_FIELD,
            "taskType": VS_QUERY_TASK_TYPE,
            "topK": max(1, top_k),
            "outputFields": {"dataFields": list(_CATALOG_FIELDS)},
        }
    }

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {_token()}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60,
        )
        response.raise_for_status()
    except Exception as exc:  # pylint: disable=broad-except
        return {"error": f"Catalog search failed: {exc}", "results": []}

    hits = []
    for item in response.json().get("results", []):
        data = (item.get("dataObject") or {}).get("data", {}) or {}
        hit = {k: data.get(k) for k in _CATALOG_FIELDS if k in data}
        hit["_score"] = item.get("distance")
        hits.append(hit)

    return {"path": "rest", "query": query, "count": len(hits), "results": hits}
